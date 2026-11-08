from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from fyc import data
from fyc.bc_client import BCError

st.title("Posting dates")
st.caption(
    "Allow Posting From and To in each entity's User Setup. A blank pair means the user follows General Ledger "
    "Setup. With **Open posting window** on in the setup, the close sets these to the closing date only while the "
    "journal posts and puts them back straight after, so you should rarely need to change them here."
)

env = data.environment()
can_write = data.writes_allowed()
if not can_write:
    st.info("This environment is read-only in the app.", icon=":material/lock:")

status = [s for s in data.load_status(env) if s.get("extension") == "Installed"]
if not status:
    st.warning("No entity in this environment can see the extension yet. Install it first.", icon=":material/extension_off:")
    st.stop()
by_entity = {s["entity"]: s for s in status}

left_open = [s for s in status if (s.get("setup") or {}).get("postingWindowUser")]
if left_open:
    st.warning(
        "A posting window is open in: "
        + ", ".join(f'{s["entity"]} (user {s["setup"]["postingWindowUser"]})' for s in left_open)
        + ". A run is either posting right now or was cut off. The next run in that entity puts the saved dates back.",
        icon=":material/lock_open:",
    )

with st.container(horizontal=True, vertical_alignment="bottom"):
    selected = st.multiselect(
        "Entities",
        options=list(by_entity),
        default=[e for e, s in by_entity.items() if s.get("setup")],
        placeholder="Choose entities",
    )
    app_user_only = st.toggle("Only the app's user", value=True, help="The user the close runs as from this app.")

if not selected:
    st.stop()


@st.cache_data(ttl=60, show_spinner="Reading User Setup...")
def load_dates(environment_name: str, companies: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    c = data.get_client(environment_name)

    def read(item: tuple[str, str]) -> tuple[str, Any]:
        entity, company_id = item
        try:
            return entity, c.user_posting_dates(company_id)
        except BCError as exc:
            return entity, exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(read, companies))


def to_date(value: str | None) -> date | None:
    return None if not value or value == data.BLANK_DATE else date.fromisoformat(value)


def to_api(value: Any) -> str:
    return data.BLANK_DATE if value is None or pd.isna(value) else pd.Timestamp(value).date().isoformat()


results = load_dates(env, tuple((e, by_entity[e]["company_id"]) for e in selected))
failed = {e: r for e, r in results.items() if isinstance(r, BCError)}
if failed:
    st.error(
        "Could not read User Setup in: " + "; ".join(f"{e}: {r}" for e, r in failed.items())
        + ". These entities may still be on an older version of the extension.",
    )

rows = []
for entity, users in results.items():
    if entity in failed:
        continue
    app_user = (by_entity[entity].get("setup") or {}).get("currentUserId", "")
    shown = [u for u in users if u.get("isCurrentUser") or u["userId"] == app_user] if app_user_only else users
    for u in shown:
        rows.append({"entity": entity, "company_id": by_entity[entity]["company_id"], "id": u["id"],
                     "user_id": u["userId"], "is_app_user": bool(u.get("isCurrentUser")),
                     "allow_from": to_date(u.get("allowPostingFrom")), "allow_to": to_date(u.get("allowPostingTo"))})
    if app_user_only and not shown and app_user:
        # No User Setup row yet: saving dates here creates one.
        rows.append({"entity": entity, "company_id": by_entity[entity]["company_id"], "id": "",
                     "user_id": app_user, "is_app_user": True, "allow_from": None, "allow_to": None})

if not rows:
    st.info("No User Setup rows to show for the chosen entities.")
    st.stop()

original = pd.DataFrame(rows)
st.session_state.setdefault("dates_editor_version", 0)
edited = st.data_editor(
    original,
    key=f"dates_editor_{env}_{st.session_state.dates_editor_version}",
    hide_index=True,
    num_rows="fixed",
    disabled=not can_write,
    column_config={
        "entity": st.column_config.TextColumn("Entity", pinned=True, disabled=True),
        "company_id": None,
        "id": None,
        "user_id": st.column_config.TextColumn("User", disabled=True),
        "is_app_user": st.column_config.CheckboxColumn("App's user", disabled=True),
        "allow_from": st.column_config.DateColumn("Allow posting from", format="YYYY-MM-DD"),
        "allow_to": st.column_config.DateColumn("Allow posting to", format="YYYY-MM-DD"),
    },
    height="content" if len(original) <= 20 else 600,
)

pending = [
    (original.iloc[i], edited.iloc[i])
    for i in range(len(original))
    if to_api(original.iloc[i]["allow_from"]) != to_api(edited.iloc[i]["allow_from"])
    or to_api(original.iloc[i]["allow_to"]) != to_api(edited.iloc[i]["allow_to"])
]

if st.button(
    f"Save {len(pending)} rows" if pending else "Save changes",
    type="primary",
    icon=":material/save:",
    disabled=not (can_write and pending),
):
    c = data.client()
    saved = []
    with st.spinner("Saving to Business Central..."):
        for before, after in pending:
            values = {"allowPostingFrom": to_api(after["allow_from"]), "allowPostingTo": to_api(after["allow_to"])}
            try:
                if before["id"]:
                    c.update_user_posting_dates(before["company_id"], before["id"], values)
                else:
                    c.create_user_posting_dates(before["company_id"], {"userId": before["user_id"], **values})
                saved.append({"entity": before["entity"], "user": before["user_id"], "result": "Saved", "message": ""})
            except BCError as exc:
                saved.append({"entity": before["entity"], "user": before["user_id"], "result": "Failed",
                              "message": str(exc)})
    load_dates.clear()
    st.session_state.dates_editor_version += 1
    st.session_state.dates_results = saved
    st.rerun()

if saved := st.session_state.get("dates_results"):
    bad = [r for r in saved if r["result"] == "Failed"]
    (st.error if bad else st.success)(f"Saved {len(saved) - len(bad)} of {len(saved)} rows.")
    st.dataframe(pd.DataFrame(saved), hide_index=True)
