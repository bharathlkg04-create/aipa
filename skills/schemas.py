from pydantic import BaseModel, Field


class ToggleSkillRequest(BaseModel):
    business_id: str
    is_enabled: bool
    is_pinned: bool | None = None


class EnablePackRequest(BaseModel):
    business_id: str
    industry: str
    pack_size: int = Field(default=8, ge=1, le=20)
