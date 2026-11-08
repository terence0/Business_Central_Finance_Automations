"""Customer Ageing extract for Notes 21 and 22 (debtors ageing and ECL).

Pulls one row per customer ledger entry that was still open at the chosen
cut-off, bucketed by CALENDAR MONTH ON POSTING DATE to reproduce the FY25
basis, with the receivables G/L account resolved from the customer posting
group. The output is the input tab of
`FY26 Debtors Ageing and ECL - Ledger-Driven.xlsx`.

The balance is rolled back to the cut-off (Remaining Amount today less detailed
entries posted after the cut-off) because Remaining Amount is the balance today.
Run this in October and Remaining Amount would quietly understate every bucket.
"""

import io
from datetime import date, datetime

import pandas as pd
import streamlit as st

from query import Query, COMPANY_LIST

# -----------------------------------------------------
# STREAMLIT CONFIG
# -----------------------------------------------------
st.set_page_config(page_title="Customer Ageing Extract", layout="wide")
st.title("Customer Ageing Extract")
from config import bc_env as _bc_env
_bc_env.banner(st)
st.caption("Notes 21 and 22, debtors ageing and expected credit loss. "
           "Calendar-month buckets on posting date, matching FY25. "
           "Balances rolled back to the cut-off date.")

# -----------------------------------------------------
# INPUTS
# -----------------------------------------------------
all_company_keys = list(COMPANY_LIST.keys())

st.subheader("1) Companies")
company_selection = st.multiselect("Choose one or more companies",
                                   options=all_company_keys)
if st.checkbox("Select ALL companies", value=True):
    company_selection = all_company_keys

st.subheader("2) Cut-off date")
as_at_date = st.date_input("Ageing as at", value=date(2026, 8, 31))
st.caption("Year end is 31 August. For FY26 that is 31 August 2026.")

st.subheader("3) Output level")
LEVELS = {
    "Summary (recommended)":
        ("summary", "One row per company, posting group, account and bucket. "
                    "A few hundred rows. This is all the disclosure needs, and "
                    "it drops straight into the workbook's Summary Input tab."),
    "By customer":
        ("customer", "The same, split by customer. Use it to see who sits in "
                     "120+ days without pulling every invoice."),
    "Every open entry":
        ("detail", "One row per ledger entry open at the cut-off. Pull this "
                   "when TB Check shows a break and you need the invoices "
                   "behind it."),
}
level_label = st.radio("How much detail?", list(LEVELS), index=0,
                       captions=[v[1] for v in LEVELS.values()])
granularity = LEVELS[level_label][0]

with st.expander("What this extract does"):
    st.markdown(
        "- One row per customer ledger entry **open at the cut-off**, including "
        "entries settled after it.\n"
        "- **Balance rolled back to the cut-off**: Remaining Amount today, less "
        "detailed entries posted after the cut-off, excluding unrealised FX. Only "
        "the days since the year end are pulled, not all history, and the extract "
        "gives the same answer whenever you run it.\n"
        "- **Calendar-month buckets on posting date**, reproducing the FY25 Aged "
        "Accounts Receivable runs, so the comparative holds. `Bucket_DueDate_Days` "
        "carries the due-date day bands alongside as a diagnostic, so the size of "
        "the difference is visible without another extract.\n"
        "- **Receivables account** comes from the customer posting group, so the "
        "report does not have to be run once per posting group the way FY25 was.\n"
        "- **Only the 17 fields the note needs are requested**, not the whole "
        "Cust. Ledger Entry table, and every filter is applied by Business "
        "Central rather than here. The tool will not fall back to reading the "
        "ledger since inception: if a filter is refused it stops and says so.\n"
        "- Web service names are discovered at run time and reported below."
    )


def convert_df_to_excel_bytes(df: pd.DataFrame, pg: pd.DataFrame,
                              due: pd.DataFrame = None) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter",
                        datetime_format="yyyy-mm-dd",
                        date_format="yyyy-mm-dd") as writer:
        df.to_excel(writer, index=False, sheet_name="Customer Ledger")
        if due is not None and not due.empty:
            due.to_excel(writer, index=False, sheet_name="Due Date Basis")
        if pg is not None and not pg.empty:
            pg.to_excel(writer, index=False, sheet_name="Posting Groups")
    return output.getvalue()


# -----------------------------------------------------
# RUN
# -----------------------------------------------------
st.divider()
if st.button("Run ageing extract"):

    if not company_selection:
        st.error("Choose at least one company, or tick Select ALL.")
        st.stop()
    if not as_at_date:
        st.error("Choose a cut-off date.")
        st.stop()

    as_at_str = as_at_date.strftime("%Y-%m-%d")
    st.info(f"Extracting customer ageing as at **{as_at_str}** for "
            f"{len(company_selection)} company/ies. Large companies take a minute.")

    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(current, total, message):
        progress_bar.progress(min(current / total, 1.0))
        status_text.text(f"({current}/{total}) {message}")

    query = Query(accountNo=[], costCentre=[],
                  dateFrom=as_at_str, dateTo=as_at_str)

    try:
        df_results = query.getCustomerAging(
            selected_company_keys=company_selection,
            progress_callback=update_progress,
            granularity=granularity)
    except RuntimeError as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(str(exc))
        st.stop()

    pg_df = query.getCustomerPostingGroups(company_selection)

    progress_bar.progress(1.0)
    status_text.text("Done.")

    # ---- what answered -------------------------------------------------
    services = df_results.attrs.get("services", {})
    basis = df_results.attrs.get("basis", "unknown")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Customer ledger service", services.get("customer_ledger") or "none")
    c2.metric("Detailed ledger service", services.get("detailed") or "NOT PUBLISHED")
    c3.metric("Open entries read", f"{df_results.attrs.get('detail_rows', 0):,}")
    c4.metric("Rows out", f"{len(df_results):,}")

    if services.get("detailed"):
        st.success(f"Basis: {basis}")
    else:
        st.warning(
            "The detailed customer ledger service is not published, so balances "
            "are Remaining Amount as at **today**, not as at the cut-off. Any "
            "entry open at the cut-off and settled since is understated. Ask for "
            "page 29 (Detailed Cust. Ledg. Entries) to be published, then re-run. "
            "Close to the year end the difference is small; months later it is not.")

    if df_results.empty:
        st.warning("No open entries returned for the selected companies.")
        st.stop()

    # ---- summary the preparer actually checks --------------------------
    st.subheader("Summary by bucket")
    bucket_order = ["0 - 30 days", "30 - 60 days", "60 - 90 days",
                    "90 - 120 days", "120+ days"]
    summary = (df_results.pivot_table(index="Bucket", columns="Company",
                                      values="Balance_LCY", aggfunc="sum",
                                      margins=True, margins_name="Total")
               .reindex([b for b in bucket_order if b in
                         df_results["Bucket"].unique()] + ["Total"]))
    st.dataframe(summary, use_container_width=True)
    st.caption("Local currency per company. The workbook translates to sterling "
               "at the Planful EOM rate; do not add these columns together here.")

    st.subheader("Summary by receivables account")
    st.dataframe(
        df_results.pivot_table(index="Receivables_Account", columns="Bucket",
                               values="Balance_LCY", aggfunc="sum"),
        use_container_width=True)

    moved = df_results.attrs.get("moved_rows", 0)
    total = df_results.attrs.get("detail_rows", 0) or 1
    st.caption(f"{moved:,} of {total:,} open entries would fall in a different "
               "bucket on due-date day bands. That is the cost of matching the "
               "FY25 basis, and it is visible rather than assumed. The "
               "\"Due Date Basis\" sheet in the download carries that view.")

    unmapped = df_results["Receivables_Account"].isna().sum()
    if unmapped:
        st.error(f"{unmapped} rows have no receivables account. Their customer "
                 "posting group is missing from the posting group table. They "
                 "will not reach the note until that is fixed.")

    st.subheader(f"Output: {len(df_results):,} rows")
    st.dataframe(df_results, use_container_width=True, hide_index=True, height=520)

    # ---- download ------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if set(company_selection) == set(all_company_keys):
        label = "ALL"
    elif len(company_selection) > 1:
        label = "MULTI"
    else:
        label = company_selection[0]

    st.download_button(
        label="Download extract (Excel)",
        data=convert_df_to_excel_bytes(df_results, pg_df,
                                       df_results.attrs.get("due_summary")),
        file_name=f"Customer Ageing {granularity} - {label} - "
                  f"{as_at_str} - {timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.caption("Save this into `2. Supporting Workings\\1. Debtors Disclosure\\"
               "0. Automation\\1. Inputs\\Customer Ageing`, then run "
               "`1. Load Inputs.bat` in that folder. The loader works out which "
               "level you pulled and puts it in the right tab.")
