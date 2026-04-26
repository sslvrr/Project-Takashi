"""
SQLAlchemy ORM models for Project Takashi.
All tables are created via db.session.init_db().
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, Text, JSON
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)         # BUY | SELL
    entry = Column(Float, nullable=False)
    exit = Column(Float, nullable=True)
    size = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    tp = Column(Float, nullable=True)
    sl = Column(Float, nullable=True)
    score = Column(Integer, nullable=True)
    mode = Column(String(10), nullable=False, default="PAPER")  # PAPER | LIVE
    reason = Column(String(50), nullable=True)             # TP | SL | MANUAL
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Trade {self.symbol} {self.direction} PnL={self.pnl}>"


class FeatureSnapshot(Base):
    """Stores ML feature vectors for model training."""
    __tablename__ = "feature_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    features = Column(JSON, nullable=False)
    target = Column(Integer, nullable=True)   # 1 = price up next bar, 0 = down
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Investor(Base):
    __tablename__ = "investors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    capital = Column(Float, nullable=False, default=0.0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemEvent(Base):
    """Audit log for kill switch triggers, mode changes, alerts."""
    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
