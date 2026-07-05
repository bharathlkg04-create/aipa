"""Thin async client for a WAHA instance (https://waha.devlike.pro).

WAHA is the WhatsApp-Web bridge: it holds the linked-device session and
exposes it over REST. AI'PA never speaks the WhatsApp protocol itself —
it starts sessions, fetches the login QR, and sends replies through WAHA,
and WAHA POSTs inbound messages to our /webhook/whatsapp/{session} URL.

Free-tier hosting puts the bridge to sleep when idle, so every call
retries transparently while it wakes (Render answers 502/503 meanwhile).
"""

import asyncio

import httpx
import structlog

from aipa.config import get_settings

logger = structlog.get_logger(__name__)

_TIMEOUT = 30.0
_WAKE_RETRIES = 3
_WAKE_DELAY_S = 8.0

_WAKING_MESSAGE = (
    "The WhatsApp bridge is waking up (free instance sleeps when idle). "
    "Wait ~30 seconds and try again."
)


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


def _error_detail(resp: httpx.Response) -> str:
    """Human-readable slice of a WAHA error body (never raw HTML pages)."""
    text = (resp.text or "").strip()
    if not text or text.startswith("<"):
        return ""
    return " " + text[:200]


async def _request(method: str, path: str, *, json: dict | None = None,
                   accept: str | None = None) -> httpx.Response:
    """Issue a request, retrying while the bridge cold-starts."""
    headers = _headers()
    if accept:
        headers["Accept"] = accept
    url = f"{_base_url()}{path}"

    last_error: WahaError | None = None
    for attempt in range(_WAKE_RETRIES):
        if attempt:
            await asyncio.sleep(_WAKE_DELAY_S)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(method, url, json=json, headers=headers)
        except httpx.HTTPError as exc:
            last_error = WahaError(_WAKING_MESSAGE, status_code=503)
            logger.warning("waha_unreachable", path=path, error=type(exc).__name__)
            continue
        if resp.status_code in (502, 503, 504):
            last_error = WahaError(_WAKING_MESSAGE, status_code=503)
            logger.info("waha_waking", path=path, status=resp.status_code, attempt=attempt + 1)
            continue
        return resp
    raise last_error or WahaError(_WAKING_MESSAGE, status_code=503)


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
    resp = await _request(
        "POST", "/api/sessions", json={"name": session, "start": True, "config": config}
    )
    if resp.status_code in (200, 201):
        return resp.json()

    # Session already exists → update config, then (re)start it
    if resp.status_code in (409, 422, 400):
        upd = await _request("PUT", f"/api/sessions/{session}", json={"config": config})
        if upd.status_code >= 400:
            logger.warning("waha_session_update_failed", status=upd.status_code)
        start = await _request("POST", f"/api/sessions/{session}/start")
        if start.status_code < 400:
            return start.json() if start.content else {"name": session}

    raise WahaError(
        f"WAHA rejected session start (HTTP {resp.status_code}).{_error_detail(resp)}"
    )


async def get_session(session: str) -> dict:
    resp = await _request("GET", f"/api/sessions/{session}")
    if resp.status_code == 404:
        return {"name": session, "status": "STOPPED"}
    if resp.status_code >= 400:
        raise WahaError(f"WAHA session status failed (HTTP {resp.status_code}).")
    return resp.json()


async def get_qr_png(session: str) -> bytes:
    """PNG of the login QR. Only valid while status == SCAN_QR_CODE."""
    resp = await _request("GET", f"/api/{session}/auth/qr", accept="image/png")
    if resp.status_code >= 400:
        raise WahaError(
            "QR not available yet — the session may still be starting.",
            status_code=409,
        )
    return resp.content


async def send_text(session: str, chat_id: str, text: str) -> None:
    resp = await _request(
        "POST", "/api/sendText",
        json={"session": session, "chatId": chat_id, "text": text},
    )
    if resp.status_code >= 400:
        raise WahaError(
            f"WAHA sendText failed (HTTP {resp.status_code}).{_error_detail(resp)}"
        )


async def logout_session(session: str) -> None:
    """Unlink the device and stop the session (safe to call when already stopped)."""
    resp = await _request("POST", f"/api/sessions/{session}/logout")
    if resp.status_code >= 400 and resp.status_code != 404:
        logger.warning("waha_logout_failed", session=session, status=resp.status_code)
    await _request("POST", f"/api/sessions/{session}/stop")
