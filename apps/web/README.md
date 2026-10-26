# AR Operations Portal — web app

Next.js (App Router) + TypeScript + Tailwind CSS v4. Same layout and colors as the current portal:
top bar, icon rail, secondary panel with saved views, and the workspace.

## Run locally

```bash
npm install
cp .env.example .env.local   # API_ORIGIN for the /api rewrite
npm run dev                  # http://localhost:3000
```

Other scripts: `npm run build`, `npm run lint`, `npm run typecheck`.

## Where things live

| Path | What it holds |
|---|---|
| `app/globals.css` | Color tokens (navy, brand, status colors). Change colors here only. |
| `lib/navigation.ts` | Rail items and the views in the secondary panel, in one list. |
| `lib/config.ts` | App name and monogram shown in the top bar. |
| `lib/status.ts` | Claim and upload statuses and their pill colors. |
| `lib/sample-data.ts` | Fake records for the template. Replaced by API calls from M1. |
| `components/shell/` | Top bar, rail, secondary panel, page header, menus. |
| `components/data/` | Panel, metric card, status pill, table, activity list, empty state. |
| `components/ui/` | Button and form field styles. |
| `app/(portal)/` | One folder per screen. Dashboard and Claims are built; the rest are placeholders. |

## Adding a screen

1. Add the module and its views to `NAV_MODULES` in `lib/navigation.ts`.
2. Create `app/(portal)/<module>/page.tsx` using `PageHeader` and `PageBody`.
3. Read the selected view from `searchParams.view` and resolve it with `resolveView()`.

The current view is always in the URL (`/claims?view=overdue`), so back/forward,
bookmarks and shared links work.
