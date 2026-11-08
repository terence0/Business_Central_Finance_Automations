# Fiscal Year Close Automation

Closes a fiscal year in Business Central and posts the *Close Income Statement* journal, for one entity or many at once, from one screen. The result is the same as doing it by hand (*Accounting Periods > Close Year*, then *Close Income Statement*): every income-statement account ends the year at zero and the net result goes to retained earnings.

## Two parts

**A Business Central extension (AL, `src/`)** does the work inside Business Central:

| Object | Role |
|---|---|
| `FYCCloseSetup` table / page / API | Per-company setup: journal template and batch, retained-earnings account, close by global dimensions, run mode |
| `FYCCloseManagement`, `FYCCloseRunner` codeunits | Close the year, build the closing journal from an income-statement net-change query (`FYCISNetChange`), optionally post it |
| `FYCPostingWindow` codeunit | Opens the posting window **only while the closing journal posts**, so users' posting dates never need widening for the close |
| `FYCRelaxedDefaultDim`, `FYCUnblockedDimValue` | Temporarily relax default-dimension rules and blocked dimension values the closing lines would trip over, and restore them afterwards |
| `FYCCloseLog` table / page / API, `FYCCloseLogger` | Every step logged with action and status enums, readable in Business Central and over the API |
| `FYCJobQueueHandler` | Optional scheduled run through the job queue |
| `FYCUserSetupAPI` | Read and change user posting dates from the control panel |
| `FYCCloseAuto` permission set | What the integration user needs |

**A control panel (Python, `streamlit_app/`)** drives the extension in every company of an environment over its custom API:

- **Overview:** each entity's setup status and open fiscal year
- **Setup:** one editable grid for every entity; copy one entity's setup to others, or bring tested setups in from a sandbox
- **Run:** close the year and create the journal for many entities, review, then post the reviewed journal
- **Posting dates:** manage user posting windows
- **Log:** every step, in order

## Safety

- Production is **locked** in the control panel: it needs `ALLOW_PRODUCTION_UPDATES=true` in `.env` *and* the environment name typed in to unlock it for the session. Sandboxes are unlocked and marked green.
- Closing and posting are separate steps, with a review in between. *Post automatically* is off by default.
- Everything is logged in Business Central, not just in the app.

## Setup

1. Build the extension with the AL Language extension for VS Code and publish it to a **sandbox** first; grant the app registration the `FYC CLOSE AUTO` permission set.
2. Control panel:
   ```powershell
   cd streamlit_app
   python -m venv .venv; .\.venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env      # tenant, app registration, environment
   streamlit run streamlit_app.py
   ```
