"""
Builds the VAT return and recon packs from a Business Central extract.

Before this, vatRecon.py classified the rows itself and vatWorkbook.py built a
PivotTable workbook through Excel COM. That gave different answers from the
the central VAT automation:

  - the account map here (VAT Recon\\vat_expected_accounts.csv) was a
    truncated 100-row export, every row "NO", so VAT Risk could never fire;
  - "YES" was compared case sensitively, so six "Yes" accounts went unchecked;
  - anything typed into Comment was lost on the next run;
  - Source_No_PLANFUL was requested and then dropped by the template;
  - accounts missing from the map, and the four off-by-one boundary accounts,
    were never reported.

The central VAT automation fixed all of those. Its engine is copied into this folder so the
tool is self-contained:

  vat_core.py      classification and the checks (copied unchanged)
  vat_workbook.py  the xlsxwriter pack writer   (copied unchanged)
  VAT Recon\\VAT Account Map.xlsx   413 accounts + Form Type Rules (copied)
  VAT Recon\\VAT Comments.xlsx      written by save_comments(), read by
                                    build_packs()

build_packs() is the central VAT automation's vat_build.build() and save_comments() is its
vat_comments.collect(), starting from a DataFrame and this tool's folders
rather than the central VAT automation's. Tested cell for cell against the central VAT automation's Japan packs
for 2025-09 and 2026-08: no differences. If vat_core.py or vat_workbook.py is
updated in the central VAT automation, copy the new version here to keep the two the same.
"""

import re
from pathlib import Path

import pandas as pd

import vat_core as core
import vat_workbook as wb

PROJECT_DIR = Path(__file__).resolve().parent

# <library>\Finance Systems\Automations\bc-query-tool\vatPacks.py, so the
# library root is three levels up. See vatWorkbook._library_root for why no
# absolute path or OneDrive variable is used.
LIBRARY_ROOT = PROJECT_DIR.parents[2]

OUTPUT_ROOT = (LIBRARY_ROOT / "Group Finance"
               / "Shared Reference Documents"
               / "VAT Recon Report Files")

MAP_FILE = PROJECT_DIR / "VAT Recon" / "VAT Account Map.xlsx"
COMMENT_FILE = PROJECT_DIR / "VAT Recon" / "VAT Comments.xlsx"

# A sandbox run must never overwrite the published packs or mix test
# comments into the real ones, so it publishes to a local folder in the
# Query tool instead, with its own comments file. See config/bc_env.py.
import os as _os
_ENV = _os.environ.get("BC_ENVIRONMENT_NAME", "").strip()
SANDBOX = bool(_ENV) and _ENV.lower() != "production"
if SANDBOX:
    OUTPUT_ROOT = PROJECT_DIR / "Sandbox Output" / _ENV / "VAT Recon Report Files"
    COMMENT_FILE = PROJECT_DIR / "Sandbox Output" / _ENV / "VAT Comments.xlsx"

COMMENT_SHEET = "Comments"
COMMENT_COLUMNS = core.COMMENT_KEY + ["Comment"]


def safe_folder(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", str(text)).strip().rstrip(".")
    return cleaned[:80] or "Unknown Entity"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def read_comments(path: Path = COMMENT_FILE, log=print) -> pd.DataFrame:
    empty = pd.DataFrame(columns=COMMENT_COLUMNS)
    if not path.exists():
        log("  no comment file yet, nothing to carry forward")
        return empty
    try:
        book = pd.read_excel(path, sheet_name=None, dtype=object)
    except Exception as exc:                        # noqa: BLE001
        log(f"  WARNING: {path.name} could not be opened ({exc}). "
            "Carrying no comments forward.")
        return empty
    # Found by its columns, not its sheet name, which a person can rename.
    for _, frame in book.items():
        if set(COMMENT_COLUMNS).issubset(set(frame.columns)):
            live = frame[frame["Comment"].astype(str).str.strip() != ""]
            log(f"  {path.name}: {len(live):,} comment(s) carried forward")
            return frame
    log(f"  WARNING: {path.name} has no sheet with {COMMENT_COLUMNS}. "
        "Carrying no comments forward.")
    return empty


def build_packs(raw: pd.DataFrame, output_root=OUTPUT_ROOT,
                ytd_label: str = None, log=print) -> list:
    """
    Classify a raw extract and write one pack per entity per month, plus one
    whole-period pack per entity when ytd_label is given.

    Returns the list of paths written.
    """
    output_root = Path(output_root)

    if not MAP_FILE.exists():
        raise core.VatInputError(
            f"{MAP_FILE} is missing. It holds the 413 account rows and the form "
            "type rules, and nothing can be classified without it.")
    log(f"Account map:  {MAP_FILE}")
    account_map, rules = core.read_account_map(MAP_FILE)
    log(f"  {len(account_map):,} accounts, {len(rules)} form type rule(s)")

    if "Company" not in raw.columns:
        raise core.VatInputError(
            "The extract has no Company column, so it cannot be split by entity.")
    before = len(raw)
    if "Entry_No" in raw.columns:
        raw = raw.drop_duplicates(subset=["Company", "Entry_No"], keep="last")
    raw = raw.reset_index(drop=True)
    log(f"  {before:,} rows extracted, {before - len(raw):,} duplicate ledger "
        f"entries dropped, {len(raw):,} to classify")

    log(f"Comments:     {COMMENT_FILE}")
    comments = read_comments(COMMENT_FILE, log)

    classified = core.classify(raw, account_map, rules)
    classified = core.merge_comments(classified, comments)

    unparsed = int(classified["Posting_Date"].isna().sum())
    if unparsed:
        log(f"  WARNING: {unparsed:,} row(s) have a posting date that will not "
            "parse. They belong to no month and will not reach a pack.")
        classified = classified[classified["Posting_Date"].notna()]

    for col, count in core.blank_like_counts(raw).items():
        if count:
            log(f"  NOTE: {count:,} row(s) carry a whitespace-only {col}, "
                "treated as blank. Power BI treated it as a real value, so "
                "those rows are where this differs from the old model.")

    if classified.empty:
        log("No rows to publish.")
        return []

    unmapped = core.unmapped_accounts(classified, account_map)
    boundary = core.boundary_exposure(classified)
    case_only = core.case_only_yes(classified)

    # (entity, period label, rows, summary_only, is the whole-period file)
    tasks = [(entity, period, part, False, False) for (entity, period), part
             in classified.groupby(["Entity", "Period"], sort=True)]
    if ytd_label:
        # A complete pack for the whole period, unless the entity is large
        # enough that the workbook would be unopenable.
        for entity, part in classified.groupby("Entity", sort=True):
            summary_only = len(part) > wb.YTD_FULL_MAX_ROWS
            if summary_only:
                log(f"  NOTE: {entity} has {len(part):,} rows in {ytd_label}, "
                    f"over the {wb.YTD_FULL_MAX_ROWS:,} row limit, so its "
                    "year-to-date file is summary only. The monthly files "
                    "carry the transactions.")
            tasks.append((entity, ytd_label, part, summary_only, True))

    log("")
    log(f"Writing {len(tasks)} workbook(s) to {output_root}")
    written = []
    for entity, period, part, summary_only, is_whole_period in tasks:
        folder = output_root / safe_folder(entity)
        short = safe_folder(wb.short_entity_name(entity))
        if is_whole_period:
            months = sorted(m for m in part["Period"].dropna().unique())
            span = (f" ({wb.period_label(months[0])} to "
                    f"{wb.period_label(months[-1])})" if months else "")
            stem = f"{short}-VAT-Recon-{safe_folder(period)}-YTD"
            header = (f"{period}{span}" if not summary_only
                      else f"{period} year to date{span}, summary only")
        else:
            stem = f"{short}-VAT-Recon-{period}"
            header = wb.period_label(period)

        checks = {
            "Control totals": core.control_totals(part),
            "Accounts in the ledger with no row in the account map":
                core.unmapped_accounts(part, account_map),
            "Off-by-one accounts inherited from the Power BI rules":
                core.boundary_exposure(part),
            "Accounts checked only because YES is now matched case insensitively":
                core.case_only_yes(part),
        }
        target = folder / f"{stem}.xlsx"
        wb.write_workbook(target, part, entity, header, checks, summary_only)
        written.append(target)
        flagged = int((part["VAT Risk"] == core.COMMENT_REQUIRED).sum())
        log(f"  {entity:<32} {period:<10} {len(part):>8,} rows  "
            f"{flagged:>5,} to comment  ->  {target.name}")

    log("")
    if not unmapped.empty:
        log(f"WARNING: {len(unmapped)} account(s) in the ledger have no row in "
            "the account map, so Vat Expected is blank for them and nothing is "
            "checked. See each pack's Checks sheet.")
    if not boundary.empty:
        log(f"WARNING: {len(boundary)} off-by-one account(s) in this data, "
            f"net {boundary['Amount'].sum():,.2f}. Reproduced exactly as the "
            "Power BI rules had them. To include them, edit the Form Type Rules "
            "sheet of the account map.")
    if not case_only.empty:
        log(f"NOTE: {len(case_only)} account(s) are checked because YES is "
            "matched case insensitively.")
    return written


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------

def _risk_rows(path: Path, log) -> pd.DataFrame:
    """The Risk sheet of one pack, found by its columns not its name."""
    try:
        book = pd.read_excel(path, sheet_name=None, dtype=object, header=2)
    except Exception as exc:                        # noqa: BLE001
        log(f"  {path.name} could not be opened ({exc}). Skipped - close it "
            "in Excel and run again.")
        return pd.DataFrame()
    for name, frame in book.items():
        if set(COMMENT_COLUMNS).issubset(set(frame.columns)):
            rows = frame[COMMENT_COLUMNS].copy()
            rows = rows[rows["Comment"].notna()
                        & rows["Comment"].astype(str).str.strip().ne("")]
            rows = rows[rows["Comment"].astype(str).str.lower() != "nan"]
            if len(rows):
                log(f"  {path.name}: {len(rows)} comment(s) on sheet '{name}'")
            return rows
    return pd.DataFrame()


def save_comments(output_root=OUTPUT_ROOT, entity: str = None, log=print) -> int:
    """
    Harvest the Comment column from every pack's Risk sheet under output_root
    into VAT Comments.xlsx, so the next build puts them back.

    One-way merge: a comment already on file is replaced only by a non-empty
    new one. Clearing a cell in a pack does NOT delete the comment; to delete
    one, clear its row in VAT Comments.xlsx itself. A workbook reopened and
    re-saved empty must not wipe someone's work.

    Returns 0 on success, 2 when there are no packs to read.
    """
    output_root = Path(output_root)
    if not output_root.exists():
        folders = []
    elif entity:
        folders = [p for p in output_root.iterdir()
                   if p.is_dir() and p.name.lower() == safe_folder(entity).lower()]
    else:
        folders = sorted(p for p in output_root.iterdir() if p.is_dir())
    if not folders:
        log(f"No entity folder found under {output_root}. Build the packs first.")
        return 2

    found = []
    for folder in folders:
        log(f"Reading {folder}")
        for path in sorted(folder.rglob("*VAT-Recon-*.xlsx")):
            if path.name.startswith("~$"):
                continue
            rows = _risk_rows(path, log)
            if not rows.empty:
                found.append(rows)

    if not found:
        log("No comments typed into any pack. Nothing to save.")
        return 0

    new = pd.concat(found, ignore_index=True)
    for col in core.COMMENT_KEY:
        new[col] = new[col].astype(str).str.strip()
    new["Comment"] = new["Comment"].astype(str).str.strip()
    new = new.drop_duplicates(subset=core.COMMENT_KEY, keep="last")

    existing = pd.DataFrame(columns=COMMENT_COLUMNS)
    if COMMENT_FILE.exists():
        book = pd.read_excel(COMMENT_FILE, sheet_name=None, dtype=object)
        for _, frame in book.items():
            if set(COMMENT_COLUMNS).issubset(set(frame.columns)):
                existing = frame[COMMENT_COLUMNS].copy()
                break
        for col in core.COMMENT_KEY:
            existing[col] = existing[col].astype(str).str.strip()

    before = len(existing)
    merged = (pd.concat([existing, new], ignore_index=True)
              .drop_duplicates(subset=core.COMMENT_KEY, keep="last")
              .sort_values(core.COMMENT_KEY))

    COMMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(COMMENT_FILE, engine="xlsxwriter") as writer:
        merged.to_excel(writer, sheet_name=COMMENT_SHEET, index=False)
        sheet = writer.sheets[COMMENT_SHEET]
        head = writer.book.add_format({"font_name": "Arial", "font_size": 10,
                                       "bold": True, "bg_color": "#1F3864",
                                       "font_color": "white", "border": 1})
        body = writer.book.add_format({"font_name": "Arial", "font_size": 10})
        wide = writer.book.add_format({"font_name": "Arial", "font_size": 10,
                                       "bg_color": "#FFF2CC", "border": 1})
        sheet.set_column(0, 0, 30, body)
        sheet.set_column(1, 1, 14, body)
        sheet.set_column(2, 2, 70, wide)
        for i, col in enumerate(merged.columns):
            sheet.write(0, i, col, head)
        sheet.freeze_panes(1, 0)

    log("")
    log(f"{len(merged)} comment(s) on file, up from {before}.")
    log(f"Saved: {COMMENT_FILE}")
    log("They come back automatically on the next build.")
    return 0
