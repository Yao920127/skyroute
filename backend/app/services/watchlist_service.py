"""自選看盤清單：建立、編輯（名稱與巡檢頻率）、查詢（附統計）、軟刪除、歷史價格與告警紀錄。"""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.offers import FlightOffer
from app.integrations.duffel_client import DuffelClient
from app.models import AlertHistory, PriceHistory, TrackedWatchlist, WatchStatus
from app.schemas import (
    AlertOut,
    Itinerary,
    PricePoint,
    WatchlistCreate,
    WatchlistOut,
    WatchlistUpdate,
)
from app.services.airport_service import ensure_airport
from app.services.alerts import validate_webhook_url
from app.services.board_stats import PriceSample, compute_stats
from app.services.credentials import CipherUnavailable, TokenCipher
from app.services.schedule import IntervalNotAllowed, PatrolSchedule, check_interval

STATS_LOOKBACK_DAYS = 30

log = logging.getLogger(__name__)


class NotFoundError(Exception):
    pass


class ValidationFailed(Exception):
    pass


def to_out(watch: TrackedWatchlist, **extra: object) -> WatchlistOut:
    base = WatchlistOut.model_validate(watch)
    flags = {"has_webhook": bool(watch.webhook_url), "uses_own_key": bool(watch.token_fingerprint)}
    return base.model_copy(update={**flags, **extra})


async def create_watchlist(
    session: AsyncSession,
    client: DuffelClient,
    user_id: str,
    payload: WatchlistCreate,
    allowed_webhook_hosts: list[str],
    cipher: TokenCipher,
    user_token: str | None = None,
    schedule: PatrolSchedule | None = None,
    now: datetime | None = None,
) -> WatchlistOut:
    try:
        check_interval(payload.patrol_interval_minutes, uses_own_key=bool(user_token))
    except IntervalNotAllowed as exc:
        raise ValidationFailed(str(exc)) from exc
    token_enc = None
    if user_token:
        try:
            token_enc = cipher.encrypt(user_token)
        except CipherUnavailable as exc:
            raise ValidationFailed(str(exc)) from exc
    webhook = None
    if payload.webhook_url:
        try:
            webhook = validate_webhook_url(payload.webhook_url, allowed_webhook_hosts)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
    codes = {payload.origin, payload.destination}
    codes.update(c for leg in payload.extra_legs for c in (leg.origin, leg.destination))
    for code in sorted(codes):
        if not await ensure_airport(session, client, code):
            raise ValidationFailed(f"找不到機場或城市代碼：{code}")

    watch = TrackedWatchlist(
        user_identifier=user_id,
        **payload.model_dump(exclude={"webhook_url", "extra_legs"}),
        extra_legs=[leg.model_dump(mode="json") for leg in payload.extra_legs],
        webhook_url=webhook,
        duffel_token_enc=token_enc,
        token_fingerprint=client.namespace if user_token else None,
        next_check_at=(
            schedule.next_check(
                now or datetime.now(UTC), payload.patrol_interval_minutes, bool(user_token)
            )
            if schedule
            else None
        ),
    )
    session.add(watch)
    await session.commit()
    await session.refresh(watch)
    return to_out(watch)


async def get_owned(session: AsyncSession, user_id: str, watch_id: uuid.UUID) -> TrackedWatchlist:
    watch = await session.get(TrackedWatchlist, watch_id)
    if watch is None or watch.user_identifier != user_id:
        raise NotFoundError("找不到此追蹤項目")
    return watch


async def update_watchlist(
    session: AsyncSession,
    user_id: str,
    watch_id: uuid.UUID,
    payload: WatchlistUpdate,
    schedule: PatrolSchedule,
    now: datetime | None = None,
) -> WatchlistOut:
    """名稱直接覆寫舊值；變更巡檢頻率時，從現在起重新排定下一次巡檢。"""
    watch = await get_owned(session, user_id, watch_id)
    fields = payload.model_fields_set
    if "label" in fields:
        watch.label = payload.label
    if fields & {"target_price", "drop_percent"}:
        target = payload.target_price if "target_price" in fields else watch.target_price
        drop = payload.drop_percent if "drop_percent" in fields else watch.drop_percent
        if target is None and drop is None:
            raise ValidationFailed("請至少設定目標價或相對降幅其中一項")
        watch.target_price = target
        watch.drop_percent = drop
    if "patrol_interval_minutes" in fields:
        if watch.status != WatchStatus.TRACKING:
            raise ValidationFailed("已結束的追蹤無法變更巡檢頻率")
        minutes = payload.patrol_interval_minutes
        own_key = bool(watch.token_fingerprint)
        try:
            check_interval(minutes, uses_own_key=own_key)
        except IntervalNotAllowed as exc:
            raise ValidationFailed(str(exc)) from exc
        watch.patrol_interval_minutes = minutes
        watch.next_check_at = schedule.next_check(now or datetime.now(UTC), minutes, own_key)
    await session.commit()
    await session.refresh(watch)
    return to_out(watch)


async def cancel_watchlist(
    session: AsyncSession, user_id: str, watch_id: uuid.UUID
) -> WatchlistOut:
    watch = await get_owned(session, user_id, watch_id)
    await session.execute(
        update(TrackedWatchlist)
        .where(TrackedWatchlist.id == watch.id)
        .values(
            status=WatchStatus.CANCELLED,
            is_active=False,
            duffel_token_enc=None,  # 不再巡檢就不保留使用者金鑰
        )
    )
    await session.commit()
    await session.refresh(watch)
    return to_out(watch)


ENDED_STATUSES = (WatchStatus.CANCELLED, WatchStatus.EXPIRED)


async def purge_watchlist(session: AsyncSession, user_id: str, watch_id: uuid.UUID) -> None:
    """永久刪除：連同歷史價格與告警紀錄（資料庫外鍵 ON DELETE CASCADE）一併移除。"""
    watch = await get_owned(session, user_id, watch_id)
    await session.execute(delete(TrackedWatchlist).where(TrackedWatchlist.id == watch.id))
    await session.commit()


async def purge_ended(session: AsyncSession, user_id: str) -> int:
    """清除此使用者所有已取消／已過期的追蹤，回傳刪除筆數。"""
    result = await session.execute(
        delete(TrackedWatchlist).where(
            TrackedWatchlist.user_identifier == user_id,
            TrackedWatchlist.status.in_(ENDED_STATUSES),
        )
    )
    await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def list_watchlists(
    session: AsyncSession, user_id: str, include_inactive: bool, now: datetime | None = None
) -> list[WatchlistOut]:
    stmt = select(TrackedWatchlist).where(TrackedWatchlist.user_identifier == user_id)
    if not include_inactive:
        stmt = stmt.where(TrackedWatchlist.status != WatchStatus.CANCELLED)
    watches = list((await session.scalars(stmt.order_by(TrackedWatchlist.departure_date))).all())
    if not watches:
        return []
    ids = [w.id for w in watches]
    since = (now or datetime.now(UTC)) - timedelta(days=STATS_LOOKBACK_DAYS)

    # 一次撈出所有標的的近期價格與最後告警時間，避免 N+1 查詢
    history_rows = await session.execute(
        select(
            PriceHistory.watchlist_id,
            PriceHistory.recorded_at,
            PriceHistory.price,
            PriceHistory.currency,
        )
        .where(PriceHistory.watchlist_id.in_(ids), PriceHistory.recorded_at >= since)
        .order_by(PriceHistory.recorded_at)
    )
    samples: dict[uuid.UUID, list[PriceSample]] = defaultdict(list)
    for wid, recorded_at, price, currency in history_rows:
        samples[wid].append(PriceSample(recorded_at, price, currency))

    alert_rows = await session.execute(
        select(AlertHistory.watchlist_id, func.max(AlertHistory.sent_at))
        .where(AlertHistory.watchlist_id.in_(ids))
        .group_by(AlertHistory.watchlist_id)
    )
    last_alert = {wid: sent_at for wid, sent_at in alert_rows}

    return [to_out(w, stats=compute_stats(samples[w.id], last_alert.get(w.id))) for w in watches]


async def price_history(
    session: AsyncSession, user_id: str, watch_id: uuid.UUID, days: int
) -> list[PricePoint]:
    await get_owned(session, user_id, watch_id)
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await session.scalars(
        select(PriceHistory)
        .where(PriceHistory.watchlist_id == watch_id, PriceHistory.recorded_at >= since)
        .order_by(PriceHistory.recorded_at)
    )
    return [
        PricePoint(
            recorded_at=r.recorded_at,
            price=r.price,
            currency=r.currency,
            airline_code=r.airline_code,
            stops=r.stops,
            duration_minutes=r.duration_minutes,
        )
        for r in rows
    ]


async def latest_itinerary(
    session: AsyncSession, user_id: str, watch_id: uuid.UUID
) -> Itinerary | None:
    """最近一筆有航班明細的價格紀錄；舊紀錄（尚未記錄明細）或資料格式不符時回傳 None。"""
    await get_owned(session, user_id, watch_id)
    row = await session.scalar(
        select(PriceHistory)
        .where(PriceHistory.watchlist_id == watch_id, PriceHistory.offers.is_not(None))
        .order_by(PriceHistory.recorded_at.desc())
        .limit(1)
    )
    if row is None or not row.offers:
        return None
    try:
        offers = [FlightOffer.model_validate(o) for o in row.offers]
    except ValidationError as exc:
        log.warning("標的 %s 的航班明細格式不符，略過：%s", watch_id, exc)
        return None
    return Itinerary(
        recorded_at=row.recorded_at, price=row.price, currency=row.currency, offers=offers
    )


async def alert_history(session: AsyncSession, user_id: str, watch_id: uuid.UUID) -> list[AlertOut]:
    await get_owned(session, user_id, watch_id)
    rows = await session.scalars(
        select(AlertHistory)
        .where(AlertHistory.watchlist_id == watch_id)
        .order_by(AlertHistory.sent_at.desc())
        .limit(50)
    )
    return [AlertOut.model_validate(r) for r in rows]
