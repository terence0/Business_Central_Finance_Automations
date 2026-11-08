# AP Approval Routing Generator

Generates the **approval-routing import** for an accounts-payable automation platform from a routing workbook the finance team maintains (vendors, cost centres, budget holders and limit approvers per entity), so routing changes are made in one spreadsheet instead of by hand in the platform.

## How it works

- `routingScript.py` reads the platform's routing export and the routing workbook, and rebuilds each approval gateway (review, budget-holder approval, limit approver, head-office approval, payment approval) for every entity.
- **Entity-specific overrides:** the same cost centre can route to different approvers in different entities; an override sheet takes precedence over the default approver, and unrecognised entries are logged and ignored rather than guessed.
- `test.py` compares the generated import with the previous one and writes the differences.
- `notifier.py` emails the generated file and an HTML table of the changes through Outlook, so every routing change is visible before it is imported.
- Everything is logged to the console and a log file, so a run started from a launcher shows live progress.

The input files (routing workbook, platform export) are company data and are not included.

## Run

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
python routingScript.py
```

Requires Outlook desktop (signed in) for the email step.
