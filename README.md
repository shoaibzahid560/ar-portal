# AR Operations Portal

Internal portal for AR claim uploads, reconciliation, assignment, follow-ups,
audit trail and reporting. See `AR_Portal_Technical_Build_Guideline` for the full plan.

## Project layout

```
ar-portal/            Project root: open this folder in VS Code; Git lives here
├── .vscode/          Shared settings, debug configurations, recommended extensions
├── apps/
│   ├── web/          Next.js app (run npm commands inside this folder)
│   └── api/          FastAPI app (Python; run commands inside this folder)
└── supabase/         Local database config (added with the API)
```

## Prerequisites

Git, Node.js 20.9 or newer, Python 3.12+, Docker Desktop, Supabase CLI, Vercel CLI.

## First-time setup

Web app, from `apps\web`:

```powershell
npm install
copy .env.example .env.local
```

API, from `apps\api`:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
```

## Run

In VS Code, open **Run and Debug**, choose **Web + API**, and press F5.
Then open http://localhost:3000. The dashboard header shows whether the web app can reach the API.

Each app's own README covers running it from a terminal, tests and lint.
