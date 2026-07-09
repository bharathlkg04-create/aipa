"""Owner-facing inbox API: conversation history and the activity log.

Everything is read-only and tenant-guarded — a conversation is only
returned when it belongs to the authenticated business.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from aipa.core.auth import verify_owner
from aipa.db.queries.conversations import (
    get_conversation_for_business,
    list_conversations,
)
from aipa.db.queries.messages import list_messages, list_recent_activity
from aipa.dependencies import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api", tags=["conversations"])


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: not a UUID")


@router.get("/conversations")
async def get_conversations(
    business_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    rows = await list_conversations(pool, business_id, limit, offset)
    return {
        "ok": True,
        "conversations": [
            {
                "id": str(r["id"]),
                "customer_id": r["customer_id"],
                "customer_name": r["customer_name"],
                "channel": r["channel_type"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "message_count": r["message_count"] or 0,
                "last_message_at": (
                    r["last_message_at"].isoformat() if r["last_message_at"] else None
                ),
                "last_message_role": r["last_message_role"],
                "last_message_preview": r["last_message_preview"],
            }
            for r in rows
        ],
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    business_id: str = Query(...),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(business_id, "business_id")
    conversation_id = _validate_uuid(conversation_id, "conversation_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    convo = await get_conversation_for_business(pool, business_id, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    rows = await list_messages(pool, conversation_id, limit, offset)
    return {
        "ok": True,
        "conversation": {
            "id": str(convo["id"]),
            "customer_id": convo["customer_id"],
            "customer_name": convo["customer_name"],
            "channel": convo["channel_type"],
        },
        "messages": [
            {
                "id": str(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/logs")
async def get_logs(
    business_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=300),
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(business_id, "business_id")
    await verify_owner(pool, business_id, x_owner_token, authorization)

    rows = await list_recent_activity(pool, business_id, limit)
    return {
        "ok": True,
        "logs": [
            {
                "id": str(r["id"]),
                "role": r["role"],
                "preview": r["preview"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "conversation_id": str(r["conversation_id"]),
                "customer_id": r["customer_id"],
                "customer_name": r["customer_name"],
                "channel": r["channel_type"],
            }
            for r in rows
        ],
    }
