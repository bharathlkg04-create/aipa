import secrets
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response

from aipa.config import get_settings
from aipa.core.auth import verify_owner
from aipa.db.queries.channels import (
    create_channel,
    get_channel_by_business,
    get_channel_by_token,
    set_channel_active,
)
from aipa.dependencies import get_db
from aipa.whatsapp import waha
from aipa.whatsapp.schemas import WahaEvent, WhatsAppConnectRequest, WhatsAppDisconnectRequest

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["whatsapp"])


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: not a UUID")


def _webhook_url(request: Request, session: str) -> str:
    settings = get_settings()
    base = settings.BASE_URL.rstrip("/") if settings.BASE_URL else str(request.base_url).rstrip("/")
    return f"{base}/webhook/whatsapp/{session}"


async def _get_or_create_wa_channel(pool, business_id: str):
    channel = await get_channel_by_business(pool, business_id, "whatsapp")
    if channel is not None:
        if not channel["is_active"]:
            await set_channel_active(pool, str(channel["id"]), True)
        return channel

    settings = get_settings()
    # Each business gets its own WAHA session (WAHA ≥ 2026.6.1 allows
    # unlimited sessions for free); the single shared session "default"
    # is kept only for older WAHA images.
    session = f"wa-{secrets.token_hex(6)}" if settings.WAHA_MULTI_SESSION else "default"
    try:
        return await create_channel(
            pool, business_id, session, secrets.token_urlsafe(24), "whatsapp"
        )
    except Exception:
        raise HTTPException(
            status_code=409,
            detail="WhatsApp session 'default' is already linked to another business. "
            "Set WAHA_MULTI_SESSION=true to give every business its own number.",
        )


def _extract_push_name(payload: dict) -> str | None:
    """The sender's WhatsApp display name. Field depends on the WAHA engine:
    WEBJS uses notifyName, NOWEB (Baileys) uses pushName, GOWS uses Info.PushName."""
    raw = payload.get("_data") or {}
    info = raw.get("Info") or {}
    for candidate in (
        payload.get("notifyName"),
        payload.get("pushName"),
        raw.get("notifyName"),
        raw.get("pushName"),
        info.get("PushName"),
    ):
        if candidate and isinstance(candidate, str):
            return candidate.strip()[:80]
    return None


# ── Inbound webhook (called by WAHA) ─────────────────────────────────────────

@router.post("/webhook/whatsapp/{channel_token}", status_code=200)
async def whatsapp_webhook(
    channel_token: str,
    event: WahaEvent,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None),
    pool=Depends(get_db),
) -> dict:
    channel = await get_channel_by_token(pool, channel_token, "whatsapp")
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    # WAHA is configured to echo our secret back as a custom header
    if x_webhook_secret is not None and x_webhook_secret != channel["webhook_secret"]:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    if event.event != "message":
        return {"ok": True}

    payload = event.payload or {}
    chat_id = payload.get("from") or ""
    body = payload.get("body") or ""

    # Skip our own messages, group chats, and non-text payloads
    if payload.get("fromMe") or not body or not chat_id or chat_id.endswith("@g.us"):
        return {"ok": True}

    from aipa.conversations.manager import process_whatsapp_message

    customer_name = _extract_push_name(payload)

    background_tasks.add_task(
        process_whatsapp_message,
        pool=pool,
        channel=channel,
        chat_id=chat_id,
        user_text=body,
        customer_name=customer_name,
    )
    return {"ok": True}


# ── Owner-facing management API ──────────────────────────────────────────────

@router.post("/api/whatsapp/connect")
async def connect_whatsapp(
    payload: WhatsAppConnectRequest,
    request: Request,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(payload.business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    channel = await _get_or_create_wa_channel(pool, business_id)
    session = channel["channel_token"]

    try:
        state = await waha.start_session(
            session, _webhook_url(request, session), channel["webhook_secret"]
        )
    except waha.WahaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    logger.info("whatsapp_session_starting", business_id=business_id, session=session)
    return {"ok": True, "session": session, "status": state.get("status", "STARTING")}


@router.get("/api/whatsapp/status")
async def whatsapp_status(
    business_id: str = Query(...),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    channel = await get_channel_by_business(pool, business_id, "whatsapp")
    if channel is None:
        return {"ok": True, "status": "NOT_CONNECTED"}

    try:
        state = await waha.get_session(channel["channel_token"])
    except waha.WahaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    me = state.get("me") or {}
    return {
        "ok": True,
        "session": channel["channel_token"],
        "status": state.get("status", "UNKNOWN"),
        "phone": me.get("id", ""),
        "name": me.get("pushName", ""),
    }


@router.get("/api/whatsapp/qr")
async def whatsapp_qr(
    business_id: str = Query(...),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Response:
    business_id = _validate_uuid(business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    channel = await get_channel_by_business(pool, business_id, "whatsapp")
    if channel is None:
        raise HTTPException(status_code=404, detail="No WhatsApp channel — call /api/whatsapp/connect first")

    try:
        png = await waha.get_qr_png(channel["channel_token"])
    except waha.WahaError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/api/whatsapp/disconnect")
async def disconnect_whatsapp(
    payload: WhatsAppDisconnectRequest,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(payload.business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    channel = await get_channel_by_business(pool, business_id, "whatsapp")
    if channel is None:
        return {"ok": True, "status": "NOT_CONNECTED"}

    try:
        await waha.logout_session(channel["channel_token"])
    except waha.WahaError as exc:
        logger.warning("whatsapp_logout_error", detail=str(exc))
    await set_channel_active(pool, str(channel["id"]), False)

    logger.info("whatsapp_disconnected", business_id=business_id)
    return {"ok": True, "status": "DISCONNECTED"}
