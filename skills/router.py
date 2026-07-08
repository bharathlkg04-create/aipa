from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from aipa.core.auth import verify_owner as _verify_owner
from aipa.db.queries.skills import (
    count_enabled_skills,
    enable_industry_pack,
    get_skills_meta,
    list_skills,
    set_skill_enabled,
)
from aipa.dependencies import get_db
from aipa.skills.schemas import EnablePackRequest, ToggleSkillRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/skills", tags=["skills"])


def _validate_uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: not a UUID")


@router.get("")
async def browse_skills(
    business_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    industry: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    enabled_only: bool = Query(default=False),
    pool=Depends(get_db),
) -> dict:
    if business_id:
        business_id = _validate_uuid(business_id, "business_id")
    if enabled_only and not business_id:
        raise HTTPException(status_code=400, detail="enabled_only requires business_id")

    rows = await list_skills(
        pool, business_id, category, industry, q, limit, offset, enabled_only
    )
    enabled_count = (
        await count_enabled_skills(pool, business_id) if business_id else 0
    )
    return {
        "skills": [
            {**dict(r), "id": str(r["id"])} for r in rows
        ],
        "enabled_count": enabled_count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/meta")
async def skills_meta(pool=Depends(get_db)) -> dict:
    return await get_skills_meta(pool)


@router.put("/{skill_id}/toggle")
async def toggle_skill(
    skill_id: str,
    payload: ToggleSkillRequest,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    skill_id = _validate_uuid(skill_id, "skill_id")
    business_id = _validate_uuid(payload.business_id, "business_id")
    await _verify_owner(pool, business_id, x_owner_token, authorization)

    found = await set_skill_enabled(
        pool, business_id, skill_id, payload.is_enabled, payload.is_pinned
    )
    if not found:
        raise HTTPException(status_code=404, detail="Skill not found")

    enabled_count = await count_enabled_skills(pool, business_id)
    logger.info(
        "skill_toggled",
        business_id=business_id,
        skill_id=skill_id,
        is_enabled=payload.is_enabled,
    )
    return {"ok": True, "enabled_count": enabled_count}


@router.post("/enable-pack")
async def enable_pack(
    payload: EnablePackRequest,
    pool=Depends(get_db),
    x_owner_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    business_id = _validate_uuid(payload.business_id, "business_id")
    await _verify_owner(pool, business_id, x_owner_token, authorization)

    enabled = await enable_industry_pack(
        pool, business_id, payload.industry, payload.pack_size
    )
    if enabled == 0:
        raise HTTPException(
            status_code=404, detail=f"No skills found for industry '{payload.industry}'"
        )

    enabled_count = await count_enabled_skills(pool, business_id)
    logger.info(
        "industry_pack_enabled",
        business_id=business_id,
        industry=payload.industry,
        skills_enabled=enabled,
    )
    return {"ok": True, "skills_enabled": enabled, "enabled_count": enabled_count}
