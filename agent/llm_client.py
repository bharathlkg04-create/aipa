import litellm
import structlog
from litellm.exceptions import APIError, AuthenticationError, RateLimitError

from aipa.core.exceptions import LLMAuthError, LLMCallError, LLMRateLimitError

logger = structlog.get_logger(__name__)

# Disable LiteLLM's built-in success/failure callbacks to keep logs clean
litellm.success_callback = []
litellm.failure_callback = []


async def call_llm(
    model: str,
    messages: list[dict],
    api_key: str,
    temperature: float = 0.7,
) -> str:
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=temperature,
            timeout=30,
        )
        return response.choices[0].message.content
    except AuthenticationError as exc:
        logger.error("llm_auth_failed", model=model, error=str(exc))
        raise LLMAuthError("Business API key is invalid or expired.") from exc
    except RateLimitError as exc:
        logger.warning("llm_rate_limited", model=model)
        raise LLMRateLimitError("LLM provider rate limit reached.") from exc
    except APIError as exc:
        logger.error("llm_api_error", model=model, error=str(exc))
        raise LLMCallError(f"LLM API call failed: {exc}") from exc
