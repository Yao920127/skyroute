"""航線拓撲過濾引擎：直飛、轉機次數、樞紐白／黑名單、停留時間窗口、航司。"""

from collections.abc import Iterable

from pydantic import Field

from app.domain.offers import FlightOffer, Frozen

DEFAULT_MIN_LAYOVER = 90
DEFAULT_MAX_LAYOVER = 300


class TopologyFilter(Frozen):
    direct_only: bool = False
    max_stops: int = Field(default=1, ge=0, le=3)
    allowed_hubs: frozenset[str] = frozenset()
    excluded_hubs: frozenset[str] = frozenset()
    min_layover_minutes: int = Field(default=DEFAULT_MIN_LAYOVER, ge=0, le=24 * 60)
    max_layover_minutes: int = Field(default=DEFAULT_MAX_LAYOVER, ge=0, le=48 * 60)
    airlines: frozenset[str] = frozenset()
    # 每一段行程（含轉機）的總時長範圍，單位分鐘；None 代表不限
    min_slice_minutes: int | None = Field(default=None, ge=0)
    max_slice_minutes: int | None = Field(default=None, ge=0)

    @property
    def effective_max_stops(self) -> int:
        return 0 if self.direct_only else self.max_stops


def offer_matches(offer: FlightOffer, rule: TopologyFilter) -> bool:
    """所有 slice 都必須通過規則，整筆 offer 才保留。"""
    if rule.airlines and offer.airline_code not in rule.airlines:
        return False
    if offer.max_stops > rule.effective_max_stops:
        return False
    # 「只看直飛」＝不轉機也不經停；同班機中途落地（如 BR67 經停曼谷）不算直飛
    if rule.direct_only and not offer.is_nonstop:
        return False
    # 黑名單也套用到經停機場（例如想避開某國機場）；白名單只約束需要換機的轉機點
    if offer.stop_airports & rule.excluded_hubs:
        return False
    if rule.max_slice_minutes is not None and offer.longest_slice_minutes > rule.max_slice_minutes:
        return False
    if rule.min_slice_minutes is not None and offer.shortest_slice_minutes < rule.min_slice_minutes:
        return False
    for slice_ in offer.slices:
        for layover in slice_.layovers:
            if rule.allowed_hubs and layover.airport not in rule.allowed_hubs:
                return False
            if layover.airport in rule.excluded_hubs:
                return False
            if not rule.min_layover_minutes <= layover.minutes <= rule.max_layover_minutes:
                return False
    return True


def apply_topology(offers: Iterable[FlightOffer], rule: TopologyFilter) -> list[FlightOffer]:
    return [offer for offer in offers if offer_matches(offer, rule)]


def collect_hubs(offers: Iterable[FlightOffer]) -> list[str]:
    """列出結果中出現過的轉機點與經停點，供前端產生白／黑名單選項。"""
    return sorted({hub for offer in offers for hub in offer.transit_airports | offer.stop_airports})
