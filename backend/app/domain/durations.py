"""ISO 8601 時長與當地時間差計算。"""

import re
from datetime import datetime

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso_duration(value: str | None) -> int | None:
    """把 'PT3H22M'、'P1DT2H' 之類的字串轉成分鐘數；無法解析時回傳 None。"""
    if not value:
        return None
    match = _DURATION_RE.match(value.strip())
    if not match or value.strip() in ("P", "PT"):
        return None
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] // 60


def minutes_between(start_local: str, end_local: str) -> int:
    """同一地點（同時區）兩個當地時間的分鐘差，用於計算轉機停留時間。"""
    start = datetime.fromisoformat(start_local)
    end = datetime.fromisoformat(end_local)
    return int((end - start).total_seconds() // 60)
