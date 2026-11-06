"""API 邊界的 request / response 結構（輸入驗證全部在此完成）。"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.metrics import DEFAULT_TIME_VALUE_PER_HOUR, SortKey
from app.domain.offers import CabinClass, RankedOffer
from app.domain.topology import DEFAULT_MAX_LAYOVER, DEFAULT_MIN_LAYOVER, TopologyFilter
from app.services.fx import CurrencyCode
from app.services.schedule import PatrolInterval
from app.services.search_service import Leg, RouteQuery


def _upper(value: str) -> str:
    return value.upper()


def _upper_set(values: list[str]) -> list[str]:
    return sorted({v.upper() for v in values})


IataCode = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$"), AfterValidator(_upper)]
AirlineCode = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{2}$"), AfterValidator(_upper)]
HubList = Annotated[list[IataCode], Field(max_length=20), AfterValidator(_upper_set)]


class ApiResponse[T](BaseModel):
    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


# ---------- 航班搜尋 ----------


MAX_EXTRA_LEGS = 4  # 多航段最多 5 段


class LegIn(BaseModel):
    origin: IataCode
    destination: IataCode
    departure_date: date


class TripParams(BaseModel):
    origin: IataCode
    destination: IataCode
    departure_date: date
    return_date: date | None = None
    # 多航段：第 2 段以後（例如 台北→倫敦 之後的 巴黎→台北）；與 return_date 互斥
    extra_legs: Annotated[list[LegIn], Field(max_length=MAX_EXTRA_LEGS)] = []
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    cabin_class: CabinClass = "economy"

    @model_validator(mode="after")
    def _check_trip(self) -> Self:
        if self.origin == self.destination:
            raise ValueError("出發地與目的地不可相同")
        if self.departure_date < date.today():
            raise ValueError("出發日期不可早於今天")
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("回程日期不可早於出發日期")
        if self.adults + self.children > 9:
            raise ValueError("乘客總數不可超過 9 人")
        if self.extra_legs:
            if self.return_date:
                raise ValueError("多航段行程請用 extra_legs 描述回程，不可同時設定回程日期")
            previous = self.departure_date
            for leg in self.extra_legs:
                if leg.origin == leg.destination:
                    raise ValueError("出發地與目的地不可相同")
                if leg.departure_date < previous:
                    raise ValueError("多航段的日期必須依序排列")
                previous = leg.departure_date
        return self

    def to_legs(self) -> tuple[Leg, ...]:
        return tuple(
            Leg(origin=leg.origin, destination=leg.destination, departure_date=leg.departure_date)
            for leg in self.extra_legs
        )


class FilterParams(BaseModel):
    direct_only: bool = False
    max_stops: int = Field(default=1, ge=0, le=2)
    allowed_hubs: HubList = []
    excluded_hubs: HubList = []
    min_layover_minutes: int = Field(default=DEFAULT_MIN_LAYOVER, ge=0, le=1440)
    max_layover_minutes: int = Field(default=DEFAULT_MAX_LAYOVER, ge=0, le=2880)
    airlines: Annotated[list[AirlineCode], Field(max_length=20)] = []
    # 滑桿範圍：票價（顯示幣別）與每段飛行時長（分鐘）；None 代表不限
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    duration_min: int | None = Field(default=None, ge=0, le=4320)
    duration_max: int | None = Field(default=None, ge=0, le=4320)

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.min_layover_minutes > self.max_layover_minutes:
            raise ValueError("最短轉機時間不可大於最長轉機時間")
        prices = (self.price_min, self.price_max)
        if None not in prices and prices[0] > prices[1]:  # type: ignore[operator]
            raise ValueError("最低票價不可大於最高票價")
        durations = (self.duration_min, self.duration_max)
        if None not in durations and durations[0] > durations[1]:  # type: ignore[operator]
            raise ValueError("最短飛行時長不可大於最長飛行時長")
        return self

    def to_filter(self) -> TopologyFilter:
        return TopologyFilter(
            direct_only=self.direct_only,
            max_stops=self.max_stops,
            allowed_hubs=frozenset(self.allowed_hubs),
            excluded_hubs=frozenset(self.excluded_hubs),
            min_layover_minutes=self.min_layover_minutes,
            max_layover_minutes=self.max_layover_minutes,
            airlines=frozenset(self.airlines),
            min_slice_minutes=self.duration_min,
            max_slice_minutes=self.duration_max,
        )


class SearchRequest(TripParams, FilterParams):
    currency: CurrencyCode = "TWD"
    # 每小時時間價值，單位固定為 USD（後端換算成顯示幣別再計算綜合代價）
    time_value_per_hour: Decimal = Field(default=DEFAULT_TIME_VALUE_PER_HOUR, ge=0, le=10_000)
    sort: SortKey = "price"
    descending: bool = False
    limit: int = Field(default=60, ge=1, le=300)
    refresh: bool = False

    def to_route_query(self) -> RouteQuery:
        return RouteQuery(
            origin=self.origin,
            destination=self.destination,
            departure_date=self.departure_date,
            return_date=self.return_date,
            adults=self.adults,
            children=self.children,
            cabin_class=self.cabin_class,
            max_connections=0 if self.direct_only else self.max_stops,
            extra_legs=self.to_legs(),
        )


class AirlineOption(BaseModel):
    code: str
    name: str


class CacheInfo(BaseModel):
    hit: bool
    key: str
    fetched_at: datetime


class NumericRange(BaseModel):
    min: Decimal
    max: Decimal


class FxInfo(BaseModel):
    currency: str
    as_of: datetime
    source: str
    approximate: bool


class FxTable(BaseModel):
    base: str
    rates: dict[str, Decimal]
    as_of: datetime
    source: str
    approximate: bool


class SearchResult(BaseModel):
    currency: str
    fx: FxInfo
    price_bounds: NumericRange | None = None
    duration_bounds: NumericRange | None = None
    origin_airports: list[str]
    destination_airports: list[str]
    cache: CacheInfo
    total_raw: int
    total_filtered: int
    hubs: list[str]
    airlines: list[AirlineOption]
    offers: list[RankedOffer]


class MatrixRequest(TripParams, FilterParams):
    radius_days: int = Field(default=3, ge=0, le=3)
    currency: CurrencyCode = "TWD"

    @model_validator(mode="after")
    def _single_trip_only(self) -> Self:
        if self.extra_legs:
            raise ValueError("日期矩陣只支援單程或來回行程")
        return self


# ---------- 機場 ----------


class AirportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    iata_code: str
    city_code: str
    name_zh: str | None
    name_en: str
    country: str
    timezone: str | None
    kind: str
    city_name: str | None = None


# ---------- 自選看盤 ----------


TicketMode = Literal["ticket", "split"]


class WatchlistCreate(TripParams):
    """整張票（單程／來回／多航段）或分段購票（每段各自一張單程票，價格加總）。"""

    label: str | None = Field(default=None, max_length=100)
    ticket_mode: TicketMode = "ticket"
    # 分段購票每段指定的航司，順序同航段（含第 1 段）；None 代表該段不限航司
    leg_airlines: Annotated[list[AirlineCode | None], Field(max_length=MAX_EXTRA_LEGS + 1)] = []
    target_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    drop_percent: Decimal | None = Field(default=None, gt=0, le=90, decimal_places=2)
    preferred_airline: AirlineCode | None = None
    allowed_transits: HubList = []
    excluded_transits: HubList = []
    max_stops: int = Field(default=1, ge=0, le=2)
    min_layover_minutes: int = Field(default=DEFAULT_MIN_LAYOVER, ge=0, le=1440)
    max_layover_minutes: int = Field(default=DEFAULT_MAX_LAYOVER, ge=0, le=2880)
    webhook_url: str | None = Field(default=None, max_length=500)
    # 目標價使用的幣別；巡檢時把報價換算成此幣別再比對與記錄
    currency: CurrencyCode = "TWD"
    # 巡檢頻率（分鐘）；None＝每日固定時間。30 分鐘以內需使用自己的金鑰
    patrol_interval_minutes: PatrolInterval | None = None

    @model_validator(mode="after")
    def _check_threshold(self) -> Self:
        if self.ticket_mode == "split":
            if self.return_date:
                raise ValueError("分段購票請把回程列為第 2 段，不要使用回程日期")
            if not self.extra_legs:
                raise ValueError("分段購票至少需要兩段行程")
            if self.leg_airlines and len(self.leg_airlines) != 1 + len(self.extra_legs):
                raise ValueError("每一段都要對應一個航司設定")
        elif self.leg_airlines:
            raise ValueError("只有分段購票可以逐段指定航司")
        if self.target_price is None and self.drop_percent is None:
            raise ValueError("請至少設定目標價或相對降幅其中一項")
        if self.min_layover_minutes > self.max_layover_minutes:
            raise ValueError("最短轉機時間不可大於最長轉機時間")
        return self


class WatchlistUpdate(BaseModel):
    """只會更新有送出的欄位；名稱直接覆寫（不保留舊名稱），空字串視為清除。"""

    label: str | None = Field(default=None, max_length=100)
    patrol_interval_minutes: PatrolInterval | None = None
    # 門檻：送 null 代表取消該條件；兩者不可同時為空（在服務層檢查合併後的結果）
    target_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    drop_percent: Decimal | None = Field(default=None, gt=0, le=90, decimal_places=2)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class PricePoint(BaseModel):
    recorded_at: datetime
    price: Decimal
    currency: str
    airline_code: str
    stops: int
    duration_minutes: int


ChangeBasis = Literal["day", "start"]


class WatchStats(BaseModel):
    latest_price: Decimal | None = None
    currency: str | None = None
    last_checked_at: datetime | None = None
    previous_day_price: Decimal | None = None
    day_change: Decimal | None = None
    day_change_pct: Decimal | None = None
    # day＝與 24 小時前比較；start＝追蹤未滿 24 小時，與第一筆價格比較
    change_basis: ChangeBasis | None = None
    week_change_pct: Decimal | None = None
    week_low: Decimal | None = None
    week_avg: Decimal | None = None
    last_alert_at: datetime | None = None
    sparkline: list[Decimal] = []


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str | None
    origin: str
    destination: str
    departure_date: date
    return_date: date | None
    adults: int
    children: int
    cabin_class: str
    target_price: Decimal | None
    drop_percent: Decimal | None
    preferred_airline: str | None
    allowed_transits: list[str]
    excluded_transits: list[str]
    max_stops: int
    min_layover_minutes: int
    max_layover_minutes: int
    currency: str | None = None
    ticket_mode: str = "ticket"
    extra_legs: list[LegIn] = []
    leg_airlines: list[str | None] = []
    patrol_interval_minutes: int | None = None
    next_check_at: datetime | None = None
    has_webhook: bool = False
    uses_own_key: bool = False
    is_active: bool
    status: str
    created_at: datetime
    stats: WatchStats = WatchStats()


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    triggered_price: Decimal
    currency: str
    reason: str
    channel: str
    sent_at: datetime


class DeletedCount(BaseModel):
    deleted: int


class AppConfig(BaseModel):
    has_server_key: bool
    can_store_user_key: bool
    # 有值代表已啟用 Google 登入（前端用來載入登入按鈕）
    google_client_id: str | None = None


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class AccountKeyIn(BaseModel):
    token: str = Field(min_length=10, max_length=220)


class AccountOut(BaseModel):
    email: str
    name: str | None
    picture: str | None
    # 帳號的 Duffel 金鑰：只回遮罩與模式，不回傳金鑰本身
    key_mask: str | None = None
    key_mode: Literal["test", "live"] | None = None


class CredentialCheck(BaseModel):
    valid: bool
    mode: Literal["test", "live"]


class PatrolReport(BaseModel):
    expired: int = 0
    active: int = 0
    route_groups: int = 0
    api_calls: int = 0
    prices_recorded: int = 0
    alerts_sent: int = 0
    alerts_suppressed: int = 0
    failures: int = 0
    skipped_locked: bool = False
