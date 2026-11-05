"""巡檢排程：每日固定時間、自訂頻率（共用金鑰最短 30 分鐘）、編輯名稱與頻率、只巡檢到期項目。"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from sqlalchemy import select, update

from app.container import Container
from app.models import TrackedWatchlist
from app.services.patrol import run_patrol
from app.services.schedule import PatrolSchedule, effective_interval, next_daily
from tests.conftest import USER
from tests.factories import direct_raw
from tests.test_api import DEP, RET, mock_search

TAIPEI = ZoneInfo("Asia/Taipei")
OWN_KEY = {"X-Duffel-Token": "duffel_test_userownkey123"}
WATCH = {
    "origin": "TPE",
    "destination": "NRT",
    "departure_date": DEP,
    "return_date": RET,
    "target_price": 50,
}


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class TestScheduleRules:
    pytestmark = pytest.mark.unit

    def test_next_daily_is_strictly_after_now(self) -> None:
        before = datetime(2026, 11, 6, 2, 59, tzinfo=TAIPEI)
        after = datetime(2026, 11, 6, 3, 0, tzinfo=TAIPEI)
        assert next_daily(before, "03:00", TAIPEI) == datetime(2026, 11, 6, 3, 0, tzinfo=TAIPEI)
        assert next_daily(after, "03:00", TAIPEI) == datetime(2026, 11, 7, 3, 0, tzinfo=TAIPEI)

    def test_short_intervals_need_own_key(self) -> None:
        assert effective_interval(5, uses_own_key=True) == 5
        assert effective_interval(5, uses_own_key=False) == 30
        assert effective_interval(60, uses_own_key=False) == 60
        assert effective_interval(None, uses_own_key=False) is None

    def test_next_check(self) -> None:
        schedule = PatrolSchedule("03:00", "Asia/Taipei")
        now = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
        assert schedule.next_check(now, 60, False) == now + timedelta(hours=1)
        assert schedule.next_check(now, 15, False) == now + timedelta(minutes=30)
        assert schedule.next_check(now, None, False) == datetime(2026, 11, 7, 3, 0, tzinfo=TAIPEI)


class TestCreateAndEdit:
    async def test_default_is_next_daily_slot(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/watchlists", json=WATCH, headers=USER)).json()["data"]
        assert created["patrol_interval_minutes"] is None
        next_at = parse(created["next_check_at"]).astimezone(TAIPEI)
        assert (next_at.hour, next_at.minute) == (3, 0)
        assert timedelta(0) < next_at - datetime.now(TAIPEI) <= timedelta(days=1)

    async def test_interval_limits_depend_on_key(self, client: httpx.AsyncClient) -> None:
        denied = await client.post(
            "/api/watchlists", json={**WATCH, "patrol_interval_minutes": 5}, headers=USER
        )
        assert denied.status_code == 422
        assert "自己的 Duffel 金鑰" in denied.json()["error"]

        own = await client.post(
            "/api/watchlists",
            json={**WATCH, "patrol_interval_minutes": 5},
            headers={**USER, **OWN_KEY},
        )
        assert own.status_code == 201
        delta = parse(own.json()["data"]["next_check_at"]) - datetime.now(UTC)
        assert timedelta(minutes=4) < delta <= timedelta(minutes=5)

        odd = await client.post(
            "/api/watchlists", json={**WATCH, "patrol_interval_minutes": 7}, headers=USER
        )
        assert odd.status_code == 422  # 只接受固定選項

    async def test_rename_overwrites_and_interval_reschedules(
        self, client: httpx.AsyncClient
    ) -> None:
        watch = (
            await client.post("/api/watchlists", json={**WATCH, "label": "舊名稱"}, headers=USER)
        ).json()["data"]
        url = f"/api/watchlists/{watch['id']}"

        renamed = (await client.patch(url, json={"label": "  米蘭  "}, headers=USER)).json()
        assert renamed["data"]["label"] == "米蘭"
        assert renamed["data"]["next_check_at"] == watch["next_check_at"]  # 只改名不影響排程

        hourly = (
            await client.patch(url, json={"patrol_interval_minutes": 60}, headers=USER)
        ).json()["data"]
        assert hourly["label"] == "米蘭" and hourly["patrol_interval_minutes"] == 60
        delta = parse(hourly["next_check_at"]) - datetime.now(UTC)
        assert timedelta(minutes=59) < delta <= timedelta(minutes=60)

        cleared = (await client.patch(url, json={"label": ""}, headers=USER)).json()["data"]
        assert cleared["label"] is None

        too_short = await client.patch(url, json={"patrol_interval_minutes": 5}, headers=USER)
        assert too_short.status_code == 422

        back_to_daily = (
            await client.patch(url, json={"patrol_interval_minutes": None}, headers=USER)
        ).json()["data"]
        assert back_to_daily["patrol_interval_minutes"] is None

        stranger = await client.patch(url, json={"label": "x"}, headers={"X-User-Id": "someone"})
        assert stranger.status_code == 404

    async def test_ended_watch_can_rename_but_not_reschedule(
        self, client: httpx.AsyncClient
    ) -> None:
        watch = (await client.post("/api/watchlists", json=WATCH, headers=USER)).json()["data"]
        url = f"/api/watchlists/{watch['id']}"
        await client.delete(url, headers=USER)
        assert (await client.patch(url, json={"label": "封存"}, headers=USER)).status_code == 200
        response = await client.patch(url, json={"patrol_interval_minutes": 60}, headers=USER)
        assert response.status_code == 422


class TestDuePatrol:
    @respx.mock
    async def test_only_due_watches_are_checked_and_rescheduled(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        search = mock_search(direct_raw("d1", "100"))
        due = (
            await client.post(
                "/api/watchlists", json={**WATCH, "patrol_interval_minutes": 30}, headers=USER
            )
        ).json()["data"]
        later = (
            await client.post("/api/watchlists", json={**WATCH, "destination": "KIX"}, headers=USER)
        ).json()["data"]
        now = datetime.now(UTC)
        async with container.sessions() as session:
            await session.execute(
                update(TrackedWatchlist)
                .where(TrackedWatchlist.id == uuid.UUID(due["id"]))
                .values(next_check_at=now - timedelta(minutes=1))
            )
            await session.commit()

        report = await run_patrol(
            container.patrol_context(), container.cache, 1, 60, now=now, due_only=True
        )
        assert report.active == 1 and report.prices_recorded == 1
        assert len(search.calls) == 1

        async with container.sessions() as session:
            rows = {str(w.id): w for w in (await session.scalars(select(TrackedWatchlist))).all()}
        assert rows[due["id"]].next_check_at == now + timedelta(minutes=30)
        assert rows[later["id"]].next_check_at == parse(later["next_check_at"])

        # 下一分鐘沒有到期項目 → 不呼叫 Duffel
        idle = await run_patrol(
            container.patrol_context(),
            container.cache,
            1,
            60,
            now=now + timedelta(minutes=1),
            due_only=True,
        )
        assert idle.active == 0 and len(search.calls) == 1
