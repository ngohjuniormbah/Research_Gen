#!/usr/bin/env python
"""Seed N test users, each with one scoped API key. Raw keys are printed ONCE.

Usage:
    python scripts/seed.py [N]          # defaults to SEED_USERS env or 3

Run migrations first (alembic upgrade head). Intended for staging/dev only — never
against production data.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _seed(n: int) -> list[tuple[str, str]]:
    # Imported here so the module can be run as a script with src on the path.
    from app.db.session import dispose_engine, get_sessionmaker
    from app.services import auth as auth_service

    maker = get_sessionmaker()
    issued: list[tuple[str, str]] = []
    async with maker() as session:
        for i in range(1, n + 1):
            email = f"seed{i}@example.com"
            user = await auth_service.get_or_create_user(session, email, f"Seed User {i}")
            _, raw = await auth_service.issue_api_key(session, user, name=f"seed-key-{i}")
            issued.append((email, raw))
        await session.commit()
    await dispose_engine()
    return issued


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("SEED_USERS", "3"))
    issued = asyncio.run(_seed(n))
    print("\n=== Seeded API keys (shown once — copy them now) ===")
    print(f"{'EMAIL':<28} API_KEY")
    for email, raw in issued:
        print(f"{email:<28} {raw}")
    print(f"\nSeeded {len(issued)} user(s). Use header:  X-API-Key: <api_key>")


if __name__ == "__main__":
    main()
