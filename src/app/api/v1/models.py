from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..deps import SettingsDep

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get(
    "",
    summary="List selectable LLM models",
    description="Returns every model the frontend can offer in a picker, plus the "
    "default. Send a chosen `key` as `provider` in POST /reviews. API keys are never "
    "exposed here. Public so the picker can populate before the user has a key.",
)
async def list_models(settings: SettingsDep) -> dict[str, Any]:
    providers = [
        {
            "key": key,
            "label": cfg.label or key,
            "model": cfg.model,
            "kind": cfg.kind,
            "location": cfg.location(),  # "local" | "cloud" | "builtin"
        }
        for key, cfg in settings.llm_providers.items()
    ]
    return {"default": settings.llm_default_provider, "providers": providers}
