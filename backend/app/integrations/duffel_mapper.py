"""把 Duffel 深層巢狀的 offer 結構扁平化為 SkyRoute 領域模型（防腐層的翻譯部分）。"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.durations import minutes_between, parse_iso_duration
from app.domain.offers import FlightOffer, Layover, Segment, Slice, TechnicalStop

log = logging.getLogger(__name__)


def _condition_allowed(condition: dict[str, Any] | None) -> bool | None:
    """null 代表未知（不是不允許）。"""
    if condition is None:
        return None
    return bool(condition.get("allowed"))


def map_stop(raw: dict[str, Any]) -> TechnicalStop:
    airport = raw.get("airport") or {}
    minutes = parse_iso_duration(raw.get("duration"))
    if minutes is None and raw.get("arriving_at") and raw.get("departing_at"):
        # 同一機場、同一時區，直接相減即可
        minutes = max(0, minutes_between(raw["arriving_at"], raw["departing_at"]))
    return TechnicalStop(
        airport=airport.get("iata_code") or "???",
        city_name=airport.get("city_name"),
        minutes=minutes or 0,
    )


def map_segment(raw: dict[str, Any]) -> Segment:
    carrier = raw.get("marketing_carrier") or raw.get("operating_carrier") or {}
    operating = raw.get("operating_carrier") or {}
    is_codeshare = bool(operating.get("iata_code")) and operating.get("iata_code") != carrier.get(
        "iata_code"
    )
    duration = parse_iso_duration(raw.get("duration"))
    if duration is None:
        # 缺 duration 時以當地時間差估算（跨時區時僅為近似值）
        duration = max(0, minutes_between(raw["departing_at"], raw["arriving_at"]))
    aircraft = raw.get("aircraft") or {}
    code = carrier.get("iata_code") or ""
    number = raw.get("marketing_carrier_flight_number") or ""
    return Segment(
        carrier_code=carrier.get("iata_code") or "??",
        carrier_name=carrier.get("name") or carrier.get("iata_code") or "Unknown",
        flight_number=f"{code}{number}",
        origin=raw["origin"]["iata_code"],
        destination=raw["destination"]["iata_code"],
        departing_at=raw["departing_at"],
        arriving_at=raw["arriving_at"],
        duration_minutes=duration,
        aircraft=aircraft.get("name"),
        stops=tuple(map_stop(stop) for stop in raw.get("stops") or []),
        operating_code=operating.get("iata_code") if is_codeshare else None,
        operating_name=operating.get("name") if is_codeshare else None,
    )


def map_slice(raw: dict[str, Any]) -> Slice:
    raw_segments = raw.get("segments") or []
    segments = tuple(map_segment(s) for s in raw_segments)
    layovers = tuple(
        Layover(
            airport=segments[i].destination,
            city_name=(raw_segments[i].get("destination") or {}).get("city_name"),
            minutes=minutes_between(segments[i].arriving_at, segments[i + 1].departing_at),
        )
        for i in range(len(segments) - 1)
    )
    duration = parse_iso_duration(raw.get("duration"))
    if duration is None:
        duration = sum(s.duration_minutes for s in segments) + sum(lay.minutes for lay in layovers)
    return Slice(
        origin=raw["origin"]["iata_code"],
        destination=raw["destination"]["iata_code"],
        departing_at=segments[0].departing_at,
        arriving_at=segments[-1].arriving_at,
        duration_minutes=duration,
        segments=segments,
        layovers=layovers,
    )


def map_offer(raw: dict[str, Any]) -> FlightOffer:
    owner = raw.get("owner") or {}
    conditions = raw.get("conditions") or {}
    emissions = raw.get("total_emissions_kg")
    return FlightOffer(
        id=raw["id"],
        airline_code=owner.get("iata_code") or "??",
        airline_name=owner.get("name") or "Unknown",
        airline_logo=owner.get("logo_symbol_url"),
        total_amount=Decimal(raw["total_amount"]),
        currency=raw["total_currency"],
        slices=tuple(map_slice(s) for s in raw["slices"]),
        refundable=_condition_allowed(conditions.get("refund_before_departure")),
        changeable=_condition_allowed(conditions.get("change_before_departure")),
        emissions_kg=int(emissions) if emissions else None,
        expires_at=raw.get("expires_at"),
        is_simulated=raw.get("live_mode") is False,
    )


def involves_airline(raw: dict[str, Any], airlines: frozenset[str]) -> bool:
    """出票航司或任一航段的行銷／實際營運航司在名單內即為 True。"""
    if not airlines:
        return False
    if (raw.get("owner") or {}).get("iata_code") in airlines:
        return True
    for slice_ in raw.get("slices") or []:
        for seg in slice_.get("segments") or []:
            for key in ("marketing_carrier", "operating_carrier"):
                if (seg.get(key) or {}).get("iata_code") in airlines:
                    return True
    return False


def map_offers(
    raw_offers: list[dict[str, Any]], excluded_airlines: frozenset[str] = frozenset()
) -> list[FlightOffer]:
    """逐筆轉換；剔除指定航司（例如 Duffel 的虛構測試航司 ZZ），單筆資料異常時略過並記錄。"""
    mapped: list[FlightOffer] = []
    for raw in raw_offers:
        try:
            if involves_airline(raw, excluded_airlines):
                continue
            if raw.get("slices") and all(s.get("segments") for s in raw["slices"]):
                mapped.append(map_offer(raw))
        except (KeyError, TypeError, ValueError, InvalidOperation, IndexError) as exc:
            log.warning("略過無法解析的 offer %s：%s", raw.get("id"), exc)
    return mapped
