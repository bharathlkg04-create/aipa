from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    bot_token: str
    api_key: str
    model: str = "openai/gpt-4o-mini"
    business_name: str = "My Business"
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class VerifyBotRequest(BaseModel):
    bot_token: str = Field(min_length=10, max_length=100)
