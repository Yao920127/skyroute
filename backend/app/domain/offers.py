"""SkyRoute 內部的標準航班領域模型（與 Duffel 的巢狀結構解耦）。

所有模型皆為 frozen，建立後不可變；需要變更時以 model_copy(update=...) 產生新物件。
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

CabinClass = Literal["economy", "premium_economy", "business", "first"]
OfferTag = Literal["cheapest", "fastest", "best_value"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TechnicalStop(Frozen):
    """同一班機（同班號）中途落地，例如長榮 BR67 台北→倫敦 經停曼谷；旅客不需換機。"""

    airport: str
    city_name: str | None = None
    minutes: int


class Segment(Frozen):
    carrier_code: str
    carrier_name: str
    flight_number: str
    origin: str
    destination: str
    departing_at: str  # 當地時間 ISO 8601（無時區，與 Duffel 一致）
    arriving_at: str
    duration_minutes: int
    aircraft: str | None = None
    stops: tuple[TechnicalStop, ...] = ()
    # 代碼共享：行銷航司與實際營運航司不同時記錄（例如 MU8901 實際由華航 CI 營運）
    operating_code: str | None = None
    operating_name: str | None = None


class Layover(Frozen):
    airport: str
    city_name: str | None = None
    minutes: int


class Slice(Frozen):
    origin: str
    destination: str
    departing_at: str
    arriving_at: str
    duration_minutes: int
    segments: tuple[Segment, ...]
    layovers: tuple[Layover, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stops(self) -> int:
        return len(self.segments) - 1

    @computed_field  # type: ignore[prop-decorator]
    @property
    def technical_stops(self) -> int:
        """中途經停次數（不換機），與轉機次數 stops 分開計算。"""
        return sum(len(seg.stops) for seg in self.segments)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def flight_minutes(self) -> int:
        return sum(seg.duration_minutes for seg in self.segments)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def layover_minutes(self) -> int:
        return sum(lay.minutes for lay in self.layovers)


class FlightOffer(Frozen):
    id: str
    airline_code: str
    airline_name: str
    airline_logo: str | None = None
    total_amount: Decimal
    currency: str
    slices: tuple[Slice, ...]
    refundable: bool | None = None
    changeable: bool | None = None
    emissions_kg: int | None = None
    expires_at: str | None = None
    # Duffel 測試模式（live_mode = false）回傳的模擬報價：班號、航線、時間、票價都不是真實資料
    is_simulated: bool = False
    # 換算成顯示幣別後，保留航空公司原始報價
    original_amount: Decimal | None = None
    original_currency: str | None = None

    @property
    def total_duration_minutes(self) -> int:
        return sum(s.duration_minutes for s in self.slices)

    @property
    def flight_minutes(self) -> int:
        return sum(s.flight_minutes for s in self.slices)

    @property
    def layover_minutes(self) -> int:
        return sum(s.layover_minutes for s in self.slices)

    @property
    def max_stops(self) -> int:
        return max((s.stops for s in self.slices), default=0)

    @property
    def longest_slice_minutes(self) -> int:
        return max((s.duration_minutes for s in self.slices), default=0)

    @property
    def shortest_slice_minutes(self) -> int:
        return min((s.duration_minutes for s in self.slices), default=0)

    @property
    def transit_airports(self) -> frozenset[str]:
        return frozenset(lay.airport for s in self.slices for lay in s.layovers)

    @property
    def stop_airports(self) -> frozenset[str]:
        """中途經停（不換機）的機場。"""
        return frozenset(
            stop.airport for s in self.slices for seg in s.segments for stop in seg.stops
        )

    @property
    def is_nonstop(self) -> bool:
        """真正的直飛：沒有轉機，也沒有中途經停。"""
        return self.max_stops == 0 and not self.stop_airports


class RankedOffer(Frozen):
    """經過代價計算與標籤後、回傳給前端的報價。"""

    offer: FlightOffer
    total_duration_minutes: int
    flight_minutes: int
    layover_minutes: int
    max_stops: int
    cost_index: Decimal
    tags: tuple[OfferTag, ...] = ()
