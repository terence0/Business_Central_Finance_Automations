from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The .env file sits next to streamlit_app.py, whatever folder the app is started from.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    environment_name: str
    client_id: str
    client_secret: str
    scope: str
    base_url: str
    allow_production_updates: bool
    verify_ssl: bool
    api_publisher: str
    api_group: str
    api_version: str

    def missing(self) -> list[str]:
        required = {
            "BC_TENANT_ID": self.tenant_id,
            "BC_CLIENT_ID": self.client_id,
            "BC_CLIENT_SECRET": self.client_secret,
        }
        return [name for name, value in required.items() if not value]


def settings() -> Settings:
    return Settings(
        tenant_id=os.getenv("BC_TENANT_ID", ""),
        environment_name=os.getenv("BC_ENVIRONMENT_NAME", "Production"),
        client_id=os.getenv("BC_CLIENT_ID", ""),
        client_secret=os.getenv("BC_CLIENT_SECRET", ""),
        scope=os.getenv("BC_SCOPE", "https://api.businesscentral.dynamics.com/.default"),
        base_url=os.getenv("BC_BASE_URL", "https://api.businesscentral.dynamics.com/v2.0").rstrip("/"),
        allow_production_updates=_flag("ALLOW_PRODUCTION_UPDATES", "false"),
        verify_ssl=_flag("BC_VERIFY_SSL", "true"),
        api_publisher=os.getenv("BC_API_PUBLISHER", "contoso"),
        api_group=os.getenv("BC_API_GROUP", "financeautomation"),
        api_version=os.getenv("BC_API_VERSION", "v1.0"),
    )


def is_production(environment_name: str) -> bool:
    return "prod" in environment_name.lower()
