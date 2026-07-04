from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from aipa.core.auth import verify_owner
from aipa.core.encryption import encrypt_api_key
from aipa.db.queries.api_keys import get_api_key_meta
from aipa.db.queries.boss_config import get_boss_config
from aipa.db.queries.businesses import get_business
from aipa.db.queries.channels import list_channels
from aipa.db.queries.setup import save_api_key, save_boss_config
from aipa.dependencies import get_db, get_fernet
from aipa.account.schemas import ReplaceApiKeyRequest, UpdateConfigRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["account"])


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: not a UUID")


def _mask_token(token: str) -> str:
    if len(token) <= 12:
        return token[:4] + "…"
    return token[:8] + "…" + token[-4:]


@router.get("/account")
async def get_account(
    business_id: str = Query(...),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token)

    business = await get_business(pool, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    config = await get_boss_config(pool, business_id)
    key_meta = await get_api_key_meta(pool, business_id)
    channels = await list_channels(pool, business_id)

    return {
        "ok": True,
        "business": {
            "id": str(business["id"]),
            "name": business["name"],
            "created_at": business["created_at"].isoformat() if business["created_at"] else None,
        },
        "config": dict(config) if config else None,
        "api_key": (
            {
                "provider": key_meta["provider"],
                "created_at": key_meta["created_at"].isoformat() if key_meta["created_at"] else None,
            }
            if key_meta
            else None
        ),
        "channels": [
            {
                "id": str(c["id"]),
                "type": c["channel_type"],
                "token_hint": _mask_token(c["channel_token"]),
                "is_active": c["is_active"],
                "created_at": c["created_at"].isoformat() if c["created_at"] else None,
            }
            for c in channels
        ],
    }


@router.put("/config")
async def update_config(
    payload: UpdateConfigRequest,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(payload.business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token)

    system_prompt = payload.system_prompt.strip() if payload.system_prompt else None
    await save_boss_config(
        pool, business_id, payload.llm_model, payload.temperature, system_prompt
    )
    logger.info("config_updated", business_id=business_id, model=payload.llm_model)
    return {"ok": True}


@router.put("/api-key")
async def replace_api_key(
    payload: ReplaceApiKeyRequest,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(payload.business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token)

    provider = payload.provider
    if not provider:
        config = await get_boss_config(pool, business_id)
        model = config["llm_model"] if config else "openai/gpt-4o-mini"
        provider = model.split("/")[0] if "/" in model else "openai"

    encrypted = encrypt_api_key(get_fernet(), payload.api_key.strip())
    await save_api_key(pool, business_id, encrypted, provider)
    logger.info("api_key_replaced", business_id=business_id, provider=provider)
    return {"ok": True, "provider": provider}
