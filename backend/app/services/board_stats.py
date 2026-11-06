"""看盤統計：最新價、24 小時漲跌、7 日漲跌幅、7 日低點與均價。

漲跌的比較基準是「24 小時前（含）最後一筆價格」；追蹤未滿 24 小時時改用第一筆價格，
並以 change_basis 標示（day／start），讓每張卡片都以同樣格式顯示漲跌。
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from app.schemas import ChangeBasis, WatchStats

SPARKLINE_POINTS = 30
DAY = timedelta(hours=24)
_CENT = Decimal("0.01")


class PriceSample(NamedTuple):
    recorded_at: datetime
    price: Decimal
    currency: str


def _pct(new: Decimal, old: Decimal) -> Decimal | None:
    if old == 0:
        return None
    return ((new - old) / old * 100).quantize(_CENT, rounding=ROUND_HALF_UP)


def compute_stats(
    samples: Sequence[PriceSample], last_alert_at: datetime | None = None
) -> WatchStats:
    """samples 需依 recorded_at 由舊到新排序。"""
    if not samples:
        return WatchStats(last_alert_at=last_alert_at)
    latest = samples[-1]
    cutoff = latest.recorded_at - DAY
    previous = next((s for s in reversed(samples) if s.recorded_at <= cutoff), None)
    basis: ChangeBasis | None = "day" if previous else None
    if previous is None and len(samples) > 1:
        previous, basis = samples[0], "start"
    week = [s for s in samples if s.recorded_at >= latest.recorded_at - timedelta(days=7)]
    week_prices = [s.price for s in week]
    first_in_week = week[0]

    return WatchStats(
        latest_price=latest.price,
        currency=latest.currency,
        last_checked_at=latest.recorded_at,
        previous_day_price=previous.price if previous else None,
        day_change=(latest.price - previous.price) if previous else None,
        day_change_pct=_pct(latest.price, previous.price) if previous else None,
        change_basis=basis,
        week_change_pct=_pct(latest.price, first_in_week.price) if len(week) > 1 else None,
        week_low=min(week_prices),
        week_avg=(sum(week_prices, Decimal(0)) / len(week_prices)).quantize(_CENT),
        last_alert_at=last_alert_at,
        sparkline=[s.price for s in samples[-SPARKLINE_POINTS:]],
    )
