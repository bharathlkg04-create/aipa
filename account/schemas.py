from pydantic import BaseModel, Field


class UpdateConfigRequest(BaseModel):
    business_id: str
    llm_model: str = Field(min_length=1, max_length=100)
    temperature: float = Field(ge=0.0, le=2.0)
    system_prompt: str | None = Field(default=None, max_length=4000)
    timezone: str | None = Field(default=None, max_length=64)


class ReplaceApiKeyRequest(BaseModel):
    business_id: str
    api_key: str = Field(min_length=8, max_length=500)
    provider: str | None = Field(default=None, max_length=40)


class LinkBusinessRequest(BaseModel):
    business_id: str
    owner_token: str = Field(min_length=8, max_length=200)


class GoogleSignInRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=4000)


class SignUpRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)
