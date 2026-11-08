from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from .bc_client import BCError, BusinessCentralClient
from .config import is_production, settings

BLANK_DATE = "0001-01-01"


@dataclass(frozen=True)
class Field:
    api: str
    label: str
    kind: str  # bool | int | date | text
    help: str = ""


# Editable setup fields, in the order they appear on the BC setup page.
SETUP_FIELDS: list[Field] = [
    Field("enabled", "Enabled", "bool", "Lets the daily Job Queue entry run the automation."),
    Field("closeDelayDays", "Close delay (days)", "int", "Days after year end before the year is closed."),
    Field("earliestFiscalYearStart", "Earliest FY start", "date", "Safety guard. Older years are never touched."),
    Field("recloseLookbackYears", "Re-close lookback (years)", "int", "Closed years re-checked for late postings."),
    Field("autoCreateNextFiscalYear", "Auto-create next FY", "bool"),
    Field("periodLength", "Period length", "text", "For example 1M."),
    Field("noOfPeriods", "No. of periods", "int"),
    Field("journalTemplateName", "Journal template", "text"),
    Field("journalBatchName", "Journal batch", "text", "Dedicated batch. If it has a No. Series, the closing document takes its next number."),
    Field("retainedEarningsAccount", "Retained earnings acc.", "text"),
    Field("documentNoPrefix", "Document no. prefix", "text"),
    Field("postingDescription", "Posting description", "text", "%1 is replaced with the year end date."),
    Field("closeByBusinessUnit", "Close by business unit", "bool"),
    Field("closeByGlobalDimension1", "Close by global dim. 1", "bool"),
    Field("closeByGlobalDimension2", "Close by global dim. 2", "bool"),
    Field("postAutomatically", "Post automatically", "bool", "Off leaves the journal in the batch for review."),
    Field(
        "openPostingWindow",
        "Open posting window",
        "bool",
        "Allows the closing date for the user running the close only while the journal posts, then puts their "
        "posting dates back. No one needs the ledger left open.",
    ),
]
FIELD_BY_API = {f.api: f for f in SETUP_FIELDS}


# ---- shared resources ---------------------------------------------------


def _client_class() -> type[BusinessCentralClient]:
    # Always the class from the bc_client module loaded now. Streamlit reloads changed modules
    # one by one, so the name imported at the top of this file can be an older copy.
    return sys.modules[BusinessCentralClient.__module__].BusinessCentralClient


@st.cache_resource(max_entries=5)
def _cached_client(environment_name: str) -> BusinessCentralClient:
    return _client_class()(settings(), environment_name)


def get_client(environment_name: str) -> BusinessCentralClient:
    c = _cached_client(environment_name)
    # Cached resources survive module reloads. A client built by an old module raises an old
    # BCError class that the pages' "except BCError" no longer matches, so rebuild it.
    if type(c) is not _client_class():
        _cached_client.clear()
        c = _cached_client(environment_name)
    return c


def environment() -> str:
    return st.session_state.environment


def client() -> BusinessCentralClient:
    return get_client(environment())


def production_unlocked() -> bool:
    # Unlocking is per browser session and per environment, so switching environment locks it again.
    return st.session_state.get("production_unlocked_for") == environment()


def writes_allowed() -> bool:
    # Production needs both the .env master switch and a deliberate unlock in this session.
    if not is_production(environment()):
        return True
    return settings().allow_production_updates and production_unlocked()


@st.cache_data(ttl=600, show_spinner="Loading companies...")
def load_companies(environment_name: str) -> pd.DataFrame:
    rows = get_client(environment_name).companies()
    df = pd.DataFrame(
        [{"entity": r.get("displayName") or r["name"], "name": r["name"], "company_id": r["id"]} for r in rows]
    )
    return df.sort_values("entity", key=lambda s: s.str.lower()).reset_index(drop=True)


def clear_caches() -> None:
    load_companies.clear()
    load_status.clear()


# ---- value conversion ---------------------------------------------------


def from_api(f: Field, value: Any) -> Any:
    if f.kind == "date":
        if not value or value == BLANK_DATE:
            return None
        return date.fromisoformat(value)
    if f.kind == "bool":
        return bool(value)
    if f.kind == "int":
        return int(value or 0)
    return value or ""


def to_api(f: Field, value: Any) -> Any:
    if f.kind == "date":
        if value is None or pd.isna(value):
            return BLANK_DATE
        return pd.Timestamp(value).date().isoformat()
    if f.kind == "bool":
        return bool(value)
    if f.kind == "int":
        return int(value or 0)
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()


def same(f: Field, a: Any, b: Any) -> bool:
    return to_api(f, a) == to_api(f, b)


def nice_action(value: str) -> str:
    # OData encodes spaces in enum names as _x0020_.
    return (value or "").replace("_x0020_", " ")


STATUS_LABELS = {"Success": "✅ Success", "Failed": "❌ Failed", "Info": "ℹ️ Info"}


def status_label(value: str | None) -> str:
    # Entries written before version 1.0.0.3 of the extension have no status.
    return STATUS_LABELS.get(value or "", "")


# ---- status across entities ---------------------------------------------


def _fiscal_year_summary(periods: list[dict[str, Any]], delay_days: int) -> dict[str, Any]:
    starts = sorted(periods, key=lambda p: p["startingDate"])
    years = []
    for i, p in enumerate(starts):
        end = None
        if i + 1 < len(starts):
            end = date.fromisoformat(starts[i + 1]["startingDate"]) - timedelta(days=1)
        years.append({"start": date.fromisoformat(p["startingDate"]), "end": end, "closed": bool(p.get("closed"))})

    closed = [y for y in years if y["closed"] and y["end"]]
    open_years = [y for y in years if not y["closed"]]
    oldest_open = open_years[0] if open_years else None
    due = bool(oldest_open and oldest_open["end"] and date.today() >= oldest_open["end"] + timedelta(days=delay_days))
    return {
        "last_closed_fy_end": closed[-1]["end"] if closed else None,
        "open_fy_start": oldest_open["start"] if oldest_open else None,
        "open_fy_end": oldest_open["end"] if oldest_open else None,
        "close_due": due,
        "years": [y for y in years if y["end"]],
    }


def plan_for_year(entity_status: dict[str, Any], action: str, year_end: date) -> tuple[bool, str]:
    """What an action will do to the fiscal year ending year_end in one entity: (will run, explanation)."""
    years = entity_status.get("years") or []
    year = next((y for y in years if y["end"] == year_end), None)
    if not year:
        return False, f"Skipped: no fiscal year ends on {year_end:%d/%m/%Y} in this entity."
    span = f'{year["start"]:%d/%m/%Y} to {year["end"]:%d/%m/%Y}'
    earlier_open = [y for y in years if y["end"] < year_end and not y["closed"]]
    if action == "run_now":
        if year["closed"]:
            return True, f"Already closed: {span} is not closed again. Only its closing journal is created."
        if date.today() <= year_end:
            return False, f"Skipped: {span} has not ended yet."
        if earlier_open:
            e = earlier_open[0]
            return False, f'Skipped: an earlier year ({e["start"]:%d/%m/%Y} to {e["end"]:%d/%m/%Y}) is still open.'
        return True, f"Closes {span} and creates its closing journal."
    if action == "create_journal":
        if not year["closed"]:
            return False, f"Skipped: {span} is still open. Use Run full close."
        return True, f"Creates the closing journal for {span}."
    if action == "post_journal":
        return True, f"Posts the reviewed closing journal for {span}. Refused if the batch holds another year."
    return True, ""


def _entity_status(c: BusinessCentralClient, company: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"entity": company["entity"], "company_id": company["company_id"]}
    try:
        setup = c.get_setup(company["company_id"])
    except BCError as exc:
        row["extension"] = "Not installed" if exc.extension_missing else "Error"
        row["message"] = "" if exc.extension_missing else str(exc)
        return row

    row["extension"] = "Installed"
    row["setup"] = setup
    delay = int(setup.get("closeDelayDays", 0)) if setup else 0
    try:
        row.update(_fiscal_year_summary(c.fiscal_year_starts(company["company_id"]), delay))
        logs = c.log_entries(company["company_id"], top=1)
        if logs:
            row["last_log_at"] = pd.to_datetime(logs[0]["createdAt"], utc=True)
            row["last_log_action"] = nice_action(logs[0]["logAction"])
            row["last_log_message"] = logs[0].get("message", "")
    except BCError as exc:
        row["message"] = str(exc)
    return row


@st.cache_data(ttl=300, show_spinner="Reading every entity from Business Central...")
def load_status(environment_name: str) -> list[dict[str, Any]]:
    """Setup, fiscal year position and last log entry for every company, read in parallel."""
    c = get_client(environment_name)
    companies = load_companies(environment_name).to_dict("records")
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda co: _entity_status(c, co), companies))


def setup_frame(status: list[dict[str, Any]]) -> pd.DataFrame:
    """One editable row per company that has the extension, with its current setup values."""
    rows = []
    for s in status:
        if s.get("extension") != "Installed":
            continue
        setup = s.get("setup") or {}
        row = {"entity": s["entity"], "company_id": s["company_id"], "setup_id": setup.get("id", ""),
               "has_setup": bool(setup)}
        for f in SETUP_FIELDS:
            row[f.api] = from_api(f, setup.get(f.api)) if setup else _default(f)
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty and "earliestFiscalYearStart" in df:
        df["earliestFiscalYearStart"] = pd.to_datetime(df["earliestFiscalYearStart"]).dt.date
    return df


def _default(f: Field) -> Any:
    # Mirrors the InitValue properties of table 68300 so new rows look like a fresh BC setup.
    defaults = {"closeDelayDays": 30, "recloseLookbackYears": 1, "noOfPeriods": 12, "periodLength": "1M",
                "documentNoPrefix": "CLOSE", "postingDescription": "Close Income Statement FY ending %1",
                "openPostingWindow": True}
    if f.api in defaults:
        return defaults[f.api]
    return {"bool": False, "int": 0, "date": None, "text": ""}[f.kind]

