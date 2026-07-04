"""Thin async client for a WAHA instance (https://waha.devlike.pro).

WAHA is the WhatsApp-Web bridge: it holds the linked-device session and
exposes it over REST. AI'PA never speaks the WhatsApp protocol itself —
it starts sessions, fetches the login QR, and sends replies through WAHA,
and WAHA POSTs inbound messages to our /webhook/whatsapp/{session} URL.
"""

import httpx
import structlog

from aipa.config import get_settings

logger = structlog.get_logger(__name__)

_TIMEOUT = 25.0


class WahaError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _base_url() -> str:
    url = get_settings().WAHA_URL.rstrip("/")
    if not url:
        raise WahaError(
            "WhatsApp is not configured on this server (WAHA_URL is unset).",
            status_code=503,
        )
    return url


def _headers() -> dict:
    key = get_settings().WAHA_API_KEY
    return {"X-Api-Key": key} if key else {}


def _session_config(webhook_url: str, webhook_secret: str) -> dict:
    return {
        "webhooks": [
            {
                "url": webhook_url,
                "events": ["message"],
                "customHeaders": [
                    {"name": "X-Webhook-Secret", "value": webhook_secret}
                ],
            }
        ]
    }


async def start_session(session: str, webhook_url: str, webhook_secret: str) -> dict:
    """Create the session if needed, update its webhook config, and start it."""
    config = _session_config(webhook_url, webhook_secret)
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = await client.post(
            f"{_base_url()}/api/sessions",
            json={"name": session, "start": True, "config": config},
        )
        if resp.status_code in (200, 201):
            return resp.json()

        # Session already exists → update config, then (re)start it
        if resp.status_code in (409, 422, 400):
            upd = await client.put(
                f"{_base_url()}/api/sessions/{session}", json={"config": config}
            )
            if upd.status_code >= 400:
                logger.warning("waha_session_update_failed", status=upd.status_code)
            start = await client.post(f"{_base_url()}/api/sessions/{session}/start")
            if start.status_code < 400:
                return start.json() if start.content else {"name": session}

        raise WahaError(f"WAHA rejected session start: HTTP {resp.status_code} {resp.text[:200]}")


async def get_session(session: str) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = await client.get(f"{_base_url()}/api/sessions/{session}")
    if resp.status_code == 404:
        return {"name": session, "status": "STOPPED"}
    if resp.status_code >= 400:
        raise WahaError(f"WAHA session status failed: HTTP {resp.status_code}")
    return resp.json()


async def get_qr_png(session: str) -> bytes:
    """PNG of the login QR. Only valid while status == SCAN_QR_CODE."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = await client.get(
            f"{_base_url()}/api/{session}/auth/qr",
            headers={"Accept": "image/png", **_headers()},
        )
    if resp.status_code >= 400:
        raise WahaError(
            f"QR not available (session may not be in SCAN_QR_CODE state): HTTP {resp.status_code}",
            status_code=409,
        )
    return resp.content


async def send_text(session: str, chat_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = await client.post(
            f"{_base_url()}/api/sendText",
            json={"session": session, "chatId": chat_id, "text": text},
        )
    if resp.status_code >= 400:
        raise WahaError(f"WAHA sendText failed: HTTP {resp.status_code} {resp.text[:200]}")


async def logout_session(session: str) -> None:
    """Unlink the device and stop the session (safe to call when already stopped)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
        resp = await client.post(f"{_base_url()}/api/sessions/{session}/logout")
        if resp.status_code >= 400 and resp.status_code != 404:
            logger.warning("waha_logout_failed", session=session, status=resp.status_code)
        await client.post(f"{_base_url()}/api/sessions/{session}/stop")
