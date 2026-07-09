import asyncio
from typing import Awaitable, Callable

import structlog

from aipa.agent.context_fetcher import fetch_agent_context
from aipa.agent.llm_client import call_llm
from aipa.agent.prompt_builder import build_llm_messages, build_system_prompt
from aipa.core.exceptions import (
    EncryptionError,
    LLMAuthError,
    LLMCallError,
    LLMRateLimitError,
    MissingAPIKeyError,
)
from aipa.db.queries.conversations import get_or_create_conversation
from aipa.db.queries.messages import save_message
from aipa.dependencies import get_fernet
from aipa.telegram.schemas import TelegramUpdate
from aipa.telegram.sender import send_telegram_message, send_typing_action

logger = structlog.get_logger(__name__)

_ERROR_MESSAGES = {
    LLMAuthError: "I'm having trouble connecting right now. Please contact support.",
    LLMRateLimitError: "I'm a bit busy right now — please try again in a moment.",
    LLMCallError: "Something went wrong on my end. Please try again.",
    MissingAPIKeyError: "This assistant isn't fully configured yet. Please contact the business.",
    EncryptionError: "A configuration error occurred. Please contact support.",
}

SendReply = Callable[[str], Awaitable[None]]
SetTyping = Callable[[bool], Awaitable[None]]

# Telegram's typing indicator expires after ~5s, so refresh just under that.
_TYPING_REFRESH_S = 4.0


async def _process_inbound(
    pool,
    channel,
    customer_id: str,
    user_text: str,
    send_reply: SendReply,
    log,
    customer_name: str | None = None,
    set_typing: SetTyping | None = None,
) -> None:
    """Channel-agnostic pipeline: persist → build context → LLM → reply."""

    async def _reply_error(error_text: str) -> None:
        try:
            await send_reply(error_text)
        except Exception as send_exc:
            log.error("failed_to_send_error_reply", error=str(send_exc))

    business_id = str(channel["business_id"])
    channel_id = str(channel["id"])

    # Cosmetic only: keep the 'typing…' presence alive until the reply is sent,
    # and never let an indicator failure break message processing.
    typing_task: asyncio.Task | None = None
    if set_typing is not None:
        async def _keep_typing() -> None:
            try:
                while True:
                    await set_typing(True)
                    await asyncio.sleep(_TYPING_REFRESH_S)
            except Exception as exc:
                log.debug("typing_indicator_failed", error=str(exc))
        typing_task = asyncio.create_task(_keep_typing())

    try:
        conversation_id = await get_or_create_conversation(
            pool, business_id, channel_id, customer_id
        )

        await save_message(pool, conversation_id, role="user", content=user_text)

        fernet = get_fernet()
        context = await fetch_agent_context(
            pool, business_id, conversation_id, fernet, user_text=user_text
        )

        system_prompt = build_system_prompt(context, customer_name)
        llm_messages = build_llm_messages(
            system_prompt, context.recent_messages, user_text
        )

        model: str = (context.boss_config or {}).get("llm_model", "openai/gpt-4o-mini")
        temperature: float = float((context.boss_config or {}).get("temperature", 0.7))

        ai_response = await call_llm(model, llm_messages, context.decrypted_api_key, temperature)

        await save_message(pool, conversation_id, role="assistant", content=ai_response)
        await send_reply(ai_response)

        log.info("message_processed_ok")

    except tuple(_ERROR_MESSAGES.keys()) as exc:
        error_text = _ERROR_MESSAGES[type(exc)]
        log.warning("handled_agent_error", error_type=type(exc).__name__, detail=str(exc))
        await _reply_error(error_text)

    except Exception as exc:
        log.exception("unhandled_message_processing_error", error=str(exc))
        await _reply_error("An unexpected error occurred. Please try again later.")

    finally:
        if typing_task is not None:
            typing_task.cancel()
            try:
                await set_typing(False)
            except Exception:
                pass


async def process_telegram_message(
    pool,
    channel,
    update: TelegramUpdate,
) -> None:
    msg = update.message
    bot_token: str = channel["channel_token"]
    chat_id: int = msg.chat.id

    # The customer's Telegram account name, e.g. "Bharath (@bharath_k)"
    customer_name = None
    if msg.from_user is not None:
        customer_name = msg.from_user.first_name
        if msg.from_user.username:
            customer_name += f" (@{msg.from_user.username})"

    log = logger.bind(
        business_id=str(channel["business_id"]),
        update_id=update.update_id,
        chat_id=chat_id,
    )

    async def send_reply(text: str) -> None:
        await send_telegram_message(bot_token, chat_id, text)

    async def set_typing(on: bool) -> None:
        if on:  # Telegram has no explicit "stop"; it expires on its own
            await send_typing_action(bot_token, chat_id)

    await _process_inbound(
        pool, channel, str(chat_id), msg.text, send_reply, log,
        customer_name=customer_name, set_typing=set_typing,
    )


async def process_whatsapp_message(
    pool,
    channel,
    chat_id: str,
    user_text: str,
    customer_name: str | None = None,
) -> None:
    # Imported here so Telegram-only deployments never touch WAHA settings
    from aipa.whatsapp.waha import send_text, start_typing, stop_typing

    session: str = channel["channel_token"]

    log = logger.bind(
        business_id=str(channel["business_id"]),
        channel_type="whatsapp",
        chat_id=chat_id,
        customer_name=customer_name,
    )

    async def send_reply(text: str) -> None:
        await send_text(session, chat_id, text)

    async def set_typing(on: bool) -> None:
        if on:
            await start_typing(session, chat_id)
        else:
            await stop_typing(session, chat_id)

    await _process_inbound(
        pool, channel, chat_id, user_text, send_reply, log,
        customer_name=customer_name, set_typing=set_typing,
    )
