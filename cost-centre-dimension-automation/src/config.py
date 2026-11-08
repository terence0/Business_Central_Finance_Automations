from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    environment_name: str
    client_id: str
    client_secret: str
    scope: str
    base_url: str
    allow_production_updates: bool
    api_publisher: str
    api_group: str
    api_version: str


def settings() -> Settings:
    return Settings(
        tenant_id=os.getenv("BC_TENANT_ID", ""),
        environment_name=os.getenv("BC_ENVIRONMENT_NAME", "Sandbox_Test"),
        client_id=os.getenv("BC_CLIENT_ID", ""),
        client_secret=os.getenv("BC_CLIENT_SECRET", ""),
        scope=os.getenv("BC_SCOPE", "https://api.businesscentral.dynamics.com/.default"),
        base_url=os.getenv("BC_BASE_URL", "https://api.businesscentral.dynamics.com/v2.0").rstrip("/"),
        allow_production_updates=os.getenv("ALLOW_PRODUCTION_UPDATES", "false").lower() == "true",
        api_publisher=os.getenv("BC_API_PUBLISHER", "contoso"),
        api_group=os.getenv("BC_API_GROUP", "financeautomation"),
        api_version=os.getenv("BC_API_VERSION", "v1.0"),
    )
