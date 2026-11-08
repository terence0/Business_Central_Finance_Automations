from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.bc_client import BusinessCentralClient
from src.config import settings

st.set_page_config(
    page_title="BC Cost Centre Dimension Automation",
    page_icon="🧩",
    layout="wide",
)

st.title("Business Central - Cost Centre Dimension Automation")
st.caption("Create COST CENTRE dimension values across selected Business Central entities.")

cfg = settings()

if cfg.environment_name.lower() == "production" and not cfg.allow_production_updates:
    st.error(
        "Production updates are blocked. Change BC_ENVIRONMENT_NAME to a Sandbox, "
        "or intentionally set ALLOW_PRODUCTION_UPDATES=true."
    )
    st.stop()

client = BusinessCentralClient(cfg)
client.authorize()

with st.sidebar:
    st.subheader("Environment")
    st.write(f"Tenant: `{cfg.tenant_id}`")
    st.write(f"Environment: `{cfg.environment_name}`")
    st.write(f"Base URL: `{cfg.base_url}`")
    st.write(f"API: `{cfg.api_publisher}/{cfg.api_group}/{cfg.api_version}`")

st.info(
    "This app expects the custom AL API pages included in the /al folder to be installed "
    "in the target Business Central environment. Keep Dry Run ticked first."
)

bc_companies = client.get_companies()
company_names = sorted([c["name"] for c in bc_companies])

st.subheader("Cost Centre Details")

col1, col2 = st.columns(2)

with col1:
    dimension_code = st.text_input("Dimension Code", value="COST CENTRE")
    cost_centre_code = st.text_input("Cost Centre Code", value="")

with col2:
    cost_centre_name = st.text_input("Cost Centre Name", value="")
    effective_date = st.date_input("Reference date", value=date.today(), format="YYYY-MM-DD")

st.session_state.setdefault("selected_entities", [])


def _toggle_select_all_entities() -> None:
    if st.session_state.select_all_entities:
        st.session_state.selected_entities = company_names.copy()
    else:
        st.session_state.selected_entities = []


st.checkbox(
    "Select all entities",
    key="select_all_entities",
    on_change=_toggle_select_all_entities,
)

selected_entities = st.multiselect(
    "Select entities / companies",
    options=company_names,
    key="selected_entities",
)

st.subheader("Default Dimension Options")

apply_to_gl_accounts = st.checkbox(
    "Apply COST CENTRE default-dimension rule to all G/L Accounts",
    value=False,
)

default_dimension_mode = st.selectbox(
    "Default dimension mode",
    options=[
        "Code Mandatory - do not force value",
        "Same Code - force this cost centre value",
    ],
    index=0,
    help=(
        "Recommended: Code Mandatory - do not force value. "
        "Use Same Code only if you intentionally want every G/L Account to default to this cost centre."
    ),
)

dry_run = st.checkbox("Dry run only - preview without creating", value=True)

if st.button("Run Cost Centre Automation", type="primary"):
    if not selected_entities:
        st.warning("Select at least one entity.")
        st.stop()

    if not cost_centre_code.strip() or not cost_centre_name.strip():
        st.warning("Enter both Cost Centre Code and Cost Centre Name.")
        st.stop()

    rows = []

    with st.spinner("Processing selected entities..."):
        for entity in selected_entities:
            row = {
                "entity": entity,
                "dimension_code": dimension_code,
                "cost_centre_code": cost_centre_code,
                "cost_centre_name": cost_centre_name,
                "reference_date": str(effective_date),
                "dry_run": dry_run,
                "status": "pending",
                "message": "",
            }

            try:
                company_id = client.company_id_by_name(entity)
                row["company_id"] = company_id

                result = client.create_cost_centre_across_company(
                    company_id=company_id,
                    dimension_code=dimension_code.strip(),
                    cost_centre_code=cost_centre_code.strip(),
                    cost_centre_name=cost_centre_name.strip(),
                    apply_to_gl_accounts=apply_to_gl_accounts,
                    default_dimension_mode=default_dimension_mode,
                    dry_run=dry_run,
                )

                row["dimension_value_action"] = result.get("dimensionValueAction")
                row["gl_account_rules_created"] = result.get("glAccountRulesCreated")
                row["gl_account_rules_skipped"] = result.get("glAccountRulesSkipped")
                row["message"] = "; ".join(result.get("messages", []))
                row["status"] = "dry-run" if dry_run else "success"

            except Exception as exc:
                row["status"] = "failed"
                row["message"] = str(exc)

            rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    if any(r["status"] == "failed" for r in rows):
        st.warning("Some entities failed. Review the message column and terminal output.")
    elif dry_run:
        st.success("Dry run completed successfully.")
    else:
        st.success("Cost Centre automation completed successfully.")
