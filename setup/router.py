import httpx
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from aipa.config import get_settings
from aipa.core.auth import get_account_by_bearer
from aipa.core.encryption import encrypt_api_key
from aipa.core.google_auth import google_enabled, verify_google_bearer
from aipa.db.queries.accounts import link_account
from aipa.db.queries.businesses import link_google_user
from aipa.db.queries.setup import (
    get_or_create_business_and_channel,
    save_api_key,
    save_boss_config,
)
from aipa.dependencies import get_db, get_fernet
from aipa.setup.schemas import SetupRequest, VerifyBotRequest
from aipa.telegram.sender import get_bot_info

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["setup"])


@router.post("/telegram/verify")
async def verify_bot_token(payload: VerifyBotRequest) -> dict:
    """Resolve a bot token to its bot account (name/username) via getMe,
    so the dashboard can recognise the bot before setup is submitted."""
    bot = await get_bot_info(payload.bot_token.strip())
    if bot is None:
        return {"ok": False, "detail": "Telegram does not recognise this token."}
    return {"ok": True, "bot": bot}


@router.post("/setup")
async def setup_business(
    payload: SetupRequest,
    request: Request,
    pool=Depends(get_db),
    authorization: str | None = Header(default=None),
) -> dict:
    fernet = get_fernet()
    settings = get_settings()

    # Resolve the signed-in identity up front so a bad session fails before
    # we create anything. Bearer is either an account token or a Google ID token.
    account = await get_account_by_bearer(pool, authorization)
    google_user_id = None
    if account is None and authorization and google_enabled():
        google_user_id = await verify_google_bearer(authorization)

    result = await get_or_create_business_and_channel(
        pool, payload.bot_token, payload.business_name
    )
    business_id = result["business_id"]
    webhook_secret = result["webhook_secret"]

    linked = False
    if account is not None or google_user_id:
        if account is not None:
            outcome = await link_account(pool, business_id, str(account["id"]))
        else:
            outcome = await link_google_user(pool, business_id, google_user_id)
        if outcome == "business_taken":
            raise HTTPException(
                status_code=409,
                detail="This bot is already registered to another account.",
            )
        if outcome == "user_taken":
            raise HTTPException(
                status_code=409,
                detail="Your account already has a business. One business per account for now.",
            )
        linked = True

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
    return {
        "ok": True,
        "business_id": business_id,
        "webhook_url": webhook_url,
        "owner_token": result["owner_token"],
        "linked": linked,
    }
