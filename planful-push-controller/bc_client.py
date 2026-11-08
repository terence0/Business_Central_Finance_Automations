import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import msal
import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BusinessCentralConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    environment: str
    base_url: str
    api_publisher: str
    api_group: str
    api_version: str
    api_entity_set: str

    @property
    def environment_url(self) -> str:
        return f"{self.base_url}/{self.tenant_id}/{self.environment}"


class BusinessCentralClient:
    def __init__(self, config: BusinessCentralConfig):
        self.config = config
        self._access_token: Optional[str] = None

    @classmethod
    def from_env(cls) -> "BusinessCentralClient":
        config = BusinessCentralConfig(
            tenant_id=os.getenv("BC_TENANT_ID", "").strip(),
            client_id=os.getenv("BC_CLIENT_ID", "").strip(),
            client_secret=os.getenv("BC_CLIENT_SECRET", "").strip(),
            environment=os.getenv("BC_ENVIRONMENT_NAME", "Production").strip(),
            base_url=os.getenv("BC_BASE_URL", "https://api.businesscentral.dynamics.com/v2.0").strip(),
            api_publisher=os.getenv("BC_API_PUBLISHER", "contoso").strip(),
            api_group=os.getenv("BC_API_GROUP", "financeautomation").strip(),
            api_version=os.getenv("BC_API_VERSION", "v1.0").strip(),
            api_entity_set=os.getenv("BC_API_ENTITY_SET", "planfulPushRuns").strip(),
        )

        missing = [
            key for key, value in {
                "BC_TENANT_ID": config.tenant_id,
                "BC_CLIENT_ID": config.client_id,
                "BC_CLIENT_SECRET": config.client_secret,
                "BC_ENVIRONMENT_NAME": config.environment,
            }.items()
            if not value
        ]

        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        return cls(config)

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        authority = f"https://login.microsoftonline.com/{self.config.tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=self.config.client_id,
            authority=authority,
            client_credential=self.config.client_secret,
        )

        result = app.acquire_token_for_client(
            scopes=["https://api.businesscentral.dynamics.com/.default"]
        )

        if "access_token" not in result:
            raise RuntimeError(f"Could not get access token: {result}")

        self._access_token = result["access_token"]
        return self._access_token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_companies(self) -> List[Dict[str, Any]]:
        url = f"{self.config.environment_url}/api/v2.0/companies"
        response = requests.get(url, headers=self._headers(), timeout=60)
        if not response.ok:
            raise RuntimeError(f"Could not load companies. Status: {response.status_code}\n{response.text}")
        return response.json().get("value", [])

    def run_summary_push(
        self,
        company_id: str,
        starting_date: str,
        ending_date: str,
        gl_account_filter: str = "",
        send_data_to_planful: bool = True,
        filter_on_period: bool = False,
        period_formula: str = "",
        export_to_xml: bool = False,
    ) -> Dict[str, Any]:
        # Expected BC endpoint:
        # /api/contoso/financeautomation/v1.0/companies({companyId})/planfulPushRuns
        url = (
            f"{self.config.environment_url}"
            f"/api/{self.config.api_publisher}/{self.config.api_group}/{self.config.api_version}"
            f"/companies({company_id})/{self.config.api_entity_set}"
        )

        # A sandbox never sends to Planful: its Planful connector setup is a copy of
        # Production's and may point at live Planful. Enforced here, not only
        # in the page, so no caller can get round it.
        if not sends_allowed(self.config.environment):
            send_data_to_planful = False

        payload = {
            "startingDate": starting_date,
            "endingDate": ending_date,
            "glAccountNoFilter": gl_account_filter or "",
            "sendDataToPlanful": bool(send_data_to_planful),
            "filterOnPeriod": bool(filter_on_period),
            "periodFormula": period_formula or "",
            "exportToXml": bool(export_to_xml),
        }

        response = requests.post(url, headers=self._headers(), json=payload, timeout=300)
        if not response.ok:
            raise RuntimeError(f"Status: {response.status_code}\n{response.text}")

        try:
            return response.json()
        except ValueError:
            return {"status": "Success", "rawResponse": response.text}


def sends_allowed(environment: str) -> bool:
    """Only Production may send data on to Planful."""
    return (environment or "").strip().lower() == "production"
