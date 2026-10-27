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

## Layout

| Path | What it holds |
|---|---|
| `app/main.py` | Creates the FastAPI app and registers each module's router. |
| `app/core/config.py` | Settings from environment variables or `.env`. |
| `app/core/db.py` | Database engine and per-request session, set up for Vercel and Supabase's pooler. |
| `app/core/orm.py` | Base class for tables; everything lives in the `ar` schema. |
| `app/models.py` | Imports every table so Alembic sees the whole schema. |
| `migrations/` | Alembic migrations. `0001_foundation.py` creates the M0 tables, roles and permissions. |
| `app/modules/<name>/` | One folder per feature: `router.py`, `schemas.py`, `service.py`, `models.py` and `repository.py`. |
| `tests/` | pytest tests, run in CI on every pull request. |
