from datetime import date

import pandas as pd
import streamlit as st

from fyc import data
from fyc.bc_client import BCError

ACTIONS = {
    "create_journal": "Create closing journal",
    "post_journal": "Post reviewed journal",
    "run_now": "Run full close",
    "create_job": "Schedule daily job",
}
EXPLAIN = {
    "create_journal": (
        "Creates the Close Income Statement journal for the chosen fiscal year, which must already be closed, and "
        "**does not post it**. Review the lines in each entity's journal batch. The batch must be empty first."
    ),
    "post_journal": (
        "Posts the closing lines you reviewed in each entity's journal batch. It refuses to post anything that is not "
        "a closing entry of the chosen year. With **Open posting window** on, the closing date is allowed for the "
        "app's user only while the journal posts, so nobody's posting dates need widening."
    ),
    "run_now": (
        "Closes the chosen fiscal year, then creates its closing journal. Entities with **Post automatically** on "
        "also post it. Only the chosen year is touched. Closing a fiscal year cannot be undone from the app."
    ),
    "create_job": (
        "Creates the daily 02:00 Job Queue entry in each entity, if it does not exist yet. "
        "The job only acts when the entity's setup is enabled and a year is due."
    ),
}

st.title("Run across entities")

env = data.environment()
can_write = data.writes_allowed()
if not can_write:
    st.info("This environment is read-only in the app.", icon=":material/lock:")

status = [s for s in data.load_status(env) if s.get("extension") == "Installed"]
if not status:
    st.warning("No entity in this environment can see the extension yet. Install it first.", icon=":material/extension_off:")
    st.stop()
by_entity = {s["entity"]: s for s in status}
ready = [e for e, s in by_entity.items() if s.get("setup")]

action = st.segmented_control(
    "Action", list(ACTIONS), format_func=ACTIONS.get, default="create_journal", required=True
)
st.markdown(EXPLAIN[action])

all_ready = st.checkbox(f"All entities with a saved setup ({len(ready)})")
selected = st.multiselect(
    "Entities",
    options=list(by_entity),
    default=ready if all_ready else None,
    disabled=all_ready,
    placeholder="Choose entities",
    key=f"run_entities_{all_ready}",
)
if all_ready:
    selected = ready

no_setup = [e for e in selected if not by_entity[e].get("setup")]
if no_setup:
    st.warning("These entities have no saved setup and will be skipped: " + ", ".join(no_setup))
targets = [e for e in selected if by_entity[e].get("setup")]

# The fail-safe: every close names one fiscal year, and BC acts on that year only.
year_end = None
if action != "create_job" and targets:
    ended = sorted(
        {y["end"] for e in targets for y in by_entity[e].get("years", []) if y["end"] < date.today()}, reverse=True
    )
    if not ended:
        st.warning("None of the chosen entities has a fiscal year that has ended.")
        targets = []
    else:
        year_end = st.selectbox(
            "Fiscal year to act on (year end)",
            ended,
            index=None,
            format_func=lambda d: f"{d:%d/%m/%Y}",
            placeholder="Choose the fiscal year end",
            help="Only this fiscal year is closed, journalled or posted. Later years are never touched, "
            "and BC stops with a clear message instead of guessing if anything does not match.",
        )
        if year_end is None:
            targets = []

plans = {e: data.plan_for_year(by_entity[e], action, year_end) for e in targets} if year_end else {}
if plans:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "entity": e,
                    "runs": ok,
                    "what_happens": text,
                    "post_automatically": bool(by_entity[e]["setup"].get("postAutomatically")),
                    "journal_batch": f'{by_entity[e]["setup"].get("journalTemplateName", "")} / '
                    f'{by_entity[e]["setup"].get("journalBatchName", "")}',
                }
                for e, (ok, text) in plans.items()
            ]
        ),
        hide_index=True,
        column_config={
            "entity": "Entity",
            "runs": st.column_config.CheckboxColumn("Runs"),
            "what_happens": st.column_config.TextColumn("What happens", width="large"),
            "post_automatically": st.column_config.CheckboxColumn("Auto post"),
            "journal_batch": "Journal batch",
        },
    )
    targets = [e for e, (ok, _) in plans.items() if ok]

confirmed = True
if targets and year_end:
    year_text = f"the fiscal year ending {year_end:%d/%m/%Y}"
    if action == "run_now":
        closing = [e for e in targets if not plans[e][1].startswith("Already closed")]
        posting = [e for e in targets if by_entity[e]["setup"].get("postAutomatically")]
        post_text = f" It is also posted in {len(posting)} entities (Post automatically on)." if posting else ""
        if closing:
            st.warning(
                f"**This closes {year_text}** in {len(closing)} of {len(targets)} entities and creates its closing "
                f"journal.{post_text} Closing a fiscal year cannot be undone from the app. No other year is touched.",
                icon=":material/warning:",
            )
            confirmed = st.checkbox(f"Yes, close {year_text} in {len(closing)} entities.")
        else:
            st.info(
                f"**{year_text[0].upper() + year_text[1:]} is already closed** in every chosen entity. Nothing is "
                f"closed; only its closing journal is created.{post_text} No other year is touched.",
                icon=":material/info:",
            )
            confirmed = st.checkbox(f"Yes, create the closing journal for {year_text}.")
    elif action == "post_journal":
        confirmed = st.checkbox(f"I have reviewed the closing journal for {year_text} and want to post it in {len(targets)} entities.")
    elif action == "create_journal":
        st.info(f"Creates the closing journal for **{year_text}** only, without posting.", icon=":material/info:")

go = st.button(
    f"{ACTIONS[action]} in {len(targets)} entities" if targets else ACTIONS[action],
    type="primary",
    icon=":material/play_arrow:",
    disabled=not (can_write and targets and confirmed),
)

if go:
    c = data.client()
    results, steps = [], []
    with st.status(f"{ACTIONS[action]}...", expanded=True) as box:
        for entity in targets:
            s = by_entity[entity]
            st.write(entity)
            row = {"entity": entity, "result": "Succeeded", "retained_earnings": None, "message": ""}
            try:
                last_no = c.last_log_entry_no(s["company_id"])
                # Pin the run to the chosen year. The daily job runs unpinned, so scheduling clears it.
                target = year_end.isoformat() if year_end else data.BLANK_DATE
                c.update_setup(s["company_id"], s["setup"]["id"], {"targetFiscalYearEnd": target})
                try:
                    c.run_action(s["company_id"], s["setup"]["id"], action)
                except BCError as exc:
                    row["result"], row["message"] = "Failed", str(exc)
                # Read every step the run logged, including the error entry of a failed run.
                new_logs = c.log_entries(s["company_id"], top=100, after_entry_no=last_no)
                new_logs.reverse()
                for l in new_logs:
                    steps.append(
                        {
                            "entity": entity,
                            "status": data.status_label(l.get("status")),
                            "step": data.nice_action(l["logAction"]),
                            "fiscal_year_end": None if l.get("fiscalYearEnd", data.BLANK_DATE) == data.BLANK_DATE
                            else pd.Timestamp(l["fiscalYearEnd"]).date(),
                            "document_no": l.get("documentNo", ""),
                            "lines": l.get("noOfLines") or None,
                            "retained_earnings": l.get("retainedEarningsAmount") or None,
                            "message": l.get("message", ""),
                        }
                    )
                if any(l.get("status") == "Failed" for l in new_logs):
                    row["result"] = "Failed"
                amounts = [l["retainedEarningsAmount"] for l in new_logs if l.get("retainedEarningsAmount")]
                row["retained_earnings"] = amounts[-1] if amounts else None
                if not row["message"]:
                    row["message"] = "; ".join(
                        l["message"] for l in new_logs if l.get("message") and l.get("status") != "Success"
                        and data.nice_action(l["logAction"]) not in ("Run Started", "Run Completed")
                    )
                if action == "create_job" and not new_logs:
                    row["message"] = "Job Queue entry in place"
                elif not new_logs and row["result"] != "Failed":
                    # From version 1.0.0.3 every run logs at least Run Started and Run Completed.
                    row["result"] = "Nothing logged"
                    row["message"] = (
                        "Business Central reported success but logged nothing, so nothing was done. This entity is "
                        "running an extension version older than 1.0.0.3. Publish the latest version to see each step."
                    )
            except BCError as exc:
                row["result"], row["message"] = "Failed", str(exc)
            results.append(row)
        failed = sum(r["result"] == "Failed" for r in results)
        box.update(
            label=f"{ACTIONS[action]}: {len(results) - failed} succeeded, {failed} failed",
            state="error" if failed else "complete",
            expanded=False,
        )
    data.load_status.clear()
    st.session_state.run_results = {"action": action, "rows": results, "steps": steps}

if outcome := st.session_state.get("run_results"):
    st.subheader(f"Last run: {ACTIONS[outcome['action']]}")
    st.dataframe(
        pd.DataFrame(outcome["rows"]),
        hide_index=True,
        column_config={
            "entity": "Entity",
            "result": "Result",
            "retained_earnings": st.column_config.NumberColumn("Retained earnings", format="localized"),
            "message": st.column_config.TextColumn("Notes and errors", width="large"),
        },
    )
    if outcome.get("steps"):
        st.markdown("**Every step, in order**")
        st.dataframe(
            pd.DataFrame(outcome["steps"]),
            hide_index=True,
            column_config={
                "entity": "Entity",
                "status": "Status",
                "step": "Step",
                "fiscal_year_end": st.column_config.DateColumn("FY end"),
                "document_no": "Document no.",
                "lines": st.column_config.NumberColumn("Lines"),
                "retained_earnings": st.column_config.NumberColumn("Retained earnings", format="localized"),
                "message": st.column_config.TextColumn("Message", width="large"),
            },
        )
