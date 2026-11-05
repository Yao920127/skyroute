"""匯率服務：把不同幣別的報價換算成使用者選擇的顯示幣別。

來源為免金鑰的公開匯率 API（以 USD 為基準），結果快取；
外部服務失敗時改用內建參考匯率並標示為概略值。
"""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, get_args

import httpx

from app.domain.offers import FlightOffer, Frozen
from app.services.cache import Cache

log = logging.getLogger(__name__)

CurrencyCode = Literal[
    "TWD", "USD", "EUR", "GBP", "JPY", "KRW", "HKD", "SGD", "CNY", "THB", "AUD", "CAD"
]
SUPPORTED_CURRENCIES: tuple[str, ...] = get_args(CurrencyCode)
ZERO_DECIMAL = frozenset({"JPY", "KRW"})  # 這些幣別實務上不用小數

# 外部來源失敗時的參考匯率（1 USD = x），僅供概略換算
FALLBACK_USD_RATES: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "TWD": Decimal("32.8"),
    "EUR": Decimal("0.89"),
    "GBP": Decimal("0.74"),
    "JPY": Decimal("158"),
    "KRW": Decimal("1340"),
    "HKD": Decimal("7.85"),
    "SGD": Decimal("1.29"),
    "CNY": Decimal("6.69"),
    "THB": Decimal("33"),
    "AUD": Decimal("1.52"),
    "CAD": Decimal("1.38"),
}

CACHE_KEY = "fx:usd"
FALLBACK_TTL_S = 10 * 60


class UnsupportedCurrency(ValueError):
    pass


def quantize(amount: Decimal, currency: str) -> Decimal:
    exp = Decimal("1") if currency in ZERO_DECIMAL else Decimal("0.01")
    return amount.quantize(exp, rounding=ROUND_HALF_UP)


class FxRates(Frozen):
    """以 USD 為基準的匯率表（1 USD = rates[x]）。"""

    rates: dict[str, Decimal]
    as_of: datetime
    source: str
    approximate: bool = False

    def rate(self, source: str, target: str) -> Decimal:
        if source == target:
            return Decimal(1)
        try:
            return self.rates[target] / self.rates[source]
        except KeyError as exc:
            raise UnsupportedCurrency(f"不支援的幣別：{exc.args[0]}") from exc

    def convert(self, amount: Decimal, source: str, target: str) -> Decimal:
        return quantize(amount * self.rate(source, target), target)


def to_currency(offer: FlightOffer, fx: FxRates, target: str) -> FlightOffer:
    """回傳以 target 幣別計價的新 offer，原始金額保留在 original_*。"""
    if offer.currency == target:
        return offer
    return offer.model_copy(
        update={
            "total_amount": fx.convert(offer.total_amount, offer.currency, target),
            "currency": target,
            "original_amount": offer.total_amount,
            "original_currency": offer.currency,
        }
    )


def fallback_rates() -> FxRates:
    return FxRates(
        rates=FALLBACK_USD_RATES,
        as_of=datetime.now(UTC),
        source="built-in reference rates",
        approximate=True,
    )


def parse_rates(body: dict[str, Any]) -> FxRates:
    raw = body["rates"]
    rates = {code: Decimal(str(raw[code])) for code in SUPPORTED_CURRENCIES if code in raw}
    rates["USD"] = Decimal(1)
    missing = set(SUPPORTED_CURRENCIES) - rates.keys()
    if missing:
        raise ValueError(f"匯率來源缺少幣別：{sorted(missing)}")
    updated = body.get("time_last_update_unix")
    as_of = datetime.fromtimestamp(int(updated), UTC) if updated else datetime.now(UTC)
    return FxRates(rates=rates, as_of=as_of, source="open.er-api.com")


class FxService:
    def __init__(self, http: httpx.AsyncClient, cache: Cache, url: str, ttl_s: int) -> None:
        self._http = http
        self._cache = cache
        self._url = url
        self._ttl_s = ttl_s

    async def rates(self) -> FxRates:
        cached = await self._cache.get(CACHE_KEY)
        if cached:
            try:
                return FxRates.model_validate_json(cached)
            except ValueError:
                log.warning("匯率快取損毀，重新取得")
        try:
            resp = await self._http.get(self._url, timeout=8)
            resp.raise_for_status()
            fx = parse_rates(resp.json())
            ttl = self._ttl_s
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("取得匯率失敗，改用內建參考匯率：%s", exc)
            fx = fallback_rates()
            ttl = FALLBACK_TTL_S  # 概略匯率只短暫快取，盡快重試外部來源
        await self._cache.set(CACHE_KEY, fx.model_dump_json(), ttl)
        return fx
