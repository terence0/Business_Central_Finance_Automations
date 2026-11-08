"""
Builds the accountant-ready VAT Return & Recon workbook.

The extract coming out of Business Central is raw transaction data. What the
accountants actually work with is the shaped view they used to get by
exporting from Power BI: a summary matrix (VAT Per Return > VAT Per BC >
VAT Tag per Return > account) with subtotals, VAT%, a VAT Risk flag and a
blank Comment column to fill in.

Rather than pre-splitting a file per entity, the workbook carries a live
PivotTable with Entity/Period slicers so each accountant filters in place.

Layout is template-driven. 'VAT Recon Template.xlsx' holds the pivot, the
slicers and all the formatting; a run copies the template, swaps in fresh
rows and refreshes. That means layout changes made to the template survive
every future run - the automation only ever replaces data, never design.
The template is regenerated automatically if it is missing or if the column
set of the extract has changed (otherwise the data would not line up).

Slicers can only be created through Excel itself - neither xlsxwriter nor
openpyxl can write them, and openpyxl silently drops them on round-trip -
so the pivot layer is built and refreshed via COM against installed Excel.
"""

import calendar
import datetime
import math
import os
import shutil
import tempfile

import numpy as np
import pandas as pd

# Excel's 1900 date system counts days from this point.
EXCEL_EPOCH = pd.Timestamp("1899-12-30")
DATE_NUMBER_FORMAT = "yyyy-mm-dd"

# Hard limit on rows in a worksheet, header included.
EXCEL_MAX_ROWS = 1_048_576

# Excel COM enums (avoids depending on the makepy-generated constants module).
XL_SRC_RANGE = 1
XL_DATABASE = 1
XL_ROW_FIELD = 1
XL_SUM = -4157
XL_TABULAR_ROW = 1
XL_YES = 1
XL_CALC_MANUAL = -4135
XL_CALC_AUTOMATIC = -4105

SUMMARY_SHEET = "VAT Return Summary"
DASHBOARD_SHEET = "Dashboard"
DATA_SHEET = "Data"
TABLE_NAME = "VATData"

# Dashboard geometry.
DASH_KPI_LABEL_ROW = 5
DASH_KPI_VALUE_ROW = 6
DASH_KPI_COLS = (1, 3, 5, 7, 9)   # A, C, E, G, I
DASH_PIVOT_ROW = 9

XL_PASTE_VALUES = -4163
XL_DECIMAL_SEPARATOR = 3
XL_THOUSANDS_SEPARATOR = 4
TEMPLATE_PATH = os.path.join("VAT Recon", "VAT Recon Template.xlsx")

# Header block above the pivot. Each published file names its own entity and
# period here, which is what the slicers used to convey - now unnecessary,
# since a file only ever holds one entity for one month.
HEADER_ENTITY_CELL = "A1"
HEADER_TITLE_CELL = "A2"
HEADER_PERIOD_CELL = "A3"
# Header occupies rows 1-3; row 4 separates it from the pivot. (This used to
# be row 8, to clear the slicers that sat above the pivot.)
PIVOT_TOP_ROW = 5

# Subtotal and grand-total rows are set apart from the detail lines.
TOTAL_ROW_FONT_SIZE = 12
BODY_FONT_SIZE = 11

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Path within the Global Finance library, relative to its root.
OUTPUT_SUBPATH = os.path.join(
    "Group Finance",
    "Shared Reference Documents",
    "VAT Recon Report Files",
)
LIBRARY_MARKER = "Group Finance"


def _library_root() -> str:
    """
    The Global Finance library root, derived from this file's own location.

    No absolute path can be hardcoded here, because colleagues' synced paths
    differ in two ways: the OneDrive root may or may not carry a "(1)" suffix
    (people with two accounts get one), and the library folder is named
    "Documents - Finance" for some and "Finance - Documents"
    for others, depending on how SharePoint set the sync up.

    What is stable is this file's position inside the library:
        <library>\\Finance Systems\\Automations\\Query tool\\vatWorkbook.py
    so the root is three directories up.

    The OneDrive / OneDriveCommercial environment variables are deliberately
    not used: on the author's own PC they point at a different OneDrive root
    from the one actually holding the library.
    """
    return os.path.abspath(os.path.join(PROJECT_DIR, "..", "..", ".."))


# Where the per-entity recon files are published. One subfolder per entity,
# one file per month inside it, overwritten on re-run.
OUTPUT_ROOT = os.path.join(_library_root(), OUTPUT_SUBPATH)

# Rows written per COM call. One call per cell would be unusably slow; one
# call for the whole sheet risks a very large variant array.
CHUNK_ROWS = 20000

PREFERRED_ORDER = [
    "Entity", "Period", "Posting_Date",
    "VAT Per Return", "VAT Per BC", "VAT Tag per Return",
    "G_L_Account_No", "G_L_Account_Name", "Source_No_PLANFUL",
    "Document_Type", "Document_No", "Description",
    "Amount", "VAT_Amount", "VAT%",
    "Vat Required", "VAT Risk", "Comment",
]


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renames the classification columns to the accountants' terminology,
    derives VAT% and Period, and adds the blank Comment column.

    The renames match the Power BI export headers ('Vat Type Form' was
    surfaced to them as 'VAT Per Return', and so on) so the workbook reads
    the same as what they already use.
    """
    df = df.copy()

    df = df.rename(columns={
        "Vat Type Form": "VAT Per Return",
        "VAT Type Return": "VAT Per BC",
        "VAT Tag Return": "VAT Tag per Return",
        "Company": "Entity",
    })

    df = df.drop(columns=[c for c in ["@odata.etag"] if c in df.columns])

    amount = pd.to_numeric(df.get("Amount"), errors="coerce")
    vat_amount = pd.to_numeric(df.get("VAT_Amount"), errors="coerce")
    df["Amount"] = amount
    df["VAT_Amount"] = vat_amount
    # Left blank rather than 0 where Amount is 0, so a zero-value line doesn't
    # read as a genuine 0% VAT rate.
    df["VAT%"] = (vat_amount / amount).where(amount.notna() & (amount != 0))

    posting = pd.to_datetime(df.get("Posting_Date"), errors="coerce")
    df["Posting_Date"] = posting
    df["Period"] = posting.dt.strftime("%Y-%m")

    df["Comment"] = ""

    ordered = [c for c in PREFERRED_ORDER if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


# ---------------------------------------------------------------- COM helpers

def _open_excel():
    import pythoncom
    import win32com.client

    # Streamlit reruns scripts on worker threads, and COM must be initialised
    # per-thread or DispatchEx fails outright.
    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.ScreenUpdating = False
    return excel


def _close_excel(excel):
    import pythoncom

    try:
        excel.Quit()
    finally:
        pythoncom.CoUninitialize()


def _to_excel_serial(ts: pd.Timestamp):
    """
    Date as an Excel serial number (days since 1899-12-30).

    Dates must NOT be handed to COM as datetime objects. pywin32 marshals a
    naive datetime as local time, and Excel stores the UTC equivalent, so on
    a UTC+2 machine midnight on the 1st became 22:00 on the 31st of the month
    before - every date in the workbook a day early, and a month's file
    appearing to run from the last day of the previous month. A serial number
    carries no timezone, so nothing can be applied to it. The column is given
    a date format after the write so it still reads as a date.
    """
    if pd.isna(ts):
        return None
    return (ts - EXCEL_EPOCH) / pd.Timedelta(days=1)


def _clean_cell(v):
    """Coerce pandas/numpy scalars into things COM will accept."""
    if v is None or v is pd.NaT:
        return None
    # Must precede any datetime handling: pd.Timestamp subclasses datetime.
    if isinstance(v, pd.Timestamp):
        return _to_excel_serial(v)
    if isinstance(v, np.datetime64):
        return _to_excel_serial(pd.Timestamp(v))
    if isinstance(v, datetime.datetime):
        return _to_excel_serial(pd.Timestamp(v))
    if isinstance(v, datetime.date):
        return _to_excel_serial(pd.Timestamp(v))
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _to_com_rows(df: pd.DataFrame):
    out = df.astype(object).where(pd.notna(df), None)
    return [[_clean_cell(v) for v in row] for row in out.values.tolist()]


def _write_rows(ws, rows, n_cols, start_row=2):
    for offset in range(0, len(rows), CHUNK_ROWS):
        chunk = rows[offset:offset + CHUNK_ROWS]
        top = start_row + offset
        target = ws.Range(ws.Cells(top, 1), ws.Cells(top + len(chunk) - 1, n_cols))
        target.Value = chunk


# ------------------------------------------------------------------- template

def _write_data_sheet(df: pd.DataFrame, path: str):
    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        df.to_excel(writer, index=False, sheet_name=DATA_SHEET)

        wb = writer.book
        ws = writer.sheets[DATA_SHEET]

        money = wb.add_format({"num_format": "#,##0.00"})
        pct = wb.add_format({"num_format": "0.00%"})
        header = wb.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1})

        for idx, col in enumerate(df.columns):
            ws.write(0, idx, col, header)
            if col in ("Amount", "VAT_Amount", "Debit_Amount", "Credit_Amount"):
                ws.set_column(idx, idx, 14, money)
            elif col == "VAT%":
                ws.set_column(idx, idx, 9, pct)
            elif col in ("Description", "G_L_Account_Name"):
                ws.set_column(idx, idx, 34)
            elif col == "Comment":
                ws.set_column(idx, idx, 30)
            else:
                ws.set_column(idx, idx, 16)

        ws.freeze_panes(1, 0)


def create_template(template_path: str, sample: pd.DataFrame):
    """
    Builds the template workbook: Data table plus the summary pivot and its
    slicers. A few sample rows are needed because a PivotTable cannot be
    created over an empty range; they are replaced on every run.
    """
    template_path = os.path.abspath(template_path)
    os.makedirs(os.path.dirname(template_path), exist_ok=True)

    seed = sample.head(50)

    # Built locally, then copied into place. This folder is OneDrive-synced,
    # and Excel resolves such paths to their SharePoint URL - automating
    # against that blocks on auth/co-authoring prompts that are invisible
    # when Excel is headless.
    work_dir = tempfile.mkdtemp(prefix="vatrecon_tpl_")
    work_path = os.path.join(work_dir, "template.xlsx")
    _write_data_sheet(seed, work_path)

    excel = _open_excel()
    try:
        wb = excel.Workbooks.Open(work_path)
        data_ws = wb.Worksheets(DATA_SHEET)

        data_range = data_ws.Range(
            data_ws.Cells(1, 1),
            data_ws.Cells(len(seed) + 1, len(seed.columns)),
        )
        table = data_ws.ListObjects.Add(XL_SRC_RANGE, data_range, None, XL_YES)
        table.Name = TABLE_NAME
        table.TableStyle = "TableStyleMedium2"

        summary_ws = wb.Worksheets.Add(Before=data_ws)
        summary_ws.Name = SUMMARY_SHEET

        cache = wb.PivotCaches().Create(SourceType=XL_DATABASE, SourceData=TABLE_NAME)
        # Leaves room above the pivot for the entity/period header.
        pt = cache.CreatePivotTable(
            TableDestination=summary_ws.Cells(PIVOT_TOP_ROW, 1),
            TableName="VATSummary",
        )

        # Subtotals belong on the VAT grouping levels only. On the account
        # levels they produce a redundant "300503 Total" line under every
        # single account, which reads as duplicated data.
        grouping_levels = ["Entity", "VAT Per Return", "VAT Per BC", "VAT Tag per Return"]
        account_levels = ["G_L_Account_No", "G_L_Account_Name"]

        for position, field in enumerate(grouping_levels + account_levels, start=1):
            pf = pt.PivotFields(field)
            pf.Orientation = XL_ROW_FIELD
            pf.Position = position
            if field in account_levels or field == "Entity":
                # Subtotals is a 12-element array; all False = no subtotal.
                # Entity is excluded because the grand total already covers it
                # once the slicer is filtered to a single entity.
                pf.Subtotals = [False] * 12

        pt.RowAxisLayout(XL_TABULAR_ROW)
        pt.RepeatAllLabels(1)  # xlDoNotRepeatLabels
        # Entity is the exception: repeated on every row so a line stays
        # attributable to its entity when rows are copied out of the pivot.
        pt.PivotFields("Entity").RepeatLabels = True
        pt.ColumnGrand = False
        pt.RowGrand = True

        formats = _number_formats(excel)
        amount_field = pt.AddDataField(pt.PivotFields("Amount"), "Sum of Amount", XL_SUM)
        _set_format(amount_field, formats["money"])
        vat_field = pt.AddDataField(pt.PivotFields("VAT_Amount"), "Sum of VAT Amount", XL_SUM)
        _set_format(vat_field, formats["money"])

        # Computed on the sums, so subtotal rows show the blended rate - which
        # is what the Power BI measure (DIVIDE) did.
        pt.CalculatedFields().Add("VAT Rate", "='VAT_Amount' / 'Amount'")
        rate_field = pt.AddDataField(pt.PivotFields("VAT Rate"), "VAT %", XL_SUM)
        _set_format(rate_field, formats["percent"])

        # Accounts with a nil Amount divide by zero. A calculated field can't
        # return "" (it must be numeric), so the error is blanked at the pivot
        # level instead - which is what DIVIDE() did in the Power BI model.
        pt.DisplayErrorString = True
        pt.ErrorString = ""

        # No slicers: a published file holds a single entity for a single
        # month, so there is nothing to slice. The header names both instead.
        _apply_header(summary_ws, "«Entity»", "«Period»")
        _style_header(summary_ws)

        summary_ws.Range("A:H").ColumnWidth = 22

        _build_dashboard(wb)
        summary_ws.Activate()

        wb.Save()
        wb.Close(SaveChanges=True)
    finally:
        _close_excel(excel)

    shutil.copyfile(work_path, template_path)
    shutil.rmtree(work_dir, ignore_errors=True)
    return template_path


def normalise_template_chrome(template_path: str = TEMPLATE_PATH,
                              rebuild_dashboard: bool = False) -> str:
    """
    Bring an existing template in line with the current design *without*
    rebuilding it: remove any slicers, (re)apply the header block, and add
    the dashboard sheet if it is missing.

    create_template() would also achieve this, but it rebuilds the pivot from
    scratch and so discards hand-made layout - field order, formatting. This
    edits in place, so customisation survives. The dashboard is likewise left
    alone once it exists, unless rebuild_dashboard says otherwise.
    """
    template_path = os.path.abspath(template_path)

    # Excel is kept off the OneDrive-synced path; automating a file that
    # resolves to its SharePoint URL blocks on invisible prompts.
    work_dir = tempfile.mkdtemp(prefix="vatrecon_chrome_")
    work_path = os.path.join(work_dir, "template.xlsx")
    shutil.copyfile(template_path, work_path)

    excel = _open_excel()
    try:
        wb = excel.Workbooks.Open(work_path)
        summary_ws = wb.Worksheets(SUMMARY_SHEET)

        # Backwards by index: deleting from a live COM collection while
        # iterating it forwards skips entries.
        removed = 0
        for i in range(wb.SlicerCaches.Count, 0, -1):
            wb.SlicerCaches(i).Delete()
            removed += 1
        if removed:
            print(f"Removed {removed} slicer(s).")

        _apply_header(summary_ws, "«Entity»", "«Period»")
        _style_header(summary_ws)

        try:
            pt = summary_ws.PivotTables("VATSummary")
            # Close the gap the slicers used to occupy. Deleting the rows
            # above the pivot shifts it up; doing nothing if it already sits
            # in place keeps this safe to re-run.
            current_top = pt.TableRange2.Row
            if current_top > PIVOT_TOP_ROW:
                summary_ws.Rows(f"{PIVOT_TOP_ROW}:{current_top - 1}").Delete()
                print(f"Moved pivot up from row {current_top} to {PIVOT_TOP_ROW}.")
            _emphasise_total_rows(summary_ws, summary_ws.PivotTables("VATSummary"))
        except Exception as e:
            print(f"  ! Could not tidy the summary sheet: {e}")

        had_dashboard = any(ws.Name == DASHBOARD_SHEET for ws in wb.Worksheets)
        _build_dashboard(wb, force=rebuild_dashboard)
        if not had_dashboard:
            print("Added the Dashboard sheet.")
        elif rebuild_dashboard:
            print("Rebuilt the Dashboard sheet.")

        summary_ws.Activate()
        wb.Save()
        wb.Close(SaveChanges=True)
    finally:
        _close_excel(excel)

    shutil.copyfile(work_path, template_path)
    shutil.rmtree(work_dir, ignore_errors=True)
    print(f"Template chrome updated: {template_path}")
    return template_path


def _template_headers(template_path: str):
    try:
        head = pd.read_excel(template_path, sheet_name=DATA_SHEET, nrows=0)
        return list(head.columns)
    except Exception:
        return None


def _require_template_columns(template_path: str, prepared: pd.DataFrame) -> list:
    """
    Return the template's columns, building the template only if it is
    genuinely absent.

    'Present but unreadable' must never be treated as 'missing'. A template
    open in Excel, or still syncing in OneDrive, fails to read - and
    rebuilding on that basis silently destroys whatever layout it held. That
    has happened once; hence the explicit existence check.
    """
    cols = _template_headers(template_path)
    if cols is not None:
        return cols

    if os.path.exists(template_path):
        raise RuntimeError(
            f"The template exists but could not be read:\n    {template_path}\n"
            "It is most likely open in Excel, or OneDrive has not finished "
            "syncing it.\nClose it and run again. Refusing to rebuild it, "
            "because that would discard its layout."
        )

    print("No template found - building one...")
    create_template(template_path, prepared)
    cols = _template_headers(template_path)
    if cols is None:
        raise RuntimeError(f"Template could not be created at {template_path}")
    return cols


def _conform_to_template(prepared: pd.DataFrame, template_cols: list) -> pd.DataFrame:
    """
    Reshape a run's data to exactly the template's columns.

    The template carries hand-made layout (pivot field order, formatting), so
    it must never be rebuilt just because the extract gained or lost a field -
    that would silently throw the user's work away. Instead the data is made
    to fit: absent columns are added empty, unexpected ones are left out.
    A genuinely new field only reaches the workbook when the template is
    deliberately regenerated (--make-template).
    """
    missing = [c for c in template_cols if c not in prepared.columns]
    extra = [c for c in prepared.columns if c not in template_cols]

    out = prepared.copy()
    for col in missing:
        out[col] = ""

    if missing:
        print(f"  note: not in this extract, written blank: {missing}")
    if extra:
        print(f"  note: not in the template, so not written: {extra}")
        print("        run with --make-template to rebuild the template "
              "around the new columns (this discards layout customisations).")

    return out[template_cols]


# ---------------------------------------------------------------------- build

def _refresh_with_data(path: str, df: pd.DataFrame, excel=None,
                       entity=None, period=None, summary_only=False):
    """
    Swap the template copy's data for this run's rows and refresh.

    An existing Excel instance can be passed in; when building many entity
    files, starting Excel once rather than per file dominates the runtime.

    entity/period fill in the header above the pivot. Total-row emphasis is
    reapplied here rather than stored in the template, because which rows are
    totals depends on the data.

    summary_only strips the Data sheet afterward, leaving a static Dashboard
    and detail pivot with the raw rows removed - see _make_summary_only.
    """
    n_rows, n_cols = len(df), len(df.columns)
    rows = _to_com_rows(df)

    own_excel = excel is None
    if own_excel:
        excel = _open_excel()
    try:
        wb = excel.Workbooks.Open(path)
        excel.Calculation = XL_CALC_MANUAL

        ws = wb.Worksheets(DATA_SHEET)
        table = ws.ListObjects(TABLE_NAME)

        # Drop the seed/previous rows, leaving the header intact.
        if table.DataBodyRange is not None:
            table.DataBodyRange.Delete()

        _write_rows(ws, rows, n_cols)

        # Dates went in as serial numbers (see _to_excel_serial), so the
        # columns holding them need a date format to read as dates.
        for i, col in enumerate(df.columns, start=1):
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                ws.Columns(i).NumberFormat = DATE_NUMBER_FORMAT

        # Grow the table over the new data so the pivot source follows it.
        table.Resize(ws.Range(ws.Cells(1, 1), ws.Cells(n_rows + 1, n_cols)))

        wb.RefreshAll()
        excel.CalculateUntilAsyncQueriesDone()
        excel.Calculation = XL_CALC_AUTOMATIC

        summary_ws = wb.Worksheets(SUMMARY_SHEET)
        dash_ws = None
        for ws in wb.Worksheets:
            if ws.Name == DASHBOARD_SHEET:
                dash_ws = ws
                break

        if entity is not None:
            _apply_header(summary_ws, entity, period)
            if dash_ws is not None:
                _apply_header(dash_ws, entity, period)
                dash_ws.Range(HEADER_TITLE_CELL).Value = "VAT Return and Recon - Dashboard"
        try:
            _emphasise_total_rows(summary_ws, summary_ws.PivotTables("VATSummary"))
        except Exception as e:
            # Cosmetic only - never lose a workbook over formatting.
            print(f"  ! Could not emphasise total rows: {e}")

        if summary_only and dash_ws is not None:
            try:
                _make_summary_only(wb, summary_ws, dash_ws)
            except Exception as e:
                # A summary file that still carries its detail data is a much
                # smaller problem than a corrupted one - report it and keep
                # the full workbook rather than risk leaving a broken file.
                print(f"  ! Could not strip detail rows for a summary-only "
                      f"file, keeping the Data sheet instead: {e}")

        (dash_ws or summary_ws).Activate()
        wb.Save()
        wb.Close(SaveChanges=True)
    finally:
        if own_excel:
            _close_excel(excel)


def build_vat_workbook(df: pd.DataFrame, output_path: str,
                       template_path: str = TEMPLATE_PATH) -> str:
    """
    Copies the template, writes this run's data into it and refreshes.
    Returns the output path.
    """
    prepared = prepare_dataframe(df)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Only built when genuinely absent. A column-set change conforms the data
    # instead of rebuilding, so layout work in the template is never lost.
    template_cols = _require_template_columns(template_path, prepared)
    prepared = _conform_to_template(prepared, template_cols)

    # Same reason as in create_template: keep Excel on local disk, then copy
    # the finished workbook into the synced folder.
    work_dir = tempfile.mkdtemp(prefix="vatrecon_out_")
    work_path = os.path.join(work_dir, "workbook.xlsx")
    try:
        shutil.copyfile(os.path.abspath(template_path), work_path)
        _refresh_with_data(work_path, prepared)
        shutil.copyfile(work_path, output_path)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return output_path


def _safe_folder_name(name: str) -> str:
    """Strip characters Windows won't accept in a folder name."""
    cleaned = "".join(" " if c in '<>:"/\\|?*' else c for c in str(name))
    return cleaned.strip().rstrip(".") or "Unknown Entity"


def _check_output_root(output_root: str):
    """
    Refuse to publish into a path that clearly isn't the synced library.

    os.makedirs would happily create the whole tree locally, so a mis-derived
    root would look like success while writing files that sync nowhere. The
    library is recognised by 'Group Finance' sitting alongside the folder
    the recon files go into.
    """
    if os.path.isdir(output_root):
        return

    root = os.path.abspath(os.path.join(output_root, "..", ".."))
    if os.path.isdir(root):
        return  # 'Group Finance' is there; the subfolders just don't exist yet

    raise RuntimeError(
        "Could not find the Global Finance library to publish into.\n"
        f"    Expected: {output_root}\n"
        f"    Derived from this tool's location: {PROJECT_DIR}\n"
        "The tool works out the publish folder by going three levels up from\n"
        "itself, so it must be run from its place inside the synced library\n"
        f"(...\\Finance Systems\\Automations\\Query tool). Check that\n"
        f"'{LIBRARY_MARKER}' has finished syncing in OneDrive."
    )


def _short_entity_name(entity: str) -> str:
    """
    'Contoso Singapore' -> 'Singapore', for use in the file name.

    Every entity in the config is prefixed 'Contoso ', which just repeats itself
    across a folder of files. Anything without the prefix is left alone.
    """
    name = str(entity).strip()
    if name.lower().startswith("contoso ") and len(name) > 8:
        name = name[8:].strip()
    return _safe_folder_name(name)


def _period_label(period: str) -> str:
    """'2026-08' -> 'August 2026'."""
    try:
        year, month = str(period).split("-")
        return f"{calendar.month_name[int(month)]} {int(year)}"
    except Exception:
        return str(period)


def _apply_header(summary_ws, entity, period_text):
    """
    Name the entity and period at the top of the summary sheet.

    period_text is written as given, so the caller decides how the period
    reads - e.g. "August 2026".
    """
    # Forced to Text first: Excel otherwise parses "August 2026" as a date and
    # the header shows 01/08/2026.
    for cell in (HEADER_ENTITY_CELL, HEADER_TITLE_CELL, HEADER_PERIOD_CELL):
        summary_ws.Range(cell).NumberFormat = "@"

    summary_ws.Range(HEADER_ENTITY_CELL).Value = str(entity)
    summary_ws.Range(HEADER_TITLE_CELL).Value = "VAT Return and Recon"
    summary_ws.Range(HEADER_PERIOD_CELL).Value = str(period_text)


def _style_header(summary_ws):
    """One-off styling of the header block; values are filled in per file."""
    entity = summary_ws.Range(HEADER_ENTITY_CELL)
    entity.Font.Size = 18
    entity.Font.Bold = True

    title = summary_ws.Range(HEADER_TITLE_CELL)
    title.Font.Size = 11
    title.Font.Bold = False
    title.Font.Color = 0x808080  # grey

    period = summary_ws.Range(HEADER_PERIOD_CELL)
    period.Font.Size = 13
    period.Font.Bold = True


def _rgb(r, g, b):
    """Excel takes colours as BGR integers, not RGB."""
    return (b << 16) | (g << 8) | r


def _number_formats(excel):
    """
    Number format codes written with this Excel's own separators.

    Format codes set through COM are taken literally in the local locale, so
    a US-style "0.00%" is read as digit, literal dot, digits - and renders
    0.1998 as "0,20%" instead of "19,98%". Likewise "#,##0.00" came out as
    ",199.80". Asking Excel for its separators and building the codes from
    those keeps it correct wherever it runs; they are then assigned through
    NumberFormatLocal, which is the property that expects local codes.
    """
    decimal, thousands = ",", " "
    try:
        intl = excel.International
        decimal = intl[XL_DECIMAL_SEPARATOR - 1]
        thousands = intl[XL_THOUSANDS_SEPARATOR - 1]
    except Exception:
        pass
    return {
        "money": f"#{thousands}##0{decimal}00",
        "integer": f"#{thousands}##0",
        # Whole percentages: a VAT rate reads as "20%", and this carries no
        # separator so it is safe in any locale.
        "percent": "0%",
        "date": DATE_NUMBER_FORMAT,
    }


def _set_format(target, code):
    """
    Apply a number format code built with local separators.

    A PivotField exposes only NumberFormat while a Range exposes both, and on
    this Excel the two behave identically - both read the code in the local
    locale - so NumberFormat is used, with the other as a fallback.
    """
    try:
        target.NumberFormat = code
    except Exception:
        target.NumberFormatLocal = code


BRAND_DARK = _rgb(31, 78, 121)
BRAND_LIGHT = _rgb(222, 235, 247)
BRAND_GREY = _rgb(89, 89, 89)
BRAND_RED = _rgb(192, 0, 0)

# label, formula over the Data table, format key, flag-if-nonzero
#
# Net Amount is the one figure that is expected to sit near zero on a
# complete extract - a ledger is double entry, so summing every account
# nets to (about) zero. It is kept anyway: shown next to Net VAT rather than
# in place of an effective rate, it reads as a completeness check rather
# than a meaningless percentage - a Net Amount that is NOT close to zero
# is itself the useful signal, pointing at rows missing from the extract.
KPI_TILES = [
    ("Net Amount", f"=SUM({TABLE_NAME}[Amount])", "money", False),
    ("Output VAT (Sales)",
     f'=SUMIFS({TABLE_NAME}[VAT_Amount],{TABLE_NAME}[VAT Per Return],"Sale")',
     "money", False),
    ("Input VAT (Purchases)",
     f'=SUMIFS({TABLE_NAME}[VAT_Amount],{TABLE_NAME}[VAT Per Return],"Purchase")',
     "money", False),
    ("Net VAT", f"=SUM({TABLE_NAME}[VAT_Amount])", "money", False),
    ("Needs Comment",
     f'=COUNTIF({TABLE_NAME}[VAT Risk],"Comment Required")', "integer", True),
]


def _build_dashboard(wb, force=False):
    """
    Adds the summarised dashboard sheet: headline figures and a compact
    VAT-tag pivot.

    The KPI tiles are formulas over the Data table rather than references
    into a pivot, so they follow the table as it grows and shrinks instead
    of breaking when a month has a different number of rows.

    Left alone if the sheet already exists, so that anything the accountants
    restyle survives a re-run; pass force=True to rebuild it deliberately.
    """
    existing = None
    for ws in wb.Worksheets:
        if ws.Name == DASHBOARD_SHEET:
            existing = ws
            break

    if existing is not None:
        if not force:
            return existing
        existing.Delete()

    summary_ws = wb.Worksheets(SUMMARY_SHEET)
    dash = wb.Worksheets.Add(Before=summary_ws)
    dash.Name = DASHBOARD_SHEET

    # --- header -----------------------------------------------------------
    _apply_header(dash, "«Entity»", "«Period»")
    dash.Range(HEADER_TITLE_CELL).Value = "VAT Return and Recon - Dashboard"
    _style_header(dash)

    formats = _number_formats(wb.Application)

    # --- headline figures -------------------------------------------------
    for col, (label, formula, fmt_key, flag) in zip(DASH_KPI_COLS, KPI_TILES):
        label_cell = dash.Cells(DASH_KPI_LABEL_ROW, col)
        label_cell.Value = label
        label_cell.Font.Size = 10
        label_cell.Font.Bold = True
        label_cell.Font.Color = _rgb(255, 255, 255)
        label_cell.Interior.Color = BRAND_DARK
        label_cell.HorizontalAlignment = -4131  # xlLeft
        label_cell.IndentLevel = 1

        value_cell = dash.Cells(DASH_KPI_VALUE_ROW, col)
        value_cell.Formula = formula
        _set_format(value_cell, formats[fmt_key])
        value_cell.Font.Size = 16
        value_cell.Font.Bold = True
        value_cell.Interior.Color = BRAND_LIGHT
        value_cell.HorizontalAlignment = -4131
        value_cell.IndentLevel = 1
        if flag:
            # Anything above zero is an exception the accountants must clear.
            value_cell.Font.Color = BRAND_RED

        for row in (DASH_KPI_LABEL_ROW, DASH_KPI_VALUE_ROW):
            block = dash.Range(dash.Cells(row, col), dash.Cells(row, col + 1))
            block.Merge()

    # --- summarised pivot -------------------------------------------------
    # Same cache as the detail pivot: a second cache would double the file
    # size and refresh twice for no benefit.
    cache = wb.Worksheets(SUMMARY_SHEET).PivotTables(1).PivotCache()
    pt = cache.CreatePivotTable(
        TableDestination=dash.Cells(DASH_PIVOT_ROW, 1),
        TableName="VATDashboard",
    )

    for position, field in enumerate(["VAT Tag per Return", "VAT Per Return"], start=1):
        pf = pt.PivotFields(field)
        pf.Orientation = XL_ROW_FIELD
        pf.Position = position

    pt.RowAxisLayout(XL_TABULAR_ROW)

    # Captions must differ from the source field names or Excel rejects them.
    amount = pt.AddDataField(pt.PivotFields("Amount"), "Sum of Amount", XL_SUM)
    _set_format(amount, formats["money"])
    vat = pt.AddDataField(pt.PivotFields("VAT_Amount"), "Sum of VAT Amount", XL_SUM)
    _set_format(vat, formats["money"])
    rate = pt.AddDataField(pt.PivotFields("VAT Rate"), "VAT %", XL_SUM)
    _set_format(rate, formats["percent"])

    pt.DisplayErrorString = True
    pt.ErrorString = ""
    pt.ColumnGrand = False
    pt.RowGrand = True
    try:
        pt.TableStyle2 = "PivotStyleMedium9"
    except Exception:
        pass

    # --- presentation -----------------------------------------------------
    for col in range(1, 11):
        dash.Columns(col).ColumnWidth = 20
    dash.Rows(DASH_KPI_VALUE_ROW).RowHeight = 26
    dash.Activate()
    try:
        wb.Windows(1).DisplayGridlines = False
    except Exception:
        pass

    return dash


def _flatten_pivot_to_values(pt):
    """
    Converts one PivotTable's output to plain values in place, keeping the
    number formats and fonts already applied. This is the standard
    "copy, paste special values over itself" trick; it detaches the cells
    from the PivotCache, after which the PivotTable object itself no longer
    exists as one - just static text and numbers.
    """
    rng = pt.TableRange2  # the full pivot area, including any filter fields
    rng.Copy()
    rng.PasteSpecial(Paste=XL_PASTE_VALUES)


def _make_summary_only(wb, summary_ws, dash_ws):
    """
    Strips the transaction-level Data sheet from a workbook, leaving the
    Dashboard and the detail pivot as a static year-end snapshot.

    For a year's worth of a large entity's GL, the Data sheet alone can run
    to several hundred thousand rows - unusable to open and unnecessary for
    a summary handout. Every pivot and every KPI formula (which reads
    VATData[...] directly) is converted to plain values first: once the
    sheet those depend on is gone, a live pivot cache pointing at a deleted
    table is exactly the kind of dangling reference Excel's file-repair
    flags as corruption on open. Flattening first avoids creating that
    reference at all, rather than leaving it to be discovered later.
    """
    for ws in (summary_ws, dash_ws):
        for i in range(ws.PivotTables().Count, 0, -1):
            _flatten_pivot_to_values(ws.PivotTables(i))

    # The KPI tiles are formulas straight over the Data table, not pivot
    # output, so they need the same in-place value conversion.
    for col in DASH_KPI_COLS:
        cell = dash_ws.Cells(DASH_KPI_VALUE_ROW, col)
        cell.Value = cell.Value

    wb.Application.CutCopyMode = False
    wb.Worksheets(DATA_SHEET).Delete()


def _emphasise_total_rows(summary_ws, pt):
    """
    Make subtotal and grand-total rows bolder and larger than the detail.

    Excel exposes no direct 'format the subtotal rows' handle for a pivot in
    tabular layout, so the rendered label block is read back in one call and
    the rows carrying a 'X Total' / 'Grand Total' label are styled. It has to
    run after each refresh because the row positions move with the data.
    """
    rng = pt.TableRange1
    first_row, first_col = rng.Row, rng.Column
    n_rows, n_cols = rng.Rows.Count, rng.Columns.Count
    last_row, last_col = first_row + n_rows - 1, first_col + n_cols - 1

    # Labels only live in the leftmost columns; one read rather than per-cell.
    label_last_col = min(first_col + 6, last_col)
    labels = summary_ws.Range(
        summary_ws.Cells(first_row, first_col),
        summary_ws.Cells(last_row, label_last_col),
    ).Value

    body = summary_ws.Range(
        summary_ws.Cells(first_row, first_col),
        summary_ws.Cells(last_row, last_col),
    )
    body.Font.Bold = False
    body.Font.Size = BODY_FONT_SIZE

    for offset, row_values in enumerate(labels or []):
        if not isinstance(row_values, tuple):
            row_values = (row_values,)
        is_total = any(
            isinstance(v, str) and (v.strip().endswith(" Total") or v.strip() == "Grand Total")
            for v in row_values
        )
        if not is_total:
            continue
        row = first_row + offset
        total_row = summary_ws.Range(
            summary_ws.Cells(row, first_col),
            summary_ws.Cells(row, last_col),
        )
        total_row.Font.Bold = True
        total_row.Font.Size = TOTAL_ROW_FONT_SIZE


def build_entity_workbooks(df: pd.DataFrame,
                           output_root: str = OUTPUT_ROOT,
                           template_path: str = TEMPLATE_PATH,
                           progress_callback=None,
                           ytd_label: str = None):
    """
    Publishes one recon file per entity per month.

    <output_root>/<Entity>/<Short>-VAT-Recon-<YYYY-MM>.xlsx
    e.g. Contoso Singapore/Singapore-VAT-Recon-2026-08.xlsx

    Whatever months are present in df each get their own file, so a run
    covering several months simply produces several files per entity.

    Pass ytd_label (e.g. "FY26") to additionally write one cumulative file
    per entity covering the whole of the data:

        Contoso Singapore/Singapore-VAT-Recon-FY26-YTD.xlsx

    That YTD file is summary-only: the Dashboard and detail pivot, with the
    underlying transaction rows stripped out afterward. A full year of a
    large entity's GL is several hundred thousand rows - unusable to open
    as a "summary" and not needed once the pivots holding it are built. The
    monthly files are unaffected and keep their full Data sheet.

    The entity folder is created if absent, and an existing file for that
    month is overwritten. Each file holds only its own entity's rows, so it
    can be handed straight to whoever owns that entity.

    Returns the list of paths written.
    """
    _check_output_root(output_root)

    prepared = prepare_dataframe(df)

    # Only built when genuinely absent - see _require_template_columns.
    template_cols = _require_template_columns(template_path, prepared)
    prepared = _conform_to_template(prepared, template_cols)

    # (entity, file stem, header period text, rows, summary_only)
    tasks = [
        (entity, f"VAT-Recon-{period}", _period_label(period), part, False)
        for (entity, period), part in prepared.groupby(["Entity", "Period"], sort=True)
    ]

    if ytd_label:
        for entity, part in prepared.groupby("Entity", sort=True):
            months = sorted(m for m in part["Period"].dropna().unique())
            span = (f" ({_period_label(months[0])} to {_period_label(months[-1])})"
                    if months else "")
            tasks.append((entity,
                          f"VAT-Recon-{ytd_label}-YTD",
                          f"{ytd_label} year to date{span}",
                          part,
                          True))

    written = []
    work_dir = tempfile.mkdtemp(prefix="vatrecon_batch_")
    # One Excel instance for the whole batch; startup cost would otherwise be
    # paid once per file.
    excel = _open_excel()
    try:
        local_template = os.path.join(work_dir, "template.xlsx")
        shutil.copyfile(os.path.abspath(template_path), local_template)

        for i, (entity, stem, header_period, part, summary_only) in enumerate(tasks, start=1):
            if progress_callback:
                tag = " (summary)" if summary_only else ""
                progress_callback(i, len(tasks), f"{entity} — {stem}{tag}")

            # A sheet cannot hold more rows than this, and silently writing a
            # truncated file would be worse than not writing one.
            if len(part) + 1 > EXCEL_MAX_ROWS:
                print(f"  ! Skipped {entity} {stem}: {len(part):,} rows exceeds "
                      f"Excel's limit of {EXCEL_MAX_ROWS:,}.")
                continue

            folder = os.path.join(output_root, _safe_folder_name(entity))
            os.makedirs(folder, exist_ok=True)
            destination = os.path.join(
                folder, f"{_short_entity_name(entity)}-{stem}.xlsx"
            )

            work_path = os.path.join(work_dir, f"wb_{i}.xlsx")
            shutil.copyfile(local_template, work_path)
            _refresh_with_data(work_path, part, excel=excel,
                               entity=entity, period=header_period,
                               summary_only=summary_only)
            shutil.copyfile(work_path, destination)  # overwrites by design
            os.remove(work_path)

            written.append(destination)
    finally:
        _close_excel(excel)
        shutil.rmtree(work_dir, ignore_errors=True)

    return written


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_template = "--make-template" in sys.argv
    per_entity = "--per-entity" in sys.argv

    # Editing the existing template needs no data, so handle it before the
    # source file is required.
    if "--normalise-template" in sys.argv:
        normalise_template_chrome(
            args[0] if args else TEMPLATE_PATH,
            rebuild_dashboard="--rebuild-dashboard" in sys.argv,
        )
        raise SystemExit(0)

    src = args[0]
    data = pd.read_csv(src, low_memory=False)
    print(f"Loaded {len(data):,} rows from {src}")

    if force_template:
        path = create_template(TEMPLATE_PATH, prepare_dataframe(data))
        print(f"Template written to {path}")
    elif per_entity:
        # Optional second arg overrides the publish root (used for dry runs).
        root = args[1] if len(args) > 1 else OUTPUT_ROOT
        paths = build_entity_workbooks(
            data,
            output_root=root,
            progress_callback=lambda i, n, msg: print(f"  ({i}/{n}) {msg}"),
        )
        print(f"\n{len(paths)} file(s) written under {root}")
    else:
        out = build_vat_workbook(data, args[1])
        print(f"Workbook written to {out}")
