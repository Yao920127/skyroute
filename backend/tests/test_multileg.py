"""多航段／多航司統一追蹤：整張票多航段、分段購票（每段各查單程、指定航司、合計價格）。"""

import json
from datetime import date, timedelta
from typing import Any

import httpx
import respx

from app.container import Container
from app.models import TrackedWatchlist
from app.services.alerts import format_message
from app.services.patrol import run_patrol
from tests.conftest import DUFFEL, USER
from tests.factories import make_offer, raw_offer, raw_segment

DEP = (date.today() + timedelta(days=40)).isoformat()
BACK = (date.today() + timedelta(days=47)).isoformat()
SPLIT = {
    "origin": "TPE",
    "destination": "BKK",
    "departure_date": DEP,
    "extra_legs": [{"origin": "BKK", "destination": "TPE", "departure_date": BACK}],
    "ticket_mode": "split",
    "leg_airlines": ["CZ", "BR"],
    "target_price": 400,
    "currency": "USD",
}


def one_way(offer_id: str, amount: str, origin: str, dest: str, owner: str) -> dict[str, Any]:
    seg = raw_segment(origin, dest, f"{DEP}T08:00:00", f"{DEP}T12:00:00", "PT4H", owner, "1")
    return raw_offer(offer_id, amount, [[seg]], owner=owner)


def by_route(request: httpx.Request) -> httpx.Response:
    """依查詢的第一段起訖回傳不同報價，模擬分段購票各自的單程查詢。"""
    slices = json.loads(request.content)["data"]["slices"]
    first = (slices[0]["origin"], slices[0]["destination"])
    offers = {
        ("TPE", "BKK"): [
            one_way("o1", "150", "TPE", "BKK", "CZ"),
            one_way("o2", "120", "TPE", "BKK", "VJ"),  # 更便宜但不是指定的 CZ
        ],
        ("BKK", "TPE"): [
            one_way("r1", "200", "BKK", "TPE", "BR"),
            one_way("r2", "190", "BKK", "TPE", "TG"),
        ],
    }[first]
    return httpx.Response(200, json={"data": {"offers": offers}})


class TestValidation:
    async def test_split_rules(self, client: httpx.AsyncClient) -> None:
        with_return = {**SPLIT, "return_date": BACK}
        res = await client.post("/api/watchlists", json=with_return, headers=USER)
        assert res.status_code == 422

        mismatch = {**SPLIT, "leg_airlines": ["CZ"]}
        assert (
            await client.post("/api/watchlists", json=mismatch, headers=USER)
        ).status_code == 422

        single = {**SPLIT, "extra_legs": [], "leg_airlines": []}
        assert (await client.post("/api/watchlists", json=single, headers=USER)).status_code == 422

        ticket = {**SPLIT, "ticket_mode": "ticket"}
        assert (await client.post("/api/watchlists", json=ticket, headers=USER)).status_code == 422


class TestSplitPatrol:
    @respx.mock
    async def test_sums_cheapest_offer_per_leg_with_chosen_airlines(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        route = respx.post(f"{DUFFEL}/air/offer_requests").mock(side_effect=by_route)
        created = (await client.post("/api/watchlists", json=SPLIT, headers=USER)).json()["data"]
        assert created["ticket_mode"] == "split" and created["leg_airlines"] == ["CZ", "BR"]
        # 另一筆相同航段的分段追蹤：每段只查一次，兩筆共用
        await client.post("/api/watchlists", json={**SPLIT, "target_price": 1}, headers=USER)

        report = await run_patrol(container.patrol_context(), container.cache, 2, 60)
        assert report.api_calls == 2 and route.call_count == 2
        assert report.prices_recorded == 2
        sent = [json.loads(c.request.content)["data"]["slices"] for c in route.calls]
        assert all(len(s) == 1 for s in sent)  # 每段都是單程查詢

        history = (
            await client.get(f"/api/watchlists/{created['id']}/history", headers=USER)
        ).json()["data"]
        assert history[0]["price"] == "350.00"  # CZ 150 + BR 200（不是較便宜的 VJ、TG）
        assert history[0]["airline_code"] == "CZ+BR"
        assert report.alerts_sent == 1  # 350 ≤ 目標價 400；另一筆目標價 1 不觸發

    @respx.mock
    async def test_any_leg_without_match_skips_watch(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        respx.post(f"{DUFFEL}/air/offer_requests").mock(side_effect=by_route)
        payload = {**SPLIT, "leg_airlines": ["CZ", "JL"]}  # 回程沒有 JL
        await client.post("/api/watchlists", json=payload, headers=USER)
        report = await run_patrol(container.patrol_context(), container.cache, 1, 60)
        assert report.api_calls == 2 and report.prices_recorded == 0


class TestTicketMultiCity:
    @respx.mock
    async def test_one_request_with_all_slices(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        segs = [
            [raw_segment("TPE", "BKK", f"{DEP}T08:00:00", f"{DEP}T12:00:00", "PT4H", "BR", "1")],
            [raw_segment("BKK", "TPE", f"{BACK}T08:00:00", f"{BACK}T12:00:00", "PT4H", "BR", "2")],
        ]
        route = respx.post(f"{DUFFEL}/air/offer_requests").mock(
            return_value=httpx.Response(
                200, json={"data": {"offers": [raw_offer("t1", "300", segs)]}}
            )
        )
        payload = {**SPLIT, "ticket_mode": "ticket", "leg_airlines": []}
        await client.post("/api/watchlists", json=payload, headers=USER)
        report = await run_patrol(container.patrol_context(), container.cache, 1, 60)
        assert route.call_count == 1 and report.prices_recorded == 1
        assert len(json.loads(route.calls[0].request.content)["data"]["slices"]) == 2


def test_split_alert_message_lists_every_leg() -> None:
    watch = TrackedWatchlist(
        origin="TPE",
        destination="BKK",
        departure_date=date(2026, 12, 5),
        extra_legs=[{"origin": "BKK", "destination": "TPE", "departure_date": "2026-12-12"}],
        ticket_mode="split",
        target_price=400,
    )
    text = format_message(
        watch,
        [make_offer("a", "150", airline="CZ"), make_offer("b", "200", airline="BR")],
        "target",
    )
    assert "分段購票合計 350" in text
    assert "TPE → BKK 2026-12-05、BKK → TPE 2026-12-12" in text
    assert text.count("｜轉機") == 2
