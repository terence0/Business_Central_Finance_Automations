import json
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# override=False: an environment chosen by the run file (BC_ENVIRONMENT_NAME,
# "Run BC GL Posting Automation (Sandbox).bat") must win over .env. With
# nothing set by the launcher, .env applies exactly as before.
load_dotenv(override=False)

@dataclass(frozen=True)
class Settings:
    tenant_id: str
    environment_name: str
    client_id: str
    client_secret: str
    scope: str
    base_url: str
    allow_production_updates: bool


def settings() -> Settings:
    return Settings(
        tenant_id=os.getenv("BC_TENANT_ID", ""),
        environment_name=os.getenv("BC_ENVIRONMENT_NAME", "Production"),
        client_id=os.getenv("BC_CLIENT_ID", ""),
        client_secret=os.getenv("BC_CLIENT_SECRET", ""),
        scope=os.getenv("BC_SCOPE", "https://api.businesscentral.dynamics.com/.default"),
        base_url=os.getenv("BC_BASE_URL", "https://api.businesscentral.dynamics.com/v2.0").rstrip("/"),
        allow_production_updates=os.getenv("ALLOW_PRODUCTION_UPDATES", "false").lower() == "true",
    )


def load_companies(path: str = "config/companies.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
