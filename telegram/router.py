import structlog
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request

from aipa.config import get_settings
from aipa.db.queries.channels import get_channel_by_token
from aipa.dependencies import get_db
from aipa.telegram.schemas import TelegramUpdate

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/telegram/{channel_token}", status_code=200)
async def telegram_webhook(
    channel_token: str,
    update: TelegramUpdate,
    background_tasks: BackgroundTasks,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    pool=Depends(get_db),
) -> dict:
    channel = await get_channel_by_token(pool, channel_token)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    if x_telegram_bot_api_secret_token != channel["webhook_secret"]:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    # Non-text updates (stickers, photos, etc.) are silently acknowledged
    if update.message is None or update.message.text is None:
        return {"ok": True}

    # Import here to avoid circular imports at module load time
    from aipa.conversations.manager import process_telegram_message

    background_tasks.add_task(
        process_telegram_message,
        pool=pool,
        channel=channel,
        update=update,
    )
    return {"ok": True}


@router.post("/telegram/{channel_token}/setup-webhook", status_code=200)
async def setup_telegram_webhook(
    channel_token: str,
    request: Request,
    pool=Depends(get_db),
) -> dict:
    channel = await get_channel_by_token(pool, channel_token)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    settings = get_settings()
    base_url = settings.BASE_URL.rstrip("/") if settings.BASE_URL else str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhook/telegram/{channel_token}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{channel_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": channel["webhook_secret"],
                "allowed_updates": ["message"],
            },
            timeout=10,
        )

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=f"Telegram rejected: {data.get('description', 'unknown error')}")

    logger.info("webhook_registered", channel_token=channel_token[:8] + "...", webhook_url=webhook_url)
    return {"ok": True, "webhook_url": webhook_url}
