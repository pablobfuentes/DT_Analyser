# Deployment (Netlify + Render)

The app has two parts:

| Part | Host | Role |
|------|------|------|
| **Frontend** | Netlify | React SPA, SEO, proxies `/api` to backend |
| **Backend** | Render | FastAPI + SQLite on persistent disk |

Netlify cannot run the Python API. You must deploy the backend separately, then point Netlify at it.

## 1. Deploy the backend (Render)

1. Push this repo to GitHub (already done).
2. Go to [render.com](https://render.com) → **New** → **Blueprint** (or **Web Service**).
3. Connect **pablobfuentes/DT_Analyser** and use the root `render.yaml`.
4. After deploy, note the service URL, e.g. `https://dt-analyser-api.onrender.com`.
5. In Render → **Environment**, set:

   | Variable | Example |
   |----------|---------|
   | `LTA_CORS_ORIGINS` | `https://your-site.netlify.app` |

   (`LTA_DATA_DIR`, `LTA_DATABASE_URL`, and `LTA_DISABLE_AUTOMATION` are set in `render.yaml`.)

6. Confirm health: open `https://YOUR-API.onrender.com/api/health` → `{"status":"ok"}`.

**Note:** Render free/starter tiers may spin down when idle; the first request after sleep can take ~30s.

## 2. Deploy the frontend (Netlify)

1. Go to [app.netlify.com](https://app.netlify.com) → **Add new site** → **Import from Git**.
2. Select **pablobfuentes/DT_Analyser**.
3. Build settings (from `netlify.toml`):

   - **Base directory:** `frontend`
   - **Build command:** `npm ci && npm run build`
   - **Publish directory:** `frontend/dist`

4. **Environment variables** (Site settings → Environment variables):

   | Variable | Value |
   |----------|-------|
   | `BACKEND_URL` | `https://YOUR-API.onrender.com` (no trailing slash) |

5. **Deploy site**. The build runs `scripts/prebuild.mjs`, which writes `public/_redirects` so `/api/*` is proxied to your Render API.

6. Update SEO URLs if your Netlify subdomain differs from `dt-analyser.netlify.app`:
   - `frontend/index.html` → `<link rel="canonical">`
   - `frontend/public/robots.txt` → `Sitemap:`
   - `frontend/public/sitemap.xml` → `<loc>` URLs

## 3. Verify

1. Open your Netlify URL.
2. No red **Backend not connected** banner at the top.
3. **Import** → choose a CSV → preview table and **IMPORT** button appear.
4. Dashboard loads accounts and trades.

## Local development (unchanged)

```bash
# Terminal 1
cd backend
uvicorn app.main:app --reload --port 8001

# Terminal 2
cd frontend
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` to port 8001. Do **not** set `BACKEND_URL` locally.

## Optional: direct API URL (no Netlify proxy)

Set on Netlify build:

```
VITE_API_BASE_URL=https://YOUR-API.onrender.com/api
```

Then the browser calls Render directly (CORS must include your Netlify origin via `LTA_CORS_ORIGINS`). The `BACKEND_URL` proxy is preferred so the app keeps same-origin `/api`.

## Cloud vs local behavior

On Render, `LTA_DISABLE_AUTOMATION=true` disables inbox watcher, worker, and EOD scheduler (no local `data/inbox` folder). Use the **Import** page and **Workflow → Process inbox** API actions instead of filesystem drops.

Data (SQLite DB, attachments, backups) lives on Render’s mounted disk at `/var/data`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Import does nothing | `BACKEND_URL` missing or wrong on Netlify; redeploy after setting it |
| Red backend banner | API down, cold start, or wrong URL |
| CORS errors | Add Netlify URL to `LTA_CORS_ORIGINS` on Render |
| 404 on `/trades` refresh | Rebuild frontend so `_redirects` SPA rule is present |
