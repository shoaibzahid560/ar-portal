# Deploying a demo copy on Vercel (free) and Supabase (free)

This puts a **demo copy** of the portal online, with **fake data only**.

- **No real patient data.** Vercel's free plan and Supabase's free plan don't come with a HIPAA Business
  Associate Agreement. Only the synthetic sample sheets go into this copy.
- **Personal, non-commercial use.** Vercel's free Hobby plan is for personal, non-commercial projects.
  Use this copy as your own demo or portfolio. When the company runs the portal for real work, it moves to
  Vercel Pro with the HIPAA add-on and Supabase with a BAA (see the build guideline, section 9).
- Free Supabase projects pause after about a week without use; open the dashboard and press Restore.

You'll create **one Supabase project** and **two Vercel projects** (the API and the web app) from the same
GitHub repository. Allow about an hour.

## 1. Supabase: a separate demo project

1. supabase.com → **New project** named `ar-portal-demo`. Pick a region near you (for example Singapore or
   Mumbai) and keep the database password somewhere safe.
2. **Storage → New bucket**: name `ar-portal-files`, **Public bucket: off**.
3. **Project Settings → API Keys**: open the **Legacy API keys** tab and copy the **service_role** key. Also
   copy the **Project URL** (`https://<ref>.supabase.co`). The service_role key is a secret: it goes only
   into the API's Vercel settings.
4. **Connect** (top bar) → copy two connection strings:
   - **Transaction pooler** (port **6543**): for Vercel.
   - **Session pooler** (port **5432**): for running migrations from your PC.

## 2. Create the tables and the first owner (from your PC)

In PowerShell, from `apps\api` (your `.env` stays as it is; these settings apply to this window only):

```powershell
$env:DATABASE_URL = "<Session pooler string, port 5432>"
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.cli create-admin you@gmail.com "Your Name"
Remove-Item Env:DATABASE_URL
```

Expect `Running upgrade ... -> 0010` and a confirmation that the Portal Owner was created.

## 3. Vercel: the API project

1. vercel.com → **Add New → Project** → import your GitHub repository `ar-portal`.
2. **Root Directory**: `apps/api`. Vercel detects **FastAPI** by itself (it loads `app` from `app/main.py`).
3. **Environment Variables**:

| Name | Value |
| --- | --- |
| `APP_ENV` | `staging` |
| `DATABASE_URL` | Transaction pooler string (port 6543) |
| `WEB_ORIGIN` | `https://<web-project>.vercel.app` (fill in after step 4, then redeploy) |
| `GOOGLE_CLIENT_ID` | from Google Cloud |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud |
| `ALLOWED_GOOGLE_DOMAIN` | `*` (demo: any registered Google account; never in production) |
| `BUSINESS_TIMEZONE` | `Asia/Karachi` |
| `STORAGE_BACKEND` | `supabase` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | the service_role key |
| `STORAGE_BUCKET` | `ar-portal-files` |

4. **Deploy**. Then open `https://<api-project>.vercel.app/api/health`: it should show
   `"database":"ok"` and `"schema_version":"0010"`.
5. **Settings → Functions → Function Region**: choose the region closest to your Supabase project.

## 4. Vercel: the web project

1. **Add New → Project** → the same repository again.
2. **Root Directory**: `apps/web` (Next.js is detected).
3. **Environment Variable**: `API_ORIGIN` = `https://<api-project>.vercel.app` (no trailing slash).
4. **Deploy**, and note the web address, for example `https://ar-portal-web.vercel.app`.
5. Back in the **API project**: set `WEB_ORIGIN` to that web address → **Deployments → Redeploy**.

## 5. Google sign-in

Google Cloud → **Google Auth Platform → Clients** → your web client:

- **Authorized JavaScript origins**: add `https://<web-project>.vercel.app`
- **Authorized redirect URIs**: add `https://<web-project>.vercel.app/api/auth/google/callback`

While the app is in **Testing**, add every Google account that should sign in (yours, testers, client
demo accounts) under **Audience → Test users**.

## 6. Check it

1. Open `https://<web-project>.vercel.app` and sign in with the Google account from step 2.
2. The dashboard badge should say **API and database connected**.
3. Add a practice, upload `Sample_Practice_AR-HBS_10-22-2026_sheet.xlsx`, approve it from a second account,
   and download a report: that proves the database, storage and downloads all work.

## Updating the demo later

Push to GitHub: Vercel redeploys both projects. If the update includes a new migration, run step 2's
`alembic upgrade head` against the demo database **before** pushing.
