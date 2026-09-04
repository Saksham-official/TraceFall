import base64
import binascii

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
