from __future__ import annotations

from typing import Any

import msal
import requests
import urllib3

from .config import Settings

SETUPS = "fiscalYearCloseSetups"
LOG_ENTRIES = "fiscalYearCloseLogEntries"
USER_POSTING_DATES = "userPostingDates"

# Bound actions on the setup API page (page 68310 in the AL extension).
ACTIONS = {
    "create_journal": "createClosingJournal",
    "post_journal": "postClosingJournal",
    "run_now": "runNow",
    "create_job": "createJobQueueEntry",
}


class BCError(RuntimeError):
    """A Business Central API error with the message BC returned."""

    def __init__(self, status: int, message: str, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def extension_missing(self) -> bool:
        # BC answers 404 when the custom API route is not published in the environment.
        return self.status == 404 or "No HTTP resource was found" in str(self)


class BusinessCentralClient:
    """Calls the standard BC API and the Fiscal Year Close Automation API pages."""

    def __init__(self, cfg: Settings, environment_name: str):
        self.cfg = cfg
        self.environment_name = environment_name
        self._msal = msal.ConfidentialClientApplication(
            client_id=cfg.client_id,
            client_credential=cfg.client_secret,
            authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
        )
        if not cfg.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ---- plumbing -------------------------------------------------------

    def _token(self) -> str:
        # MSAL caches the token in memory and only calls Entra ID when it is about to expire.
        result = self._msal.acquire_token_for_client(scopes=[self.cfg.scope])
        if "access_token" not in result:
            raise BCError(401, f"Token request failed: {result.get('error_description') or result}")
        return result["access_token"]

    def _root(self) -> str:
        return f"{self.cfg.base_url}/{self.cfg.tenant_id}/{self.environment_name}"

    def _standard(self, company_id: str) -> str:
        return f"{self._root()}/api/v2.0/companies({company_id})"

    def _custom(self, company_id: str) -> str:
        return (
            f"{self._root()}/api/{self.cfg.api_publisher}/{self.cfg.api_group}/"
            f"{self.cfg.api_version}/companies({company_id})"
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}
        headers.update(kwargs.pop("headers", {}))
        # Posting a closing journal can take a while in a large company.
        response = requests.request(
            method, url, headers=headers, timeout=600, verify=self.cfg.verify_ssl, **kwargs
        )
        if response.status_code >= 400:
            message, code = response.text[:1000], ""
            try:
                error = response.json().get("error", {})
                message, code = error.get("message", message), error.get("code", "")
            except ValueError:
                pass
            raise BCError(response.status_code, message, code)
        return response

    def _get_all(self, url: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while url:
            body = self._request("GET", url, params=params).json()
            rows.extend(body.get("value", []))
            url, params = body.get("@odata.nextLink"), None
        return rows

    # ---- standard API ---------------------------------------------------

    def companies(self) -> list[dict[str, Any]]:
        return self._get_all(f"{self._root()}/api/v2.0/companies")

    def fiscal_year_starts(self, company_id: str) -> list[dict[str, Any]]:
        return self._get_all(
            f"{self._standard(company_id)}/accountingPeriods",
            params={"$filter": "newFiscalYear eq true", "$orderby": "startingDate"},
        )

    # ---- extension API --------------------------------------------------

    def get_setup(self, company_id: str) -> dict[str, Any] | None:
        rows = self._get_all(f"{self._custom(company_id)}/{SETUPS}")
        return rows[0] if rows else None

    def create_setup(self, company_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"{self._custom(company_id)}/{SETUPS}", json=values).json()

    def update_setup(self, company_id: str, setup_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"{self._custom(company_id)}/{SETUPS}({setup_id})",
            json=values,
            headers={"If-Match": "*"},
        ).json()

    def run_action(self, company_id: str, setup_id: str, action: str) -> None:
        self._request(
            "POST",
            f"{self._custom(company_id)}/{SETUPS}({setup_id})/Microsoft.NAV.{ACTIONS[action]}",
        )

    def log_entries(self, company_id: str, top: int = 50, after_entry_no: int | None = None) -> list[dict[str, Any]]:
        params = {"$orderby": "entryNo desc", "$top": str(top)}
        if after_entry_no is not None:
            params["$filter"] = f"entryNo gt {after_entry_no}"
        body = self._request("GET", f"{self._custom(company_id)}/{LOG_ENTRIES}", params=params).json()
        return body.get("value", [])

    def user_posting_dates(self, company_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"{self._custom(company_id)}/{USER_POSTING_DATES}")

    def create_user_posting_dates(self, company_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"{self._custom(company_id)}/{USER_POSTING_DATES}", json=values).json()

    def update_user_posting_dates(self, company_id: str, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"{self._custom(company_id)}/{USER_POSTING_DATES}({row_id})",
            json=values,
            headers={"If-Match": "*"},
        ).json()

    def last_log_entry_no(self, company_id: str) -> int:
        rows = self.log_entries(company_id, top=1)
        return int(rows[0]["entryNo"]) if rows else 0
