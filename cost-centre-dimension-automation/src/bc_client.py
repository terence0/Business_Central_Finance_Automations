from __future__ import annotations

import json
from typing import Any

import msal
import requests
import urllib3

from .config import Settings

# DEV ONLY: avoids SSL validation issues on corporate-managed devices.
# Remove verify=False once IT certificate validation is fixed.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BusinessCentralClient:
    """Business Central API client for cost centre dimension automation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _root(self) -> str:
        return (
            f"{self.settings.base_url}/"
            f"{self.settings.tenant_id}/"
            f"{self.settings.environment_name}"
        )

    def _custom_api_root(self) -> str:
        return (
            f"{self._root()}/api/"
            f"{self.settings.api_publisher}/"
            f"{self.settings.api_group}/"
            f"{self.settings.api_version}"
        )

    def get_token(self) -> str:
        authority = f"https://login.microsoftonline.com/{self.settings.tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=self.settings.client_id,
            client_credential=self.settings.client_secret,
            authority=authority,
        )
        result = app.acquire_token_for_client(scopes=[self.settings.scope])
        if "access_token" not in result:
            raise RuntimeError(f"Token request failed: {result.get('error_description') or result}")
        return result["access_token"]

    def authorize(self) -> None:
        token = self.get_token()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        response = self.session.request(method, url, timeout=60, verify=False, **kwargs)
        print("=" * 80)
        print(method.upper(), url)
        print("STATUS:", response.status_code)
        print(response.text[:3000])
        print("=" * 80)
        response.raise_for_status()
        return response

    def get_companies(self) -> list[dict[str, Any]]:
        url = f"{self._root()}/api/v2.0/companies"
        response = self._request("GET", url)
        return response.json().get("value", [])

    def company_id_by_name(self, company_name: str) -> str:
        for company in self.get_companies():
            if company.get("name") == company_name:
                return company["id"]
        available = ", ".join(c.get("name", "") for c in self.get_companies())
        raise ValueError(f"Company not found: {company_name}. Available companies: {available}")

    def get_dimension_values(self, company_id: str, dimension_code: str) -> list[dict[str, Any]]:
        # Filter syntax is intentionally simple. If your environment rejects this,
        # remove the filter and filter in Python.
        url = (
            f"{self._custom_api_root()}/companies({company_id})/costCentreDimensionValues"
            f"?$filter=dimensionCode eq '{dimension_code}'"
        )
        response = self._request("GET", url)
        return response.json().get("value", [])

    def dimension_value_exists(self, company_id: str, dimension_code: str, code: str) -> bool:
        values = self.get_dimension_values(company_id, dimension_code)
        return any(
            str(v.get("code", "")).upper() == code.upper()
            and str(v.get("dimensionCode", "")).upper() == dimension_code.upper()
            for v in values
        )

    def create_dimension_value(
        self,
        company_id: str,
        dimension_code: str,
        code: str,
        name: str,
    ) -> dict[str, Any]:
        url = f"{self._custom_api_root()}/companies({company_id})/costCentreDimensionValues"
        payload = {
            "dimensionCode": dimension_code,
            "code": code,
            "name": name,
        }
        response = self._request(
            "POST",
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        return response.json() if response.text else {"status": "created"}

    def get_gl_accounts(self, company_id: str) -> list[dict[str, Any]]:
        url = f"{self._custom_api_root()}/companies({company_id})/costCentreGLAccounts"
        response = self._request("GET", url)
        return response.json().get("value", [])

    def create_default_dimension_for_gl_account(
        self,
        company_id: str,
        gl_account_no: str,
        dimension_code: str,
        dimension_value_code: str,
        value_posting: str,
    ) -> dict[str, Any]:
        url = f"{self._custom_api_root()}/companies({company_id})/costCentreDefaultDimensions"
        payload = {
            "tableId": 15,
            "no": gl_account_no,
            "dimensionCode": dimension_code,
            "dimensionValueCode": dimension_value_code,
            "valuePosting": value_posting,
        }
        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
            verify=False,
        )
        print("=" * 80)
        print("POST", url)
        print("PAYLOAD:", payload)
        print("STATUS:", response.status_code)
        print(response.text[:2000])
        print("=" * 80)

        # 409 conflict normally means the default dimension already exists.
        if response.status_code == 409:
            return {"status": "already_exists", "glAccountNo": gl_account_no}

        response.raise_for_status()
        return response.json() if response.text else {"status": "created", "glAccountNo": gl_account_no}

    def create_cost_centre_across_company(
        self,
        company_id: str,
        dimension_code: str,
        cost_centre_code: str,
        cost_centre_name: str,
        apply_to_gl_accounts: bool,
        default_dimension_mode: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "dimensionValueAction": "pending",
            "glAccountRulesCreated": 0,
            "glAccountRulesSkipped": 0,
            "messages": [],
        }

        exists = self.dimension_value_exists(company_id, dimension_code, cost_centre_code)
        if exists:
            result["dimensionValueAction"] = "already_exists"
        else:
            result["dimensionValueAction"] = "would_create" if dry_run else "created"
            if not dry_run:
                self.create_dimension_value(
                    company_id=company_id,
                    dimension_code=dimension_code,
                    code=cost_centre_code,
                    name=cost_centre_name,
                )

        if apply_to_gl_accounts:
            gl_accounts = self.get_gl_accounts(company_id)
            result["messages"].append(f"G/L accounts found: {len(gl_accounts)}")

            # Safer default: Code Mandatory means COST CENTRE is required but does not force this new value.
            if default_dimension_mode == "Code Mandatory - do not force value":
                value_posting = "Code Mandatory"
                dimension_value_for_default = ""
            else:
                value_posting = "Same Code"
                dimension_value_for_default = cost_centre_code

            for account in gl_accounts:
                account_no = account.get("no") or account.get("number") or account.get("id")
                if not account_no:
                    result["glAccountRulesSkipped"] += 1
                    continue

                if dry_run:
                    result["glAccountRulesCreated"] += 1
                    continue

                try:
                    outcome = self.create_default_dimension_for_gl_account(
                        company_id=company_id,
                        gl_account_no=str(account_no),
                        dimension_code=dimension_code,
                        dimension_value_code=dimension_value_for_default,
                        value_posting=value_posting,
                    )
                    if outcome.get("status") == "already_exists":
                        result["glAccountRulesSkipped"] += 1
                    else:
                        result["glAccountRulesCreated"] += 1
                except Exception as exc:
                    result["glAccountRulesSkipped"] += 1
                    result["messages"].append(f"G/L Account {account_no}: {exc}")

        return result
