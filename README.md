# Finance Automation Portfolio

Automations I built as a finance-systems analyst for a multinational group running **Microsoft Dynamics 365 Business Central** across 30+ legal entities. Each one replaced a manual, entity-by-entity process with a tool that runs across every company at once, with a dry run, a review step and an audit trail.

All company names, identifiers, people and data have been removed or made generic ("Contoso"). No credentials are included: each project reads its secrets from a local `.env` / `config.json` that is git-ignored, and ships an example file with placeholders.

## Projects

| Project | What it does | Stack |
|---|---|---|
| [bc-query-tool](bc-query-tool/) | A suite of self-service finance extracts over Business Central: General Ledger, Trial Balance, Fixed Assets, Customer Ageing (ECL), VAT return & reconciliation packs, and a chart-of-accounts roll-out tool that writes to every entity | Python, Streamlit, OData, pandas, xlsxwriter |
| [fiscal-year-close](fiscal-year-close/) | Closes the fiscal year and posts the income-statement closing journal for many entities at once, with posting-window control and step-by-step logging | AL (BC extension), Python, Streamlit |
| [cost-centre-dimension-automation](cost-centre-dimension-automation/) | Creates a cost-centre dimension value and its default-dimension rules in every selected entity | AL API pages, Python, Streamlit |
| [gl-posting-automation](gl-posting-automation/) | Opens and closes posting periods ("Allow Posting From") across entities in one action | AL API page, Python, Streamlit |
| [bc-user-permission-export](bc-user-permission-export/) | Exposes user / permission-set assignments across companies for licence and access reviews | AL |
| [planful-push-controller](planful-push-controller/) | Triggers the month-end push of summary transactions from Business Central to Planful (FP&A) for many entities from one screen | Python, Streamlit, BC custom API |
| [approval-routing](approval-routing/) | Generates the accounts-payable approval-routing import for an AP automation platform from a maintained routing workbook, and emails a change report | Python, pandas, Outlook COM |
| [launchers](launchers/) | One-click Windows launchers with a **Production / Sandbox** switch for every tool above | Windows batch |

## Patterns used throughout

- **Dry run, review, then write.** Every tool that changes Business Central shows exactly what it will do per entity first, and only writes after an explicit approval. Anything changed after the dry run invalidates it.
- **Read back and verify.** After writing, records are read back and compared field by field; results and an audit log are kept.
- **Production / Sandbox without editing code.** One environment variable (`BC_ENVIRONMENT_NAME`), set by the launcher, decides where a tool connects. Sandbox runs open on a different port, are visibly marked, and never touch production outputs (e.g. a sandbox VAT run never publishes to the shared report folder; a sandbox Planful push never sends to Planful).
- **Production guards.** Writes to Production need an explicit `ALLOW_PRODUCTION_UPDATES` flag and/or an in-app unlock.
- **Fail loudly, never silently short.** A company Business Central refuses stops the run instead of producing a file that looks complete. OData paging (`@odata.nextLink`) is always followed.
- **Server-side filtering.** Extracts filter by date, account and company in the OData query rather than downloading whole ledgers.
- **No machine-specific paths.** Every path is derived from the script's own location; per-user virtual environments live outside synced folders.

## Running a project

Each folder has its own README. In short: create a virtual environment, `pip install -r requirements.txt`, copy the example config (`.env.example` or `config/config.example.json`) to the real file name, fill in an Entra ID app registration that has access to Business Central, and run `streamlit run <app>.py`. The AL extensions are built with the AL Language extension for VS Code and published to a sandbox first.

## Author

Terence Matasva
