"""即時航班搜尋：參數正規化 → 產生快取鍵 → Cache-Aside → 呼叫 Duffel → 扁平化。"""

import hashlib
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.domain.offers import CabinClass, FlightOffer, Frozen
from app.integrations.duffel_client import DuffelClient
from app.integrations.duffel_mapper import map_offers
from app.services.cache import Cache

log = logging.getLogger(__name__)

CHILD_DEFAULT_AGE = 10  # Duffel 要求未滿 18 歲乘客提供年齡；未指定時以 10 歲計價


class Leg(Frozen):
    origin: str
    destination: str
    departure_date: date


class RouteQuery(Frozen):
    """已正規化、可作為快取與去重依據的查詢條件（不含後置過濾條件）。

    單程／來回用 origin、destination、departure_date、return_date；
    多航段（例如 台北→倫敦、巴黎→台北）時，第 2 段以後放在 extra_legs，且 return_date 為 None。
    """

    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    extra_legs: tuple[Leg, ...] = ()
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    cabin_class: CabinClass = "economy"
    max_connections: int = Field(default=1, ge=0, le=2)

    @property
    def pax_hash(self) -> str:
        raw = f"a{self.adults}:c{self.children}:m{self.max_connections}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def legs(self) -> tuple[Leg, ...]:
        first = Leg(
            origin=self.origin, destination=self.destination, departure_date=self.departure_date
        )
        back = (
            (
                Leg(
                    origin=self.destination,
                    destination=self.origin,
                    departure_date=self.return_date,
                ),
            )
            if self.return_date
            else ()
        )
        return (first, *back, *self.extra_legs)

    @property
    def cache_key(self) -> str:
        ret = self.return_date.isoformat() if self.return_date else "-"
        key = (
            f"route:{self.origin}:{self.destination}:{self.departure_date.isoformat()}"
            f":{ret}:{self.cabin_class}:{self.pax_hash}"
        )
        if self.extra_legs:
            key += ":mc:" + "|".join(
                f"{leg.origin}-{leg.destination}-{leg.departure_date.isoformat()}"
                for leg in self.extra_legs
            )
        return key

    @property
    def route_hash(self) -> str:
        return hashlib.sha256(self.cache_key.encode()).hexdigest()

    def to_duffel(self) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        slices = [
            {
                "origin": leg.origin,
                "destination": leg.destination,
                "departure_date": leg.departure_date.isoformat(),
            }
            for leg in self.legs
        ]
        passengers: list[dict[str, Any]] = [{"type": "adult"} for _ in range(self.adults)]
        passengers += [{"age": CHILD_DEFAULT_AGE} for _ in range(self.children)]
        return slices, passengers


class CachedSearch(Frozen):
    offers: tuple[FlightOffer, ...]
    fetched_at: datetime


class SearchOutcome(Frozen):
    offers: tuple[FlightOffer, ...]
    fetched_at: datetime
    cache_hit: bool
    cache_key: str


def _itinerary_key(offer: FlightOffer) -> tuple[str, ...]:
    return (offer.airline_code,) + tuple(
        f"{seg.flight_number}@{seg.departing_at}" for s in offer.slices for seg in s.segments
    )


def dedupe_itineraries(offers: list[FlightOffer]) -> list[FlightOffer]:
    """Duffel 會對同一行程回傳多個票價品牌，此處只保留每個行程的最低價。"""
    best: dict[tuple[str, ...], FlightOffer] = {}
    for offer in offers:
        key = _itinerary_key(offer)
        current = best.get(key)
        if current is None or offer.total_amount < current.total_amount:
            best[key] = offer
    return sorted(best.values(), key=lambda o: o.total_amount)


class SearchService:
    """快取與查詢邏輯；呼叫端傳入綁定特定金鑰的 DuffelClient。"""

    def __init__(
        self, cache: Cache, ttl_s: int, excluded_airlines: frozenset[str] = frozenset()
    ) -> None:
        self._excluded = excluded_airlines
        self._cache = cache
        self._ttl_s = ttl_s

    async def fetch(
        self, query: RouteQuery, client: DuffelClient, *, refresh: bool = False
    ) -> SearchOutcome:
        # 依金鑰指紋分隔快取：不同 Duffel 帳號的報價（含私有票價）不互相共用
        key = f"{query.cache_key}:{client.namespace}"
        if not refresh:
            cached = await self._cache.get(key)
            if cached is not None:
                try:
                    hit = CachedSearch.model_validate_json(cached)
                    return SearchOutcome(
                        offers=hit.offers, fetched_at=hit.fetched_at, cache_hit=True, cache_key=key
                    )
                except ValueError:
                    log.warning("快取內容損毀，重新查詢：%s", key)

        slices, passengers = query.to_duffel()
        raw = await client.create_offer_request(
            slices, passengers, query.cabin_class, query.max_connections
        )
        offers = tuple(dedupe_itineraries(map_offers(raw.get("offers") or [], self._excluded)))
        fetched_at = datetime.now(UTC)
        await self._cache.set(
            key, CachedSearch(offers=offers, fetched_at=fetched_at).model_dump_json(), self._ttl_s
        )
        log.info("Duffel 查詢 %s → %d 筆行程", key, len(offers))
        return SearchOutcome(offers=offers, fetched_at=fetched_at, cache_hit=False, cache_key=key)


def cheapest_price(offers: tuple[FlightOffer, ...] | list[FlightOffer]) -> Decimal | None:
    return min((o.total_amount for o in offers), default=None)
