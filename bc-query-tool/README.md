# Business Central Query Tool

A set of Streamlit apps that give the finance team self-service extracts and reconciliations from Microsoft Dynamics 365 Business Central, across every legal entity at once, without waiting on a Power BI refresh or exporting entity by entity.

| App | File | What it produces |
|---|---|---|
| General Ledger Query | `app.py` | GL entries for chosen companies, dates and accounts, to Excel |
| Trial Balance | `trialBalance.py` | Trial balances per company and period |
| Fixed Asset Listing | `fixedAssets.py` | Fixed asset register with depreciation books |
| Customer Ageing | `CustomerAgeing.py` | Debtors ageing for the year-end notes (ECL), rebuilt to the cut-off from detailed ledger entries so the answer is the same whenever it is run |
| VAT Return and Recon | `vatRecon.py`, `vatPacks.py` | One VAT reconciliation workbook per entity per month (and a year-to-date file), with a summary matrix, risk sheet and checks |
| Chart of Accounts | `coaSetup.py`, `coaCore.py` | Creates a G/L account identically in every entity, with a dry run, approval and read-back verification |

`QueryTool.bat` is a menu over all of them; `query.py` holds the shared Business Central client.

## Highlights

**Extraction (`query.py`)**
- Filters by posting date, account and company **server-side** in the OData query, instead of downloading whole ledgers and filtering afterwards (the Power BI model this replaced pulled the entire group ledger on every refresh).
- Follows `@odata.nextLink` paging, so large companies are never silently truncated.
- **Stops the run** if Business Central refuses a company, rather than publishing a short file that looks complete.
- Drops optional fields a web service does not expose and retries, so one tenant's page differences do not break the extract.

**VAT reconciliation packs (`vatPacks.py`)**
- Classifies every ledger entry against a maintained account map and form-type rules, and writes workbooks with `xlsxwriter`: every summary figure is a live `SUMIFS` over the data sheet, so correcting a row moves the return.
- Comments typed into a pack's Risk sheet are harvested back into a comments file and **carried forward** into every rebuild of that period (one-way merge: a blank never deletes a saved comment).
- Packs are cell-for-cell identical to the central VAT automation they align with (tested by rebuilding the same months and diffing every cell).
- The classification engine (`vat_core.py`, `vat_workbook.py`) belongs to a colleague's central VAT automation and is **not included** here, so the VAT page will not run on its own. `vatWorkbook.py` is my earlier version, which built PivotTable workbooks through Excel COM.

**Chart of Accounts roll-out (`coaCore.py`, `coaSetup.py`)**
- Enter an account once (every G/L Account Card field plus default dimensions), or upload several from an Excel template, and create it in every selected entity.
- **Plan, review, apply, verify:** the dry run shows per entity whether the account will be created, already exists (never changed) or cannot be created, and why. Approval is invalidated by any later edit. After writing, each account is read back and compared field by field, and every write is appended to an audit log.
- **Entity-specific posting setup:** posting groups differ by entity and country, so each entity copies them from its *own* copy of a reference account. When the reference is missing somewhere, the tool suggests one with the same setup that exists in every entity.
- Validates codes against each entity first (VAT groups, dimensions and values, subcategories) so Business Central never rejects a half-applied batch.

**Production / Sandbox (`config/bc_env.py`)**
- `BC_ENVIRONMENT_NAME`, set by the [launchers](../launchers/), rewrites the configured URLs to the chosen environment, so `config.json` is never edited. Each page shows the environment in a banner; sandbox VAT runs publish to a local folder instead of the shared report library.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy config\config.example.json config\config.json   # then fill in the app registration
streamlit run app.py
```

`config.json` needs an Entra ID app registration with access to Business Central, and the company list. It is git-ignored; never commit the real one. `QueryTool.bat` builds a per-user virtual environment outside synced folders and launches any of the apps from a menu.
