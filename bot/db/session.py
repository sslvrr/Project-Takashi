"""
SQLAlchemy session factory.
Provides get_session() context manager for all DB access.
"""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from db.models import Base
from config.settings import settings
from core.logger import logger

_engine = None
_SessionFactory = None


def init_db() -> None:
    """Create all tables (idempotent — safe to call on every start)."""
    global _engine, _SessionFactory
    try:
        _engine = create_engine(
            settings.DB_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        Base.metadata.create_all(_engine)
        _SessionFactory = sessionmaker(bind=_engine)
        logger.info("[db] Database initialized.")
    except Exception as exc:
        logger.error(f"[db] Database init failed: {exc}. Running without persistence.")
        _engine = None
        _SessionFactory = None


@contextmanager
def get_session():
    """Yield a SQLAlchemy session, committing on success or rolling back on error."""
    if _SessionFactory is None:
        yield None
        return
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"[db] Session error: {exc}")
        raise
    finally:
        session.close()


def is_available() -> bool:
    return _engine is not None
