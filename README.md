# GraceDays

GraceDays is a Python-first assistant that helps people track post-purchase obligations such as return windows, trial cancellations, renewals, and warranty dates. It aims to show evidence for extracted dates and never invents a missing deadline.

> Current status: Phase 0 starter scaffold only. The MCP server, database operations, extraction pipeline, and assistant are not implemented yet.

## Requirements

- Python 3.12
- Git
- One terminal for the MCP server and one for Streamlit in later phases

## Windows PowerShell setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

For initial setup, keep `LLM_PROVIDER=mock` in `.env`. Do not add API keys until a live provider is implemented. Never commit `.env`.

## Run the setup screen

```powershell
streamlit run src/gracedays/app.py
```

The screen only validates and displays configuration. It does not yet connect to an MCP server.

## Tests

```powershell
pytest -q
```

## Planned build order

1. Phase 0: project and configuration scaffold
2. Phase 1: MCP SDK compatibility spike (hello tool over Streamable HTTP)
3. Phase 2: SQLite schema, repository, clock, date rules and tests
4. Phase 3: MCP tool contracts and client gateway
5. Phase 4: evidence-backed extraction and review-before-save
6. Phase 5: dashboard and synthetic demo data
7. Phase 6: conversational agent, tool activity and action drafts
8. Phase 7–8: hardening, documentation and hackathon submission

## Security notes

This is a local development scaffold, not a production service. The intended unauthenticated MCP server must bind to `127.0.0.1` only. Do not paste real payment-card data or commit real purchase emails, API keys, or the local database.
