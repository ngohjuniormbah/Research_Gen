# GCP Deploy — Monday Runbook

Top-to-bottom sequence to get **backend + frontend** live on GCP. Two deployments:
the API on **Cloud Run** (+ **Cloud SQL** Postgres) and the static frontend on hosting.

Prereqs: `gcloud` CLI installed + `gcloud auth login`; Node 18+ for the frontend build.

---

## 1. Deploy the backend (one command)

From the repo root:

```bash
PROJECT=your-gcp-project \
REGION=us-central1 \
DB_PASSWORD='choose-a-strong-password' \
FRONTEND_ORIGIN='https://your-frontend-domain' \
OPENAI_API_KEY='sk-...'            # optional (or OPENROUTER_API_KEY=sk-or-...) \
bash scripts/deploy_gcp.sh
```

The script: enables APIs → builds & pushes the image (frontend excluded via
`.gcloudignore`) → creates Cloud SQL + DB + user (skips if they exist) → deploys Cloud Run
with all env vars. Migrations run automatically on container start. It prints the backend
**URL** at the end — copy it.

> Don't have the frontend domain yet? Leave `FRONTEND_ORIGIN` unset (defaults to `*`, open)
> and lock it later:
> `gcloud run services update litreview-web --region=us-central1 --update-env-vars='^@^CORS_ORIGINS=["https://your-frontend"]'`

## 2. Verify the backend

```bash
BASE=<the URL the script printed>
curl -s $BASE/readyz                                   # {"status":"ready","database":"ok"}
python scripts/smoke_test.py $BASE --provider fake      # → 12/12 checks passed
```
If you set an OpenAI/OpenRouter key: `python scripts/smoke_test.py $BASE --provider openai`.

## 3. Build & deploy the frontend

Point the frontend at the backend URL, build, and deploy the static files:

```bash
cd frontend
echo "VITE_API_BASE_URL=$BASE" > .env.production
npm ci
npm run build          # outputs frontend/dist/
```

Host `frontend/dist/` on any static host, e.g. **Firebase Hosting**:
```bash
npm i -g firebase-tools
firebase login
firebase init hosting   # public dir = dist, single-page app = yes
firebase deploy
```
(or upload `dist/` to a Cloud Storage bucket + load balancer / Cloud CDN.)

## 4. Lock CORS to the real frontend URL

Once the frontend is live at its final URL, set it on the backend (if not already):
```bash
gcloud run services update litreview-web --region=$REGION \
  --update-env-vars='^@^CORS_ORIGINS=["https://your-frontend-domain"]'
```

## 5. Final check
- Open the frontend URL → it should reach the backend (no CORS errors in the browser
  console), let you enter/create an API key, pick a model, upload, and generate a review.
- `curl -s $BASE/readyz` → `database: ok`.

Done. 🎉

---

### Notes & knobs
- **Real models**: set `OPENAI_API_KEY` (+ `LLM_DEFAULT_PROVIDER=openai`) or
  `OPENROUTER_API_KEY`. They're env vars — never commit them.
- **Rate limiting**: the simple path sets `RATE_LIMIT_ENABLED=false` (no Redis). To enable
  it, add **Memorystore for Redis** and set `REDIS_URL`; the limiter also fails open if
  Redis is unreachable.
- **Scale later**: for heavy async load, add a worker on GKE with the same image and
  command `arq app.worker.settings.WorkerSettings`, and set `JOBS_EAGER=false`
  (see `deploy-gcp.md`).
- **Secrets**: for production, prefer GCP **Secret Manager** over plaintext env vars for
  `FERNET_KEY`, `EXPORT_URL_SECRET`, and API keys.
