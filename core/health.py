import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from aipa.config import get_settings
from aipa.dependencies import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health")
async def health(pool=Depends(get_db)) -> JSONResponse:
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "ok"
        status_code = 200
    except Exception as exc:
        logger.error("health_check_db_failed", error=str(exc))
        db_status = "unreachable"
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if status_code == 200 else "degraded",
            "db": db_status,
            "environment": get_settings().ENVIRONMENT,
        },
    )
