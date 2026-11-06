"""非同步資料庫引擎與 Session 工廠（連線池由 SQLAlchemy 管理）。"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

SCHEMA_LOCK_ID = 727_001  # 任意固定值，用於 pg_advisory_xact_lock


# create_all 不會替既有資料表加欄位；這裡列出冪等的新增欄位遷移（正式環境建議改用 Alembic）
_ADDITIVE_MIGRATIONS = (
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS duffel_token_enc TEXT",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS token_fingerprint VARCHAR(16)",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS currency VARCHAR(3)",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS patrol_interval_minutes INTEGER",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_watchlists_next_check ON tracked_watchlists (next_check_at)",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS ticket_mode VARCHAR(10) "
    "NOT NULL DEFAULT 'ticket'",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS extra_legs JSONB "
    "NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE tracked_watchlists ADD COLUMN IF NOT EXISTS leg_airlines JSONB "
    "NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE price_history ALTER COLUMN airline_code TYPE VARCHAR(20)",
    "ALTER TABLE airports ADD COLUMN IF NOT EXISTS city_name VARCHAR(100)",
    "ALTER TABLE airports ADD COLUMN IF NOT EXISTS size_rank INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE airports ADD COLUMN IF NOT EXISTS search_text TEXT",
    "ALTER TABLE price_history ADD COLUMN IF NOT EXISTS offers JSONB",
)


class Base(DeclarativeBase):
    pass


SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_size=10, max_overflow=10, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_schema(engine: AsyncEngine) -> None:
    """建立資料表（冪等）。正式環境可改由 migration 工具管理。"""
    from app import models  # noqa: F401  確保模型已註冊到 metadata

    async with engine.begin() as conn:
        # 多個 API／Worker 程序同時啟動時，序列化建表避免競爭
        await conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": SCHEMA_LOCK_ID})
        await conn.run_sync(Base.metadata.create_all)
        for statement in _ADDITIVE_MIGRATIONS:
            await conn.execute(text(statement))
