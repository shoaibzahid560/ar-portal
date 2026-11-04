# AR Operations Portal

Internal portal for AR sheet uploads, claim work, assignment, follow-ups, review, notifications and an
append-only audit trail. See `AR_Portal_Technical_Build_Guideline` for the full plan.

## Project layout

```
ar-portal/                Open this folder in VS Code; Git lives here
├── .github/workflows/    CI: API lint and tests (with a throwaway PostgreSQL), web lint, types, build
├── .vscode/              Shared settings, debug configurations, recommended extensions
└── apps/
    ├── web/              Next.js app (npm commands run here)
    └── api/              FastAPI app (Python commands run here)
        ├── app/          The API, one folder per module
        ├── migrations/   Database changes (Alembic): 0001 foundation ... 0004 notifications
        └── tests/        Unit tests, and database tests that run in CI
```

## What's built

| Area | Status |
|---|---|
| M0 foundation: Google sign-in, sessions, users, roles and permissions, practices, teams, audit log | Done |
| M1 uploads and claims: AR sheet upload and validation, claims with the sheet's work fields and dropdowns, notes, EOB, history | Done |
| Bulk assignment and the review queue (same claim / separate claim) | Done |
| M5 notifications | Done |
| M6 reports and exports | Next |
| Staging and production deploy (Vercel, Supabase) | Needs a company Google account and Vercel Pro |

## Prerequisites

Git, Node.js 20.9 or newer, Python 3.14, and access to the Supabase dev project.

## First-time setup

```powershell
# API
cd apps\api
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env          # then fill in DATABASE_URL and the Google values
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.cli create-admin you@company.com "Your Name"

# Web
cd ..\web
npm install
copy .env.example .env.local    # API_ORIGIN=http://localhost:8000
```

## Run

From VS Code: **Run and Debug**, choose **Web + API**, press F5. Or in two terminals:

```powershell
cd apps\api; .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd apps\web; npm run dev
```

Then open http://localhost:3000 (always port 3000; 8000 is the API behind it).

## Data safety

Development and testing use only the synthetic sample sheets. Real AR sheets contain patient information
and go only into production, once the Vercel and Supabase Business Associate Agreements are in place.
`.env`, `.env.local` and uploaded files (`apps/api/.storage/`) are never committed.
