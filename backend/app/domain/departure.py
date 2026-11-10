"""追蹤何時自動結清：起飛前 1 小時（航空公司多半此時關櫃，票已買不到）。

追蹤只記出發「日期」，航班時間取自最近一次巡檢選中的航班；
還沒有巡檢紀錄時，等出發地當地的出發日過完才結清。
"""

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

CHECK_IN_CLOSES_BEFORE = timedelta(hours=1)


def _zone(timezone: str | None) -> tzinfo:
    if not timezone:
        return UTC
    try:
        return ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):  # 未知或格式不合法的時區名稱
        return UTC


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def first_departing_at(offers: object) -> str | None:
    """price_history.offers（JSON）中第一段航班的起飛時間；舊資料或格式不符時為 None。"""
    try:
        value = offers[0]["slices"][0]["departing_at"]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        return None
    return value if isinstance(value, str) else None


def departure_cutoff(
    departure_date: date, timezone: str | None, departing_at: str | None
) -> datetime:
    """過了這個時間點，追蹤就該結清。

    departing_at 是出發地當地時間（Duffel 不帶時區），timezone 是出發機場的時區。
    """
    zone = _zone(timezone)
    takeoff = _parse(departing_at)
    if takeoff is not None and takeoff.date() == departure_date:
        local = takeoff if takeoff.tzinfo else takeoff.replace(tzinfo=zone)
        return local - CHECK_IN_CLOSES_BEFORE
    return datetime.combine(departure_date + timedelta(days=1), time.min, tzinfo=zone)
