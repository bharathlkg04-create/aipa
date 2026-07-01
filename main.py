from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from aipa.config import get_settings
from aipa.core.health import router as health_router
from aipa.db.client import create_pool
from aipa.logging_config import configure_logging
from aipa.setup.router import router as setup_router
from aipa.telegram.router import router as telegram_router
from aipa.ui import router as ui_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    app.state.db_pool = await create_pool()
    logger.info("aipa_started", environment=settings.ENVIRONMENT)

    yield

    await app.state.db_pool.close()
    logger.info("aipa_stopped")


app = FastAPI(
    title="AI'PA",
    description="Multi-tenant AI agent platform for small businesses.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if get_settings().ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.include_router(health_router)
app.include_router(setup_router)
app.include_router(telegram_router)
app.include_router(ui_router)
