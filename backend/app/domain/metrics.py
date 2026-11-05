"""綜合代價指標、標籤（最便宜／最快速／性價比首選）與排序。

綜合代價 = 票價 + (純飛行時數 + 轉機等待時數 × 1.5) × 時間權重單價
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.domain.offers import FlightOffer, OfferTag, RankedOffer

LAYOVER_PENALTY = Decimal("1.5")
DEFAULT_TIME_VALUE_PER_HOUR = Decimal("15")
_MINUTES_PER_HOUR = Decimal(60)

SortKey = Literal["price", "duration", "departure", "arrival", "airline", "cost"]


def cost_index(offer: FlightOffer, time_value_per_hour: Decimal) -> Decimal:
    flight_hours = Decimal(offer.flight_minutes) / _MINUTES_PER_HOUR
    layover_hours = Decimal(offer.layover_minutes) / _MINUTES_PER_HOUR
    weighted_hours = flight_hours + layover_hours * LAYOVER_PENALTY
    value = offer.total_amount + weighted_hours * time_value_per_hour
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rank_offers(
    offers: Sequence[FlightOffer], time_value_per_hour: Decimal = DEFAULT_TIME_VALUE_PER_HOUR
) -> list[RankedOffer]:
    """計算每筆 offer 的代價並標記最便宜、最快速、性價比首選。"""
    if not offers:
        return []
    costs = [cost_index(o, time_value_per_hour) for o in offers]
    cheapest = min(range(len(offers)), key=lambda i: (offers[i].total_amount, costs[i]))
    fastest = min(
        range(len(offers)), key=lambda i: (offers[i].total_duration_minutes, offers[i].total_amount)
    )
    best = min(range(len(offers)), key=lambda i: (costs[i], offers[i].total_amount))

    ranked: list[RankedOffer] = []
    for i, offer in enumerate(offers):
        tags: list[OfferTag] = []
        if i == cheapest:
            tags.append("cheapest")
        if i == fastest:
            tags.append("fastest")
        if i == best:
            tags.append("best_value")
        ranked.append(
            RankedOffer(
                offer=offer,
                total_duration_minutes=offer.total_duration_minutes,
                flight_minutes=offer.flight_minutes,
                layover_minutes=offer.layover_minutes,
                max_stops=offer.max_stops,
                cost_index=costs[i],
                tags=tuple(tags),
            )
        )
    return ranked


def _sort_value(item: RankedOffer, key: SortKey) -> tuple[object, ...]:
    offer = item.offer
    first = offer.slices[0]
    match key:
        case "price":
            return (offer.total_amount, item.total_duration_minutes)
        case "duration":
            return (item.total_duration_minutes, offer.total_amount)
        case "departure":
            return (first.departing_at, offer.total_amount)
        case "arrival":
            return (first.arriving_at, offer.total_amount)
        case "airline":
            return (offer.airline_name, offer.total_amount)
        case "cost":
            return (item.cost_index, offer.total_amount)


def sort_offers(
    items: Sequence[RankedOffer], key: SortKey, descending: bool = False
) -> list[RankedOffer]:
    return sorted(items, key=lambda item: _sort_value(item, key), reverse=descending)
