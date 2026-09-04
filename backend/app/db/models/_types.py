"""Shared column types.

Amounts are NUMERIC(78, 0) integers at raw chain precision. A float anywhere in an
amount path is a bug (docs/DATA_ARCHITECTURE.md section 3).
"""

from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Numeric

RawAmount = Numeric(78, 0)
Fraction = Numeric(18, 12)


def pg_enum(enum_cls: Any, name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, native_enum=True, validate_strings=True)
