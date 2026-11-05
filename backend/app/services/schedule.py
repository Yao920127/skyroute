"""巡檢排程：每筆追蹤可自訂頻率；未設定時沿用每日固定時間（預設台北時間 03:00）。

- 使用網站預設金鑰（共用配額）：最短 30 分鐘
- 使用自己的 Duffel 金鑰（自己的配額）：最短 5 分鐘
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

PatrolInterval = Literal[5, 15, 30, 60, 360, 720]
INTERVAL_CHOICES: tuple[int, ...] = (5, 15, 30, 60, 360, 720)
MIN_SHARED_INTERVAL = 30


class IntervalNotAllowed(ValueError):
    pass


def next_daily(now: datetime, daily_at: str, tz: ZoneInfo) -> datetime:
    """下一個每日固定巡檢時間（嚴格晚於 now）。"""
    hour, minute = (int(x) for x in daily_at.split(":"))
    local_now = now.astimezone(tz)
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=tz)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def effective_interval(minutes: int | None, uses_own_key: bool) -> int | None:
    """沒有自己的金鑰時，短於 30 分鐘的頻率一律放寬為 30 分鐘（保護共用配額）。"""
    if minutes is None or uses_own_key:
        return minutes
    return max(minutes, MIN_SHARED_INTERVAL)


def check_interval(minutes: int | None, uses_own_key: bool) -> None:
    if minutes is not None and minutes < MIN_SHARED_INTERVAL and not uses_own_key:
        raise IntervalNotAllowed("30 分鐘以內的巡檢頻率需要使用自己的 Duffel 金鑰")


@dataclass(frozen=True)
class PatrolSchedule:
    daily_at: str
    timezone: str

    def next_check(self, now: datetime, minutes: int | None, uses_own_key: bool) -> datetime:
        interval = effective_interval(minutes, uses_own_key)
        if interval is None:
            return next_daily(now, self.daily_at, ZoneInfo(self.timezone))
        return now + timedelta(minutes=interval)
