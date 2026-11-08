import pandas as pd
import streamlit as st

from fyc import data

st.title("Fiscal year close across entities")
st.caption(f"Environment **{data.environment()}**. Status is cached for five minutes. Use Refresh in the sidebar to reload.")

status = data.load_status(data.environment())

rows = []
for s in status:
    setup = s.get("setup") or {}
    rows.append(
        {
            "entity": s["entity"],
            "extension": s.get("extension", ""),
            "setup": "Done" if setup else ("Missing" if s.get("extension") == "Installed" else ""),
            "enabled": bool(setup.get("enabled")),
            "job_queue": bool(setup.get("jobQueueEntryExists")),
            "post_automatically": bool(setup.get("postAutomatically")),
            "last_closed_fy_end": s.get("last_closed_fy_end"),
            "open_fy_end": s.get("open_fy_end"),
            "close_due": bool(s.get("close_due")),
            "posting_window_open": bool(setup.get("postingWindowUser")),
            "last_activity": s.get("last_log_at"),
            "last_action": s.get("last_log_action", ""),
            "message": s.get("message") or s.get("last_log_message", ""),
        }
    )
df = pd.DataFrame(rows)

installed = df[df["extension"] == "Installed"]
with st.container(horizontal=True):
    st.metric("Entities", len(df), border=True)
    st.metric("Extension available", len(installed), border=True)
    st.metric("Setup done", int((installed["setup"] == "Done").sum()), border=True)
    st.metric("Scheduled", int(installed["job_queue"].sum()), border=True)
    st.metric("Year close due", int(installed["close_due"].sum()), border=True)

not_installed = df[df["extension"] == "Not installed"]
if len(not_installed):
    st.warning(
        f"{len(not_installed)} entities cannot see the extension. Extensions are installed per environment, "
        "so this usually means these companies belong to a different environment, or the extension is not "
        "installed in this one yet.",
        icon=":material/extension_off:",
    )

st.dataframe(
    df,
    hide_index=True,
    height="content" if len(df) <= 25 else 700,
    column_config={
        "entity": st.column_config.TextColumn("Entity", pinned=True),
        "extension": "Extension",
        "setup": "Setup",
        "enabled": st.column_config.CheckboxColumn("Enabled"),
        "job_queue": st.column_config.CheckboxColumn("Job queue"),
        "post_automatically": st.column_config.CheckboxColumn("Auto post"),
        "last_closed_fy_end": st.column_config.DateColumn("Last closed FY end"),
        "open_fy_end": st.column_config.DateColumn("Open FY end"),
        "close_due": st.column_config.CheckboxColumn("Close due", help="Year end plus the close delay has passed."),
        "posting_window_open": st.column_config.CheckboxColumn(
            "Posting window open",
            help="A run has the closing date temporarily allowed. Normally only for the seconds the journal posts.",
        ),
        "last_activity": st.column_config.DatetimeColumn("Last activity", format="D MMM YYYY, HH:mm"),
        "last_action": "Last action",
        "message": st.column_config.TextColumn("Message", width="large"),
    },
)
