# Research_Gen API Contract

Base URL (staging): `https://<your-app>.up.railway.app`
All endpoints are versioned under `/api/v1`. Interactive docs: `/docs` (Swagger) and
`/redoc`. Machine-readable schema: [`openapi.json`](./openapi.json).

Real captured request/response payloads live in [`samples/`](./samples/).

---

## 1. Authentication

Every endpoint except `POST /api/v1/auth/api-keys`, the health probes, and the signed
export download requires an API key sent as a header:

```
X-API-Key: lrk_xxxxxxxxxxxxxxxxxxxxxxxx
```

Issue a key (bootstrap, no auth required):

```
POST /api/v1/auth/api-keys
{ "email": "you@example.com", "name": "my app" }
→ 201 { "id": "...", "prefix": "lrk_ab12cd", "api_key": "lrk_....", ... }
```

The plaintext `api_key` is returned **once** — store it. Manage keys:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/auth/api-keys` | List your keys (never returns plaintext) |
| `DELETE` | `/api/v1/auth/api-keys/{id}` | Revoke a key (`204`) |

---

## 2. The generate → poll → export lifecycle

Generation is asynchronous. You submit, poll a job, then read the review and export it.

```
1. POST /api/v1/documents            (optional) upload sources → document_id
2. POST /api/v1/reviews              → 202 { id: job_id, status: "queued" }
3. GET  /api/v1/reviews/jobs/{job_id}  poll until status == "succeeded"
                                       → result.review_id
4. GET  /api/v1/reviews/{review_id}    the structured, cited review
5. GET  /api/v1/reviews/{review_id}/preview?format=html   sanitized HTML
6. GET  /api/v1/reviews/{review_id}/export?format=md|docx|pdf
```

### Submit a review

```
POST /api/v1/reviews
Headers: X-API-Key, [Idempotency-Key: <uuid>]
{
  "topic": "attention mechanisms",
  "provider": "fake",                // optional; omit for the configured default
  "records": [ { "title": "...", "abstract": "...", "year": 2017 } ],
  "document_ids": ["<uuid>"],        // reference previously uploaded files
  "max_tokens": 1500                 // optional
}
→ 202 JobInfo
```

`records` and `document_ids` may be combined. Provide an `Idempotency-Key` so a retried
submit returns the original job instead of generating twice.

### Poll the job

```
GET /api/v1/reviews/jobs/{job_id}
→ 200 { "id", "kind", "status": "queued|running|succeeded|failed",
        "progress": 0-100, "error", "result": { "review_id": "..." }, ... }
```

### Fetch the review

```
GET /api/v1/reviews/{review_id}
→ 200 {
  "id", "topic", "provider", "model",
  "content_md": "# Literature Review: ...",
  "structured": { "sections": [...], "citations": [...], "sources": [...], "usage": {...} },
  "csl_json": [ { "type": "article-journal", "title": "...", "author": [...] } ]
}
```

### Preview & export

- `GET /reviews/{id}/preview?format=html` → `{ id, format, html }` — sanitized HTML.
- `GET /reviews/{id}/export?format=md`  → `200`, `text/markdown` (inline attachment).
- `GET /reviews/{id}/export?format=docx` → `200`, Word document (inline attachment).
- `GET /reviews/{id}/export?format=pdf` → `202` JobInfo (async). Poll the job; when it
  succeeds, `result.download_url` is a **signed, temporary URL** (default TTL 15 min) you
  can GET without an API key to download the file.

---

## 3. Documents

```
POST /api/v1/documents           multipart/form-data: file=<csv|xlsx|pdf|json>
→ 201 DocumentInfo { id, kind, status: "parsed|failed", parsed_meta: { record_count, records } }

GET /api/v1/documents/{id}       → 200 DocumentInfo
```

File type is verified by **magic bytes**, not the extension. A parse failure still returns
`201` with `status: "failed"` and an `error` — inspect `status` before using a document.

---

## 4. ORKG

```
POST /api/v1/orkg/connect        { "username", "password" }   → { connected, expires_in }
GET  /api/v1/orkg/search?q=...&size=20                          → { query, total, items }
POST /api/v1/orkg/sparql         { "query": "SELECT ...", "limit": 50 }
```

SPARQL is **read-only and guarded**: only `SELECT` / `CONSTRUCT` / `ASK` / `DESCRIBE` are
allowed, a `LIMIT` is injected if absent (and clamped to the server max), a single
statement only, and a hard timeout applies. ORKG OIDC tokens are encrypted at rest.

---

## 5. Error envelope

Every error (validation, auth, rate limit, not found, upstream, internal) uses one shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "request validation failed",
    "details": [ { "field": "topic", "message": "field required", "type": "missing" } ],
    "request_id": "b1f2..."
  }
}
```

`request_id` also comes back in the `X-Request-ID` response header for correlation.

### Error-code table

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `unknown_provider` | `provider` not in the registry |
| 400 | `sparql_rejected` | SPARQL query failed the read-only guard |
| 401 | `unauthorized` | Missing/invalid/revoked API key, or bad download token |
| 401 | `orkg_auth_failed` | ORKG credentials rejected |
| 404 | `not_found` | Resource missing or not owned by the caller; unknown route |
| 413 | `payload_too_large` | Upload exceeds `MAX_UPLOAD_BYTES` |
| 422 | `validation_error` | Body/query validation failed (see `details`) |
| 429 | `rate_limited` | Rate/concurrency cap hit (see `Retry-After`) |
| 502 | `upstream_unavailable` | ORKG/triplestore unreachable |
| 500 | `internal_error` | Unexpected server error (no stack trace leaked) |

---

## 6. Rate limits

Enforced per API key via Redis. On a breach you get `429` with a `Retry-After` header and
`code: "rate_limited"`.

| Scope | Default | Applies to |
| --- | --- | --- |
| General | 60 / minute | All authenticated endpoints |
| Concurrent generations | 3 in-flight | `POST /reviews` |
| SPARQL | 10 / minute | `POST /orkg/sparql` |

Defaults are configurable (`RATE_LIMIT_PER_MINUTE`, `MAX_CONCURRENT_GENERATIONS`,
`SPARQL_RATE_LIMIT_PER_MINUTE`) and can be disabled entirely with
`RATE_LIMIT_ENABLED=false`.

---

## 7. Pagination

Step 3 endpoints return bounded collections directly:
- `GET /orkg/search` accepts `size` (1–100) and echoes `total`.
- `GET /auth/api-keys` returns the caller's keys (small, unpaginated).

List endpoints that could grow (documents, reviews history) are intentionally **not**
exposed yet; when added they will use `?limit=&offset=` with a `total` field, matching the
search shape above.

---

## 8. Getting started in 10 minutes

```bash
# 0. Base URL of your deployment
BASE=https://<your-app>.up.railway.app

# 1. Issue an API key (copy the api_key from the response)
KEY=$(curl -s -X POST $BASE/api/v1/auth/api-keys \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","name":"quickstart"}' | jq -r .api_key)

# 2. Upload sources
DOC=$(curl -s -X POST $BASE/api/v1/documents \
  -H "X-API-Key: $KEY" -F file=@papers.csv | jq -r .id)

# 3. Generate a review (async) -> job id
JOB=$(curl -s -X POST $BASE/api/v1/reviews \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d "{\"topic\":\"graph neural networks\",\"document_ids\":[\"$DOC\"]}" | jq -r .id)

# 4. Poll until succeeded
curl -s $BASE/api/v1/reviews/jobs/$JOB -H "X-API-Key: $KEY" | jq '{status,progress,result}'
REVIEW=$(curl -s $BASE/api/v1/reviews/jobs/$JOB -H "X-API-Key: $KEY" | jq -r .result.review_id)

# 5. Read + preview + export
curl -s $BASE/api/v1/reviews/$REVIEW -H "X-API-Key: $KEY" | jq '.structured.sections[].heading'
curl -s "$BASE/api/v1/reviews/$REVIEW/preview?format=html" -H "X-API-Key: $KEY" | jq -r .html | head
curl -s "$BASE/api/v1/reviews/$REVIEW/export?format=md" -H "X-API-Key: $KEY" -o review.md
```
