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
from aipa.telegram.sender import send_telegram_message

logger = structlog.get_logger(__name__)

_ERROR_MESSAGES = {
    LLMAuthError: "I'm having trouble connecting right now. Please contact support.",
    LLMRateLimitError: "I'm a bit busy right now — please try again in a moment.",
    LLMCallError: "Something went wrong on my end. Please try again.",
    MissingAPIKeyError: "This assistant isn't fully configured yet. Please contact the business.",
    EncryptionError: "A configuration error occurred. Please contact support.",
}


async def process_telegram_message(
    pool,
    channel,
    update: TelegramUpdate,
) -> None:
    msg = update.message
    business_id = str(channel["business_id"])
    channel_id = str(channel["id"])
    bot_token: str = channel["channel_token"]
    chat_id: int = msg.chat.id
    user_text: str = msg.text

    log = logger.bind(
        business_id=business_id,
        update_id=update.update_id,
        chat_id=chat_id,
    )

    async def _reply_error(error_text: str) -> None:
        try:
            await send_telegram_message(bot_token, chat_id, error_text)
        except Exception as send_exc:
            log.error("failed_to_send_error_reply", error=str(send_exc))

    try:
        conversation_id = await get_or_create_conversation(
            pool, business_id, channel_id, str(chat_id)
        )

        await save_message(pool, conversation_id, role="user", content=user_text)

        fernet = get_fernet()
        context = await fetch_agent_context(
            pool, business_id, conversation_id, fernet, user_text=user_text
        )

        system_prompt = build_system_prompt(context)
        llm_messages = build_llm_messages(
            system_prompt, context.recent_messages, user_text
        )

        model: str = (context.boss_config or {}).get("llm_model", "openai/gpt-4o-mini")
        temperature: float = float((context.boss_config or {}).get("temperature", 0.7))

        ai_response = await call_llm(model, llm_messages, context.decrypted_api_key, temperature)

        await save_message(pool, conversation_id, role="assistant", content=ai_response)
        await send_telegram_message(bot_token, chat_id, ai_response)

        log.info("message_processed_ok")

    except tuple(_ERROR_MESSAGES.keys()) as exc:
        error_text = _ERROR_MESSAGES[type(exc)]
        log.warning("handled_agent_error", error_type=type(exc).__name__, detail=str(exc))
        await _reply_error(error_text)

    except Exception as exc:
        log.exception("unhandled_message_processing_error", error=str(exc))
        await _reply_error("An unexpected error occurred. Please try again later.")
