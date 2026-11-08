from __future__ import annotations

import json
import requests
import msal
import urllib3

from .config import Settings

# DEV ONLY
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BusinessCentralClient:
    """Business Central API client."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json"
            }
        )

    def _tenant_environment_root(self) -> str:
        return (
            f"{self.settings.base_url}/"
            f"{self.settings.tenant_id}/"
            f"{self.settings.environment_name}"
        )

    def get_token(self) -> str:

        authority = (
            f"https://login.microsoftonline.com/"
            f"{self.settings.tenant_id}"
        )

        app = msal.ConfidentialClientApplication(
            client_id=self.settings.client_id,
            client_credential=self.settings.client_secret,
            authority=authority,
        )

        result = app.acquire_token_for_client(
            scopes=[self.settings.scope]
        )

        if "access_token" not in result:
            raise RuntimeError(
                f"Token request failed: "
                f"{result.get('error_description') or result}"
            )

        return result["access_token"]

    def authorize(self) -> None:

        token = self.get_token()

        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}"
            }
        )

    def get_companies(self) -> list[dict]:
        url = (
            f"{self._tenant_environment_root()}"
            f"/api/v2.0/companies"
        )

        response = self.session.get(
            url,
            timeout=60,
            verify=False
        )

        response.raise_for_status()

        return response.json().get("value", [])

    def company_id_by_name(self, company_name: str) -> str:

        companies = self.get_companies()

        for company in companies:

            if company.get("name") == company_name:
                return company["id"]

        available = ", ".join(
            c.get("name", "")
            for c in companies
        )

        raise ValueError(
            f"Company not found: {company_name}. "
            f"Available companies: {available}"
        )

    def test_api_root(
        self,
        publisher: str = "contoso",
        group: str = "financeautomation",
        version: str = "v1.0"
    ) -> None:

        url = (
            f"{self._tenant_environment_root()}"
            f"/api/{publisher}/{group}/{version}"
        )

        response = self.session.get(
            url,
            timeout=60,
            verify=False
        )

        print("=" * 80)
        print("API ROOT TEST")
        print("URL:", url)
        print("STATUS:", response.status_code)
        print(response.text)
        print("=" * 80)

    def get_custom_gl_setup(
        self,
        company_id: str,
        publisher: str = "contoso",
        group: str = "financeautomation",
        version: str = "v1.0",
    ) -> dict:

        url = (
            f"{self._tenant_environment_root()}"
            f"/api/{publisher}/{group}/{version}"
            f"/companies({company_id})/glSetups"
        )

        print("=" * 80)
        print("GET URL")
        print(url)

        response = self.session.get(
            url,
            timeout=60,
            verify=False
        )

        print("STATUS:", response.status_code)
        print("RESPONSE:")
        print(response.text)
        print("=" * 80)

        if response.status_code == 404:
            raise RuntimeError(
                f"""
Custom GL Setup API endpoint not found.

URL:
{url}

Verify:

1. Extension installed successfully
2. APIPublisher = contoso
3. APIGroup = financeautomation
4. APIVersion = v1.0
5. EntitySetName = glSetups
6. Sandbox = Sandbox_Test

Also test:

https://api.businesscentral.dynamics.com/v2.0/{self.settings.tenant_id}/{self.settings.environment_name}/api/{publisher}/{group}/{version}
"""
            )

        response.raise_for_status()

        data = response.json()

        with open(
            "gl_setup_response.json",
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4
            )

        return data

    def patch_allow_posting_from(
        self,
        company_id: str,
        allow_posting_from: str,
        publisher: str = "contoso",
        group: str = "financeautomation",
        version: str = "v1.0",
        use_etag: bool = True,
    ):

        setup = self.get_custom_gl_setup(
            company_id=company_id,
            publisher=publisher,
            group=group,
            version=version,
        )

        if "value" not in setup:
            raise RuntimeError(
                f"Unexpected API response:\n{json.dumps(setup, indent=2)}"
            )

        if len(setup["value"]) == 0:
            raise RuntimeError(
                "No GL Setup records returned."
            )

        record = setup["value"][0]

        record_id = record.get("id")

        if not record_id:
            raise RuntimeError(
                f"Record does not contain id field:\n{record}"
            )

        etag = (
            record.get("@odata.etag")
            if use_etag
            else None
        )

        url = (
            f"{self._tenant_environment_root()}"
            f"/api/{publisher}/{group}/{version}"
            f"/companies({company_id})/glSetups({record_id})"
        )

        headers = {
            "Content-Type": "application/json"
        }

        if use_etag and etag:
            headers["If-Match"] = etag

        payload = {
            "allowPostingFrom": allow_posting_from
        }

        print("=" * 80)
        print("PATCH URL")
        print(url)

        print("PATCH PAYLOAD")
        print(payload)

        response = self.session.patch(
            url,
            json=payload,
            headers=headers,
            timeout=60,
            verify=False
        )

        print("PATCH STATUS:", response.status_code)
        print(response.text)
        print("=" * 80)

        response.raise_for_status()

        return {
            "status": "updated",
            "company": company_id,
            "allowPostingFrom": allow_posting_from
        }