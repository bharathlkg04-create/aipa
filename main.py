from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from aipa.account.router import router as account_router
from aipa.config import get_settings
from aipa.core.health import router as health_router
from aipa.db.client import create_pool
from aipa.logging_config import configure_logging
from aipa.setup.router import router as setup_router
from aipa.skills.router import router as skills_router
from aipa.telegram.router import router as telegram_router
from aipa.ui import router as ui_router
from aipa.whatsapp.router import router as whatsapp_router

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
app.include_router(account_router)
app.include_router(setup_router)
app.include_router(skills_router)
app.include_router(telegram_router)
app.include_router(whatsapp_router)
app.include_router(ui_router)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
