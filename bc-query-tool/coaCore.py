"""
Chart of accounts: create a G/L account identically in every entity.

Used by coaSetup.py (the Streamlit page). Nothing here touches Streamlit, so
it can be driven from a script too.

The flow is always plan -> review -> apply -> verify:

    plan_accounts()   reads every selected entity and works out, per entity
                      and account, what would happen. Writes nothing.
    apply_plan()      creates what the plan said to create, then reads each
                      account back and compares it field by field.

Contoso UK (Contoso UK Ltd) is the master: its chart is a superset
of every other entity's, so new accounts are designed against it and an
existing UK account can be used as the starting point for a new one.

An account that already exists in an entity is NEVER changed. It is reported,
with any differences from what was asked for, and left alone. This tool adds
accounts; it does not edit them.

Writes go through the published G/L Account Card (G_L_Account_Card_Excel) and
Default Dimensions (Default_Dimensions_Excel) web services, the same pages a
user would fill in, so Business Central runs its own validation on every field.
"""

import csv
import json
import logging
import os
import urllib.parse
from datetime import datetime

import requests

import config.token_2 as token_2

CONFIG = json.load(open(os.path.join("config", "config.json")))["api"]

# Which environment this tool writes to. The run files choose it through
# BC_ENVIRONMENT_NAME (launchers\_bc_environment.cmd):
#     Production\Run Chart of Accounts.bat           -> Production
#     Sandbox\Run Chart of Accounts (Sandbox).bat    -> the sandbox
# Launched any other way (QueryTool.bat double-clicked, run_coaSetup.bat) it
# falls back to the sandbox, because this tool writes. BC_COA_ENVIRONMENT is
# still honoured as an override for this tool alone.
ENVIRONMENT = (os.environ.get("BC_COA_ENVIRONMENT")
               or os.environ.get("BC_ENVIRONMENT_NAME")
               or "Sandbox_Test")
IS_PRODUCTION = ENVIRONMENT.lower() == "production"

_ROOT = f"https://api.businesscentral.dynamics.com/v2.0/{CONFIG['tenant_id']}/{ENVIRONMENT}"
ODATA = f"{_ROOT}/ODataV4/"
API_COMPANIES = f"{_ROOT}/api/v2.0/companies"

MASTER_COMPANY = "Contoso UK Ltd"

# Never offered as a target.
NEVER_TARGET = {"CRONUS UK Ltd."}

# An entity sharing less than this share of the master's account numbers is
# running a different chart (e.g. a local statutory one) and is unticked by
# default rather than silently given accounts that do not fit it.
SAME_CHART_THRESHOLD = 0.5

GL_SERVICE = "G_L_Account_Card_Excel"
DIM_SERVICE = "Default_Dimensions_Excel"
GL_TABLE_ID = 15

AUDIT_FILE = os.path.join("logging", "coa_changes.csv")

# ---------------------------------------------------------------------------
# the fields
# ---------------------------------------------------------------------------
# (field, label, group, kind, choices)
#   kind: text | bool | int | choice | code
#   choice = a Business Central option field: one of the listed values
#   code   = a code that must exist in the target entity (posting groups etc.)
# Order is the G/L Account Card's own order, which is also the order Business
# Central validates them in: Income/Balance before Account Category, Gen.
# Posting Type before the posting groups.
BLANK = " "  # how Business Central sends a blank option value

FIELDS = [
    ("No", "No.", "General", "text", None),
    ("Name", "Name", "General", "text", None),
    ("Income_Balance", "Income/Balance", "General", "choice",
     ["Income Statement", "Balance Sheet"]),
    ("Account_Category", "Account Category", "General", "choice",
     [BLANK, "Assets", "Liabilities", "Equity", "Income", "Cost of Goods Sold", "Expense"]),
    ("SubCategoryDescription", "Account Subcategory", "General", "subcategory", None),
    ("Debit_Credit", "Debit/Credit", "General", "choice", ["Both", "Debit", "Credit"]),
    ("Account_Type", "Account Type", "General", "choice",
     ["Posting", "Heading", "Total", "Begin-Total", "End-Total"]),
    ("Totaling", "Totaling (total accounts only)", "General", "text", None),
    ("No_of_Blank_Lines", "No. of Blank Lines", "General", "int", None),
    ("New_Page", "New Page", "General", "bool", None),
    ("Search_Name", "Search Name", "General", "text", None),
    ("Reconciliation_Account", "Reconciliation Account", "General", "bool", None),
    ("Automatic_Ext_Texts", "Automatic Ext. Texts", "General", "bool", None),
    ("Direct_Posting", "Direct Posting", "General", "bool", None),
    ("Blocked", "Blocked", "General", "bool", None),
    ("Omit_Default_Descr_in_Jnl", "Omit Default Descr. in Jnl.", "General", "bool", None),
    ("No_2", "No. 2", "General", "text", None),
    ("Review_Policy", "Review Policy", "General", "choice",
     ["None", "Allow Review", "Allow Review and Match Balance"]),
    ("FJHLocalNo", "Local No.", "Local chart", "text", None),
    ("FJHLocalName", "Local Name", "Local chart", "text", None),
    ("FJHShowAccount", "Show Account (local)", "Local chart", "bool", None),
    ("FJHIndentation", "Indentation (local)", "Local chart", "int", None),
    ("Gen_Posting_Type", "Gen. Posting Type", "Posting", "choice", [BLANK, "Purchase", "Sale"]),
    ("Gen_Bus_Posting_Group", "Gen. Bus. Posting Group", "Posting", "code", None),
    ("Gen_Prod_Posting_Group", "Gen. Prod. Posting Group", "Posting", "code", None),
    ("VAT_Bus_Posting_Group", "VAT Bus. Posting Group", "Posting", "code", None),
    ("VAT_Prod_Posting_Group", "VAT Prod. Posting Group", "Posting", "vatprod", None),
    ("Tax_Group_Code", "Tax Group Code", "Posting", "code", None),
    ("Default_IC_Partner_G_L_Acc_No", "Default IC Partner G/L Acc. No.", "Posting", "text", None),
    ("Wthldg_Tax_Bus_Post_Group", "Withholding Tax Bus. Posting Group", "Posting", "code", None),
    ("Wthldg_Tax_Prod_Post_Group", "Withholding Tax Prod. Posting Group", "Posting", "code", None),
    ("Default_Deferral_Template_Code", "Default Deferral Template", "Posting", "code", None),
    ("Source_Currency_Posting", "Source Currency Posting", "Currency", "text", None),
    ("Source_Currency_Code", "Source Currency Code", "Currency", "text", None),
    ("Source_Currency_Revaluation", "Source Currency Revaluation", "Currency", "bool", None),
    ("Unrealized_Revaluation", "Unrealized Revaluation", "Currency", "bool", None),
    ("Exchange_Rate_Adjustment", "Exchange Rate Adjustment", "Currency", "choice",
     ["No Adjustment", "Adjust Amount", "Adjust Additional-Currency Amount"]),
    ("Consol_Debit_Acc", "Consol. Debit Acc.", "Consolidation", "account", None),
    ("Consol_Credit_Acc", "Consol. Credit Acc.", "Consolidation", "account", None),
    ("Consol_Translation_Method", "Consol. Translation Method", "Consolidation", "choice",
     ["Average Rate (Manual)", "Closing Rate", "Historical Rate", "Composite Rate", "Equity Rate"]),
    ("Exclude_From_Consolidation", "Exclude From Consolidation", "Consolidation", "bool", None),
    ("RSMUKCurrency_Type_Code_PLANFUL", "Currency Type Code (Planful)", "Reporting", "text", None),
    ("RSMUKNormal_Data_PLANFUL", "Normal Data (Planful)", "Reporting", "text", None),
    ("Default_Sust_Account", "Default Sustainability Account", "Reporting", "text", None),
    ("Incl_in_Yooz_Exp_YZ_PWD", "Include in Yooz Export", "Reporting", "bool", None),
]
FIELD_NAMES = [f[0] for f in FIELDS]
FIELD_KIND = {f[0]: f[3] for f in FIELDS}
LABELS = {f[0]: f[1] for f in FIELDS}

# The Yooz flag is managed by the Yooz export itself after creation; sending
# it is fine, but it is not compared afterwards since Yooz can flip it.
NOT_VERIFIED = {"Incl_in_Yooz_Exp_YZ_PWD", "Search_Name"}

# Posting setup is entity specific: the Gen. Bus. Posting Group is the
# entity's own code (UKL in the UK, CLM in Colombia, CHI in China...) and the
# VAT Prod. Posting Group follows the country (STANDARD PURCHASE in one, NO VAT
# in another). So these are not copied from the master. When an account names
# a reference account in POSTING_FROM, each entity takes these five fields from
# its OWN copy of that reference account.
POSTING_FIELDS = ["Gen_Posting_Type", "Gen_Bus_Posting_Group", "Gen_Prod_Posting_Group",
                  "VAT_Bus_Posting_Group", "VAT_Prod_Posting_Group"]
POSTING_FROM = "Posting_From"

DIM_FIELDS = ["Dimension_Code", "Dimension_Value_Code", "Value_Posting"]
VALUE_POSTING = [BLANK, "Code Mandatory", "Same Code", "No Code"]


class CoaError(Exception):
    pass


# ---------------------------------------------------------------------------
# Business Central access
# ---------------------------------------------------------------------------

class BC:
    def __init__(self):
        self.s = requests.Session()
        self._auth()

    def _auth(self):
        self.s.headers.update({"Authorization": f"Bearer {token_2.get_access_token()}"})

    def _req(self, method, url, **kw):
        for attempt in range(4):
            try:
                r = self.s.request(method, url, timeout=120, **kw)
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError):
                if attempt == 3:
                    raise
                continue
            if r.status_code == 401 and attempt == 0:
                self._auth()
                continue
            return r
        return r

    def companies(self):
        r = self._req("GET", API_COMPANIES)
        r.raise_for_status()
        return [c["name"] for c in r.json()["value"] if c["name"] not in NEVER_TARGET]

    @staticmethod
    def _co(company):
        return ODATA + "Company('" + urllib.parse.quote(company) + "')/"

    def get_all(self, company, service, params=None):
        url, rows = self._co(company) + service, []
        while url:
            r = self._req("GET", url, params=params)
            params = None
            if not r.ok:
                raise CoaError(f"{company}: reading {service} failed "
                               f"(HTTP {r.status_code}) {r.text[:300]}")
            body = r.json()
            rows += body.get("value", [])
            url = body.get("@odata.nextLink")
        return rows

    def get_account(self, company, no):
        url = self._co(company) + f"{GL_SERVICE}('{urllib.parse.quote(no)}')"
        r = self._req("GET", url)
        return r.json() if r.ok else None

    def post(self, company, service, body):
        r = self._req("POST", self._co(company) + service, json=body,
                      headers={"Content-Type": "application/json"})
        return r.ok, r.status_code, (r.json() if r.ok else _bc_error(r))


def _bc_error(r):
    try:
        return r.json()["error"]["message"]
    except Exception:                                   # noqa: BLE001
        return r.text[:500]


# ---------------------------------------------------------------------------
# values
# ---------------------------------------------------------------------------

def norm(field, value):
    """Comparable form: BC's single-space blank option becomes '', etc."""
    kind = FIELD_KIND.get(field, "text")
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1", "y")
        return bool(value)
    if kind == "int":
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0
    return "" if value is None else str(value).strip()


def clean_account(raw: dict) -> dict:
    """An account as the tool works with it: the writable fields, normalised,
    plus the optional reference account for the entity-specific posting setup."""
    out = {f: norm(f, raw.get(f)) for f in FIELD_NAMES}
    out[POSTING_FROM] = norm(POSTING_FROM, raw.get(POSTING_FROM))
    return out


def payload(account: dict, omit=()) -> dict:
    """What is POSTed: blanks and defaults left out so Business Central fills them."""
    out = {}
    for f in FIELD_NAMES:
        if f in omit:
            continue
        v = account.get(f)
        kind = FIELD_KIND[f]
        if kind == "bool":
            if v:
                out[f] = True
        elif kind == "int":
            if v:
                out[f] = int(v)
        elif v not in ("", None):
            out[f] = v
    return out


# ---------------------------------------------------------------------------
# reading an entity
# ---------------------------------------------------------------------------

def read_entity(bc: BC, company: str) -> dict:
    """Everything the planner needs from one entity."""
    chart = {a["No"]: a for a in bc.get_all(company, GL_SERVICE)}
    dims = [d for d in bc.get_all(company, DIM_SERVICE, {"$filter": f"Table_ID eq {GL_TABLE_ID}"})
            if (d.get("Dimension_Code") or "").strip()]
    dim_values = {}
    for v in bc.get_all(company, "Dimension_Values_Excel",
                        {"$select": "Dimension_Code,Code,Blocked"}):
        dim_values.setdefault(v["Dimension_Code"], set()).add(v["Code"])
    subcats = {(c.get("Description") or "").strip()
               for c in bc.get_all(company, "G_L_Account_Categories_Excel")}
    subcats.discard("")
    vat_prod = {g["Code"] for g in bc.get_all(company, "VAT_Product_Posting_Groups_Excel")}
    used = {f: {norm(f, a.get(f)) for a in chart.values()} - {""}
            for f in FIELD_NAMES if FIELD_KIND[f] == "code"}
    return {"chart": chart, "dims": dims, "dim_values": dim_values,
            "subcats": subcats, "vat_prod": vat_prod, "codes_used": used}


def master_template(entity: dict, no: str):
    """(account, default dimensions) of an existing account, ready to edit."""
    raw = entity["chart"].get(no)
    if raw is None:
        return None, []
    dims = [{k: d.get(k, "") for k in DIM_FIELDS}
            for d in entity["dims"] if d["No"] == no]
    return clean_account(raw), dims


def suggest_posting_reference(master: dict, entities: dict, no: str):
    """
    An account to take the posting groups from when `no` itself is missing in
    some of `entities` (typically a new account created in the UK first).

    It must be a posting account present in every one of `entities`, with the
    same posting setup in the master as `no`, and a full posting setup in each
    entity. The nearest account number wins. None when nothing qualifies.
    """
    src = master["chart"].get(no)
    if src is None:
        return None
    want = tuple(norm(f, src.get(f)) for f in POSTING_FIELDS)
    best = None
    for cand, acc in master["chart"].items():
        if cand == no or norm("Account_Type", acc.get("Account_Type")) != "Posting" or acc.get("Blocked"):
            continue
        if tuple(norm(f, acc.get(f)) for f in POSTING_FIELDS) != want:
            continue
        if not all(cand in e["chart"] for e in entities.values()):
            continue
        if want[0] and not all(norm("Gen_Posting_Type", e["chart"][cand].get("Gen_Posting_Type"))
                               for e in entities.values()):
            continue
        dist = (abs(int(cand) - int(no)) if cand.isdigit() and no.isdigit() else 10 ** 9, cand)
        if best is None or dist < best[0]:
            best = (dist, cand)
    return best[1] if best else None


def same_chart_share(entity: dict, master: dict) -> float:
    m = set(master["chart"])
    return len(m & set(entity["chart"])) / len(m) if m else 0.0


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def validate_account(acc: dict) -> list:
    """Problems with the account itself, before any entity is looked at."""
    errs = []
    if not acc.get("No"):
        errs.append("No. is required.")
    if not acc.get("Name"):
        errs.append("Name is required.")
    for f, _, _, kind, choices in FIELDS:
        if kind == "choice" and acc.get(f) not in ("", None):
            if norm(f, acc[f]) not in {norm(f, c) for c in choices}:
                errs.append(f"{LABELS[f]} '{acc[f]}' is not one of {choices}.")
    if acc.get("Account_Type") in ("Total", "End-Total") and not acc.get("Totaling"):
        errs.append("A Total / End-Total account needs Totaling (e.g. 100000..199999).")
    if acc.get("Account_Type") == "Posting" and acc.get("Totaling"):
        errs.append("Totaling only applies to total accounts; clear it for a Posting account.")
    return errs


def plan_accounts(accounts: list, dims_by_no: dict, entities: dict) -> list:
    """
    accounts:    [account dict]
    dims_by_no:  {No: [ {Dimension_Code, Dimension_Value_Code, Value_Posting} ]}
    entities:    {company: read_entity(...)}

    Returns one row per (company, account):
        action  create | exists | error
        errors  reasons it cannot be created there
        warnings  created anyway, but worth knowing (field omitted, etc.)
        diffs   for an existing account, fields that differ from the request
        omit    fields left out of the POST for this entity
    """
    rows = []
    for acc in accounts:
        no = acc["No"]
        dims = [d for d in dims_by_no.get(no, []) if (d.get("Dimension_Code") or "").strip()]
        own = validate_account(acc)
        for company, ent in entities.items():
            # This entity's version of the account: the posting setup comes
            # from its own copy of the reference account, when one is named.
            eff = dict(acc)
            ref_no = acc.get(POSTING_FROM)
            ref_missing = False
            if ref_no:
                ref = ent["chart"].get(ref_no)
                if ref is None:
                    ref_missing = True
                else:
                    ref_clean = clean_account(ref)
                    for f in POSTING_FIELDS:
                        eff[f] = ref_clean[f]
            row = {"company": company, "No": no, "Name": acc.get("Name", ""),
                   "action": "create", "errors": list(own), "warnings": [],
                   "diffs": [], "omit": [], "account": eff, "dims": dims,
                   "posting": " / ".join(eff[f] or "-" for f in POSTING_FIELDS)}
            if ref_missing:
                row["errors"].append(f"Reference account {ref_no} (for the posting setup) does not "
                                     "exist in this entity.")
            acc_here = eff
            existing = ent["chart"].get(no)
            if existing is not None:
                row["action"] = "exists"
                have = clean_account(existing)
                row["diffs"] = [f"{LABELS[f]}: has '{have[f]}', asked '{acc_here.get(f)}'"
                                for f in FIELD_NAMES
                                if f not in NOT_VERIFIED and norm(f, acc_here.get(f)) != have[f]]
                rows.append(row)
                continue

            # codes that must exist in this entity
            if acc_here.get("VAT_Prod_Posting_Group") and acc_here["VAT_Prod_Posting_Group"] not in ent["vat_prod"]:
                row["errors"].append(f"VAT Prod. Posting Group '{acc_here['VAT_Prod_Posting_Group']}' "
                                     "does not exist in this entity.")
            for f in FIELD_NAMES:
                if FIELD_KIND[f] == "code" and acc_here.get(f) and acc_here[f] not in ent["codes_used"].get(f, set()):
                    row["warnings"].append(f"{LABELS[f]} '{acc_here[f]}' is not used on any account here; "
                                           "Business Central will reject it if it does not exist.")
                if FIELD_KIND[f] == "account" and acc_here.get(f) and acc_here[f] not in ent["chart"]:
                    row["warnings"].append(f"{LABELS[f]} '{acc_here[f]}' is not an account in this entity.")
            sub = acc_here.get("SubCategoryDescription")
            if sub and sub not in ent["subcats"]:
                row["omit"].append("SubCategoryDescription")
                row["warnings"].append(f"Subcategory '{sub}' is not set up in this entity, so the "
                                       "account is created without one.")
            for d in dims:
                code, value = d["Dimension_Code"], (d.get("Dimension_Value_Code") or "").strip()
                if code not in ent["dim_values"]:
                    row["errors"].append(f"Dimension '{code}' does not exist in this entity.")
                elif value and value not in ent["dim_values"][code]:
                    row["errors"].append(f"Dimension value {code} '{value}' does not exist in this entity.")
            if row["errors"]:
                row["action"] = "error"
            rows.append(row)
    return rows


def summarise(plan: list) -> dict:
    out = {"create": 0, "exists": 0, "error": 0}
    for r in plan:
        out[r["action"]] += 1
    return out


# ---------------------------------------------------------------------------
# apply + verify
# ---------------------------------------------------------------------------

def apply_plan(bc: BC, plan: list, progress=None) -> list:
    """Create every 'create' row, then read it back. Returns one result per row."""
    todo = [r for r in plan if r["action"] == "create"]
    results = []
    for i, row in enumerate(todo, start=1):
        company, no, acc = row["company"], row["No"], row["account"]
        if progress:
            progress(i, len(todo), f"{company} — {no} {acc.get('Name', '')}")
        res = {"company": company, "No": no, "Name": acc.get("Name", ""),
               "account": "", "dimensions": "", "verified": "", "detail": ""}

        # Re-checked at the last moment: someone may have added it since the
        # dry run, and an existing account is never touched.
        if bc.get_account(company, no) is not None:
            res.update(account="skipped", detail="already exists (created since the dry run)")
            results.append(res)
            continue

        ok, status, body = bc.post(company, GL_SERVICE, payload(acc, row["omit"]))
        if not ok:
            res.update(account="FAILED", detail=f"HTTP {status}: {body}")
            results.append(res)
            continue
        res["account"] = "created"

        dim_fail = []
        for d in row["dims"]:
            body = {"Table_ID": GL_TABLE_ID, "No": no, "Dimension_Code": d["Dimension_Code"]}
            if (d.get("Dimension_Value_Code") or "").strip():
                body["Dimension_Value_Code"] = d["Dimension_Value_Code"].strip()
            if (d.get("Value_Posting") or "").strip():
                body["Value_Posting"] = d["Value_Posting"]
            ok, status, err = bc.post(company, DIM_SERVICE, body)
            if not ok:
                dim_fail.append(f"{d['Dimension_Code']}: {err}")
        res["dimensions"] = ("none" if not row["dims"] else
                             "FAILED" if dim_fail else f"{len(row['dims'])} created")

        diffs = verify(bc, company, no, acc, row["dims"], row["omit"])
        res["verified"] = "OK" if not diffs else "DIFFERS"
        res["detail"] = "; ".join(dim_fail + diffs)
        results.append(res)
    _audit(results)
    return results


def verify(bc: BC, company, no, acc, dims, omit) -> list:
    got = bc.get_account(company, no)
    if got is None:
        return ["account not found when read back"]
    have = clean_account(got)
    diffs = [f"{LABELS[f]}: is '{have[f]}', expected '{norm(f, acc.get(f))}'"
             for f in FIELD_NAMES
             if f not in NOT_VERIFIED and f not in omit and norm(f, acc.get(f)) != have[f]]
    if dims:
        live = {d["Dimension_Code"]: d for d in bc.get_all(
            company, DIM_SERVICE,
            {"$filter": f"Table_ID eq {GL_TABLE_ID} and No eq '{no}'"})}
        for d in dims:
            g = live.get(d["Dimension_Code"])
            if g is None:
                diffs.append(f"default dimension {d['Dimension_Code']} missing")
                continue
            for k in ("Dimension_Value_Code", "Value_Posting"):
                if (g.get(k) or "").strip() != (d.get(k) or "").strip():
                    diffs.append(f"default dimension {d['Dimension_Code']} {k}: is "
                                 f"'{(g.get(k) or '').strip()}', expected '{(d.get(k) or '').strip()}'")
    return diffs


# ---------------------------------------------------------------------------
# Excel: several accounts at once
# ---------------------------------------------------------------------------

ACCOUNTS_SHEET = "Accounts"
DIMS_SHEET = "Default Dimensions"


def template_workbook(examples: list, example_dims: list) -> bytes:
    """An upload template: one column per card field, examples prefilled."""
    import io

    import pandas as pd

    buf = io.BytesIO()
    cols = FIELD_NAMES[:2] + [POSTING_FROM] + FIELD_NAMES[2:]
    acc = pd.DataFrame([{f: a.get(f, "") for f in cols} for a in examples], columns=cols)
    dims = pd.DataFrame(example_dims, columns=["No"] + DIM_FIELDS)
    notes = pd.DataFrame({"Read me": [
        "One row per new G/L account on the Accounts sheet. Column names must not change.",
        "No. and Name are required. Leave any other cell blank to take Business Central's default.",
        f"{POSTING_FROM}: an existing account No. Each entity then takes the posting groups "
        f"({', '.join(POSTING_FIELDS)}) from its OWN copy of that account, because they differ "
        "by entity (UKL in the UK, CLM in Colombia...). Leave it blank to use the posting "
        "group columns as typed, in every entity.",
        "Choice columns accept exactly the values Business Central shows, e.g. "
        "Income_Balance = 'Income Statement' or 'Balance Sheet'.",
        "TRUE/FALSE columns accept TRUE, FALSE, Yes, No, 1, 0.",
        "Default Dimensions: one row per dimension rule, keyed on the account No.; "
        f"Value_Posting is one of {VALUE_POSTING[1:]} or blank.",
        "Upload the file on the page, run the dry run, review it, then approve.",
        "An account that already exists in an entity is never changed.",
    ]})
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        acc.to_excel(xw, sheet_name=ACCOUNTS_SHEET, index=False)
        dims.to_excel(xw, sheet_name=DIMS_SHEET, index=False)
        notes.to_excel(xw, sheet_name="Read me", index=False)
        for name, frame in ((ACCOUNTS_SHEET, acc), (DIMS_SHEET, dims)):
            ws = xw.sheets[name]
            ws.freeze_panes(1, 0)
            for i, col in enumerate(frame.columns):
                ws.set_column(i, i, max(12, min(len(col) + 4, 34)))
        xw.sheets["Read me"].set_column(0, 0, 120)
    return buf.getvalue()


def read_workbook(file) -> tuple:
    """(accounts, dims_by_no, problems) from an uploaded template."""
    import pandas as pd

    # keep_default_na=False: otherwise a cell reading "None" (a real Review
    # Policy value) comes back as blank.
    book = pd.read_excel(file, sheet_name=None, dtype=object, keep_default_na=False, na_values=[""])
    acc_sheet = next((f for f in book.values() if {"No", "Name"}.issubset(f.columns)
                      and "Dimension_Code" not in f.columns), None)
    if acc_sheet is None:
        return [], {}, ["No sheet has the 'No' and 'Name' columns. Use the downloaded template."]
    problems = []
    unknown = [c for c in acc_sheet.columns if c not in FIELD_NAMES + [POSTING_FROM]]
    if unknown:
        problems.append(f"Ignored columns that are not G/L Account Card fields: {unknown}")
    accounts = []
    for _, r in acc_sheet.dropna(how="all").iterrows():
        raw = {f: ("" if pd.isna(r.get(f)) else r.get(f)) for f in FIELD_NAMES + [POSTING_FROM]}
        for k in ("No", POSTING_FROM):
            if isinstance(raw[k], float) and raw[k].is_integer():
                raw[k] = int(raw[k])
        accounts.append(clean_account(raw))
    seen = [a["No"] for a in accounts]
    dupes = sorted({n for n in seen if seen.count(n) > 1})
    if dupes:
        problems.append(f"Account No. appears more than once: {dupes}")

    dims_by_no = {}
    dim_sheet = next((f for f in book.values() if {"No", "Dimension_Code"}.issubset(f.columns)), None)
    if dim_sheet is not None:
        for _, r in dim_sheet.dropna(how="all").iterrows():
            no = r.get("No")
            if isinstance(no, float) and no.is_integer():
                no = int(no)
            no = "" if pd.isna(no) else str(no).strip()
            if not no or pd.isna(r.get("Dimension_Code")):
                continue
            dims_by_no.setdefault(no, []).append({
                k: ("" if pd.isna(r.get(k)) else str(r.get(k)).strip()) for k in DIM_FIELDS})
        stray = sorted(set(dims_by_no) - set(seen))
        if stray:
            problems.append(f"Default dimensions for accounts not on the Accounts sheet: {stray}")
    return accounts, dims_by_no, problems


def _audit(results):
    """Every write is appended to logging\\coa_changes.csv: who, when, what, outcome."""
    if not results:
        return
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    new = not os.path.exists(AUDIT_FILE)
    with open(AUDIT_FILE, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "user", "environment", "company", "No", "Name",
                        "account", "dimensions", "verified", "detail"])
        user = os.environ.get("USERNAME", "")
        for r in results:
            w.writerow([datetime.now().isoformat(timespec="seconds"), user, ENVIRONMENT, r["company"],
                        r["No"], r["Name"], r["account"], r["dimensions"],
                        r["verified"], r["detail"]])
    logging.info(f"[COA] {len(results)} result(s) written to {AUDIT_FILE}")
