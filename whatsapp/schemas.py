from pydantic import BaseModel, ConfigDict


class WahaEvent(BaseModel):
    """Envelope WAHA POSTs to our webhook. Payload shape varies by engine,
    so it stays a raw dict and the router extracts what it needs."""

    model_config = ConfigDict(extra="allow")

    event: str
    session: str
    payload: dict = {}


class WhatsAppConnectRequest(BaseModel):
    business_id: str


class WhatsAppDisconnectRequest(BaseModel):
    business_id: str
