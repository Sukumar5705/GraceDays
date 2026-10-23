# GraceDays

**An evidence-first assistant for tracking the deadlines that follow a purchase.**

GraceDays helps people keep track of return windows, trial cancellations, subscription renewals, and warranty dates without connecting to their inbox or retailer accounts. Paste an order confirmation or policy excerpt, review the extracted details and their supporting evidence, and save the record to your GraceDays account.

> **Core principle:** GraceDays should make deadlines easier to manage without inventing dates or claiming that an external action happened when it did not.

## What it does

- **Capture and review purchase details.** Paste order-confirmation or policy text and review the proposed fields before saving.
- **Extract evidence-backed deadlines.** Show the source excerpt associated with a date. Unclear, unsupported, or missing dates remain flagged for review instead of being silently guessed.
- **See what needs attention.** The dashboard surfaces overdue, due-today, and upcoming deadlines, alongside active purchases.
- **Ask about saved records.** Use the conversational assistant to look up purchases and deadlines. Answers about saved records are based on MCP tool results, and the app shows tool activity and supporting evidence where available.
- **Manage purchase status.** Update the local status of a purchase (active, returned, cancelled, or resolved) without performing an external return or cancellation.
- **Draft next-step messages.** Generate a return or subscription-cancellation message for you to review. GraceDays does not send the message.
- **Try synthetic demo records.** Seed or reset demo-only purchases without intentionally removing your non-demo records.
- **Run in mock mode.** The default mock provider supports an offline-style demo without an LLM API key. A configured OpenAI-compatible provider is also supported.

## How it works

GraceDays uses a small Python application with a separate Model Context Protocol (MCP) server and a Turso database.

```text
Streamlit UI
    |  MCP client over Streamable HTTP
    v
GraceDays MCP server
    |  Repository / validation logic
    v
Turso database

Capture text -> extraction provider -> validation and date rules
             -> user review -> confirmed saved record
```

- **Interface:** Streamlit provides the Dashboard, Capture & review, Assistant, and Purchases views.
- **MCP interface:** The UI talks to the separate MCP server at the configured URL. The assistant has an explicit allowlist of read and limited purchase-status-update/draft tools; save, delete, and demo-data operations are excluded from assistant calls.
- **Persistence:** Turso stores purchase records, deadlines, evidence, and status changes.
- **Extraction and dates:** The extraction service proposes structured fields and evidence excerpts. Python validation checks the proposed data, verifies source excerpts, parses supported dates, and handles supported relative deadline rules.
- **Grounding and safety:** The assistant is instructed to use saved records for record-specific answers. A grounding guard checks date claims against tool results, and external-action claims are constrained.
- **Privacy:** GraceDays does not read an inbox or retailer account. Text pasted into Capture & review is sent to the provider configured in your environment; card-like number patterns are masked before provider calls. Review the provider's privacy terms before using real purchase text.

## Technology stack

- Python 3.12
- Streamlit
- Model Context Protocol (MCP) Python SDK
- Pydantic
- Turso / libSQL through the `turso_serverless` Python package
- `python-dateutil`, `python-dotenv`, `httpx`, and pandas
- pytest and pytest-asyncio for tests

## Requirements

- Python **3.12**
- A Turso database and its database URL and authentication token
- Git
- Optional: an API key for an OpenAI-compatible chat-completions provider. This is not required when `LLM_PROVIDER=mock`.

## Setup (Windows PowerShell)

Run these commands from the repository root, where `pyproject.toml` is located.

### 1. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, use a permitted shell or follow your machine's Python environment policy; do not disable security controls globally just for this project.

### 2. Install the project dependencies

```powershell
python -m pip install -e . -r src/requirements.txt
python -m pip install turso_serverless
```

### 3. Configure environment variables

Create a `.env` file in the **repository root**. Keep this file local and never commit real credentials. Use the following as a starting point:

```dotenv
APP_NAME=GraceDays
APP_TIMEZONE=Asia/Kolkata
APP_FAKE_TODAY=
MAX_SOURCE_TEXT_CHARS=20000

# Database — obtain these values from your Turso database settings
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=

# Keep mock mode for a demo without an LLM API key
LLM_PROVIDER=mock
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=30

# Local MCP server — keep the host on loopback
MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
```

Set **both** `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`; leave neither set for normal persistent use. The application initializes/ensures its schema when it connects. The MCP server is intentionally restricted to loopback; do not expose it directly to the public internet.

To use a live OpenAI-compatible provider, change `LLM_PROVIDER` to `openai_compatible` and set `LLM_API_KEY`. Configure `LLM_MODEL` and `LLM_BASE_URL` for the provider you intend to use. Pasted source text will be sent to that provider for extraction and/or assistant responses.

### 4. Start the MCP server

Open **Terminal 1** at the repository root, activate the virtual environment, and run:

```powershell
python -m gracedays.mcp_server
```

Keep this terminal running. By default, the server binds to `127.0.0.1:8001` and serves MCP at `/mcp`.

### 5. Start the Streamlit interface

Open **Terminal 2** at the repository root, activate the same virtual environment, and run:

```powershell
streamlit run src/gracedays/app.py
```

Open the local URL printed by Streamlit in your browser. Use the sidebar's **Check MCP + Turso** control to inspect connectivity. Both the MCP server and database need to be reachable for persisted purchase operations.

## Basic workflow

1. Open **Capture & review**.
2. Paste relevant order-confirmation or policy text, or choose one of the synthetic examples.
3. Select **Extract fields for review** and check the proposed purchase details, deadlines, dates, and evidence excerpts.
4. Correct or review uncertain information and explicitly confirm before saving.
5. Use **Dashboard** to see deadlines that need attention.
6. Use **Purchases** to inspect saved evidence and update the purchase status.
7. Use **Assistant** to ask about saved purchases, deadlines, or next steps. Drafted messages are for review only and are not sent automatically.

You can use **Seed / refresh demo data** in the sidebar to add synthetic examples. **Reset demo records** requires the exact confirmation phrase `RESET DEMO DATA` and is intended to remove demo records only.

## Configuration reference

| Variable | Purpose | Default / example |
|---|---|---|
| `TURSO_DATABASE_URL` | Turso database URL | Obtain from Turso |
| `TURSO_AUTH_TOKEN` | Turso authentication token | Obtain from Turso; keep secret |
| `LLM_PROVIDER` | Extraction/chat provider | `mock` or `openai_compatible` |
| `LLM_API_KEY` | Provider API key | Required for a live provider |
| `LLM_MODEL` | Provider model name | `gpt-4o-mini` |
| `LLM_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |
| `LLM_TIMEOUT_SECONDS` | Provider request timeout | `30` |
| `APP_TIMEZONE` | Timezone used for deadline calculations | `Asia/Kolkata` |
| `APP_FAKE_TODAY` | Optional fixed date for deterministic development | Blank, or `YYYY-MM-DD` |
| `MAX_SOURCE_TEXT_CHARS` | Maximum source text length accepted by the UI | `20000` |
| `MCP_HOST` | MCP server bind address | `127.0.0.1` |
| `MCP_PORT` | MCP server port | `8001` |
| `MCP_SERVER_URL` | MCP endpoint used by the UI | `http://127.0.0.1:8001/mcp` |

## Tests and extraction evaluation

Run the unit and integration tests from the repository root:

```powershell
pytest -q
```

Run the synthetic extraction evaluation:

```powershell
python evals/run_extraction_eval.py
```

The evaluation reports expected-date recall, whether negative examples produced invented deadlines, evidence-verification rate, and whether ambiguous cases were flagged for review. Treat test results as a report of the current checkout; do not assume they pass without running them in your environment.

## Key project files

```text
GraceDays-main/
├── data/                       # Synthetic demo purchase data
├── evals/                      # Synthetic extraction evaluation and fixtures
├── src/
│   ├── gracedays/
│   │   ├── app.py              # Streamlit UI
│   │   ├── config.py           # Environment-backed configuration
│   │   ├── extraction.py       # Extraction and evidence validation
│   │   ├── gateway.py          # MCP client gateway
│   │   ├── mcp_server.py       # MCP tools and server entry point
│   │   ├── orchestrator.py     # Assistant tool allowlist and grounding
│   │   ├── turso_db.py         # Turso persistence and schema
│   │   ├── providers/          # Mock and OpenAI-compatible providers
│   │   └── services/           # Deadline, demo-data, and draft services
│   └── requirements.txt        # Runtime/test dependency list used by this repo
├── tests/                      # Unit and integration tests
├── .env.example                # Environment-variable example; update it for Turso settings
├── pyproject.toml              # Package metadata and pytest settings
├── PRD.md                      # Product requirements
├── SRD.md                      # System requirements/design
└── README.md
```

## Safety, privacy, and limitations

- GraceDays is a deadline-management aid, not a guarantee of a retailer's policy or eligibility decision. Always verify important deadlines with the merchant's original policy.
- GraceDays does not connect to email inboxes or retailer accounts.
- It does not submit return requests, cancel subscriptions, issue refunds, or send messages. It can draft a message and update local record statuses only.
- Missing, ambiguous, or unsupported dates should remain visible for review instead of being invented.
- Purchase text and evidence may be stored in the configured Turso database. Do not paste payment-card data, passwords, authentication codes, or other secrets.
- The MCP service is designed for local development and binds to loopback. There is no user authentication layer in this project; do not deploy it as a publicly accessible service without adding appropriate authentication, authorization, and deployment security.
- Keep `.env`, database tokens, API keys, and real purchase data out of Git. Rotate any secret that has already been committed.

## Contributing

1. Create a branch for your change.
2. Keep date calculations and evidence validation deterministic and covered by tests.
3. Do not weaken the assistant's tool allowlist or grounding checks without adding tests that cover the safety implications.
4. Run the test suite and extraction evaluation before submitting a pull request.

## License

See [LICENSE](LICENSE).
