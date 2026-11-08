from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from fyc import data
from fyc.bc_client import BCError

st.title("Close log across entities")

env = data.environment()
status = [s for s in data.load_status(env) if s.get("extension") == "Installed"]
if not status:
    st.warning("No entity in this environment can see the extension yet.", icon=":material/extension_off:")
    st.stop()
company_ids = {s["entity"]: s["company_id"] for s in status}


@st.cache_data(ttl=120, show_spinner="Reading the logs...")
def load_logs(environment_name: str, companies: tuple[tuple[str, str], ...], top: int) -> pd.DataFrame:
    c = data.get_client(environment_name)

    def read(item: tuple[str, str]) -> list[dict]:
        entity, company_id = item
        try:
            return [{"entity": entity, **row} for row in c.log_entries(company_id, top=top)]
        except BCError as exc:
            return [{"entity": entity, "logAction": "Error", "message": str(exc)}]

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for chunk in pool.map(read, companies) for r in chunk]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["logAction"] = df["logAction"].map(data.nice_action)
    df["status"] = df["status"].map(data.status_label) if "status" in df else ""
    df["createdAt"] = pd.to_datetime(df.get("createdAt"), utc=True, errors="coerce")
    for col in ("fiscalYearStart", "fiscalYearEnd"):
        df[col] = pd.to_datetime(df.get(col).replace(data.BLANK_DATE, None), errors="coerce").dt.date
    return df.sort_values("createdAt", ascending=False)


with st.container(horizontal=True, vertical_alignment="bottom"):
    chosen = st.multiselect("Entities", list(company_ids), placeholder="All entities", width=600)
    top = st.number_input("Entries per entity", min_value=5, max_value=500, value=25, step=5, width=180)

companies = tuple((e, company_ids[e]) for e in (chosen or company_ids))
logs = load_logs(env, companies, int(top))
if logs.empty:
    st.info("Nothing has been logged yet in these entities.")
    st.stop()

with st.container(horizontal=True):
    statuses = [s for s in data.STATUS_LABELS.values() if s in set(logs["status"])]
    picked_status = st.pills("Status", statuses, selection_mode="multi")
    actions = sorted(logs["logAction"].dropna().unique())
    picked = st.pills("Action", actions, selection_mode="multi")
if picked_status:
    logs = logs[logs["status"].isin(picked_status)]
if picked:
    logs = logs[logs["logAction"].isin(picked)]

columns = ["createdAt", "entity", "status", "logAction", "fiscalYearStart", "fiscalYearEnd", "documentNo",
           "noOfLines", "retainedEarningsAmount", "message", "userId"]
logs = logs.reindex(columns=columns)
st.dataframe(
    logs,
    hide_index=True,
    column_config={
        "createdAt": st.column_config.DatetimeColumn("When", format="D MMM YYYY, HH:mm"),
        "entity": st.column_config.TextColumn("Entity", pinned=True),
        "status": "Status",
        "logAction": "Action",
        "fiscalYearStart": st.column_config.DateColumn("FY start"),
        "fiscalYearEnd": st.column_config.DateColumn("FY end"),
        "documentNo": "Document no.",
        "noOfLines": st.column_config.NumberColumn("Lines"),
        "retainedEarningsAmount": st.column_config.NumberColumn("Retained earnings", format="localized"),
        "message": st.column_config.TextColumn("Message", width="large"),
        "userId": "User",
    },
)
st.download_button(
    "Download as CSV",
    logs.to_csv(index=False).encode("utf-8"),
    file_name=f"fiscal-year-close-log-{env}.csv",
    mime="text/csv",
    icon=":material/download:",
)
