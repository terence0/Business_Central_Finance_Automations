# Planful Push Controller

Runs the month-end **Summary Transaction** push from Business Central to Planful (FP&A) for many entities from one screen, instead of running the report in each company by hand.

## How it works

- A Business Central custom API (`planfulPushRuns`) accepts the run parameters (dates, G/L account filter, send to Planful, filter on period, export to XML) and runs the Planful connector's report unattended through a batch runner.
- `bc_client.py` signs in with client credentials, lists the companies and posts one run per selected company.
- `app.py` (Streamlit) collects the parameters, shows a run summary, runs the push per entity and keeps a downloadable log.

## Safety

- A sandbox is a copy of Production, so its Planful connector setup may point at **live** Planful. From any environment other than Production, *Send Data to Planful* is forced off, both in the page and in the client itself, so the Business Central side can be tested without anything reaching Planful.
- The page shows the environment in a banner (red for Production, green for a sandbox).

## Setup

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Requires Python 3.12.
