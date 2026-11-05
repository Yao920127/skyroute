"""API 與巡檢管線整合測試（真實 PostgreSQL + mock Duffel）。"""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.container import Container
from app.models import AlertHistory, TrackedWatchlist, WatchStatus
from app.services.patrol import run_patrol
from tests.conftest import DUFFEL, USER
from tests.factories import connecting_raw, direct_raw

pytestmark = pytest.mark.integration

DEP = (date.today() + timedelta(days=45)).isoformat()
RET = (date.today() + timedelta(days=52)).isoformat()
LAYOVER_OK = "2026-12-20T12:00:00"  # 10:00 抵達 → 停留 120 分
LAYOVER_SHORT = "2026-12-20T10:30:00"  # 停留 30 分，會被預設 90 分下限濾掉


def offers_payload(*offers: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": {"offers": list(offers)}})


def mock_search(*offers: dict[str, Any]) -> respx.Route:
    return respx.post(f"{DUFFEL}/air/offer_requests").mock(return_value=offers_payload(*offers))


class TestSearchApi:
    @respx.mock
    async def test_search_filters_ranks_and_caches(self, client: httpx.AsyncClient) -> None:
        route = mock_search(
            direct_raw("d1", "300"),
            connecting_raw("c1", "180", "HKG", LAYOVER_OK),
            connecting_raw("c2", "150", "ICN", LAYOVER_SHORT, owner="KE"),
        )
        body = {
            "origin": "tpe",
            "destination": "TYO",
            "departure_date": DEP,
            "return_date": RET,
            "currency": "USD",
        }
        first = (await client.post("/api/search", json=body)).json()
        assert first["success"] is True
        data = first["data"]
        assert data["destination_airports"] == ["HND", "NRT"]
        assert data["total_raw"] == 3 and data["total_filtered"] == 2
        assert data["hubs"] == ["HKG", "ICN"]
        assert {a["code"] for a in data["airlines"]} == {"BR", "CX", "KE"}
        ids = [o["offer"]["id"] for o in data["offers"]]
        assert ids == ["c1", "d1"]
        assert "cheapest" in data["offers"][0]["tags"]
        assert "fastest" in data["offers"][1]["tags"]
        assert data["cache"]["hit"] is False

        second = (await client.post("/api/search", json={**body, "allowed_hubs": ["sin"]})).json()
        assert second["data"]["cache"]["hit"] is True
        assert [o["offer"]["id"] for o in second["data"]["offers"]] == ["d1"]
        assert route.call_count == 1

    async def test_validation_errors_use_envelope(self, client: httpx.AsyncClient) -> None:
        res = await client.post(
            "/api/search",
            json={
                "origin": "TPE",
                "destination": "NRT",
                "departure_date": DEP,
                "return_date": "2020-01-01",
            },
        )
        assert res.status_code == 422
        assert res.json() == {**res.json(), "success": False, "error": "回程日期不可早於出發日期"}

    @respx.mock
    async def test_duffel_failure_maps_to_502(self, client: httpx.AsyncClient) -> None:
        respx.post(f"{DUFFEL}/air/offer_requests").mock(
            return_value=httpx.Response(500, json={"errors": [{"message": "Supplier down"}]})
        )
        res = await client.post(
            "/api/search", json={"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        )
        assert res.status_code == 502
        assert res.json()["error"] == "Supplier down"

    async def test_airport_suggestions(self, client: httpx.AsyncClient) -> None:
        data = (await client.get("/api/airports", params={"q": "tyo"})).json()["data"]
        assert data[0]["iata_code"] == "TYO" and data[0]["kind"] == "city"
        assert {"HND", "NRT"} <= {a["iata_code"] for a in data}
        zh = (await client.get("/api/airports", params={"q": "桃園"})).json()["data"]
        assert zh[0]["iata_code"] == "TPE"

    async def test_health(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/api/health")).json() == {"status": "ok"}

    async def test_root_redirects_to_docs(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"
        assert (await client.get("/docs")).status_code == 200


class TestFareMatrix:
    @respx.mock
    async def test_streams_axes_cells_and_done(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("d1", "300"), connecting_raw("c1", "180", "HKG", LAYOVER_OK))
        body = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "return_date": RET,
            "radius_days": 1,
            "currency": "USD",
        }
        res = await client.post("/api/fare-matrix", json=body)
        lines = [json.loads(line) for line in res.text.splitlines()]
        assert lines[0]["type"] == "axes" and len(lines[0]["departure_dates"]) == 3
        cells = [line for line in lines if line["type"] == "cell"]
        assert len(cells) == 9
        assert {c["price"] for c in cells} == {"180"}
        assert lines[-1] == {"type": "done"}

    @respx.mock
    async def test_direct_only_one_way_and_errors(self, client: httpx.AsyncClient) -> None:
        respx.post(f"{DUFFEL}/air/offer_requests").mock(
            side_effect=[offers_payload(connecting_raw("c1", "180", "HKG", LAYOVER_OK))]
            + [httpx.Response(400, json={"errors": [{"message": "bad"}]})] * 10
        )
        body = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "direct_only": True,
            "radius_days": 1,
            "currency": "USD",
        }
        lines = [
            json.loads(x)
            for x in (await client.post("/api/fare-matrix", json=body)).text.splitlines()
        ]
        statuses = sorted(c["status"] for c in lines if c["type"] == "cell")
        assert lines[0]["return_dates"] == [None]
        assert statuses == ["empty", "error", "error"]


async def create_watch(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "origin": "TPE",
        "destination": "NRT",
        "departure_date": DEP,
        "return_date": RET,
        "target_price": 200,
        "currency": "USD",
    }
    res = await client.post("/api/watchlists", json={**body, **overrides}, headers=USER)
    assert res.status_code == 201, res.text
    data: dict[str, Any] = res.json()["data"]
    return data


class TestWatchlistApi:
    async def test_requires_user_header(self, client: httpx.AsyncClient) -> None:
        res = await client.get("/api/watchlists")
        assert res.status_code == 401 and res.json()["success"] is False

    async def test_create_list_cancel_and_ownership(self, client: httpx.AsyncClient) -> None:
        created = await create_watch(client, label="東京", allowed_transits=["hkg"])
        assert created["status"] == "TRACKING" and created["allowed_transits"] == ["HKG"]
        assert created["has_webhook"] is False

        listed = (await client.get("/api/watchlists", headers=USER)).json()
        assert listed["meta"]["total"] == 1 and listed["data"][0]["stats"]["latest_price"] is None

        other = await client.delete(
            f"/api/watchlists/{created['id']}", headers={"X-User-Id": "someone-else"}
        )
        assert other.status_code == 404

        cancelled = (await client.delete(f"/api/watchlists/{created['id']}", headers=USER)).json()[
            "data"
        ]
        assert cancelled["status"] == "CANCELLED" and cancelled["is_active"] is False
        active_only = await client.get(
            "/api/watchlists", params={"include_inactive": False}, headers=USER
        )
        assert active_only.json()["data"] == []

    async def test_requires_threshold_and_valid_webhook(self, client: httpx.AsyncClient) -> None:
        base = {"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        res = await client.post("/api/watchlists", json=base, headers=USER)
        assert res.json()["error"] == "請至少設定目標價或相對降幅其中一項"
        res = await client.post(
            "/api/watchlists",
            json={**base, "drop_percent": 10, "webhook_url": "https://evil.com/x"},
            headers=USER,
        )
        assert res.status_code == 422 and "允許清單" in res.json()["error"]

    @respx.mock
    async def test_unknown_airport_is_fetched_from_duffel(self, client: httpx.AsyncClient) -> None:
        respx.get(f"{DUFFEL}/places/suggestions", params={"query": "LIS"}).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "type": "airport",
                            "iata_code": "LIS",
                            "name": "Lisbon",
                            "iata_country_code": "PT",
                            "iata_city_code": "LIS",
                            "time_zone": "Europe/Lisbon",
                        }
                    ]
                },
            )
        )
        respx.get(f"{DUFFEL}/places/suggestions", params={"query": "XXX"}).mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        created = await create_watch(client, destination="LIS")
        assert created["destination"] == "LIS"
        res = await client.post(
            "/api/watchlists",
            json={"origin": "TPE", "destination": "XXX", "departure_date": DEP, "target_price": 1},
            headers=USER,
        )
        assert res.status_code == 422 and "XXX" in res.json()["error"]


class TestPatrolPipeline:
    @respx.mock
    async def test_dedupes_records_alerts_and_cools_down(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        route = mock_search(direct_raw("d1", "300"), connecting_raw("c1", "180", "HKG", LAYOVER_OK))
        cheap = await create_watch(client, target_price=200)  # 180 ≤ 200 → 告警
        direct_only = await create_watch(
            client, target_price=250, max_stops=0
        )  # 只看直飛 300 → 不告警
        other_route = await create_watch(client, destination="KIX", target_price=100)

        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["active"] == 3
        assert report["route_groups"] == 3  # max_stops 不同 → 不同查詢條件
        assert report["prices_recorded"] == 3
        assert report["alerts_sent"] == 1
        assert route.call_count == 3

        history = (await client.get(f"/api/watchlists/{cheap['id']}/history", headers=USER)).json()[
            "data"
        ]
        assert [Decimal(p["price"]) for p in history] == [Decimal("180.00")]
        alerts = (await client.get(f"/api/watchlists/{cheap['id']}/alerts", headers=USER)).json()[
            "data"
        ]
        assert alerts[0]["reason"] == "target" and alerts[0]["channel"] == "log"
        assert (
            await client.get(f"/api/watchlists/{direct_only['id']}/alerts", headers=USER)
        ).json()["data"] == []
        assert other_route["destination"] == "KIX"

        # 同價再次巡檢 → 冷卻期內不重複發送
        again = (await client.post("/api/patrol/run")).json()["data"]
        assert again["alerts_sent"] == 0 and again["alerts_suppressed"] == 1

        # 價格進一步下探 → 即使在冷卻期內也通知
        route.mock(return_value=offers_payload(connecting_raw("c1", "160", "HKG", LAYOVER_OK)))
        third = (await client.post("/api/patrol/run")).json()["data"]
        assert third["alerts_sent"] == 1

        board = (await client.get("/api/watchlists", headers=USER)).json()["data"]
        stats = next(w["stats"] for w in board if w["id"] == cheap["id"])
        assert Decimal(stats["latest_price"]) == Decimal("160.00")
        assert stats["last_alert_at"] is not None and len(stats["sparkline"]) == 3

    @respx.mock
    async def test_same_route_is_aggregated_into_one_call(self, client: httpx.AsyncClient) -> None:
        route = mock_search(direct_raw("d1", "300"))
        for price in (100, 150, 400):
            await create_watch(client, target_price=price)
        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["route_groups"] == 1 and route.call_count == 1
        assert report["prices_recorded"] == 3 and report["alerts_sent"] == 1

    async def test_expires_departed_watches(self, container: Container) -> None:
        async with container.sessions() as session:
            session.add(
                TrackedWatchlist(
                    user_identifier="tester-1",
                    origin="TPE",
                    destination="NRT",
                    departure_date=date.today() - timedelta(days=1),
                    target_price=Decimal(1),
                )
            )
            await session.commit()
        ctx = container.patrol_context()
        report = await run_patrol(ctx, container.cache, consumers=2, lock_ttl_s=60)
        assert report.expired == 1 and report.active == 0
        async with container.sessions() as session:
            watch = (await session.scalars(select(TrackedWatchlist))).one()
            assert watch.status == WatchStatus.EXPIRED and watch.is_active is False

    @respx.mock
    async def test_drop_percent_against_7_day_average(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        route = mock_search(direct_raw("d1", "200"))
        watch = await create_watch(client, target_price=None, drop_percent=10)
        ctx = container.patrol_context()
        t0 = datetime.now(UTC) - timedelta(days=2)
        await run_patrol(ctx, container.cache, 1, 60, now=t0)
        route.mock(return_value=offers_payload(direct_raw("d1", "185")))
        r1 = await run_patrol(ctx, container.cache, 1, 60, now=t0 + timedelta(days=1))
        assert r1.alerts_sent == 0  # 跌 7.5%，未達 10%
        route.mock(return_value=offers_payload(direct_raw("d1", "170")))
        r2 = await run_patrol(ctx, container.cache, 1, 60, now=t0 + timedelta(days=2))
        assert r2.alerts_sent == 1  # 均價 192.5 × 0.9 = 173.25
        async with container.sessions() as session:
            alert = (await session.scalars(select(AlertHistory))).one()
            assert alert.reason == "drop" and str(alert.watchlist_id) == watch["id"]

    @respx.mock
    async def test_webhook_failure_does_not_record_alert(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("d1", "100"))
        respx.post("https://discord.com/api/webhooks/1").mock(return_value=httpx.Response(500))
        await create_watch(client, webhook_url="https://discord.com/api/webhooks/1")
        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["alerts_sent"] == 0 and report["failures"] == 1

    async def test_lock_prevents_concurrent_runs(self, container: Container) -> None:
        await container.cache.acquire_lock("skyroute:lock:patrol", 60)
        report = await run_patrol(container.patrol_context(), container.cache, 1, 60)
        assert report.skipped_locked is True

    async def test_admin_token_required_when_configured(
        self, settings: Settings, container: Container
    ) -> None:
        from app.main import create_app

        secured = settings.model_copy(update={"admin_token": SecretStr("s3cret")})
        app = create_app(secured, container)
        app.state.container = container.__class__(**{**container.__dict__, "settings": secured})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as http:
            assert (await http.post("/api/patrol/run")).status_code == 403
            ok = await http.post("/api/patrol/run", headers={"X-Admin-Token": "s3cret"})
            assert ok.status_code == 200


class TestDeleteWatchlist:
    @respx.mock
    async def test_purge_removes_watch_history_and_alerts(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        mock_search(direct_raw("d1", "100"))
        watch = await create_watch(client, target_price=200)
        await client.post("/api/patrol/run")  # 產生歷史價格與告警

        res = await client.delete(
            f"/api/watchlists/{watch['id']}", params={"purge": True}, headers=USER
        )
        assert res.status_code == 200 and res.json()["meta"] == {"purged": True}

        async with container.sessions() as session:
            assert (await session.scalars(select(TrackedWatchlist))).all() == []
            assert (await session.scalars(select(AlertHistory))).all() == []
        missing = await client.get(f"/api/watchlists/{watch['id']}/history", headers=USER)
        assert missing.status_code == 404

    async def test_purge_requires_ownership(self, client: httpx.AsyncClient) -> None:
        watch = await create_watch(client)
        res = await client.delete(
            f"/api/watchlists/{watch['id']}",
            params={"purge": True},
            headers={"X-User-Id": "intruder"},
        )
        assert res.status_code == 404
        assert len((await client.get("/api/watchlists", headers=USER)).json()["data"]) == 1

    async def test_purge_ended_keeps_tracking_and_other_users(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        keep = await create_watch(client)
        cancelled = await create_watch(client, destination="KIX")
        await client.delete(f"/api/watchlists/{cancelled['id']}", headers=USER)
        other = {"X-User-Id": "someone-else"}
        payload = {"origin": "TPE", "destination": "NRT", "departure_date": DEP, "target_price": 1}
        others = (await client.post("/api/watchlists", json=payload, headers=other)).json()["data"]
        await client.delete(f"/api/watchlists/{others['id']}", headers=other)
        async with container.sessions() as session:
            session.add(
                TrackedWatchlist(
                    user_identifier="tester-1",
                    origin="TPE",
                    destination="NRT",
                    departure_date=date.today() - timedelta(days=3),
                    target_price=Decimal(1),
                    status=WatchStatus.EXPIRED,
                    is_active=False,
                )
            )
            await session.commit()

        res = await client.delete("/api/watchlists", params={"scope": "ended"}, headers=USER)
        assert res.json()["data"] == {"deleted": 2}
        remaining = (await client.get("/api/watchlists", headers=USER)).json()["data"]
        assert [w["id"] for w in remaining] == [keep["id"]]
        assert len((await client.get("/api/watchlists", headers=other)).json()["data"]) == 1

    async def test_bulk_delete_requires_scope(self, client: httpx.AsyncClient) -> None:
        assert (await client.delete("/api/watchlists", headers=USER)).status_code == 422
        bad = await client.delete("/api/watchlists", params={"scope": "all"}, headers=USER)
        assert bad.status_code == 422
