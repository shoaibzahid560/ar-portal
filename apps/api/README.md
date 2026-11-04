# AR Operations Portal — API

FastAPI (Python 3.12+), SQLAlchemy 2 (async), Pydantic. Every route lives under `/api`.

## First-time setup (Windows PowerShell, from `apps\api`)

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
```

`py --version` must show 3.12 or newer.

## Run

From VS Code: **Run and Debug → API: uvicorn** (or **Web + API** to start both apps).

From a terminal:

```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Check http://localhost:8000/api/health, and the interactive docs at http://localhost:8000/api/docs.

## Tests and lint

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
.venv\Scripts\ruff format .
```

## Database

`DATABASE_URL` in `.env` points at the Supabase dev project (see `.env.example`).

Create or update the tables (run after pulling new code that adds a migration):

```powershell
.venv\Scripts\alembic upgrade head
.venv\Scripts\alembic current        # shows the version the database is at
```

Every table lives in the `ar` schema. In the Supabase dashboard, open **Table Editor** and pick
`ar` from the schema list to see them.

### Database tests

`tests/test_migrations.py` drops and recreates every table, so it runs only when
`TEST_DATABASE_URL` is set, and must never point at a database with real data.
Without it those tests are skipped. GitHub Actions runs them against a temporary database.

## Sign-in

People sign in with Google, and the API lets them in only if their email is in `ar.users` and
active. Sessions end after 30 minutes idle or 12 hours, or at sign-out.

Create the first System Administrator once per database (there is no web page for this):

```powershell
.venv\Scripts\python -m app.cli create-admin you@yourcompany.com "Your Name"
```

Google settings go in `.env` (see `.env.example`): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`ALLOWED_GOOGLE_DOMAIN`. The OAuth client's authorized redirect URI must be
`http://localhost:3000/api/auth/google/callback` for local development.

## Uploads and claims (M1)

An AR Lead uploads a practice's AR sheet (.xlsx or .csv, the layout used for every practice). Each
valid line becomes a claim; lines already in the system are skipped; problems are listed by row
without repeating cell values. The work columns from the sheet (Claim Status, Pay Status, Check
Status, Action Taken, amounts, dates, notes, EOB, Assigned To) are filled in on each claim.

Claims can be assigned one at a time or in bulk (tick claims in the list). A new line for a patient,
subscriber ID and service date that already has a claim waits in the **Review Queue**: a reviewer
(System Administrator, AR Manager or AR Lead; the `claims.review` permission) decides whether it is
the same claim (the earlier claim takes its uploaded values and the line is folded in) or a separate
claim (both stay).

During local development, uploaded files are stored in `apps/api/.storage/` (ignored by Git).
Deployed environments will use a private Supabase Storage bucket (M0 step 7).

## Notifications (M5)

The bell shows each person's own notifications (brief, section 8): assignments and hand-offs, notes
from colleagues, follow-ups due or overdue, upload errors and lines waiting for review, and, for
holders of `notifications.oversight` (Management, System Administrator), every upload, assignment,
file download, user or permission change and refused sign-in. Titles never contain patient details.
Follow-up reminders are created when the person next opens the portal, so no background job is needed.

## Layout

| Path | What it holds |
|---|---|
| `app/main.py` | Creates the FastAPI app and registers each module's router. |
| `app/core/config.py` | Settings from environment variables or `.env`. |
| `app/core/db.py` | Database engine and per-request session, set up for Vercel and Supabase's pooler. |
| `app/core/orm.py` | Base class for tables; everything lives in the `ar` schema. |
| `app/core/context.py` | Who is calling: `CurrentCtx` for signed-in routes, `require("permission")` for protected ones. |
| `app/core/audit.py` | `audit.record(...)`, written in the same transaction as the change. |
| `app/cli.py` | Command-line maintenance, such as `create-admin`. |
| `app/models.py` | Imports every table so Alembic sees the whole schema. |
| `migrations/` | Alembic migrations. `0001_foundation.py` creates the M0 tables, roles and permissions. |
| `app/modules/<name>/` | One folder per feature: `router.py`, `schemas.py`, `service.py`, `models.py` and `repository.py`. |
| `tests/` | pytest tests, run in CI on every pull request. |
