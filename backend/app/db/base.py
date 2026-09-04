"""Declarative base with a fixed constraint naming convention.

Alembic needs deterministic constraint names to generate reversible migrations; without
a convention, autogenerate produces unnamed constraints it cannot later drop.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Every timestamp is timestamptz, stored UTC (DATABASE_DESIGN.md section 9, rule 7).
    # Set once here so no individual column can forget it.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )


def utcnow_column(**kwargs: Any) -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False, **kwargs)
