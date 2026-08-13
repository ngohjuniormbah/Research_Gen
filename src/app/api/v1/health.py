from fastapi import APIRouter
from sqlalchemy import text

from ..deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz(session: SessionDep) -> dict[str, str]:
    """Ready only when the database answers. Redis is checked by the worker itself."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        return {"status": "degraded", "database": f"error: {exc}"[:200]}
    return {"status": "ready", "database": "ok"}
