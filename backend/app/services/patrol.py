"""每日看盤巡檢與自動失效流程（Offline Pipeline）。

1. 出發日已過的追蹤標的 → EXPIRED（不再輪詢）
2. 讀取有效清單，依「航線 + 日期 + 乘客 + 艙等 + 轉機上限」去重聚合
3. 推入佇列，由多個 consumer 受控消費（對外呼叫經過令牌桶節流）
4. 每個標的套用自己的拓撲條件取最低價 → 寫入 price_history
5. 比對目標價 / 7 日均價降幅 → 檢查 24 小時冷卻 → 推播並寫入 alert_history
"""

import asyncio
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionFactory
from app.domain.offers import FlightOffer
from app.domain.topology import TopologyFilter, apply_topology
from app.integrations.duffel_client import (
    DuffelClient,
    DuffelError,
    DuffelGateway,
    MissingCredentialsError,
)
from app.models import AlertHistory, PriceHistory, TrackedWatchlist, WatchStatus
from app.schemas import PatrolReport
from app.services.alerts import NotificationError, Notifier, in_cooldown, threshold_reason
from app.services.cache import Cache
from app.services.credentials import TokenCipher
from app.services.fx import FxRates, FxService, to_currency
from app.services.search_service import RouteQuery, SearchService

log = logging.getLogger(__name__)

PATROL_LOCK = "skyroute:lock:patrol"
BASELINE_DAYS = 7


@dataclass(frozen=True)
class PatrolContext:
    sessions: SessionFactory
    search: SearchService
    gateway: DuffelGateway
    cipher: TokenCipher
    fx: FxService
    notifier: Notifier
    cooldown_hours: int


class GroupKey(NamedTuple):
    """去重聚合的單位：相同查詢條件 + 相同金鑰（不同帳號的配額與報價不可混用）。"""

    query: RouteQuery
    key_fingerprint: str | None


def route_query_for(watch: TrackedWatchlist) -> RouteQuery:
    return RouteQuery(
        origin=watch.origin,
        destination=watch.destination,
        departure_date=watch.departure_date,
        return_date=watch.return_date,
        adults=watch.adults,
        children=watch.children,
        cabin_class=watch.cabin_class,
        max_connections=watch.max_stops,
    )


def filter_for(watch: TrackedWatchlist) -> TopologyFilter:
    return TopologyFilter(
        # 看盤畫面把 max_stops=0 標示為「僅直飛」，因此同樣排除中途經停的航班
        direct_only=watch.max_stops == 0,
        max_stops=watch.max_stops,
        allowed_hubs=frozenset(watch.allowed_transits or []),
        excluded_hubs=frozenset(watch.excluded_transits or []),
        min_layover_minutes=watch.min_layover_minutes,
        max_layover_minutes=watch.max_layover_minutes,
        airlines=frozenset([watch.preferred_airline]) if watch.preferred_airline else frozenset(),
    )


def best_offer_for(watch: TrackedWatchlist, offers: tuple[FlightOffer, ...]) -> FlightOffer | None:
    matched = apply_topology(offers, filter_for(watch))
    return min(matched, key=lambda o: o.total_amount, default=None)


def group_by_route(watches: list[TrackedWatchlist]) -> dict[GroupKey, list[TrackedWatchlist]]:
    groups: dict[GroupKey, list[TrackedWatchlist]] = defaultdict(list)
    for watch in watches:
        groups[GroupKey(route_query_for(watch), watch.token_fingerprint)].append(watch)
    return dict(groups)


def client_for(ctx: PatrolContext, key: GroupKey, watches: list[TrackedWatchlist]) -> DuffelClient:
    """群組內金鑰相同（指紋一致），解密任一筆即可；無法解密時拋出 MissingCredentialsError。"""
    if key.key_fingerprint is None:
        return ctx.gateway.client(None)
    for watch in watches:
        token = ctx.cipher.decrypt(watch.duffel_token_enc) if watch.duffel_token_enc else None
        if token:
            return ctx.gateway.client(token)
    raise MissingCredentialsError("無法解密使用者金鑰（SECRET_KEY 可能已更換）")


async def expire_departed(session: AsyncSession, today: date) -> int:
    result = await session.execute(
        update(TrackedWatchlist)
        .where(TrackedWatchlist.is_active.is_(True), TrackedWatchlist.departure_date < today)
        .values(status=WatchStatus.EXPIRED, is_active=False, duffel_token_enc=None)
    )
    await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def _baseline_avg(session: AsyncSession, watch_id: object, now: datetime) -> Decimal | None:
    value = await session.scalar(
        select(func.avg(PriceHistory.price)).where(
            PriceHistory.watchlist_id == watch_id,
            PriceHistory.recorded_at >= now - timedelta(days=BASELINE_DAYS),
        )
    )
    return Decimal(value) if value is not None else None


async def _last_alert(session: AsyncSession, watch_id: object) -> AlertHistory | None:
    return await session.scalar(
        select(AlertHistory)
        .where(AlertHistory.watchlist_id == watch_id)
        .order_by(AlertHistory.sent_at.desc())
        .limit(1)
    )


async def process_watch(
    ctx: PatrolContext,
    session: AsyncSession,
    watch: TrackedWatchlist,
    query: RouteQuery,
    offers: tuple[FlightOffer, ...],
    now: datetime,
    stats: Counter[str],
    fx: FxRates | None = None,
) -> None:
    if watch.currency and fx is not None:
        # 換算成使用者設定的幣別，歷史價格與門檻比對都用同一幣別
        offers = tuple(to_currency(o, fx, watch.currency) for o in offers)
    offer = best_offer_for(watch, offers)
    if offer is None:
        log.info("標的 %s 本次無符合條件的航班", watch.id)
        return

    baseline = await _baseline_avg(session, watch.id, now)  # 寫入前計算，不含本次價格
    record = PriceHistory(
        watchlist_id=watch.id,
        route_hash=query.route_hash,
        airline_code=offer.airline_code,
        price=offer.total_amount,
        currency=offer.currency,
        duration_minutes=offer.total_duration_minutes,
        stops=offer.max_stops,
        recorded_at=now,
    )
    session.add(record)
    await session.flush()
    stats["prices_recorded"] += 1

    reason = threshold_reason(offer.total_amount, watch.target_price, watch.drop_percent, baseline)
    if reason is None:
        return
    last = await _last_alert(session, watch.id)
    if in_cooldown(
        last.sent_at if last else None,
        last.triggered_price if last else None,
        offer.total_amount,
        now,
        ctx.cooldown_hours,
    ):
        stats["alerts_suppressed"] += 1
        return
    try:
        channel = await ctx.notifier.send(watch, offer, reason)
    except (NotificationError, ValueError) as exc:
        log.error("標的 %s 告警推播失敗：%s", watch.id, exc)
        stats["failures"] += 1
        return
    session.add(
        AlertHistory(
            watchlist_id=watch.id,
            price_history_id=record.id,
            triggered_price=offer.total_amount,
            currency=offer.currency,
            reason=reason,
            channel=channel,
            sent_at=now,
        )
    )
    stats["alerts_sent"] += 1


async def process_group(
    ctx: PatrolContext,
    key: GroupKey,
    watches: list[TrackedWatchlist],
    now: datetime,
    stats: Counter[str],
) -> None:
    query = key.query
    try:
        client = client_for(ctx, key, watches)
        # 巡檢一律取最新報價並回寫快取
        outcome = await ctx.search.fetch(query, client, refresh=True)
    except (DuffelError, MissingCredentialsError) as exc:
        log.error("巡檢查詢失敗 %s：%s", query.cache_key, exc)
        stats["failures"] += 1
        return
    stats["api_calls"] += 1
    fx = await ctx.fx.rates() if any(w.currency for w in watches) else None
    async with ctx.sessions() as session:
        for watch in watches:
            await process_watch(ctx, session, watch, query, outcome.offers, now, stats, fx)
        await session.commit()


async def _consume(
    ctx: PatrolContext,
    queue: asyncio.Queue[tuple[GroupKey, list[TrackedWatchlist]]],
    now: datetime,
    stats: Counter[str],
) -> None:
    while True:
        try:
            key, watches = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            await process_group(ctx, key, watches, now, stats)
        except Exception:  # 單一群組失敗不可中斷整個巡檢
            log.exception("巡檢群組 %s 發生未預期錯誤", key.query.cache_key)
            stats["failures"] += 1
        finally:
            queue.task_done()


async def run_patrol(
    ctx: PatrolContext,
    cache: Cache,
    consumers: int,
    lock_ttl_s: int,
    today: date | None = None,
    now: datetime | None = None,
) -> PatrolReport:
    token = await cache.acquire_lock(PATROL_LOCK, lock_ttl_s)
    if token is None:
        log.info("另一個巡檢正在執行，略過本次")
        return PatrolReport(skipped_locked=True)

    now = now or datetime.now(UTC)
    today = today or now.date()
    stats: Counter[str] = Counter()
    try:
        async with ctx.sessions() as session:
            stats["expired"] = await expire_departed(session, today)
            watches = list(
                (
                    await session.scalars(
                        select(TrackedWatchlist).where(
                            TrackedWatchlist.is_active.is_(True),
                            TrackedWatchlist.status == WatchStatus.TRACKING,
                        )
                    )
                ).all()
            )
        stats["active"] = len(watches)
        groups = group_by_route(watches)
        stats["route_groups"] = len(groups)

        queue: asyncio.Queue[tuple[GroupKey, list[TrackedWatchlist]]] = asyncio.Queue()
        for item in groups.items():
            queue.put_nowait(item)
        await asyncio.gather(*(_consume(ctx, queue, now, stats) for _ in range(consumers)))
    finally:
        await cache.release_lock(PATROL_LOCK, token)

    report = PatrolReport(**{k: v for k, v in stats.items() if k in PatrolReport.model_fields})
    log.info("巡檢完成：%s", report.model_dump())
    return report
