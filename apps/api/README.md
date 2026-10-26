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

## Local database (optional until M0 step 2)

Needs Docker Desktop running. From the project root (`ar-portal`):

```powershell
npx supabase init     # once; answer N to the Deno/VS Code questions
npx supabase start    # first run downloads the containers and takes a few minutes
```

Then uncomment `DATABASE_URL` in `apps\api\.env` and restart the API.
`/api/health` reports `"database": "ok"` once it can connect.

## Layout

| Path | What it holds |
|---|---|
| `app/main.py` | Creates the FastAPI app and registers each module's router. |
| `app/core/config.py` | Settings from environment variables or `.env`. |
| `app/core/db.py` | Database engine, set up for Vercel and Supabase's pooler. |
| `app/modules/<name>/` | One folder per feature: `router.py`, `schemas.py`, `service.py`, and from M0 step 2 `models.py` and `repository.py`. |
| `tests/` | pytest tests, run in CI on every pull request. |
