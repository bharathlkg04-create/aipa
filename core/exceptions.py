class AIPayError(Exception):
    """Base exception for all AI'PA errors."""


class EncryptionError(AIPayError):
    """Raised when Fernet decryption fails — key mismatch or corrupted ciphertext."""


class ChannelNotFoundError(AIPayError):
    """Raised when a webhook arrives for an unknown or inactive channel token."""


class LLMAuthError(AIPayError):
    """Raised when the business's API key is rejected by the LLM provider."""


class LLMRateLimitError(AIPayError):
    """Raised when the LLM provider returns a rate-limit response."""


class LLMCallError(AIPayError):
    """Raised for generic LLM API failures."""


class MissingAPIKeyError(AIPayError):
    """Raised when no API key is configured for a business."""
