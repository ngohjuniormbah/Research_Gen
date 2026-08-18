#!/usr/bin/env python
"""End-to-end smoke test against a LIVE deployment. No frontend needed.

Runs the full lifecycle and prints a pass/fail checklist you can show your boss:
  health -> readiness -> issue key -> list models -> upload -> generate (chosen model)
  -> poll -> fetch review -> preview -> export md -> export pdf -> download.

Usage:
  python scripts/smoke_test.py https://research-gen.onrender.com
  python scripts/smoke_test.py https://research-gen.onrender.com --provider qwen
  python scripts/smoke_test.py https://research-gen.onrender.com --provider fake

Exit code 0 = all passed, 1 = something failed.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"

CSV = (
    b"title,abstract,authors,year,doi\n"
    b"Attention Is All You Need,Introduces the transformer.,Vaswani; Shazeer,2017,10.5555/x\n"
    b"BERT,Bidirectional pretraining.,Devlin,2019,10.18653/y\n"
)


class Runner:
    def __init__(self, base: str, provider: str, email: str) -> None:
        self.base = base.rstrip("/")
        self.provider = provider
        self.email = email
        self.client = httpx.Client(timeout=120.0)
        self.results: list[tuple[str, bool, str]] = []
        self.key: str | None = None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, ok, detail))
        print(f"  {PASS if ok else FAIL}  {name}" + (f"  — {detail}" if detail else ""))
        return ok

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.key} if self.key else {}

    def _wait_healthy(self, attempts: int = 40, delay: float = 5.0) -> bool:
        """Poll until the service answers, to ride out a Cloud Run cold start.

        A freshly deployed revision runs DB migrations on container start, so the
        very first request can take a couple of minutes before the app serves 200.
        We accept either /healthz returning ok, or /readyz reporting the database
        is up (a ready DB means the app has finished booting) — whichever comes
        first — and keep trying for up to ~3 minutes before giving up.
        """
        for _ in range(attempts):
            for path in ("/healthz", "/readyz"):
                try:
                    r = self.client.get(f"{self.base}{path}", timeout=20)
                    if r.status_code == 200:
                        body = r.json()
                        if body.get("status") == "ok" or body.get("database") == "ok":
                            return True
                except Exception:  # noqa: BLE001 - transient cold-start errors are expected
                    pass
            time.sleep(delay)
        return False

    def run(self) -> bool:
        print(f"\nSmoke test → {self.base}  (provider: {self.provider})\n")

        self.check("GET /healthz", self._wait_healthy())

        r = self.client.get(f"{self.base}/readyz")
        db = r.json().get("database") if r.status_code == 200 else None
        self.check("GET /readyz (database)", db == "ok", f"database={db}")

        r = self.client.post(f"{self.base}/api/v1/auth/api-keys", json={"email": self.email})
        ok = r.status_code == 201 and r.json().get("api_key", "").startswith("lrk_")
        if ok:
            self.key = r.json()["api_key"]
        self.check("POST /auth/api-keys (issue key)", ok)
        if not self.key:
            return self._summary()

        r = self.client.get(f"{self.base}/api/v1/models", headers=self._headers())
        keys = [p["key"] for p in r.json().get("providers", [])] if r.status_code == 200 else []
        self.check(
            f"GET /models (provider '{self.provider}' available)",
            self.provider in keys,
            f"available={keys}",
        )

        r = self.client.post(
            f"{self.base}/api/v1/documents",
            headers=self._headers(),
            files={"file": ("papers.csv", CSV, "text/csv")},
        )
        doc_ok = r.status_code == 201 and r.json().get("status") == "parsed"
        doc_id = r.json().get("id") if r.status_code == 201 else None
        self.check("POST /documents (upload+parse CSV)", doc_ok,
                   f"records={r.json().get('parsed_meta', {}).get('record_count')}")

        body = {
            "topic": "transformer architectures",
            "instructions": "Keep it concise and compare the two papers.",
            "provider": self.provider,
            "document_ids": [doc_id] if doc_id else [],
        }
        r = self.client.post(f"{self.base}/api/v1/reviews", headers=self._headers(), json=body)
        job = r.json() if r.status_code == 202 else {}
        job_id = job.get("id")
        self.check(
            "POST /reviews (submit job)", r.status_code == 202, f"status={job.get('status')}"
        )

        review_id = None
        if job_id:
            for _ in range(30):  # poll up to ~60s (real models take time)
                jr = self.client.get(
                    f"{self.base}/api/v1/reviews/jobs/{job_id}", headers=self._headers()
                ).json()
                if jr.get("status") in ("succeeded", "failed"):
                    review_id = jr.get("result", {}).get("review_id")
                    self.check(
                        "GET /reviews/jobs/{id} (poll → done)",
                        jr.get("status") == "succeeded",
                        f"status={jr.get('status')} error={jr.get('error','')}",
                    )
                    break
                time.sleep(2)
            else:
                self.check("GET /reviews/jobs/{id} (poll → done)", False, "timed out")

        if review_id:
            rev = self.client.get(
                f"{self.base}/api/v1/reviews/{review_id}", headers=self._headers()
            ).json()
            sections = rev.get("structured", {}).get("sections", [])
            self.check("GET /reviews/{id} (has content)",
                       bool(rev.get("content_md")) and len(sections) > 0,
                       f"sections={len(sections)}")

            pv = self.client.get(
                f"{self.base}/api/v1/reviews/{review_id}/preview?format=html",
                headers=self._headers(),
            )
            self.check("GET /preview?format=html", pv.status_code == 200 and "html" in pv.json())

            md = self.client.get(
                f"{self.base}/api/v1/reviews/{review_id}/export?format=md",
                headers=self._headers(),
            )
            self.check("GET /export?format=md", md.status_code == 200 and len(md.content) > 0)

            pdf = self.client.get(
                f"{self.base}/api/v1/reviews/{review_id}/export?format=pdf",
                headers=self._headers(),
            )
            url = None
            if pdf.status_code == 202:
                import json as _json
                url = _json.loads(pdf.content).get("result", {}).get("download_url")
            self.check("GET /export?format=pdf (async job)", bool(url))
            if url:
                dl = self.client.get(f"{self.base}{url}")
                self.check(
                    "GET signed export download",
                    dl.status_code == 200 and len(dl.content) > 0,
                )

        return self._summary()

    def _summary(self) -> bool:
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        print(f"\n{'='*50}\n  {passed}/{total} checks passed\n{'='*50}")
        return passed == total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Deployment URL, e.g. https://research-gen.onrender.com")
    parser.add_argument("--provider", default="fake", help="Model key to test (default: fake)")
    parser.add_argument("--email", default="smoke@example.com")
    args = parser.parse_args()

    ok = Runner(args.base_url, args.provider, args.email).run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
