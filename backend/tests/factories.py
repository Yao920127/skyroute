"""測試資料工廠：產生 Duffel 原始 offer 與領域模型。"""

from decimal import Decimal
from typing import Any

from app.domain.offers import FlightOffer, Layover, Segment, Slice


def raw_segment(
    origin: str,
    destination: str,
    dep: str,
    arr: str,
    duration: str | None = "PT2H",
    carrier: str = "BR",
    number: str = "100",
) -> dict[str, Any]:
    return {
        "origin": {"iata_code": origin, "city_name": origin.title()},
        "destination": {"iata_code": destination, "city_name": destination.title()},
        "departing_at": dep,
        "arriving_at": arr,
        "duration": duration,
        "marketing_carrier": {"iata_code": carrier, "name": f"{carrier} Air"},
        "marketing_carrier_flight_number": number,
        "aircraft": {"name": "Airbus A350"},
        "stops": [],
    }


def raw_offer(
    offer_id: str,
    amount: str,
    slices: list[list[dict[str, Any]]],
    owner: str = "BR",
    currency: str = "USD",
) -> dict[str, Any]:
    return {
        "id": offer_id,
        "total_amount": amount,
        "total_currency": currency,
        "owner": {"iata_code": owner, "name": f"{owner} Air", "logo_symbol_url": None},
        "conditions": {
            "refund_before_departure": None,
            "change_before_departure": {"allowed": True},
        },
        "total_emissions_kg": "120",
        "expires_at": "2026-12-01T00:00:00Z",
        "slices": [
            {
                "origin": {"iata_code": segs[0]["origin"]["iata_code"]},
                "destination": {"iata_code": segs[-1]["destination"]["iata_code"]},
                "duration": None,
                "segments": segs,
            }
            for segs in slices
        ],
    }


def direct_raw(
    offer_id: str, amount: str, owner: str = "BR", number: str = "100"
) -> dict[str, Any]:
    return raw_offer(
        offer_id,
        amount,
        [
            [
                raw_segment(
                    "TPE",
                    "NRT",
                    "2026-12-20T08:00:00",
                    "2026-12-20T12:00:00",
                    "PT3H",
                    owner,
                    number,
                )
            ]
        ],
        owner=owner,
    )


def connecting_raw(
    offer_id: str, amount: str, hub: str, layover_end: str, owner: str = "CX"
) -> dict[str, Any]:
    return raw_offer(
        offer_id,
        amount,
        [
            [
                raw_segment(
                    "TPE", hub, "2026-12-20T08:00:00", "2026-12-20T10:00:00", "PT2H", owner, "1"
                ),
                raw_segment(hub, "NRT", layover_end, "2026-12-20T18:00:00", "PT4H", owner, "2"),
            ]
        ],
        owner=owner,
    )


def make_offer(
    offer_id: str = "off_1",
    amount: str = "100",
    layovers: list[tuple[str, int]] | None = None,
    airline: str = "BR",
    flight_minutes: int = 180,
    departing_at: str = "2026-12-20T08:00:00",
) -> FlightOffer:
    layovers = layovers or []
    segment_count = len(layovers) + 1
    per_segment = flight_minutes // segment_count
    segments = tuple(
        Segment(
            carrier_code=airline,
            carrier_name=f"{airline} Air",
            flight_number=f"{airline}{i}",
            origin="TPE",
            destination="NRT",
            departing_at=departing_at,
            arriving_at=departing_at,
            duration_minutes=per_segment,
        )
        for i in range(segment_count)
    )
    lays = tuple(Layover(airport=a, minutes=m) for a, m in layovers)
    duration = per_segment * segment_count + sum(m for _, m in layovers)
    return FlightOffer(
        id=offer_id,
        airline_code=airline,
        airline_name=f"{airline} Air",
        total_amount=Decimal(amount),
        currency="USD",
        slices=(
            Slice(
                origin="TPE",
                destination="NRT",
                departing_at=departing_at,
                arriving_at=departing_at,
                duration_minutes=duration,
                segments=segments,
                layovers=lays,
            ),
        ),
    )
