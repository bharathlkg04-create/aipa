import structlog
import httpx

logger = structlog.get_logger(__name__)


async def get_bot_info(bot_token: str) -> dict | None:
    """Resolve a bot token to its identity via Telegram getMe.
    Returns {'id', 'username', 'name'} or None when the token is invalid."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not data.get("ok"):
        return None
    result = data["result"]
    return {
        "id": result.get("id"),
        "username": result.get("username"),
        "name": result.get("first_name"),
    }


async def send_telegram_message(
    bot_token: str,
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Markdown parse errors: retry as plain text
            if exc.response.status_code == 400 and parse_mode != "None":
                logger.warning(
                    "telegram_send_markdown_failed_retrying_plain",
                    chat_id=chat_id,
                    status=exc.response.status_code,
                )
                plain_payload = {"chat_id": chat_id, "text": text}
                retry = await client.post(url, json=plain_payload)
                retry.raise_for_status()
            else:
                raise
