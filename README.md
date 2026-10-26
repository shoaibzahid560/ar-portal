# AR Operations Portal

Internal portal for AR claim uploads, reconciliation, assignment, follow-ups,
audit trail and reporting. See `AR_Portal_Technical_Build_Guideline` for the full plan.

## Project layout

```
ar-portal/            Project root: open this folder in VS Code; Git lives here
├── .vscode/          Shared settings, debug configurations, recommended extensions
├── apps/
│   ├── web/          Next.js app (run npm commands inside this folder)
│   └── api/          FastAPI app (added in M0 step 1)
└── supabase/         Local database config (added with the API)
```

## Prerequisites

Git, Node.js 20.9 or newer, Python 3.12+, Docker Desktop, Supabase CLI, Vercel CLI.

## Run the web app

From VS Code: open **Run and Debug**, choose **Web: next dev**, press F5.

From a terminal:

```powershell
cd apps\web
npm install
npm run dev
```

Then open http://localhost:3000.

Once the API exists, choose **Web + API** in Run and Debug to start both with one key.
