import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from aipa.config import get_settings
from aipa.core.encryption import encrypt_api_key
from aipa.db.queries.setup import (
    get_or_create_business_and_channel,
    save_api_key,
    save_boss_config,
)
from aipa.dependencies import get_db, get_fernet
from aipa.setup.schemas import SetupRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["setup"])


@router.post("/setup")
async def setup_business(
    payload: SetupRequest,
    request: Request,
    pool=Depends(get_db),
) -> dict:
    fernet = get_fernet()
    settings = get_settings()

    result = await get_or_create_business_and_channel(
        pool, payload.bot_token, payload.business_name
    )
    business_id = result["business_id"]
    webhook_secret = result["webhook_secret"]

    encrypted = encrypt_api_key(fernet, payload.api_key)
    provider = payload.model.split("/")[0] if "/" in payload.model else "openai"
    await save_api_key(pool, business_id, encrypted, provider)

    await save_boss_config(
        pool, business_id, payload.model, payload.temperature, payload.system_prompt
    )

    base_url = settings.BASE_URL.rstrip("/") if settings.BASE_URL else str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook/telegram/{payload.bot_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{payload.bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": webhook_secret,
                "allowed_updates": ["message"],
            },
            timeout=10,
        )

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Config saved, but Telegram rejected webhook: {data.get('description', 'unknown error')}",
        )

    logger.info("business_setup_complete", business_id=business_id, model=payload.model)
    return {"ok": True, "business_id": business_id, "webhook_url": webhook_url}
