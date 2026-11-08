# Launchers: Production / Sandbox

One-click Windows launchers for every automation in this repository, so finance users never open a terminal, and so testing in a sandbox needs no code or config change.

```
launchers/
├── Production/   Run <tool>.bat               -> Production
├── Sandbox/      Run <tool> (Sandbox).bat     -> the sandbox
├── _bc_environment.cmd   which environment, port offset, the sandbox name (one line to change)
├── _find_project.cmd     finds each project folder from the launcher's own location
├── _ensure_venv.cmd      per-user virtual environment, rebuilt when requirements.txt changes
└── _find_py312.cmd       locates a Python 3.12 interpreter for projects that pin it
```

## Design

- **A sandbox launcher only calls its Production twin with the word `sandbox`**, so the two can never drift apart.
- `_bc_environment.cmd` sets `BC_ENVIRONMENT_NAME`, which every app reads, plus a **port offset of +100** so Production and sandbox can be open side by side. A sandbox console window turns green.
- **No hard-coded paths.** Synced document-library paths differ per user (OneDrive root suffixes, library naming), so `_find_project.cmd` derives the library root from its own location and confirms each project by a marker file.
- **Virtual environments live under `%LOCALAPPDATA%`**, not in the synced folder: a venv's activation scripts hard-code the creating machine's path, so a shared one works for its creator only. `_ensure_venv.cmd` hashes `requirements.txt` and reinstalls only when it changes.
- Friendly preflight messages (Python missing, folder still syncing, config missing) instead of stack traces.

| Tool | Production port | Sandbox port |
|---|---|---|
| General Ledger Query | 8502 | 8602 |
| Trial Balance | 8503 | 8603 |
| VAT Recon | 8504 | 8604 |
| Customer Ageing | 8505 | 8605 |
| Chart of Accounts | 8506 | 8606 |
| Fiscal Year Close | 8510 | 8610 |
| Cost Centre Dimensions | 8511 | 8611 |
| GL Posting | 8512 | 8612 |
| Planful Push Controller | 8513 | 8613 |
