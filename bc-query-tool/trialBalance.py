import streamlit as st
from datetime import datetime
import calendar
import pandas as pd
import io


from query import Query, COMPANY_LIST

# RUN IN TERMINAL: streamlit run trialBalance.py

st.set_page_config(page_title="Trial Balance Query Tool", layout="wide")
st.title("📊 Trial Balance Query Tool")
from config import bc_env as _bc_env
_bc_env.banner(st)

st.write("Use the inputs below to extract Trial Balance data from Business Central.")

# -----------------------------
# UI INPUTS
# -----------------------------

all_company_keys = list(COMPANY_LIST.keys())

st.subheader("1) Select Company / Companies")
company_selection = st.multiselect(
    "Choose one or more companies",
    options=all_company_keys,
)

select_all = st.checkbox("Select ALL companies")

if select_all:
    company_selection = all_company_keys

st.subheader("2) Select Date Range")
st.caption("The tool will automatically extract the Trial Balance at the **end of each month** within this range.")

col1, col2 = st.columns(2)
with col1:
    date_from = st.date_input("Start date")
with col2:
    date_to = st.date_input("End date")

# Preview which month-ends will be queried
if date_from and date_to and date_from <= date_to:
    month_ends = Query._get_month_end_dates(
        date_from.strftime("%Y-%m-%d"),
        date_to.strftime("%Y-%m-%d")
    )
    if month_ends:
        st.info(f"Will extract Trial Balance for **{len(month_ends)}** month-end(s): {', '.join(month_ends)}")
    else:
        st.warning("No complete month-ends fall within this range. Extend the date range to include at least one month-end.")


# -----------------------------
# VALIDATION HELPERS
# -----------------------------

def validate_inputs(companies, d_from, d_to):
    if not companies:
        return False, "Please select at least one company (or choose ALL)."
    if d_from > d_to:
        return False, "Start date cannot be after end date."
    return True, None

def convert_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Converts a dataframe to Excel bytes in-memory.
    """
    output = io.BytesIO()
    # xlsxwriter is the preferred engine, openpyxl is the fallback. Both are in
    # requirements.txt; the fallback exists so a stripped-down environment still
    # produces a file instead of a ModuleNotFoundError at the download step.
    try:
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
    except (ImportError, ValueError):
        writer = pd.ExcelWriter(output, engine="openpyxl")
    with writer:
        df.to_excel(writer, index=False, sheet_name="Trial Balance")
    return output.getvalue()


# -----------------------------
# RUN EXTRACTION
# -----------------------------
st.divider()
run_button = st.button("▶ Run Extraction")

if run_button:
    valid, err = validate_inputs(company_selection, date_from, date_to)

    if not valid:
        st.error(err)
    else:
        date_from_str = date_from.strftime("%Y-%m-%d")
        date_to_str = date_to.strftime("%Y-%m-%d")

        # Check month-ends exist
        month_ends = Query._get_month_end_dates(date_from_str, date_to_str)
        if not month_ends:
            st.error("No complete month-ends in the selected range. Please extend the date range.")
            st.stop()

        st.info(f"Extracting Trial Balance for {len(month_ends)} month-end(s) across {len(company_selection)} company/ies...")

        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, message):
            progress_bar.progress(current / total)
            status_text.text(f"({current}/{total}) {message}")

        query = Query(
            accountNo=[],
            costCentre=[],
            dateFrom=date_from_str,
            dateTo=date_to_str
        )

        df_results = query.getTrialBalance(
            selected_company_keys=company_selection,
            progress_callback=update_progress
        )

        progress_bar.progress(1.0)
        status_text.text("Done.")

        st.success(f"✅ Extraction complete. Rows returned: {len(df_results)}")

        if df_results.empty:
            st.warning("No data returned for the selected parameters.")
        else:
            st.subheader("Results")
            st.caption(f"Showing all {len(df_results)} rows × {len(df_results.columns)} columns")

            # Show per-period row counts
            if "Period" in df_results.columns:
                period_counts = df_results.groupby("Period").size().reset_index(name="Rows")
                st.write("**Rows per period:**")
                st.dataframe(period_counts, use_container_width=False, hide_index=True)

            # Show full data with all columns visible
            st.dataframe(
                df_results,
                use_container_width=True,
                hide_index=True,
                height=600
            )

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Determine output label for filename
        all_keys = list(COMPANY_LIST.keys())
        if set(company_selection) == set(all_keys):
            output_label = "ALL"
        elif len(company_selection) > 1:
            output_label = "MULTI"
        else:
            output_label = company_selection[0]

        file_name = f"TB - {output_label} - {timestamp}.xlsx"

        # Convert to Excel bytes
        excel_bytes = convert_df_to_excel_bytes(df_results)

        st.download_button(
            label="⬇ Download Excel (All Rows)",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
