"""實體資料模型：airports、users、tracked_watchlists、price_history、alert_history。"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WatchStatus(StrEnum):
    TRACKING = "TRACKING"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Airport(Base):
    __tablename__ = "airports"

    iata_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    city_code: Mapped[str] = mapped_column(String(3), index=True)
    name_zh: Mapped[str | None] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2))
    timezone: Mapped[str | None] = mapped_column(String(50))
    # airport：實體機場；city：城市聚合代碼（如 TYO → HND/NRT）
    kind: Mapped[str] = mapped_column(String(10), default="airport", server_default="airport")
    city_name: Mapped[str | None] = mapped_column(String(100))
    # 排序用：0＝內建常用／城市、1＝大型、2＝中型、3＝小型機場
    size_rank: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # 搜尋用：代碼＋中英文名稱＋城市，去除重音並轉小寫（reykjavik 可找到 Reykjavík）
    search_text: Mapped[str | None] = mapped_column(Text)


class User(Base):
    """以 Google 帳號登入的使用者；帳號專屬的 Duffel 金鑰以 SECRET_KEY 加密保存。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    picture: Mapped[str | None] = mapped_column(String(500))
    duffel_token_enc: Mapped[str | None] = mapped_column(Text)
    token_fingerprint: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrackedWatchlist(Base):
    __tablename__ = "tracked_watchlists"
    __table_args__ = (
        Index("ix_watchlists_patrol", "is_active", "departure_date"),
        Index("ix_watchlists_next_check", "next_check_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_identifier: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str | None] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(ForeignKey("airports.iata_code"))
    destination: Mapped[str] = mapped_column(ForeignKey("airports.iata_code"))
    departure_date: Mapped[date] = mapped_column(Date, index=True)
    return_date: Mapped[date | None] = mapped_column(Date)
    adults: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    children: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cabin_class: Mapped[str] = mapped_column(String(20), default="economy")
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    drop_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    preferred_airline: Mapped[str | None] = mapped_column(String(2))
    allowed_transits: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    excluded_transits: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    max_stops: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    min_layover_minutes: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    max_layover_minutes: Mapped[int] = mapped_column(Integer, default=300, server_default="300")
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    # 使用者自備金鑰：以 SECRET_KEY 加密保存，供背景巡檢使用；取消／過期時清除
    # 目標價的幣別；NULL 為舊資料（沿用航空公司原始幣別，不換算）
    currency: Mapped[str | None] = mapped_column(String(3))
    duffel_token_enc: Mapped[str | None] = mapped_column(Text)
    token_fingerprint: Mapped[str | None] = mapped_column(String(16))
    # ticket＝整張票（可含多航段 extra_legs）；split＝分段購票：每段各查單程、合計價格，可混搭航司
    ticket_mode: Mapped[str] = mapped_column(String(10), default="ticket", server_default="ticket")
    # 第 2 段以後：[{origin, destination, departure_date}]
    extra_legs: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # 分段購票時每段指定的航司（與航段一一對應，None＝不限）
    leg_airlines: Mapped[list[str | None]] = mapped_column(JSONB, default=list, server_default="[]")
    # 巡檢頻率（分鐘）；NULL＝每日固定時間。next_check_at 為下一次應巡檢的時間
    patrol_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=WatchStatus.TRACKING, server_default=WatchStatus.TRACKING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_watch_time", "watchlist_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracked_watchlists.id", ondelete="CASCADE"), index=True
    )
    route_hash: Mapped[str] = mapped_column(String(64), index=True)
    # 分段購票會記錄多家航司，例如 CZ+BR
    airline_code: Mapped[str] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="TWD", server_default="TWD")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    stops: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = (Index("ix_alert_history_watch_time", "watchlist_id", "sent_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracked_watchlists.id", ondelete="CASCADE")
    )
    price_history_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_history.id", ondelete="SET NULL")
    )
    triggered_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(String(20))  # target / drop
    channel: Mapped[str] = mapped_column(String(20))  # webhook / log
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
