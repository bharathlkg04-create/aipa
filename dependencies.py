from cryptography.fernet import Fernet
from fastapi import Request

from aipa.config import get_settings


async def get_db(request: Request):
    return request.app.state.db_pool


def get_fernet() -> Fernet:
    return Fernet(get_settings().FERNET_KEY.encode())
