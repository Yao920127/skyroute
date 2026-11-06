"""看盤巡檢與自動失效流程（Offline Pipeline）。

Worker 每分鐘觸發一次，只處理「到期」（next_check_at 已到）的追蹤；手動巡檢則處理全部。
1. 出發日已過的追蹤標的 → EXPIRED（不再輪詢）
2. 讀取要巡檢的清單，依「航線 + 日期 + 乘客 + 艙等 + 轉機上限」去重聚合
3. 推入佇列，由多個 consumer 受控消費（對外呼叫經過令牌桶節流）
4. 每個標的套用自己的拓撲條件取最低價 → 寫入 price_history
5. 比對目標價 / 7 日均價降幅 → 檢查 24 小時冷卻 → 推播並寫入 alert_history
6. 依各自的頻率排定下一次巡檢時間（失敗也照排，避免每分鐘重試耗盡配額）
"""

import asyncio
import hashlib
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionFactory
from app.domain.connections import cheapest_chain
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
from app.services.schedule import PatrolSchedule
from app.services.search_service import Leg, RouteQuery, SearchService

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
    schedule: PatrolSchedule


class GroupKey(NamedTuple):
    """去重聚合的單位：相同查詢條件 + 相同金鑰（不同帳號的配額與報價不可混用）。"""

    query: RouteQuery
    key_fingerprint: str | None


def stored_legs(watch: TrackedWatchlist) -> tuple[Leg, ...]:
    """第 2 段以後的航段（資料庫以 JSON 保存）。"""
    return tuple(
        Leg(
            origin=leg["origin"],
            destination=leg["destination"],
            departure_date=date.fromisoformat(leg["departure_date"]),
        )
        for leg in (watch.extra_legs or [])
    )


def _query(watch: TrackedWatchlist, first: Leg, **extra: object) -> RouteQuery:
    return RouteQuery(
        origin=first.origin,
        destination=first.destination,
        departure_date=first.departure_date,
        adults=watch.adults,
        children=watch.children,
        cabin_class=watch.cabin_class,
        max_connections=watch.max_stops,
        **extra,
    )


def first_leg(watch: TrackedWatchlist) -> Leg:
    return Leg(
        origin=watch.origin, destination=watch.destination, departure_date=watch.departure_date
    )


def route_query_for(watch: TrackedWatchlist) -> RouteQuery:
    """整張票：單程、來回或多航段，一次查詢。"""
    return _query(
        watch, first_leg(watch), return_date=watch.return_date, extra_legs=stored_legs(watch)
    )


def queries_for(watch: TrackedWatchlist) -> list[RouteQuery]:
    """分段購票：每一段各自查單程；整張票：一個查詢。"""
    if watch.ticket_mode == "split":
        return [_query(watch, leg) for leg in (first_leg(watch), *stored_legs(watch))]
    return [route_query_for(watch)]


def leg_airline(watch: TrackedWatchlist, index: int) -> str | None:
    airlines = watch.leg_airlines or []
    return airlines[index] if index < len(airlines) else watch.preferred_airline


def filter_for(watch: TrackedWatchlist, airline: str | None = None) -> TopologyFilter:
    chosen = airline if airline is not None else watch.preferred_airline
    return TopologyFilter(
        # 看盤畫面把 max_stops=0 標示為「僅直飛」，因此同樣排除中途經停的航班
        direct_only=watch.max_stops == 0,
        max_stops=watch.max_stops,
        allowed_hubs=frozenset(watch.allowed_transits or []),
        excluded_hubs=frozenset(watch.excluded_transits or []),
        min_layover_minutes=watch.min_layover_minutes,
        max_layover_minutes=watch.max_layover_minutes,
        airlines=frozenset([chosen]) if chosen else frozenset(),
    )


def _cheapest(offers: tuple[FlightOffer, ...], rule: TopologyFilter) -> FlightOffer | None:
    return min(apply_topology(offers, rule), key=lambda o: o.total_amount, default=None)


def best_offer_for(watch: TrackedWatchlist, offers: tuple[FlightOffer, ...]) -> FlightOffer | None:
    return _cheapest(offers, filter_for(watch))


@dataclass(frozen=True)
class Priced:
    """一筆追蹤本次的價格：整張票為一個報價；分段購票為每段最便宜報價的合計。"""

    offers: tuple[FlightOffer, ...]

    @property
    def total_amount(self) -> Decimal:
        return sum((o.total_amount for o in self.offers), Decimal(0))

    @property
    def currency(self) -> str:
        return self.offers[0].currency

    @property
    def airline_code(self) -> str:
        return "+".join(o.airline_code for o in self.offers)

    @property
    def duration_minutes(self) -> int:
        return sum(o.total_duration_minutes for o in self.offers)

    @property
    def stops(self) -> int:
        return max(o.max_stops for o in self.offers)


def price_watch(
    watch: TrackedWatchlist, offer_sets: list[tuple[FlightOffer, ...]]
) -> Priced | None:
    """任何一段找不到符合條件的航班，整筆就視為本次無價格。"""
    if watch.ticket_mode != "split":
        best = best_offer_for(watch, offer_sets[0])
        return Priced((best,)) if best else None
    # 每段先套用條件與指定航司，再找「時間銜接得上」的最便宜組合（不是各段各自最便宜）
    candidates = [
        list(apply_topology(offers, filter_for(watch, leg_airline(watch, index))))
        for index, offers in enumerate(offer_sets)
    ]
    chain = cheapest_chain(candidates)
    return Priced(tuple(chain)) if chain else None


def route_hash_for(queries: list[RouteQuery]) -> str:
    if len(queries) == 1:
        return queries[0].route_hash
    joined = "|".join(q.route_hash for q in queries)
    return hashlib.sha256(joined.encode()).hexdigest()


def group_by_route(watches: list[TrackedWatchlist]) -> dict[GroupKey, list[TrackedWatchlist]]:
    """同一個查詢（含分段購票的單段）只打一次 Duffel，供所有需要它的追蹤共用。"""
    groups: dict[GroupKey, list[TrackedWatchlist]] = defaultdict(list)
    for watch in watches:
        for query in queries_for(watch):
            groups[GroupKey(query, watch.token_fingerprint)].append(watch)
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
    priced: Priced,
    route_hash: str,
    now: datetime,
    stats: Counter[str],
) -> None:
    baseline = await _baseline_avg(session, watch.id, now)  # 寫入前計算，不含本次價格
    amount = priced.total_amount
    record = PriceHistory(
        watchlist_id=watch.id,
        route_hash=route_hash,
        airline_code=priced.airline_code[:20],
        price=amount,
        currency=priced.currency,
        duration_minutes=priced.duration_minutes,
        stops=priced.stops,
        offers=[o.model_dump(mode="json") for o in priced.offers],
        recorded_at=now,
    )
    session.add(record)
    await session.flush()
    stats["prices_recorded"] += 1

    reason = threshold_reason(amount, watch.target_price, watch.drop_percent, baseline)
    if reason is None:
        return
    last = await _last_alert(session, watch.id)
    if in_cooldown(
        last.sent_at if last else None,
        last.triggered_price if last else None,
        amount,
        now,
        ctx.cooldown_hours,
    ):
        stats["alerts_suppressed"] += 1
        return
    try:
        channel = await ctx.notifier.send(watch, priced.offers, reason)
    except (NotificationError, ValueError) as exc:
        log.error("標的 %s 告警推播失敗：%s", watch.id, exc)
        stats["failures"] += 1
        return
    session.add(
        AlertHistory(
            watchlist_id=watch.id,
            price_history_id=record.id,
            triggered_price=amount,
            currency=priced.currency,
            reason=reason,
            channel=channel,
            sent_at=now,
        )
    )
    stats["alerts_sent"] += 1


FetchResults = dict[GroupKey, tuple[FlightOffer, ...] | None]


async def fetch_group(
    ctx: PatrolContext, key: GroupKey, watches: list[TrackedWatchlist], stats: Counter[str]
) -> tuple[FlightOffer, ...] | None:
    try:
        client = client_for(ctx, key, watches)
        # 巡檢一律取最新報價並回寫快取
        outcome = await ctx.search.fetch(key.query, client, refresh=True)
    except (DuffelError, MissingCredentialsError) as exc:
        log.error("巡檢查詢失敗 %s：%s", key.query.cache_key, exc)
        stats["failures"] += 1
        return None
    stats["api_calls"] += 1
    return outcome.offers


async def _consume(
    ctx: PatrolContext,
    queue: asyncio.Queue[tuple[GroupKey, list[TrackedWatchlist]]],
    results: FetchResults,
    stats: Counter[str],
) -> None:
    while True:
        try:
            key, watches = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            results[key] = await fetch_group(ctx, key, watches, stats)
        except Exception:  # 單一群組失敗不可中斷整個巡檢
            log.exception("巡檢群組 %s 發生未預期錯誤", key.query.cache_key)
            stats["failures"] += 1
            results[key] = None
        finally:
            queue.task_done()


async def evaluate(
    ctx: PatrolContext,
    watches: list[TrackedWatchlist],
    results: FetchResults,
    now: datetime,
    stats: Counter[str],
) -> None:
    """所有查詢完成後，逐筆算出價格（分段購票要等每一段都查到）並寫入歷史、判斷告警。"""
    fx: FxRates | None = await ctx.fx.rates() if any(w.currency for w in watches) else None
    async with ctx.sessions() as session:
        for watch in watches:
            queries = queries_for(watch)
            offer_sets = [results.get(GroupKey(q, watch.token_fingerprint)) for q in queries]
            if any(offers is None for offers in offer_sets):
                continue  # 查詢失敗已計入 failures
            sets = [offers for offers in offer_sets if offers is not None]
            if watch.currency and fx is not None:
                # 換算成使用者設定的幣別，歷史價格與門檻比對都用同一幣別
                sets = [tuple(to_currency(o, fx, watch.currency) for o in s) for s in sets]
            priced = price_watch(watch, sets)
            if priced is None:
                log.info("標的 %s 本次無符合條件的航班", watch.id)
                continue
            try:
                await process_watch(
                    ctx, session, watch, priced, route_hash_for(queries), now, stats
                )
            except Exception:
                log.exception("標的 %s 寫入價格失敗", watch.id)
                stats["failures"] += 1
        await session.commit()


async def run_patrol(
    ctx: PatrolContext,
    cache: Cache,
    consumers: int,
    lock_ttl_s: int,
    today: date | None = None,
    now: datetime | None = None,
    owner: str | None = None,
    due_only: bool = False,
) -> PatrolReport:
    """owner 為 None 時巡檢全站；指定時只巡檢該使用者的追蹤（使用各自的鎖，互不阻擋）。

    due_only=True（Worker 每分鐘的排程）只處理 next_check_at 已到或尚未排定的追蹤。
    """
    lock_name = f"{PATROL_LOCK}:{owner}" if owner else PATROL_LOCK
    token = await cache.acquire_lock(lock_name, lock_ttl_s)
    if token is None:
        log.info("另一個巡檢正在執行，略過本次")
        return PatrolReport(skipped_locked=True)

    now = now or datetime.now(UTC)
    today = today or now.date()
    stats: Counter[str] = Counter()
    try:
        async with ctx.sessions() as session:
            stats["expired"] = await expire_departed(session, today)
            query = select(TrackedWatchlist).where(
                TrackedWatchlist.is_active.is_(True),
                TrackedWatchlist.status == WatchStatus.TRACKING,
            )
            if owner:
                query = query.where(TrackedWatchlist.user_identifier == owner)
            if due_only:
                query = query.where(
                    or_(
                        TrackedWatchlist.next_check_at.is_(None),
                        TrackedWatchlist.next_check_at <= now,
                    )
                )
            watches = list((await session.scalars(query)).all())
        stats["active"] = len(watches)
        groups = group_by_route(watches)
        stats["route_groups"] = len(groups)

        queue: asyncio.Queue[tuple[GroupKey, list[TrackedWatchlist]]] = asyncio.Queue()
        for item in groups.items():
            queue.put_nowait(item)
        results: FetchResults = {}
        await asyncio.gather(*(_consume(ctx, queue, results, stats) for _ in range(consumers)))
        await evaluate(ctx, watches, results, now, stats)
        await reschedule(ctx, watches, now)
    finally:
        await cache.release_lock(lock_name, token)

    report = PatrolReport(**{k: v for k, v in stats.items() if k in PatrolReport.model_fields})
    if report.active or report.expired:  # 每分鐘的排程多半沒有到期項目，不必每次記錄
        log.info("巡檢完成：%s", report.model_dump())
    return report


async def reschedule(ctx: PatrolContext, watches: list[TrackedWatchlist], now: datetime) -> None:
    """依各自的頻率排定下一次巡檢；沒有自己金鑰的追蹤最短 30 分鐘。"""
    if not watches:
        return
    async with ctx.sessions() as session:
        for watch in watches:
            next_at = ctx.schedule.next_check(
                now, watch.patrol_interval_minutes, bool(watch.token_fingerprint)
            )
            await session.execute(
                update(TrackedWatchlist)
                .where(TrackedWatchlist.id == watch.id)
                .values(next_check_at=next_at)
            )
        await session.commit()
