import csv
import datetime as dt
import io
import traceback

import os

import streamlit as st

from bc_client import BusinessCentralClient, sends_allowed

st.set_page_config(page_title="CON Planful Push Controller", layout="wide")

st.title("CON Planful Push Controller")
st.caption(
    "Run Business Central Planful Summary Transaction MTD pushes across multiple entities from one screen. "
    "This version uses the updated Planful connector report automation path and does not use request XML."
)

# Production or sandbox comes from BC_ENVIRONMENT_NAME, set by the run files
# ("Run Planful Streamlit Project.bat" / "... (Sandbox).bat").
BC_ENVIRONMENT = os.getenv("BC_ENVIRONMENT_NAME", "Production").strip()
if sends_allowed(BC_ENVIRONMENT):
    st.error(f"Business Central environment: **{BC_ENVIRONMENT}**. Pushes are LIVE and send "
             "data to Planful.", icon=":material/warning:")
else:
    st.success(f"Business Central environment: **{BC_ENVIRONMENT}** (sandbox). The push runs in "
               "Business Central only: sending to Planful is switched off in the sandbox.",
               icon=":material/science:")


@st.cache_data(show_spinner=False)
def load_companies():
    client = BusinessCentralClient.from_env()
    return client.get_companies()


def rows_to_csv(rows):
    if not rows:
        return ""
    output = io.StringIO()
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


if "logs" not in st.session_state:
    st.session_state.logs = []

with st.sidebar:
    st.header("Prerequisites")
    st.markdown(
        """
        - Planful connector extension must include `SetAutomationParameters(...)` on Report 50201.
        - `CON Planful Batch Runner` must be callable from the custom API.
        - The Microsoft Entra Application must have access to Business Central and the required permission sets.
        - `.env` must contain the Business Central API app registration details.
        """
    )

try:
    companies = load_companies()
except Exception as ex:
    st.error("Could not load Business Central companies.")
    st.exception(ex)
    st.stop()

company_options = {company.get("name", ""): company for company in companies if company.get("name")}

col1, col2 = st.columns(2)
with col1:
    starting_date = st.date_input("Starting Date", value=dt.date.today().replace(day=1))
with col2:
    ending_date = st.date_input("Ending Date", value=dt.date.today())

if ending_date < starting_date:
    st.error("Ending Date cannot be before Starting Date.")
    st.stop()

all_company_names = sorted(company_options.keys())


def _toggle_select_all_companies():
    if st.session_state.get("select_all_companies"):
        st.session_state["selected_company_names"] = all_company_names
    else:
        st.session_state["selected_company_names"] = []


st.checkbox(
    "Select all entities / companies",
    key="select_all_companies",
    on_change=_toggle_select_all_companies,
)

selected_company_names = st.multiselect(
    "Select entities / companies",
    options=all_company_names,
    placeholder="Choose companies to push to Planful",
    key="selected_company_names",
)

with st.expander("Report options", expanded=True):
    gl_account_filter = st.text_input(
        "G/L Account No. Filter",
        value="",
        help="Leave blank to use all relevant G/L accounts. You can use BC filter syntax if supported by the report, for example 1000..1999 or 4*.",
    )
    send_data_to_planful = st.checkbox(
        "Send Data to Planful",
        value=sends_allowed(BC_ENVIRONMENT),
        disabled=not sends_allowed(BC_ENVIRONMENT),
        help=None if sends_allowed(BC_ENVIRONMENT) else
        "Never sent from a sandbox: its Planful connector setup could point at live Planful.",
    )
    filter_on_period = st.checkbox("Filter On Period", value=False)
    period_formula = st.text_input("Period Formula", value="")
    export_to_xml = st.checkbox("Export to XML", value=False)

st.subheader("Run Summary")
st.write(
    {
        "startingDate": str(starting_date),
        "endingDate": str(ending_date),
        "glAccountNoFilter": gl_account_filter,
        "sendDataToPlanful": send_data_to_planful,
        "filterOnPeriod": filter_on_period,
        "periodFormula": period_formula,
        "exportToXml": export_to_xml,
        "selectedCompanies": selected_company_names,
    }
)

run_clicked = st.button(
    "Run Planful Summary Push",
    type="primary",
    disabled=not selected_company_names,
)

if run_clicked:
    client = BusinessCentralClient.from_env()
    st.session_state.logs = []
    progress = st.progress(0)
    status_placeholder = st.empty()
    total = len(selected_company_names)

    for index, company_name in enumerate(selected_company_names, start=1):
        company = company_options[company_name]
        status_placeholder.write(f"Running {index}/{total}: {company_name}")

        log_row = {
            "company": company_name,
            "company_id": company.get("id"),
            "started_at": dt.datetime.now().isoformat(timespec="seconds"),
            "status": "Running",
            "error": "",
            "run_id": "",
            "completed_at": "",
        }

        try:
            result = client.run_summary_push(
                company_id=company["id"],
                starting_date=str(starting_date),
                ending_date=str(ending_date),
                gl_account_filter=gl_account_filter,
                send_data_to_planful=send_data_to_planful,
                filter_on_period=filter_on_period,
                period_formula=period_formula,
                export_to_xml=export_to_xml,
            )

            log_row["status"] = str(result.get("status", result.get("Status", "Submitted")))
            log_row["error"] = str(result.get("errorMessage", result.get("error", "")))
            log_row["run_id"] = str(result.get("runId", result.get("runID", "")))

        except Exception as ex:
            log_row["status"] = "Failed"
            log_row["error"] = str(ex)
            log_row["trace"] = traceback.format_exc()

        finally:
            log_row["completed_at"] = dt.datetime.now().isoformat(timespec="seconds")
            st.session_state.logs.append(log_row)
            progress.progress(index / total)

    status_placeholder.success("Batch complete. Review the log below.")

st.subheader("Run Log")
if st.session_state.logs:
    st.dataframe(st.session_state.logs, use_container_width=True)
    csv_data = rows_to_csv(st.session_state.logs).encode("utf-8")
    st.download_button(
        "Download CSV log",
        data=csv_data,
        file_name=f"planful_summary_push_log_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
else:
    st.write("No run log yet.")
