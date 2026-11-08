from typing import Any

import pandas as pd
import streamlit as st

from fyc import data
from fyc.bc_client import BCError

st.title("Setup per entity")
st.caption(
    "Each entity keeps its own setup in Business Central. Edit the grid, then save. "
    "You can paste a column from Excel into the grid."
)

env = data.environment()
can_write = data.writes_allowed()
if not can_write:
    st.info("This environment is read-only in the app.", icon=":material/lock:")

original = data.setup_frame(data.load_status(env))
if original.empty:
    st.warning("No entity in this environment can see the extension yet. Install it first.", icon=":material/extension_off:")
    st.stop()

st.session_state.setdefault("setup_editor_version", 0)


def save(changes: list[tuple[pd.Series, dict[str, Any]]]) -> list[dict[str, str]]:
    """Creates or updates the setup in each company. Returns one result row per company."""
    c = data.client()
    results = []
    for row, values in changes:
        try:
            if row["has_setup"]:
                c.update_setup(row["company_id"], row["setup_id"], values)
                results.append({"entity": row["entity"], "result": "Updated", "message": ", ".join(values)})
            else:
                c.create_setup(row["company_id"], values)
                results.append({"entity": row["entity"], "result": "Created", "message": ""})
        except BCError as exc:
            results.append({"entity": row["entity"], "result": "Failed", "message": str(exc)})
    data.load_status.clear()
    st.session_state.setup_editor_version += 1
    st.session_state.setup_results = results
    return results


def changed_values(before: pd.Series, after: pd.Series) -> dict[str, Any]:
    if not before["has_setup"]:
        # A new setup is created with every value from the grid.
        return {f.api: data.to_api(f, after[f.api]) for f in data.SETUP_FIELDS}
    return {
        f.api: data.to_api(f, after[f.api])
        for f in data.SETUP_FIELDS
        if not data.same(f, before[f.api], after[f.api])
    }


column_config: dict[str, Any] = {
    "entity": st.column_config.TextColumn("Entity", pinned=True, disabled=True),
    "company_id": None,
    "setup_id": None,
    "has_setup": st.column_config.CheckboxColumn("Saved in BC", disabled=True),
}
for f in data.SETUP_FIELDS:
    if f.kind == "bool":
        column_config[f.api] = st.column_config.CheckboxColumn(f.label, help=f.help or None)
    elif f.kind == "int":
        column_config[f.api] = st.column_config.NumberColumn(f.label, help=f.help or None, min_value=0, step=1)
    elif f.kind == "date":
        column_config[f.api] = st.column_config.DateColumn(f.label, help=f.help or None, format="YYYY-MM-DD")
    else:
        column_config[f.api] = st.column_config.TextColumn(f.label, help=f.help or None)

edited = st.data_editor(
    original,
    key=f"setup_editor_{env}_{st.session_state.setup_editor_version}",
    hide_index=True,
    num_rows="fixed",
    disabled=not can_write,
    column_config=column_config,
    height="content" if len(original) <= 20 else 600,
)

pending = []
for i in range(len(original)):
    before, after = original.iloc[i], edited.iloc[i]
    touched = any(not data.same(f, before[f.api], after[f.api]) for f in data.SETUP_FIELDS)
    if touched:
        pending.append((before, changed_values(before, after)))

with st.container(horizontal=True, vertical_alignment="center"):
    if st.button(
        f"Save {len(pending)} entities" if pending else "Save changes",
        type="primary",
        icon=":material/save:",
        disabled=not (can_write and pending),
    ):
        with st.spinner("Saving to Business Central..."):
            save(pending)
        st.rerun()
    if pending:
        st.caption("Entities with unsaved changes: " + ", ".join(str(r["entity"]) for r, _ in pending))

if results := st.session_state.get("setup_results"):
    failed = [r for r in results if r["result"] == "Failed"]
    (st.error if failed else st.success)(
        f"Saved {len(results) - len(failed)} of {len(results)} entities."
        + (" Business Central rejected the rest. See the messages below." if failed else "")
    )
    st.dataframe(pd.DataFrame(results), hide_index=True)

st.subheader("Copy settings to other entities")
st.caption(
    "Use this to roll out one entity's settings. Account numbers and journal batches must exist in every target entity, "
    "or Business Central rejects the change for that entity."
)
with st.form("copy_settings", border=True):
    source = st.selectbox("Copy from", original["entity"].tolist())
    targets = st.multiselect("Copy to", original["entity"].tolist(), placeholder="Choose entities")
    fields = st.multiselect(
        "Settings to copy",
        options=[f.api for f in data.SETUP_FIELDS],
        default=[f.api for f in data.SETUP_FIELDS if f.api != "enabled"],
        format_func=lambda api: data.FIELD_BY_API[api].label,
    )
    submitted = st.form_submit_button("Copy settings", icon=":material/content_copy:", disabled=not can_write)

if submitted:
    targets = [t for t in targets if t != source]
    if not targets or not fields:
        st.warning("Choose at least one other entity and one setting.")
    else:
        src = original[original["entity"] == source].iloc[0]
        changes = []
        for target in targets:
            row = original[original["entity"] == target].iloc[0]
            if row["has_setup"]:
                values = {k: data.to_api(data.FIELD_BY_API[k], src[k]) for k in fields}
            else:
                merged = row.copy()
                for k in fields:
                    merged[k] = src[k]
                values = {f.api: data.to_api(f, merged[f.api]) for f in data.SETUP_FIELDS}
            changes.append((row, values))
        with st.spinner(f"Copying to {len(changes)} entities..."):
            save(changes)
        st.rerun()

st.subheader("Copy setups from another environment")
st.caption(
    "Brings setups tested in a sandbox into this environment, for example before the first production close. "
    "Entities are matched by name. Enabled is never copied, so no daily job starts. Check each copied row before running."
)
with st.form("copy_environment", border=True):
    source_env = st.text_input(
        "Copy from environment", value="" if env == "Sandbox_Test" else "Sandbox_Test"
    )
    if st.form_submit_button("Show setups to copy", icon=":material/search:"):
        st.session_state.copy_source_env = source_env.strip()

source_env = st.session_state.get("copy_source_env")
if source_env and source_env == env:
    st.warning("Choose an environment other than the one open now.")
elif source_env:
    try:
        source_status = data.load_status(source_env)
    except Exception as exc:  # noqa: BLE001 - show any connection problem to the user
        st.error(f"Could not read **{source_env}**. {exc}")
    else:
        here = set(original["entity"])
        source_setups = {s["entity"]: s["setup"] for s in source_status if s.get("setup") and s["entity"] in here}
        if not source_setups:
            st.info(f"No entity in **{source_env}** has a setup that matches an entity here.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "entity": e,
                            "retained_earnings": s.get("retainedEarningsAccount"),
                            "earliest_fy_start": s.get("earliestFiscalYearStart"),
                            "journal": f'{s.get("journalTemplateName")} / {s.get("journalBatchName")}',
                            "dims": ", ".join(
                                n for n, k in (("BU", "closeByBusinessUnit"), ("Dim 1", "closeByGlobalDimension1"),
                                               ("Dim 2", "closeByGlobalDimension2")) if s.get(k)
                            ),
                            "post_automatically": bool(s.get("postAutomatically")),
                            "already_set_up_here": bool(original.loc[original["entity"] == e, "has_setup"].iloc[0]),
                        }
                        for e, s in source_setups.items()
                    ]
                ),
                hide_index=True,
                column_config={
                    "entity": "Entity",
                    "retained_earnings": "Retained earnings acc.",
                    "earliest_fy_start": "Earliest FY start",
                    "journal": "Journal",
                    "dims": "Close by",
                    "post_automatically": st.column_config.CheckboxColumn("Post automatically"),
                    "already_set_up_here": st.column_config.CheckboxColumn(
                        "Set up here", help="Ticked rows are overwritten with the copied values."
                    ),
                },
            )
            chosen = st.multiselect(f"Entities to copy from {source_env}", list(source_setups), default=list(source_setups))
            if st.button(
                f"Copy {len(chosen)} setups into {env}",
                icon=":material/content_copy:",
                disabled=not (can_write and chosen),
            ):
                changes = []
                for entity in chosen:
                    row = original[original["entity"] == entity].iloc[0]
                    values = {
                        f.api: data.to_api(f, data.from_api(f, source_setups[entity].get(f.api)))
                        for f in data.SETUP_FIELDS
                        if f.api != "enabled"
                    }
                    if not row["has_setup"]:
                        values["enabled"] = False
                    changes.append((row, values))
                with st.spinner(f"Copying {len(changes)} setups from {source_env}..."):
                    save(changes)
                st.session_state.pop("copy_source_env", None)
                st.rerun()
