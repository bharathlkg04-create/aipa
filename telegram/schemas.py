from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str


class TelegramMessage(BaseModel):
    message_id: int
    # `from` is a Python keyword — Telegram sends it as "from"
    from_user: TelegramUser | None = Field(None, alias="from")
    chat: TelegramChat
    text: str | None = None
    date: int

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
