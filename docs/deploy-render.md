# Deploy to Render (free, 3 steps)

Render is the **staging/test** environment (production goes to GCP — see
`deploy-gcp.md`). The [`render.yaml`](../render.yaml) Blueprint provisions a **free**
stack — **web + Postgres + Key Value** — in one click. Generation runs inline in the web
service (no paid worker), and migrations run automatically on start.

## Prerequisites
- The repo on GitHub with `render.yaml` on the `main` branch (already there).
- A free [Render](https://render.com) account.

## Step 1 — Apply the Blueprint
1. Render Dashboard → **New +** → **Blueprint**.
2. Connect this GitHub repo, branch **main**. Render detects `render.yaml`.
3. **Apply**. It creates `litreview-db` (Postgres), `litreview-redis` (Key Value), and
   `litreview-web`. `FERNET_KEY` and `EXPORT_URL_SECRET` are auto-generated.

Wait for `litreview-web` to go **Live** (first build ~5 min — it installs pandoc). Watch
**Logs** for `Running upgrade -> 0001_initial … 0002 …` then `Application startup complete`.

## Step 2 — (optional) set keys
In **litreview-web → Environment**:
- `CORS_ORIGINS = ["https://your-frontend"]` — set before the frontend integrates
  (default is open, fine for API testing).
- `OPENROUTER_API_KEY = sk-or-...` → real open-source models (qwen/llama/…); or
  `OPENAI_API_KEY = sk-...` for paid ChatGPT. Leave unset to use the instant `fake` model.

Saving redeploys automatically.

## Step 3 — Verify it's working
```bash
BASE=https://litreview-web-XXXX.onrender.com    # your web URL
curl -s $BASE/healthz      # {"status":"ok"}
curl -s $BASE/readyz       # {"status":"ready","database":"ok"}   ← DB wired + migrated
```

Then run the automated end-to-end check from a machine with Python:
```bash
pip install httpx
python scripts/smoke_test.py $BASE --provider fake
# → 12/12 checks passed
```
If you set an OpenRouter/OpenAI key, prove a real model too:
`python scripts/smoke_test.py $BASE --provider qwen` (or `openai`).

That's it — 12/12 means the backend is working end to end on managed Postgres + Redis.

---

### Notes
- **No manual migration step** — baked into the container start command.
- **Free tier** sleeps after ~15 min idle (first request then takes ~50s) and the free
  Postgres expires ~30 days after creation. Fine for staging; bump the `plan:` fields for
  always-on.
- **Key Value naming**: if Render rejects `type: keyvalue`, change that one line in
  `render.yaml` to `type: redis` and re-apply.
- **Production** (always-on worker, `JOBS_EAGER=false`, Memorystore/Cloud SQL) → GCP,
  see `deploy-gcp.md`.
