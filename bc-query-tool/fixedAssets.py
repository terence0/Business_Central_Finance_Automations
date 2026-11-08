"""
fixedAssets.py -- Fixed Asset listing extractor for Business Central.

    RUN IN TERMINAL: streamlit run fixedAssets.py
    OR double-click:  run_fixedAssets.bat

Built on the same pattern as app.py and trialBalance.py, with three deliberate
differences:

1. It does NOT import the Query class. query.py defines `class Query` twice
   (lines 194 and 727); the second silently overrides the first, so editing it
   is risky. This module imports only COMPANY_LIST and the token, and issues its
   own requests. query.py is left untouched.

2. It follows @odata.nextLink. query.py has no pagination handling at all. The GL
   app gets away with it because filtering to two accounts keeps the result under
   BC's page size. An FA ledger pull has no account filter and can exceed it, and
   the failure mode is silent truncation.

3. It resolves field names at runtime. A BC Query object only exposes the fields
   its designer chose. Rather than assume, this asks the endpoint what it returns
   and reports the mapping on a 'Field Map' sheet. If a field it cannot work
   without is missing, it says which fields DO exist instead of failing obscurely.

Read-only. Issues GETs and nothing else.
"""

from __future__ import annotations

import io
import json
import time
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st

# query.py builds these at module scope from ./config/config.json, so the app
# must run with the Query tool folder as the working directory. The .bat does
# a cd /d "%~dp0" for exactly this reason.
import config.token_2 as token_2

from config import bc_env

# Production or sandbox, from BC_ENVIRONMENT_NAME (see config/bc_env.py).
CONFIG = bc_env.load_config()

BASE_URL = CONFIG["api"]["base_api"]
COMPANY_LIST = CONFIG["company"]

HEADERS = {
    "Authorization": f"Bearer {token_2.get_access_token()}",
    "Prefer": "odata.continue-on-error",
    "Isolation": "snapshot",
}

requests.packages.urllib3.disable_warnings()   # query.py uses verify=False

# --------------------------------------------------------------------------
# endpoints
# --------------------------------------------------------------------------
# Both are published. Query 267 is the same object TYPE as the GL query already
# in use, so it is the default. Page 5604 is the fallback, because a Page
# exposes what the page shows and the FA Ledger Entries page shows FA Posting
# Type and Depreciation Book Code on screen.

LEDGER_ENDPOINTS = {
    "FALedgerEntries  (Query 267, default)": "FALedgerEntries",
    "FA_Ledger_Entries_Excel  (Page 5604, fallback)": "FA_Ledger_Entries_Excel",
}
ASSET_MASTER_ENDPOINT = "FixedAssets"                  # Page 5601
DEP_BOOK_ENDPOINT = "FA_Depreciation_Books_Excel"      # Page 5619

# --------------------------------------------------------------------------
# field resolution
# --------------------------------------------------------------------------
# BC serialises field names by stripping spaces and punctuation to underscores,
# but the exact result varies between Pages and Queries. Each concept lists the
# spellings seen in practice, most likely first.

FIELD_ALIASES = {
    "fa_no": ["FA_No_", "FA_No", "FANo", "No_", "No"],
    "posting_date": ["FA_Posting_Date", "FAPostingDate", "Posting_Date",
                     "PostingDate"],
    "posting_type": ["FA_Posting_Type", "FAPostingType", "FA_Posting_Type_Code"],
    "amount": ["Amount", "Amount_LCY_", "Amount_LCY", "AmountLCY"],
    "dep_book": ["Depreciation_Book_Code", "DepreciationBookCode",
                 "Depreciation_Book"],
    # optional, used only for enrichment
    "posting_category": ["FA_Posting_Category", "FAPostingCategory"],
    "description": ["Description", "FA_Description", "FA_Name"],
    "document_no": ["Document_No_", "DocumentNo", "Document_No"],
    "entry_no": ["Entry_No_", "EntryNo", "Entry_No", "AuxiliaryIndex1"],
    "fa_class": ["FA_Class_Code", "FAClassCode", "FA_Class"],
    "fa_subclass": ["FA_Subclass_Code", "FASubclassCode", "FA_Subclass"],
    "fa_location": ["FA_Location_Code", "FALocationCode"],
    "reversed": ["Reversed", "Reversed_Entry_No_"],
}

# Fields the listing cannot be produced without.
REQUIRED = ["fa_no", "posting_date", "posting_type", "amount"]

# Depreciation Book Code is required in substance: BC holds several books per
# asset, so without it cost and depreciation are summed across books and the
# figures are meaningless. Treated as required unless the user overrides, in
# which case a single-book company is assumed and the output says so.
BOOK_CRITICAL = "dep_book"

# --------------------------------------------------------------------------
# what makes up net book value
# --------------------------------------------------------------------------
# In BC these are governed by FA Posting Type Setup. The standard book-value
# components are below. Disposal postings (proceeds, gain, loss, book value on
# disposal) are deliberately EXCLUDED, because including them would net the sale
# proceeds against cost and understate NBV.
#
# CHECK THIS against FA Posting Type Setup before relying on the NBV column.
# Every posting type found is written as its own column, so the classification
# is visible and can be challenged.

BOOK_VALUE_TYPES = {
    "acquisition cost", "depreciation", "write-down", "write down",
    "appreciation", "custom 1", "custom 2",
}
DISPOSAL_TYPES = {
    "proceeds on disposal", "gain/loss", "gain / loss", "gain",
    "loss", "book value on disposal",
}


def resolve_fields(sample) -> tuple:
    """Map concepts onto the field names this endpoint actually returned.

    Takes the UNION of keys across rows, not just the first row. BC omits some
    fields from a row when they are null, so a field present on row 500 can be
    absent from row 0. Reading only the first row silently lost
    FA_Posting_Category in testing, which is what flags a disposal.
    """
    if isinstance(sample, dict):
        sample = [sample]
    present = {}
    for row in sample[:500]:
        for key in row:
            present.setdefault(key.lower(), key)
    mapping, missing = {}, []
    for concept, aliases in FIELD_ALIASES.items():
        hit = next((present[a.lower()] for a in aliases if a.lower() in present),
                   None)
        if hit:
            mapping[concept] = hit
        else:
            missing.append(concept)
    return mapping, missing


RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def _get(url: str, params: dict = None, attempts: int = 4):
    """One GET, retried on the failures that are worth retrying.

    429 and 5xx are transient: BC throttles per environment, and a wide FA pull
    across 28 companies will hit it. 400 and 404 are not retried, because a bad
    property name or an unpublished service will fail identically forever.
    """
    delay, last = 2.0, None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=HEADERS, params=params,
                                    verify=False, timeout=300)
        except requests.RequestException as exc:            # noqa: PERF203
            last = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                return response
            if response.status_code not in RETRY_STATUS:
                return response
            last = f"HTTP {response.status_code}: {response.text[:200]}"
            header = response.headers.get("Retry-After")
            if header:
                try:
                    delay = max(delay, float(header))
                except ValueError:
                    pass
        if attempt < attempts:
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError(f"gave up after {attempts} attempts. Last: {last}")


def service_url(service: str, company_key: str) -> str:
    return (BASE_URL + f"{COMPANY_LIST[company_key]}/"
            + urllib.parse.quote(service, safe=""))


def fetch(service: str, company_key: str, params: dict = None,
          page_limit: int = 400, on_page=None) -> list:
    """GET every page of an OData service for one company.

    Follows @odata.nextLink. query.py does not, which means a result larger than
    BC's page size is silently truncated.

    page_limit is a runaway guard, not a data limit. Hitting it raises rather
    than returning a short answer, because a truncated FA listing looks
    perfectly plausible.
    """
    url = service_url(service, company_key)
    rows, pages = [], 0
    while url and pages < page_limit:
        response = _get(url, params if pages == 0 else None)
        if response.status_code != 200:
            raise RuntimeError(
                f"{company_key}: HTTP {response.status_code} on {service}. "
                f"{response.text[:300]}")
        payload = response.json()
        rows.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
        params = None
        pages += 1
        if on_page:
            on_page(pages, len(rows))
    if url:
        raise RuntimeError(
            f"{company_key}: {service} still had pages after {page_limit} "
            f"requests. Reduce the months per request in section 4.")
    return rows


# --------------------------------------------------------------------------
# incremental requests
# --------------------------------------------------------------------------
# Three independent axes, so no single request is ever large:
#   company  -- one request set per company, which already existed
#   date     -- server-side $filter over a bounded window, chunked
#   page     -- @odata.nextLink inside each window
#
# The date axis is the one to be careful with. Cost and accumulated
# depreciation are cumulative from the day the asset was acquired, so the
# windows must cover the WHOLE history up to the period end. Starting them at
# the fiscal year start is the same mistake as the 2022-08-01 floor on the tax
# GL extract: the numbers come back looking clean and are wrong.


def add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400
                                                        == 0) else 28, 31, 30,
                           31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def date_windows(start: date, end: date, months: int) -> list:
    """Split [start, end] into consecutive windows of `months` months.

    months=0 means one window, i.e. no date chunking.
    """
    if not months or months <= 0:
        return [(start, end)]
    windows, lo = [], start
    while lo <= end:
        hi = min(add_months(lo, months) - timedelta(days=1), end)
        windows.append((lo, hi))
        lo = hi + timedelta(days=1)
    return windows


def date_filter(field: str, lo: date, hi: date) -> str:
    """OData filter for an Edm.Date field. BC serialises FA Posting Date as
    Edm.Date, so the literal is unquoted and has no time component."""
    return f"{field} ge {lo.isoformat()} and {field} le {hi.isoformat()}"


def server_filter_works(service: str, company_key: str, field: str) -> tuple:
    """Test one tiny filtered request before committing to 28 companies.

    Returns (ok, message). If BC rejects the property or the literal form, the
    caller falls back to pulling unfiltered and filtering client-side, which is
    slower but correct.
    """
    params = {"$filter": date_filter(field, date(2000, 1, 1), date(2000, 1, 2)),
              "$top": "1"}
    try:
        response = _get(service_url(service, company_key), params, attempts=2)
    except Exception as exc:                                # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if response.status_code == 200:
        return True, "server-side date filter accepted"
    return False, f"HTTP {response.status_code}: {response.text[:200]}"


def fetch_windowed(service: str, company_key: str, date_field: str,
                   windows: list, dedupe_field: str = None,
                   on_progress=None) -> list:
    """Pull one company across several date windows and concatenate.

    Deduplicates on Entry No. where the endpoint exposes it. Window boundaries
    do not overlap, so duplicates should not arise; the guard is there because
    a silent double-count in a fixed asset register is expensive to find.
    """
    rows, seen = [], set()
    for position, (lo, hi) in enumerate(windows, start=1):
        if on_progress:
            on_progress(position, len(windows), lo, hi)
        params = {"$filter": date_filter(date_field, lo, hi)}
        chunk = fetch(service, company_key, params)
        for row in chunk:
            if dedupe_field:
                marker = row.get(dedupe_field)
                if marker is not None:
                    if marker in seen:
                        continue
                    seen.add(marker)
            rows.append(row)
    return rows


def to_date(value):
    if value in (None, ""):
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def to_float(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


def build_listing(entries: list, mapping: dict, period_end, fy_start,
                  single_book: bool):
    """Aggregate FA ledger entries into one row per asset per depreciation book.

    'As at period end' is a cumulative sum of entries up to that date, the same
    way the GL behaves. It is not a snapshot like the trial balance service.
    """
    f = mapping
    listing = defaultdict(lambda: defaultdict(float))
    meta, types_seen = {}, set()

    for row in entries:
        posting_date = to_date(row.get(f["posting_date"]))
        if posting_date is None or posting_date > period_end:
            continue
        asset = str(row.get(f["fa_no"]) or "").strip()
        if not asset:
            continue
        book = ("(single book)" if single_book
                else str(row.get(f[BOOK_CRITICAL]) or "").strip() or "(blank)")
        key = (row["Company"], asset, book)

        raw_type = str(row.get(f["posting_type"]) or "").strip()
        types_seen.add(raw_type)
        amount = to_float(row.get(f["amount"]))
        listing[key][raw_type] += amount

        lowered = raw_type.lower()
        if lowered in BOOK_VALUE_TYPES:
            listing[key]["__nbv"] += amount
            if fy_start <= posting_date <= period_end:
                if lowered == "acquisition cost":
                    listing[key]["__additions"] += amount
                elif lowered == "depreciation":
                    listing[key]["__charge"] += amount
        elif lowered in DISPOSAL_TYPES:
            listing[key]["__disposal_postings"] += amount
            # A disposal posting is itself evidence of disposal. Do not rely on
            # FA Posting Category, which some services do not expose.
            listing[key]["__disposed"] = 1.0
            if fy_start <= posting_date <= period_end:
                listing[key]["__disposed_in_period"] = 1.0

        category = str(row.get(f.get("posting_category", ""), "") or "").strip()
        if category:
            listing[key]["__has_category"] = 1.0
            if "disposal" in category.lower():
                listing[key]["__disposed"] = 1.0

        current = meta.setdefault(key, {})
        for concept in ("description", "fa_class", "fa_subclass", "fa_location"):
            if concept in f and not current.get(concept):
                current[concept] = row.get(f[concept])
        if "__first" not in current or posting_date < current["__first"]:
            current["__first"] = posting_date

    ordered_types = sorted(
        types_seen,
        key=lambda t: (t.lower() not in BOOK_VALUE_TYPES, t.lower()))

    records = []
    for (company, asset, book), sums in sorted(listing.items()):
        info = meta.get((company, asset, book), {})
        record = {
            "Company": company,
            "FA No.": asset,
            "Depreciation Book": book,
            "Description": info.get("description"),
            "FA Class": info.get("fa_class"),
            "FA Subclass": info.get("fa_subclass"),
            "FA Location": info.get("fa_location"),
            "First Posting Date": info.get("__first"),
        }
        for kind in ordered_types:
            record[kind or "(blank type)"] = round(sums.get(kind, 0.0), 2)
        record["Net Book Value"] = round(sums.get("__nbv", 0.0), 2)
        record["Additions in Period"] = round(sums.get("__additions", 0.0), 2)
        record["Depreciation Charge in Period"] = round(sums.get("__charge", 0.0), 2)
        record["Disposed"] = "Yes" if sums.get("__disposed") else ""
        record["Disposed in Period"] = "Yes" if sums.get("__disposed_in_period") else ""
        records.append(record)

    return pd.DataFrame(records), ordered_types


def to_excel(sheets: dict) -> bytes:
    output = io.BytesIO()
    try:
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
    except (ImportError, ValueError):
        writer = pd.ExcelWriter(output, engine="openpyxl")
    with writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, index=False, sheet_name=name[:31])
    return output.getvalue()


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

st.set_page_config(page_title="Fixed Asset Listing Tool", layout="wide")
st.title("Fixed Asset Listing Tool")
bc_env.banner(st, CONFIG)
st.write("Extracts a fixed asset listing from Business Central, as at a period "
         "end, for one or more companies.")

all_company_keys = list(COMPANY_LIST.keys())

st.subheader("1) Select Company / Companies")
company_selection = st.multiselect("Choose one or more companies",
                                   options=all_company_keys)
if st.checkbox("Select ALL companies"):
    company_selection = all_company_keys

st.subheader("2) Period")
col1, col2, col3 = st.columns(3)
with col1:
    period_end = st.date_input("Period end (the 'as at' date)")
with col2:
    fy_start = st.date_input("Fiscal year start (for in-period movement)")
with col3:
    history_from = st.date_input("Pull history from",
                                 value=date(2010, 1, 1))
st.caption("Cost and accumulated depreciation are cumulative to the period end. "
           "Additions and the depreciation charge are measured between the "
           "fiscal year start and the period end.")
st.caption("'Pull history from' bounds the requests, not the report. It must "
           "predate the oldest asset still on the register. Setting it to the "
           "fiscal year start would give a clean-looking listing with cost and "
           "accumulated depreciation both understated.")

st.subheader("3) Source")
endpoint_label = st.radio("FA ledger web service", list(LEDGER_ENDPOINTS),
                          index=0)
LEDGER_ENDPOINT = LEDGER_ENDPOINTS[endpoint_label]
enrich = st.checkbox(
    f"Also pull asset master data from {ASSET_MASTER_ENDPOINT} (class, "
    f"subclass, description)", value=True)
allow_no_book = st.checkbox(
    "Proceed even if Depreciation Book Code is not available", value=False,
    help="BC holds several depreciation books per asset. Without the book code "
         "the figures sum across books. Only tick this if you know there is a "
         "single book.")

st.subheader("4) Request size")
st.caption("Requests are already split one per company. This splits each "
           "company's pull further, by date, so no single URL or response is "
           "large. Pagination inside each window is automatic.")
col4, col5 = st.columns(2)
with col4:
    chunk_label = st.selectbox(
        "Months per request",
        ["One request per company (no date chunking)",
         "60 months", "24 months", "12 months", "6 months", "3 months",
         "1 month"],
        index=1,
        help="Smaller windows mean more requests, each one smaller. Drop this "
             "if a window times out or comes back too large; it does not "
             "change the figures, only how they are fetched.")
with col5:
    pause_seconds = st.number_input(
        "Pause between companies (seconds)", min_value=0.0, max_value=30.0,
        value=0.0, step=0.5,
        help="Only needed if BC starts returning 429. Retries with backoff are "
             "automatic either way.")
CHUNK_MONTHS = {"One request per company (no date chunking)": 0,
                "60 months": 60, "24 months": 24, "12 months": 12,
                "6 months": 6, "3 months": 3, "1 month": 1}[chunk_label]

st.divider()
diagnose = st.button("Check fields only (fast, one company, 3 rows)")
run = st.button("Run Extraction")


def check_inputs():
    if not company_selection:
        return "Select at least one company, or choose ALL."
    if not period_end or not fy_start:
        return "Set both the period end and the fiscal year start."
    if fy_start > period_end:
        return "Fiscal year start cannot be after the period end."
    if history_from > fy_start:
        return ("'Pull history from' is after the fiscal year start. Cost and "
                "accumulated depreciation would be understated.")
    return None


if diagnose:
    problem = check_inputs()
    if problem:
        st.error(problem)
    else:
        probe_company = company_selection[0]
        try:
            sample = fetch(LEDGER_ENDPOINT, probe_company, {"$top": "3"})
        except Exception as exc:                            # noqa: BLE001
            st.error(f"{type(exc).__name__}: {exc}")
            sample = None
        if sample is not None:
            if not sample:
                st.warning(f"{LEDGER_ENDPOINT} reachable but returned no rows "
                           f"for {probe_company}. Try another company.")
            else:
                mapping, missing = resolve_fields(sample)
                st.success(f"{LEDGER_ENDPOINT} returned "
                           f"{len(sample[0])} fields for {probe_company}.")
                st.write("**Resolved mapping**")
                st.dataframe(pd.DataFrame(
                    [{"Concept": k, "Field in BC": v} for k, v in mapping.items()]),
                    hide_index=True)
                blocking = [c for c in REQUIRED if c in missing]
                if blocking:
                    st.error(f"Cannot build a listing: no field found for "
                             f"{', '.join(blocking)}.")
                if BOOK_CRITICAL in missing:
                    st.warning(
                        "No Depreciation Book Code field. Either switch to the "
                        "other web service, or tick the single-book box above "
                        "if this really is a single-book setup.")
                st.write("**All fields returned**")
                st.code("\n".join(sorted(sample[0].keys())))
                st.write("**Sample row**")
                st.json(sample[0])

if run:
    problem = check_inputs()
    if problem:
        st.error(problem)
        st.stop()

    progress = st.progress(0.0)
    status = st.empty()
    entries, failures, notes = [], [], []
    total = len(company_selection)

    # The $filter has to name the posting date field the way THIS endpoint
    # spells it, so resolve the field names first off a 3-row probe, then test
    # the filter itself on one tiny request before committing to 28 companies.
    date_field, entry_field = None, None
    windows = [(history_from, period_end)]
    use_server_filter = False

    if CHUNK_MONTHS:
        status.text("Resolving field names...")
        try:
            probe = fetch(LEDGER_ENDPOINT, company_selection[0], {"$top": "3"})
        except Exception as exc:                            # noqa: BLE001
            st.error(f"Could not reach {LEDGER_ENDPOINT}: "
                     f"{type(exc).__name__}: {exc}")
            st.stop()
        probe_map, _ = resolve_fields(probe)
        date_field = probe_map.get("posting_date")
        entry_field = probe_map.get("entry_no")
        if not date_field:
            notes.append(
                "No posting date field found on the probe, so date chunking "
                "was skipped and each company was pulled in one request set.")
        else:
            ok, message = server_filter_works(
                LEDGER_ENDPOINT, company_selection[0], date_field)
            if ok:
                use_server_filter = True
                windows = date_windows(history_from, period_end, CHUNK_MONTHS)
                notes.append(
                    f"Server-side date filter on {date_field}, "
                    f"{len(windows)} windows per company, "
                    f"{len(windows) * total} request sets in total.")
            else:
                notes.append(
                    f"BC rejected the date filter, so it was dropped and rows "
                    f"are filtered after the response instead. Reason: "
                    f"{message}")

    for index, key in enumerate(company_selection, start=1):
        def report(position, count, lo, hi, key=key, index=index):
            status.text(f"({index}/{total}) {key}: window {position}/{count}  "
                        f"{lo} to {hi}")
        try:
            if use_server_filter:
                status.text(f"({index}/{total}) {key}: starting...")
                rows = fetch_windowed(LEDGER_ENDPOINT, key, date_field,
                                      windows, entry_field, report)
            else:
                status.text(f"({index}/{total}) {key}: pulling "
                            f"{LEDGER_ENDPOINT}...")
                rows = fetch(LEDGER_ENDPOINT, key)
            for row in rows:
                row["Company"] = key
            entries.extend(rows)
        except Exception as exc:                            # noqa: BLE001
            failures.append(f"{key}: {type(exc).__name__}: {exc}")
        progress.progress(index / total)
        if pause_seconds and index < total:
            time.sleep(float(pause_seconds))

    status.text("Done pulling.")
    for line in notes:
        st.info(line)
    if failures:
        st.error("Some companies failed:")
        for line in failures:
            st.write(f"- {line}")
    if not entries:
        st.warning("No FA ledger entries returned for any selected company.")
        st.stop()

    mapping, missing = resolve_fields(entries)
    blocking = [c for c in REQUIRED if c in missing]
    if blocking:
        st.error(f"Cannot build a listing: no field found for "
                 f"{', '.join(blocking)}. Fields returned were:")
        st.code("\n".join(sorted(entries[0].keys())))
        st.info("Try the other web service in section 3.")
        st.stop()

    single_book = BOOK_CRITICAL in missing
    if single_book and not allow_no_book:
        st.error(
            "This service does not expose Depreciation Book Code. BC holds "
            "several books per asset, so cost and depreciation would be summed "
            "across books. Switch web service, or tick the single-book box if "
            "that is genuinely the case here.")
        st.code("\n".join(sorted(entries[0].keys())))
        st.stop()

    listing, ordered_types = build_listing(
        entries, mapping, period_end, fy_start, single_book)

    # Optional master data enrichment.
    if enrich and not listing.empty:
        status.text("Pulling asset master data...")
        master_rows = []
        for key in company_selection:
            try:
                for row in fetch(ASSET_MASTER_ENDPOINT, key):
                    row["Company"] = key
                    master_rows.append(row)
            except Exception as exc:                        # noqa: BLE001
                failures.append(f"{key}: master data: {exc}")
        if master_rows:
            master_map, _ = resolve_fields(master_rows)
            if "fa_no" in master_map:
                frame = pd.DataFrame(master_rows)
                keep = {master_map["fa_no"]: "FA No.", "Company": "Company"}
                for concept, label in (("description", "Description"),
                                       ("fa_class", "FA Class"),
                                       ("fa_subclass", "FA Subclass"),
                                       ("fa_location", "FA Location")):
                    if concept in master_map:
                        keep[master_map[concept]] = f"{label} (master)"
                frame = frame[[c for c in keep if c in frame.columns]].rename(
                    columns=keep).drop_duplicates(subset=["Company", "FA No."])
                frame["FA No."] = frame["FA No."].astype(str).str.strip()
                listing = listing.merge(frame, on=["Company", "FA No."],
                                        how="left")

    # Reconciliation by company: what should tie to the trial balance.
    recon_rows = []
    for company, group in listing.groupby("Company"):
        record = {"Company": company, "Assets": group["FA No."].nunique()}
        for kind in ordered_types:
            column = kind or "(blank type)"
            if column in group.columns:
                record[column] = round(group[column].sum(), 2)
        record["Net Book Value"] = round(group["Net Book Value"].sum(), 2)
        record["Additions in Period"] = round(group["Additions in Period"].sum(), 2)
        record["Depreciation Charge in Period"] = round(
            group["Depreciation Charge in Period"].sum(), 2)
        recon_rows.append(record)
    recon = pd.DataFrame(recon_rows)

    field_map = pd.DataFrame(
        [{"Concept": k, "Field in BC": v} for k, v in mapping.items()]
        + [{"Concept": "-- not found --", "Field in BC": ", ".join(missing)}]
        + [{"Concept": "web service used", "Field in BC": LEDGER_ENDPOINT},
           {"Concept": "period end", "Field in BC": str(period_end)},
           {"Concept": "fiscal year start", "Field in BC": str(fy_start)},
           {"Concept": "history pulled from", "Field in BC": str(history_from)},
           {"Concept": "request splitting",
            "Field in BC": (f"server-side $filter on {date_field}, "
                            f"{len(windows)} windows of {CHUNK_MONTHS} months "
                            f"per company" if use_server_filter
                            else "one request set per company, no date filter")},
           {"Concept": "companies", "Field in BC": ", ".join(company_selection)},
           {"Concept": "ledger rows pulled", "Field in BC": str(len(entries))},
           {"Concept": "NBV components",
            "Field in BC": "; ".join(sorted(BOOK_VALUE_TYPES))},
           {"Concept": "excluded from NBV",
            "Field in BC": "; ".join(sorted(DISPOSAL_TYPES))},
           {"Concept": "single book assumed",
            "Field in BC": "yes" if single_book else "no"},
           {"Concept": "all fields returned",
            "Field in BC": ", ".join(sorted(entries[0].keys()))}])

    st.success(f"{len(listing):,} asset/book rows from {len(entries):,} ledger "
               f"entries across {len(company_selection)} company/ies.")
    if single_book:
        st.warning("Depreciation Book Code was not available. Figures assume a "
                   "single book.")
    st.subheader("Reconciliation by company")
    st.caption("Tie the cost and depreciation columns to the trial balance "
               "before relying on the listing.")
    st.dataframe(recon, hide_index=True, use_container_width=True)
    st.subheader("Listing")
    st.dataframe(listing, hide_index=True, height=520, use_container_width=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if set(company_selection) == set(all_company_keys):
        label = "ALL"
    elif len(company_selection) > 1:
        label = "MULTI"
    else:
        label = company_selection[0]

    raw = pd.DataFrame(entries)
    st.download_button(
        "Download Excel",
        data=to_excel({"FA Listing": listing,
                       "Reconciliation": recon,
                       "FA Ledger Entries": raw,
                       "Field Map": field_map}),
        file_name=f"FA - {label} - {timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
