# GL Posting Period Automation

Updates **General Ledger Setup > Allow Posting From** across many Business Central entities in one action, for opening and closing posting periods at month end.

## Why a custom API page

Microsoft's standard `generalLedgerSetup` API is read-only. `al/GLSetupApi.Page.al` is a small custom API page over the General Ledger Setup record with modify allowed, published under `/api/contoso/financeautomation/v1.0/glSetups`. The Python client patches it with `If-Match` (optimistic concurrency), so a record changed in the meantime is not overwritten.

## How it works

- `src/bc_client.py`: client-credentials sign-in, company discovery, read and patch of each company's GL setup.
- `app.py` (Streamlit): pick entities and the new date, **dry run** (shows current vs new per entity), then apply; results per entity.

## Safety

- Dry run is on by default.
- Production is refused unless `ALLOW_PRODUCTION_UPDATES=true`; the environment comes from `BC_ENVIRONMENT_NAME`, and an environment chosen by the [launchers](../launchers/) takes precedence over `.env`.

## Setup

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```
