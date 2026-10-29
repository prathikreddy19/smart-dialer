# Smart Dialer Backend Prototype

A Python 3.12, FastAPI, SQLAlchemy, and MySQL 8 prototype for the CredResolve Smart Dialer assignment. It demonstrates progressive calling, rule-based predictive pacing, a safety controller, concurrency-safe reservations, mock telecom providers, call and agent state machines, simulation, and metrics.

This is a modular monolith for local evaluation. It intentionally has no frontend, authentication, queue, cache, broker, or deployment stack.

## Features

- **Progressive dialer:** recommends at most one outbound call per currently available active agent.
- **Predictive pacing:** estimates a call count using available agents, answer rate, expected call duration, and provider health. It only recommends; the allocator places no calls until safety approves.
- **Safety controller:** caps each batch to lockable agents and eligible borrowers; rejects or falls back to progressive pacing when provider health is low.
- **Call allocator:** reserves agents and borrowers in a transaction before calling a provider. MySQL uses `SELECT ... FOR UPDATE SKIP LOCKED` to prevent competing workers from claiming the same rows.
- **Mock providers:** Provider A is fast and reliable; Provider B is slower and simulates timeouts, duplicate callbacks, and out-of-order callbacks.
- **State machines:** explicit transitions for agents and calls. Duplicate callbacks are idempotent, late events cannot move terminal calls backward, and forward events can skip missing intermediate callbacks.
- **Failure handling:** provider timeouts fail the call and release the agent; recovery cancels stale setup calls; pausing or taking an agent offline cancels its in-flight setup calls.
- **Simulation and metrics:** run multiple dial rounds and inspect utilization, call outcomes, safety decisions, and process-local provider statistics.
- **CSV import:** imports the seven assignment datasets in parent-first order, resolves duplicate IDs deterministically, validates foreign keys, and reports skipped orphan rows.

## Project layout

```text
app/
  api/             FastAPI routers
  core/            Logging setup
  database/        SQLAlchemy engine, session, and initialization
  models/          Imported dataset and dialer ORM models
  providers/       Mock provider interface and implementations
  schemas/         Pydantic request models
  services/        CSV importer, allocator, pacing, safety, and metrics
  simulator/       Multi-round simulation
  state_machine/   Agent and call transition rules
  utils/           Shared helpers
  main.py          FastAPI app and router registration
dataset/            Assignment-provided CSV files
scripts/            Dataset import and health load-check helpers
tests/              SQLite-backed automated tests
docs/               Architecture decisions
requirements.txt
.env.example
```

## Requirements

- Python 3.12
- MySQL 8
- Windows PowerShell commands are shown below; equivalent Python commands work on other platforms.

## Setup

### 1. Create a MySQL database

Create the database using MySQL Workbench or the MySQL client:

```sql
CREATE DATABASE smart_dialer
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

Use a MySQL account that has privileges on this database. Tables are created from SQLAlchemy models when the API starts.

### 2. Create the environment and install dependencies

From the project root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use the venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Configure local credentials

Copy the example file and edit `.env` with your MySQL username and password:

```powershell
Copy-Item .env.example .env
```

Set `DATABASE_URL` to the URL for your local database, for example:

```dotenv
DATABASE_URL=mysql+pymysql://smart_dialer:YOUR_PASSWORD@127.0.0.1:3306/smart_dialer?charset=utf8mb4
```

Do not commit `.env`. It is ignored by Git. `.env.example` contains only placeholder credentials.

### 4. Start the API

```powershell
python -m uvicorn app.main:app --reload
```

Open:

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>
- Health check: <http://127.0.0.1:8000/health>

`GET /health` should return HTTP 200 with `{"status":"healthy","database":"connected"}`.

## Reviewer quick-start

1. Configure MySQL and `.env` using the setup steps above.
2. Start the API and verify `GET /health`.
3. Open `/docs` and run `POST /upload/dataset` with all seven CSVs from `dataset/`:
   - `vendor_telephony.csv`
   - `campaigns.csv`
   - `borrowers.csv`
   - `agents.csv`
   - `calls.csv`
   - `call_attempts.csv`
   - `agent_sessions.csv`
4. Wait for the full JSON report. The supplied files contain over 250,000 source rows, so import can take a few minutes on a local database.
5. Query `/campaigns`, `/agents?limit=5`, `/borrowers?limit=5`, `/calls?limit=5`, and `/metrics`.
6. Use a campaign ID returned by `/campaigns` to test dialing or simulation.
7. Run the automated tests with `python -m pytest -q`.

The uploader accepts all seven files in one multipart request and imports them in this dependency order: vendors, campaigns, borrowers, agents, calls, call attempts, agent sessions. It stops on the first failed file. Earlier files are committed per file, so call `POST /database/reset` before retrying a partially completed import.

### Duplicate and orphan handling

The assignment datasets intentionally contain duplicate and conflicting records. For each file the importer groups on the model primary key, keeps one identical row, and resolves conflicting rows to the latest `updated_at`; if no `updated_at` exists, it keeps the first row. It reports exact duplicates and conflicts resolved. It does not use `INSERT IGNORE` or upsert behavior.

Foreign-key references are checked before insert. Orphan event rows are skipped and listed in the report rather than creating fake parent entities or disabling referential integrity. The supplied data includes borrower references missing from the borrower table, so nonzero orphan counts for calls and attempts are expected.

## API reference and examples

### Dataset and database

- `GET /health` — API and database connectivity.
- `POST /upload/dataset` — multipart upload with all seven required CSV fields. Use the filenames listed above.
- `POST /database/reset` — **destructive**: drops all project tables and recreates them from current ORM models. It deletes imported data and dialer activity. Upload the dataset again afterward.

### Browse imported data

- `GET /campaigns` — list campaigns.
- `GET /agents?limit=5` — list agents and current dialer state (`limit` is 1–1000).
- `GET /borrowers?limit=5` — list borrowers (`limit` is 1–1000).
- `GET /calls?limit=5` — list recent dialer calls and historical imported calls (`limit` is 1–1000).
- `GET /metrics` — utilization, dialer call totals, safety decisions, and provider statistics.

### Dial a campaign

`POST /campaigns/{campaign_id}/dial`, using a campaign ID returned from `GET /campaigns`:

```json
{
  "mode": "progressive",
  "provider": "provider_a",
  "max_calls": 3,
  "answer_rate": 0.8,
  "average_call_duration_seconds": 120
}
```

`mode` is `progressive` or `predictive`; `provider` is `provider_a` or `provider_b`. Progressive mode never recommends above available agent capacity. Predictive mode may recommend more, but safety still caps actual calls to lockable agent and borrower capacity. Keep `max_calls` small for manual tests because the mock provider processes each call during the request.

### Update an agent state

`PUT /agents/{agent_id}/state`:

```json
{"state":"PAUSED"}
```

Allowed API targets are `AVAILABLE`, `PAUSED`, and `OFFLINE`. Only active agents can be made available. An offline or paused agent's in-flight setup calls are cancelled.

### Submit a provider callback

`POST /calls/{call_id}/events`:

```json
{
  "provider": "provider_a",
  "event_id": "reviewer-event-001",
  "event_type": "COMPLETED"
}
```

Allowed event types: `RINGING`, `ANSWERED`, `CONNECTED`, `COMPLETED`, `FAILED`, and `CANCELLED`. Repeating an event with the same provider and event ID is idempotent.

### Run simulation and recovery

`POST /simulation/run?campaign_id=CMP0000001` with a `SimulationRequest` body:

```json
{
  "mode": "progressive",
  "provider": "provider_a",
  "max_calls": 2,
  "answer_rate": 0.8,
  "average_call_duration_seconds": 120,
  "ticks": 3
}
```

`POST /simulation/recover?timeout_seconds=60` cancels setup calls older than the requested timeout and releases their agents.

## Tests

The test suite uses an isolated in-memory SQLite database and does not require MySQL credentials:

```powershell
python -m pytest -q
```

Coverage includes:

- Agent and call state transitions, including invalid, duplicate, and out-of-order transitions
- Progressive allocation and one-call-per-agent safety
- Predictive recommendation and safety reductions/fallbacks
- Database locking SQL compiled for MySQL `SKIP LOCKED`
- Duplicate provider events, provider B timeout/event scenarios, and stale call recovery
- Health, reset, Swagger schema, and multi-file upload routes

The tests do not make real telecom calls. Provider statistics are in-memory mock counters and reset when the API process restarts.

Optional concurrent health smoke test, with the API running:

```powershell
python scripts/load_test.py --requests 100 --workers 10
```

## Design decisions and prototype limits

- MySQL stores imported data and shared reservation state; SQLAlchemy ORM defines table structure and relationships.
- One call is committed with one reserved active agent before provider dispatch. Provider I/O occurs after the database transaction, so it does not hold row locks.
- `FOR UPDATE SKIP LOCKED` allows concurrent MySQL workers to reserve different agents/borrowers. SQLite is used only for fast unit and route tests; it does not provide the same locking guarantee.
- Provider B failures are deliberately simulated. A timeout fails the call and releases the agent; the prototype does not retry uncertain provider submissions.
- `POST /database/reset` is a local prototype convenience, not a production migration tool. It intentionally destroys all project tables and rebuilds them from models.
- Provider health counters are process-local because providers are mocks. A real provider adapter would need provider-side idempotency and reconciliation.
