# Cost Centre Dimension Automation

Creates a new **cost centre** dimension value in every selected Business Central company, and optionally the default-dimension rules on the G/L accounts that need it, from one Streamlit screen. Previously this was done company by company.

## How it works

- **AL API pages** (`al_project/src/`, earlier version in `al/`) expose Dimension Values, Default Dimensions and G/L Accounts through a custom API (`/api/contoso/financeautomation/v1.0/...`), because the standard API does not cover these writes.
- **Python client** (`src/bc_client.py`) signs in with an Entra ID app registration (client credentials), lists the companies dynamically and calls the custom API per company.
- **Streamlit UI** (`app.py`): choose the entities, enter the value, run a **dry run** first, then apply; a results table shows the outcome per entity.

## Safety

- Writes to Production are refused unless `ALLOW_PRODUCTION_UPDATES=true` is set deliberately; the environment comes from `BC_ENVIRONMENT_NAME` (set by the [launchers](../launchers/)).
- Dry run by default.

## Setup

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # tenant, app registration, environment, API route
streamlit run app.py
```

Publish the AL extension to a sandbox first. Requires Python 3.12 (pinned dependency versions).
