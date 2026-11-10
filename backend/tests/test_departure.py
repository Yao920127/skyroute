"""自動結清的時間點：起飛前 1 小時；不知道航班時間時，等出發地當地的出發日過完。"""

from datetime import UTC, date, datetime

import pytest

from app.domain.departure import departure_cutoff, first_departing_at

pytestmark = pytest.mark.unit

DEP = date(2026, 11, 10)


def test_closes_one_hour_before_takeoff_in_origin_local_time() -> None:
    # 截圖中的情境：TPE 11/10 19:25 起飛 → 台北 18:25（UTC 10:25）結清
    cutoff = departure_cutoff(DEP, "Asia/Taipei", "2026-11-10T19:25:00")
    assert cutoff == datetime(2026, 11, 10, 10, 25, tzinfo=UTC)


def test_without_flight_time_waits_until_local_departure_day_ends() -> None:
    cutoff = departure_cutoff(DEP, "Asia/Taipei", None)
    assert cutoff == datetime(2026, 11, 10, 16, 0, tzinfo=UTC)  # 台北 11/11 00:00


def test_ignores_flight_time_from_another_date() -> None:
    # 追蹤改過日期後，舊紀錄的航班時間不可沿用
    cutoff = departure_cutoff(DEP, "Asia/Taipei", "2026-11-08T19:25:00")
    assert cutoff == datetime(2026, 11, 10, 16, 0, tzinfo=UTC)


@pytest.mark.parametrize("timezone", [None, "Not/AZone", ""])
def test_unknown_timezone_falls_back_to_utc(timezone: str | None) -> None:
    assert departure_cutoff(DEP, timezone, None) == datetime(2026, 11, 11, tzinfo=UTC)
    assert departure_cutoff(DEP, timezone, "2026-11-10T19:25:00") == datetime(
        2026, 11, 10, 18, 25, tzinfo=UTC
    )


def test_unparseable_flight_time_falls_back_to_end_of_day() -> None:
    assert departure_cutoff(DEP, None, "soon") == datetime(2026, 11, 11, tzinfo=UTC)


def test_first_departing_at_reads_the_first_leg_of_the_stored_offers() -> None:
    offers = [
        {
            "slices": [
                {"departing_at": "2026-11-10T19:25:00"},
                {"departing_at": "2026-11-13T13:50:00"},
            ]
        }
    ]
    assert first_departing_at(offers) == "2026-11-10T19:25:00"


@pytest.mark.parametrize("offers", [None, [], [{}], [{"slices": []}], [{"slices": [{}]}], "x"])
def test_first_departing_at_tolerates_missing_or_malformed_offers(offers: object) -> None:
    assert first_departing_at(offers) is None
