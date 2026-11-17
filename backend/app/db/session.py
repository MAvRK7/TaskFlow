"""Database package: SQLAlchemy engine, session, and declarative base.

The engine and sessionmaker are created once at import time and shared
application-wide. Each request receives its own :class:`Session` via
:func:`get_db`, which is responsible for closing it when the generator is
exhausted.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""


# Shared application-wide engine and sessionmaker. The connection pool is
# reused across requests; only the Session object is per-request.
_engine = create_engine(get_settings().database_url, pool_pre_ping=True)
_session_local = sessionmaker(
    bind=_engine, autoflush=False, autocommit=False, class_=Session
)


def get_engine():
    """Return the shared application-wide SQLAlchemy engine."""
    return _engine


def get_session_local():
    """Return the shared application-wide sessionmaker."""
    return _session_local


def get_db() -> Iterator[Session]:
    """Yield a database session and close it afterwards.

    Intended for use as a FastAPI dependency:

        def route(db: Session = Depends(get_db)): ...

    The engine and sessionmaker are shared application-wide. Each request
    receives its own :class:`Session` instance, which is closed in the
    ``finally`` block when the generator is exhausted (after the response
    has been sent).
    """
    db = _session_local()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "get_db", "get_engine", "get_session_local"]
