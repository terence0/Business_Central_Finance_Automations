import streamlit as st
from datetime import date, datetime
import calendar
import pandas as pd
import io
import os

from query import Query, COMPANY_LIST
from vatPacks import OUTPUT_ROOT, MAP_FILE, COMMENT_FILE, build_packs, save_comments

# RUN IN TERMINAL: streamlit run vatRecon.py

st.set_page_config(page_title="VAT Return and Recon Query Tool", layout="wide")
st.title("🧾 VAT Return and Recon Query Tool")
from config import bc_env as _bc_env
_bc_env.banner(st)

st.write(
    "Extracts General Ledger entries from Business Central, filtered by "
    "Posting Date **server-side** (not downloaded in full and filtered "
    "afterwards), then classifies them and builds the packs with the same "
    "engine as **the central VAT automation**, so the files published here are "
    "the same as the ones that tool produces."
)

# Classification, the checks and the workbook layout come from vat_core.py
# and vat_workbook.py, copied from the central VAT automation (see vatPacks.py). The old
# 100-row VAT Recon\vat_expected_accounts.csv was truncated, every row "NO",
# so the VAT Risk flag could never fire; it is no longer read.


def convert_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Raw extract, offered only if the pack build fails."""
    output = io.BytesIO()
    try:
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
    except (ImportError, ValueError):
        writer = pd.ExcelWriter(output, engine="openpyxl")
    with writer:
        df.to_excel(writer, index=False, sheet_name="VAT Recon")
    return output.getvalue()


# -----------------------------
# UI INPUTS
# -----------------------------

all_company_keys = list(COMPANY_LIST.keys())

st.subheader("1) Select Company / Companies")
company_selection = st.multiselect("Choose one or more companies", options=all_company_keys)

select_all = st.checkbox("Select ALL companies")
if select_all:
    company_selection = all_company_keys

def month_options(count=36):
    """Most recent months first, starting with the current one."""
    today = date.today()
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        out.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return out


def month_bounds(year, month):
    """First and last day of the given month."""
    return (date(year, month, 1),
            date(year, month, calendar.monthrange(year, month)[1]))


def format_month(ym):
    year, month = ym
    return f"{year}-{month:02d}   ({calendar.month_name[month]} {year})"


def current_fy(today=None):
    """
    The financial year we are in. A financial year runs 1 September to
    31 August and is named after the calendar year it ends in, so FY26 is
    1 Sep 2025 to 31 Aug 2026.
    """
    today = today or date.today()
    return today.year + 1 if today.month >= 9 else today.year


def fy_months(fy_end_year):
    """The twelve (year, month) pairs making up a financial year."""
    out = []
    year, month = fy_end_year - 1, 9
    for _ in range(12):
        out.append((year, month))
        month += 1
        if month == 13:
            month, year = 1, year + 1
    return out


def fy_label(fy_end_year):
    return f"FY{fy_end_year % 100:02d}"


st.subheader("2) Select Period")

period_mode = st.radio(
    "Report on",
    options=["Month(s)", "Financial year"],
    horizontal=True,
    help="A financial year runs 1 September to 31 August and is named after "
         "the year it ends in - FY26 is 1 Sep 2025 to 31 Aug 2026.",
)

ytd_label = None

if period_mode == "Month(s)":
    st.caption(
        "Whole calendar months are used. Pick as many as you need - each one "
        "produces its own file per entity. Posting Date is filtered on the "
        "Business Central server, not after the fact."
    )
    months = month_options()
    period_selection = sorted(st.multiselect(
        "Month(s)",
        options=months,
        # The month just closed is the one normally being reconciled.
        default=[months[1]],
        format_func=format_month,
    ))

    if period_selection:
        first_from, _ = month_bounds(*period_selection[0])
        _, last_to = month_bounds(*period_selection[-1])
        names = ", ".join(f"{y}-{m:02d}" for y, m in period_selection)
        st.caption(
            f"**{len(period_selection)}** month(s) selected — {names}  \n"
            f"Spanning {first_from:%d %b %Y} to {last_to:%d %b %Y}, producing "
            f"`<Entity>-VAT-Recon-<YYYY-MM>.xlsx` for each."
        )
else:
    latest = current_fy()
    fy_choice = st.selectbox(
        "Financial year",
        options=[latest - i for i in range(5)],
        index=0,
        format_func=lambda y: f"{fy_label(y)}   (1 Sep {y - 1} to 31 Aug {y})",
    )
    ytd_label = fy_label(fy_choice)

    # Months beyond today would only return nothing, so they are not fetched.
    today = date.today()
    period_selection = [
        (y, m) for y, m in fy_months(fy_choice)
        if (y, m) <= (today.year, today.month)
    ]

    st.caption(
        f"**{ytd_label}** — 1 Sep {fy_choice - 1} to 31 Aug {fy_choice}.  \n"
        f"Producing {len(period_selection)} monthly file(s) per entity plus one "
        f"cumulative `<Entity>-VAT-Recon-{ytd_label}-YTD.xlsx` covering the whole year."
    )
    if len(period_selection) < 12:
        st.info(
            f"{ytd_label} is still in progress, so only the {len(period_selection)} "
            "month(s) up to now are included."
        )
    st.warning(
        "A full year is a large run: roughly 13 files per entity, and the "
        "year-to-date file for the biggest entity runs to a few hundred "
        "thousand rows. Expect it to take a while."
    )


def validate_inputs(companies, periods):
    if not companies:
        return False, "Please select at least one company (or choose ALL)."
    if not periods:
        return False, "Please select at least one month."
    return True, None


# -----------------------------
# RUN EXTRACTION
# -----------------------------
st.divider()
run_button = st.button("▶ Run Extraction")

if run_button:
    valid, err = validate_inputs(company_selection, period_selection)

    if not valid:
        st.error(err)
    else:
        st.subheader("Execution log")
        progress_bar = st.progress(0)
        log_box = st.empty()
        log_lines = []

        def log(message):
            log_lines.append(message)
            # A code block rather than a dataframe: plain scrolling text, no
            # grid, no per-row selection, no built-in CSV-export icon.
            log_box.code("\n".join(log_lines), language=None)

        company_word = "y" if len(company_selection) == 1 else "ies"
        scope = f" for {ytd_label}" if ytd_label else ""
        log(f"Extracting GL entries for {len(company_selection)} compan{company_word} "
            f"across {len(period_selection)} month(s){scope}...")

        # Each month is pulled on its own rather than as one wide range:
        # months the user did not pick would otherwise be fetched and then
        # published, since the publisher writes a file for every month it
        # finds in the data.
        total_steps = len(period_selection) * len(company_selection)
        frames = []

        for month_index, (year, month) in enumerate(period_selection):
            m_from, m_to = month_bounds(year, month)
            label = f"{year}-{month:02d}"
            log(f"  {label} ({calendar.month_name[month]} {year})")

            def update_progress(current, total, message, _done=month_index * len(company_selection)):
                progress_bar.progress(min((_done + current) / total_steps, 1.0))
                log(f"     ({current}/{total}) {message}")

            try:
                part = Query(
                    dateFrom=m_from.strftime("%Y-%m-%d"),
                    dateTo=m_to.strftime("%Y-%m-%d"),
                ).getVATLedgerEntries(
                    selected_company_keys=company_selection,
                    progress_callback=update_progress,
                )
            except RuntimeError as e:
                # A company Business Central refused would otherwise publish
                # a short pack that looks complete, so the run stops instead.
                log(f"❌ {e}")
                st.error(str(e))
                st.stop()
            log(f"     {len(part):,} rows")
            if not part.empty:
                frames.append(part)

        df_results = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        progress_bar.progress(1.0)
        log(f"Extraction complete — {len(df_results):,} rows.")

        if df_results.empty:
            log("No data returned for the selected parameters.")
            st.warning("No data returned for the selected parameters.")
        else:
            log("")
            log(f"Publishing recon packs to: {OUTPUT_ROOT}")
            log("One file per entity per month; an existing file for the same month is overwritten.")
            log("Comments saved with 'Save comments' below are put back into every rebuild.")
            if ytd_label:
                log(f"Plus one whole-period {ytd_label}-YTD file per entity.")
            log("")

            try:
                written = build_packs(df_results, OUTPUT_ROOT, ytd_label=ytd_label, log=log)
                log("")
                log(f"✅ {len(written)} recon file(s) published:")
                for p in written:
                    log(f"    {os.path.relpath(p, OUTPUT_ROOT)}")
                st.success(
                    f"Done — {len(written)} recon file(s) published. Read each "
                    "pack's Checks sheet before signing the return off."
                )
            except Exception as e:
                log(f"❌ Could not publish the recon files: {e}")
                st.error(f"Could not publish the recon files: {e}")
                st.download_button(
                    label="⬇ Download the raw extract instead",
                    data=convert_df_to_excel_bytes(df_results),
                    file_name=f"VAT Recon - {datetime.now():%Y%m%d_%H%M%S}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# -----------------------------
# SAVE COMMENTS
# -----------------------------
st.divider()
st.subheader("3) Save comments")
st.write(
    "Type answers into the yellow **Comment** column on each pack's **Risk** "
    "sheet, save and close the workbook, then press the button. The comments "
    "go into the comments file and come back on every future build of that "
    "period. A blank cell never deletes a comment already on file."
)
st.caption(f"Comments file: `{COMMENT_FILE}`  \nAccount map: `{MAP_FILE}`")

comment_entity = st.selectbox(
    "Entity folder to read",
    options=["All entities"] + all_company_keys,
)
if st.button("💾 Save comments"):
    comment_log = []
    comment_box = st.empty()

    def clog(message):
        comment_log.append(message)
        comment_box.code("\n".join(comment_log), language=None)

    entity_arg = None if comment_entity == "All entities" else comment_entity
    try:
        rc = save_comments(OUTPUT_ROOT, entity=entity_arg, log=clog)
        if rc == 0:
            st.success("Comments saved.")
        else:
            st.error("Comments were not saved. Read the log above.")
    except Exception as e:
        st.error(f"Could not save comments: {e}")
