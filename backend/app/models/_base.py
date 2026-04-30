"""
Common types, mixins and base classes used across all models.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime


def utcnow() -> datetime:
    """Single source of truth for 'now' — always UTC, always tz-aware."""
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    """
    Adds created_at / updated_at to any model.
    Use as a mixin: class MyModel(TimestampMixin, table=True): ...

    NOTE: We deliberately don't use sa_column here because SQLModel/SQLAlchemy
    can't share a Column instance across multiple tables. Each subclass gets
    its own Column auto-derived from the field type.
    """

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ISO 3166-1 alpha-3 country code, e.g. "RUS", "AZE", "ESP"
# Stored as 3-char string. Validated via list of allowed codes — see
# `app/services/countries.py` for the list and helpers.
CountryCode = str

# Currency code (ISO 4217), e.g. "RUB", "EUR", "KZT"
CurrencyCode = str
