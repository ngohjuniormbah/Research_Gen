# GCP one-time project setup (fixes "AUTH_PERMISSION_DENIED")

The automated GitHub Actions deploy failed with:

```
ERROR: (gcloud.services.enable) github-deployer@… does not have permission…
Permission denied to enable service [run.googleapis.com] …
Cloud Resource Manager API has not been used in project … or it is disabled
```

This is **not a code error** — the GCP project just needs a **one-time setup by the project
OWNER**: enable the required APIs and grant the deployer service account (`github-deployer`)
the roles it needs. Do this once, then re-run the workflow.

> Ce n'est **pas** une erreur de code. Le projet GCP a besoin d'une **configuration unique par
> le PROPRIÉTAIRE** : activer les APIs et donner les rôles au compte de service
> `github-deployer`. À faire une seule fois, puis relancer le workflow.

---

## Prerequisite / Prérequis
- **Billing must be enabled** on the project (Console → Billing → link a billing account).
- You run the commands below as the **project owner** (your own login), **not** the CI
  service account: `gcloud auth login`.

## One-time setup / Configuration unique

Run this **once**, replacing `PROJECT` with your project id (as the owner):

```bash
gcloud auth login                     # log in as the project OWNER
PROJECT=your-gcp-project-id
gcloud config set project "$PROJECT"

# 1) Enable the APIs the deploy needs (only the owner can do this the first time)
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com

# 2) Grant the deployer service account the roles it needs
SA="github-deployer@${PROJECT}.iam.gserviceaccount.com"
for ROLE in \
  roles/run.admin \
  roles/cloudsql.admin \
  roles/artifactregistry.admin \
  roles/cloudbuild.builds.editor \
  roles/storage.admin \
  roles/iam.serviceAccountUser \
  roles/serviceusage.serviceUsageAdmin ; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SA}" --role="$ROLE" --condition=None
done
```

> **Easy mode (demo only):** instead of the loop you can grant one broad role —
> `gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="roles/editor" --condition=None`
> plus `roles/iam.serviceAccountUser`. Less secure; fine for a quick staging deploy.

## Re-run the deploy / Relancer le déploiement
GitHub → **Actions** → the failed run → **Re-run all jobs**. (Or push any commit to `main`.)
It should now pass: build image → create Cloud SQL → deploy Cloud Run → build/deploy
frontend → lock CORS → smoke test.

---

## What must exist as GitHub repo secrets
(These already work if authentication succeeded — listed for completeness.)

| Secret | What it is |
| --- | --- |
| `GCP_SA_KEY` | JSON key of the `github-deployer` service account |
| `GCP_PROJECT_ID` | The GCP project id |
| `DB_PASSWORD` | Any strong password for the Cloud SQL user |
| `OPENAI_API_KEY` | *(optional)* paid ChatGPT key |
| `FIREBASE_TOKEN` | *(for the frontend job)* from `firebase login:ci` |

If you ever need to (re)create the service account + key:
```bash
gcloud iam service-accounts create github-deployer --project "$PROJECT"
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account="github-deployer@${PROJECT}.iam.gserviceaccount.com"
# Put the contents of gcp-key.json into the GitHub secret GCP_SA_KEY, then delete the file.
```

## Runtime DB access note
The Cloud Run service connects to Cloud SQL as its **runtime** service account (the default
compute SA). On most projects that SA has `roles/editor` and can connect. If `/readyz` shows
a database permission error after deploy, grant it explicitly:
```bash
PROJNUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${PROJNUM}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.client" --condition=None
```
