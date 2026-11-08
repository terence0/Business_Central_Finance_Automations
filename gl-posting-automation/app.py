from datetime import date

import streamlit as st

from src.bc_client import BusinessCentralClient
from src.config import load_companies, settings

st.set_page_config(page_title="BC Allow Posting From Updater", page_icon="📅", layout="wide")
st.title("Business Central - Allow Posting From Updater")
st.caption("Production-aware utility to update General Ledger Setup across selected entities.")

cfg = settings()

# Connect to Business Central
client = BusinessCentralClient(cfg)
client.authorize()

# Load companies directly from BC
bc_companies = client.get_companies()

company_names = sorted(
    [c["name"] for c in bc_companies]
)

with st.sidebar:
    st.subheader("Environment")
    st.write(f"Tenant: `{cfg.tenant_id}`")
    st.write(f"Environment: `{cfg.environment_name}`")
    st.write(f"Base URL: `{cfg.base_url}`")
    st.divider()
    publisher = st.text_input("Custom API publisher", value="contoso")
    group = st.text_input("Custom API group", value="financeautomation")
    version = st.text_input("Custom API version", value="v1.0")

if cfg.environment_name.lower() == "production" and not cfg.allow_production_updates:
    st.error("Production updates are blocked. Change BC_ENVIRONMENT_NAME to a Sandbox, or intentionally set ALLOW_PRODUCTION_UPDATES=true.")
    st.stop()

selected_entities = st.multiselect(
    "Select entities to update",
    options=company_names,
    default=["Contoso South Africa"] if "Contoso South Africa" in company_names else [],
)

new_date = st.date_input("Allow Posting From date", value=date.today(), format="YYYY-MM-DD")
dry_run = st.checkbox("Dry run only - preview without updating", value=True)
use_etag = st.checkbox("Use returned ETag for safer PATCH", value=True)

st.info("This app expects a small custom AL API page for General Ledger Setup. The standard Microsoft generalLedgerSetup API is suitable for reading/validation, but updates normally require a custom write-enabled API or AL action.")

if st.button("Run update", type="primary"):
    if not selected_entities:
        st.warning("Select at least one entity.")
        st.stop()

    client = BusinessCentralClient(cfg)
    results = []

    try:
        client.authorize()
        with st.spinner("Connecting to Business Central..."):
            for entity in selected_entities:
                row = {"entity": entity, "target_date": str(new_date), "status": "pending", "message": ""}
                try:
                    company_id = client.company_id_by_name(entity)
                    row["company_id"] = company_id
                    if dry_run:
                        setup = client.get_custom_gl_setup(
                            company_id=company_id,
                            publisher=publisher,
                            group=group,
                            version=version,
                        )
                        row["current_allowPostingFrom"] = str(setup)
                        row["status"] = "dry-run"
                        row["message"] = (
                            "BC response captured. "
                            "Check VS Code terminal for RAW RESPONSE."
                        )
                    else:
                        updated = client.patch_allow_posting_from(
                            company_id=company_id,
                            allow_posting_from=str(new_date),
                            publisher=publisher,
                            group=group,
                            version=version,
                            use_etag=use_etag,
                        )
                        row["status"] = "updated"
                        row["message"] = str(updated)
                except Exception as ex:
                    row["status"] = "failed"
                    row["message"] = str(ex)
                results.append(row)

        st.dataframe(results, use_container_width=True)
        if any(r["status"] == "failed" for r in results):
            st.warning("Some entities failed. Review the message column, fix the issue, and rerun for the failed entities only.")
        elif dry_run:
            st.success("Dry run completed successfully.")
        else:
            st.success("Selected entities were updated successfully.")
    except Exception as ex:
        st.error(f"Run failed before entity processing started: {ex}")
