"""探索用例：組合快取搜尋、拓撲過濾、代價排名；以及彈性日期價格矩陣。"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.metrics import rank_offers, sort_offers
from app.domain.offers import FlightOffer
from app.domain.topology import apply_topology, collect_hubs
from app.integrations.duffel_client import DuffelClient, DuffelError
from app.schemas import (
    AirlineOption,
    CacheInfo,
    FxInfo,
    MatrixRequest,
    NumericRange,
    SearchRequest,
    SearchResult,
)
from app.services.fx import FxRates, to_currency
from app.services.search_service import RouteQuery, SearchService, cheapest_price


def _within_price(offer: FlightOffer, low: Decimal | None, high: Decimal | None) -> bool:
    return (low is None or offer.total_amount >= low) and (
        high is None or offer.total_amount <= high
    )


def _bounds(values: list[Decimal]) -> NumericRange | None:
    return NumericRange(min=min(values), max=max(values)) if values else None


def fx_info(fx: FxRates, currency: str) -> FxInfo:
    return FxInfo(currency=currency, as_of=fx.as_of, source=fx.source, approximate=fx.approximate)


async def run_search(
    service: SearchService,
    client: DuffelClient,
    fx: FxRates,
    request: SearchRequest,
    origin_airports: list[str],
    destination_airports: list[str],
) -> SearchResult:
    outcome = await service.fetch(request.to_route_query(), client, refresh=request.refresh)
    # 先換算成顯示幣別，之後的票價篩選、代價指標與排序都以同一幣別比較
    converted = [to_currency(o, fx, request.currency) for o in outcome.offers]
    filtered = [
        o
        for o in apply_topology(converted, request.to_filter())
        if _within_price(o, request.price_min, request.price_max)
    ]
    # 時間價值以 USD 輸入，換算成顯示幣別後才能與票價相加
    time_value = fx.convert(request.time_value_per_hour, "USD", request.currency)
    ranked = rank_offers(filtered, time_value)
    ordered = sort_offers(ranked, request.sort, request.descending)
    airlines = {o.airline_code: o.airline_name for o in converted}
    return SearchResult(
        currency=request.currency,
        fx=fx_info(fx, request.currency),
        # 滑桿的上下限取自全部結果，篩選後範圍不會跟著縮小
        price_bounds=_bounds([o.total_amount for o in converted]),
        duration_bounds=_bounds([Decimal(s.duration_minutes) for o in converted for s in o.slices]),
        origin_airports=origin_airports,
        destination_airports=destination_airports,
        cache=CacheInfo(
            hit=outcome.cache_hit, key=outcome.cache_key, fetched_at=outcome.fetched_at
        ),
        total_raw=len(outcome.offers),
        total_filtered=len(filtered),
        hubs=collect_hubs(outcome.offers),
        airlines=[
            AirlineOption(code=c, name=n) for c, n in sorted(airlines.items(), key=lambda x: x[1])
        ],
        offers=ordered[: request.limit],
    )


def matrix_axes(request: MatrixRequest, today: date) -> tuple[list[date], list[date | None]]:
    """出發日／回程日各 ±radius 天；過去的日期不納入。"""
    offsets = range(-request.radius_days, request.radius_days + 1)
    departures = [
        d for d in (request.departure_date + timedelta(days=i) for i in offsets) if d >= today
    ]
    if request.return_date is None:
        return departures, [None]
    returns: list[date | None] = [request.return_date + timedelta(days=i) for i in offsets]
    return departures, returns


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


async def stream_matrix(
    service: SearchService,
    client: DuffelClient,
    fx: FxRates,
    request: MatrixRequest,
    concurrency: int,
    today: date,
) -> AsyncIterator[str]:
    """以 NDJSON 串流輸出矩陣：先送座標軸，再依完成順序送出每一格（先到先渲染）。"""
    departures, returns = matrix_axes(request, today)
    rule = request.to_filter()
    yield _line(
        {
            "type": "axes",
            "currency": request.currency,
            "fx_approximate": fx.approximate,
            "departure_dates": [d.isoformat() for d in departures],
            "return_dates": [r.isoformat() if r else None for r in returns],
        }
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def cell(dep: date, ret: date | None) -> dict[str, Any]:
        base = {
            "type": "cell",
            "departure_date": dep.isoformat(),
            "return_date": ret.isoformat() if ret else None,
        }
        if ret is not None and ret < dep:
            return {**base, "status": "invalid"}
        query = RouteQuery(
            origin=request.origin,
            destination=request.destination,
            departure_date=dep,
            return_date=ret,
            adults=request.adults,
            children=request.children,
            cabin_class=request.cabin_class,
            max_connections=rule.effective_max_stops,
        )
        async with semaphore:
            try:
                outcome = await service.fetch(query, client)
            except DuffelError as exc:
                return {**base, "status": "error", "message": exc.user_message}
        converted = [to_currency(o, fx, request.currency) for o in outcome.offers]
        offers = [
            o
            for o in apply_topology(converted, rule)
            if _within_price(o, request.price_min, request.price_max)
        ]
        price = cheapest_price(offers)
        return {
            **base,
            "status": "ok" if price is not None else "empty",
            "price": str(price) if price is not None else None,
            "currency": request.currency,
            "cached": outcome.cache_hit,
            "simulated": any(o.is_simulated for o in offers),
        }

    tasks = [asyncio.create_task(cell(d, r)) for d in departures for r in returns]
    try:
        for finished in asyncio.as_completed(tasks):
            yield _line(await finished)
    finally:
        for task in tasks:
            task.cancel()
    yield _line({"type": "done"})
