"""新功能：剔除測試航司、多航段、票價／時長範圍篩選、多幣別換算。"""

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from app.container import Container
from app.integrations.duffel_mapper import involves_airline, map_offers
from app.services.cache import MemoryCache
from app.services.fx import FxService, fallback_rates, parse_rates, quantize, to_currency
from tests.conftest import TEST_FX, USER
from tests.factories import connecting_raw, direct_raw, make_offer, raw_offer, raw_segment
from tests.test_api import DEP, LAYOVER_OK, mock_search

LEG2 = (date.today() + timedelta(days=50)).isoformat()


class TestExcludedAirlines:
    pytestmark = pytest.mark.unit

    def test_owner_or_any_segment_carrier_excludes_offer(self) -> None:
        zz_owner = direct_raw("zz", "10", owner="ZZ")
        zz_segment = raw_offer(
            "mixed",
            "20",
            [
                [
                    raw_segment(
                        "TPE", "NRT", "2026-12-20T08:00:00", "2026-12-20T12:00:00", carrier="ZZ"
                    )
                ]
            ],
            owner="BR",
        )
        real = direct_raw("br", "30")
        kept = map_offers([zz_owner, zz_segment, real], frozenset({"ZZ"}))
        assert [o.id for o in kept] == ["br"]
        assert involves_airline(zz_segment, frozenset({"ZZ"}))
        assert not involves_airline(real, frozenset())


class TestFxRates:
    pytestmark = pytest.mark.unit

    def test_cross_rate_and_rounding(self) -> None:
        assert TEST_FX.convert(Decimal("100"), "USD", "TWD") == Decimal("3000.00")
        assert TEST_FX.convert(Decimal("80"), "GBP", "USD") == Decimal("100.00")
        assert TEST_FX.convert(Decimal("10"), "USD", "USD") == Decimal("10")
        assert quantize(Decimal("123.456"), "JPY") == Decimal("123")

    def test_to_currency_keeps_original(self) -> None:
        offer = make_offer(amount="100")
        converted = to_currency(offer, TEST_FX, "TWD")
        assert (converted.total_amount, converted.currency) == (Decimal("3000.00"), "TWD")
        assert (converted.original_amount, converted.original_currency) == (Decimal("100"), "USD")
        assert to_currency(offer, TEST_FX, "USD") is offer

    def test_unsupported_currency(self) -> None:
        with pytest.raises(ValueError):
            TEST_FX.rate("USD", "XXX")

    def test_parse_requires_all_currencies(self) -> None:
        with pytest.raises(ValueError):
            parse_rates({"rates": {"TWD": 30}})
        fx = parse_rates(
            {
                "rates": {k: float(v) for k, v in fallback_rates().rates.items()},
                "time_last_update_unix": 1762300000,
            }
        )
        assert fx.source == "open.er-api.com" and not fx.approximate

    @respx.mock
    async def test_service_caches_and_falls_back(self) -> None:
        url = "https://fx.test/latest/USD"
        rates = {k: float(v) for k, v in fallback_rates().rates.items()}
        route = respx.get(url).mock(return_value=httpx.Response(200, json={"rates": rates}))
        async with httpx.AsyncClient() as http:
            service = FxService(http, MemoryCache(), url, ttl_s=60)
            first = await service.rates()
            await service.rates()
            assert route.call_count == 1 and not first.approximate

            broken = FxService(http, MemoryCache(), url, ttl_s=60)
            route.mock(return_value=httpx.Response(500))
            fallback = await broken.rates()
            assert fallback.approximate and fallback.source == "built-in reference rates"


pytestmark = pytest.mark.integration


def body_of(route: respx.Route, index: int = -1) -> dict[str, Any]:
    return json.loads(route.calls[index].request.content)["data"]  # type: ignore[no-any-return]


class TestSearchFeatures:
    @respx.mock
    async def test_test_airline_is_removed_from_results(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("zz", "50", owner="ZZ"), direct_raw("br", "300", number="200"))
        res = await client.post(
            "/api/search",
            json={"origin": "TPE", "destination": "NRT", "departure_date": DEP, "currency": "USD"},
        )
        data = res.json()["data"]
        assert [o["offer"]["airline_code"] for o in data["offers"]] == ["BR"]
        assert all(a["code"] != "ZZ" for a in data["airlines"])

    @respx.mock
    async def test_multi_city_sends_every_leg(self, client: httpx.AsyncClient) -> None:
        route = mock_search(direct_raw("d1", "500"))
        body = {
            "origin": "TPE",
            "destination": "LON",
            "departure_date": DEP,
            "extra_legs": [{"origin": "PAR", "destination": "TPE", "departure_date": LEG2}],
            "currency": "USD",
        }
        data = (await client.post("/api/search", json=body)).json()["data"]
        slices = body_of(route)["slices"]
        assert [(s["origin"], s["destination"]) for s in slices] == [("TPE", "LON"), ("PAR", "TPE")]
        assert ":mc:PAR-TPE-" in data["cache"]["key"]

    async def test_multi_city_validation(self, client: httpx.AsyncClient) -> None:
        base = {"origin": "TPE", "destination": "LON", "departure_date": LEG2}
        early = {
            **base,
            "extra_legs": [{"origin": "PAR", "destination": "TPE", "departure_date": DEP}],
        }
        assert (await client.post("/api/search", json=early)).json()[
            "error"
        ] == "多航段的日期必須依序排列"
        both = {
            **base,
            "return_date": LEG2,
            "extra_legs": [{"origin": "PAR", "destination": "TPE", "departure_date": LEG2}],
        }
        assert (await client.post("/api/search", json=both)).status_code == 422
        matrix = {
            **base,
            "extra_legs": [{"origin": "PAR", "destination": "TPE", "departure_date": LEG2}],
        }
        res = await client.post("/api/fare-matrix", json=matrix)
        assert res.status_code == 422 and "日期矩陣" in res.json()["error"]

    @respx.mock
    async def test_price_and_duration_ranges(self, client: httpx.AsyncClient) -> None:
        # d1：直飛 3h、300；c1：飛行 2h＋4h、轉機 2h，共 8h、180
        mock_search(direct_raw("d1", "300"), connecting_raw("c1", "180", "HKG", LAYOVER_OK))
        base = {"origin": "TPE", "destination": "NRT", "departure_date": DEP, "currency": "USD"}
        full = (await client.post("/api/search", json=base)).json()["data"]
        assert full["price_bounds"] == {"min": "180", "max": "300"}
        assert full["duration_bounds"] == {"min": "180", "max": "480"}

        cheap = (await client.post("/api/search", json={**base, "price_max": 200})).json()["data"]
        assert [o["offer"]["id"] for o in cheap["offers"]] == ["c1"]
        assert cheap["price_bounds"] == full["price_bounds"]  # 上下限不隨篩選縮小

        short = (await client.post("/api/search", json={**base, "duration_max": 240})).json()[
            "data"
        ]
        assert [o["offer"]["id"] for o in short["offers"]] == ["d1"]

        bad = await client.post("/api/search", json={**base, "price_min": 500, "price_max": 100})
        assert bad.json()["error"] == "最低票價不可大於最高票價"

    @respx.mock
    async def test_converts_to_display_currency(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("d1", "100"))
        body = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "currency": "TWD",
            "price_max": 3500,
        }
        data = (await client.post("/api/search", json=body)).json()["data"]
        offer = data["offers"][0]["offer"]
        assert (offer["total_amount"], offer["currency"]) == ("3000.00", "TWD")
        assert (offer["original_amount"], offer["original_currency"]) == ("100", "USD")
        assert data["currency"] == "TWD" and data["fx"]["source"] == "test"

    @respx.mock
    async def test_matrix_uses_display_currency(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("d1", "100"))
        body = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "radius_days": 0,
            "currency": "GBP",
        }
        lines = [
            json.loads(x)
            for x in (await client.post("/api/fare-matrix", json=body)).text.splitlines()
        ]
        assert lines[0]["currency"] == "GBP"
        cell = next(x for x in lines if x["type"] == "cell")
        assert (cell["price"], cell["currency"]) == ("80.00", "GBP")

    async def test_fx_endpoint(self, client: httpx.AsyncClient) -> None:
        data = (await client.get("/api/fx")).json()["data"]
        assert data["base"] == "USD" and data["rates"]["TWD"] == "30"
        assert set(data["rates"]) >= {"TWD", "USD", "EUR", "GBP", "JPY"}


class TestWatchCurrency:
    @respx.mock
    async def test_patrol_records_and_compares_in_watch_currency(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        mock_search(direct_raw("d1", "100"))  # 100 USD = 3000 TWD
        payload = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "target_price": 3100,
            "currency": "TWD",
        }
        watch = (await client.post("/api/watchlists", json=payload, headers=USER)).json()["data"]
        assert watch["currency"] == "TWD"
        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["alerts_sent"] == 1
        history = (await client.get(f"/api/watchlists/{watch['id']}/history", headers=USER)).json()[
            "data"
        ]
        assert (history[0]["price"], history[0]["currency"]) == ("3000.00", "TWD")

    async def test_watchlist_accepts_multi_city_ticket(self, client: httpx.AsyncClient) -> None:
        payload = {
            "origin": "TPE",
            "destination": "LON",
            "departure_date": DEP,
            "target_price": 1,
            "extra_legs": [{"origin": "PAR", "destination": "TPE", "departure_date": LEG2}],
        }
        res = await client.post("/api/watchlists", json=payload, headers=USER)
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["ticket_mode"] == "ticket"
        assert data["extra_legs"] == [
            {"origin": "PAR", "destination": "TPE", "departure_date": LEG2}
        ]


class TestErrorLanguage:
    async def test_errors_follow_accept_language(self, client: httpx.AsyncClient) -> None:
        body = {"origin": "TPE", "destination": "TPE", "departure_date": DEP}
        zh = await client.post("/api/search", json=body)
        en = await client.post(
            "/api/search", json=body, headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        assert zh.json()["error"] == "出發地與目的地不可相同"
        assert en.json()["error"] == "Origin and destination must be different"
        missing = await client.get("/api/watchlists", headers={"Accept-Language": "en"})
        assert missing.json()["error"] == "Missing or invalid X-User-Id header"

    def test_prefix_and_fallback(self) -> None:
        from app.i18n import language_of, translate

        assert translate("找不到機場或城市代碼：XXX", "en") == "Unknown airport or city code: XXX"
        assert translate("未知訊息", "en") == "未知訊息"
        assert language_of(None) == "zh" and language_of("zh-TW,en") == "zh"


class TestTimeValueCurrency:
    @respx.mock
    async def test_time_value_is_entered_in_usd(self, client: httpx.AsyncClient) -> None:
        mock_search(direct_raw("d1", "100"))  # 3h 直飛、100 USD
        body = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "currency": "TWD",
            "time_value_per_hour": 10,
        }
        offer = (await client.post("/api/search", json=body)).json()["data"]["offers"][0]
        # 3000 TWD + 3h × (10 USD × 30) = 3900 TWD
        assert offer["cost_index"] == "3900.00"


def br67_raw(offer_id: str = "br67", amount: str = "900") -> dict[str, Any]:
    """重現長榮 BR67：台北→倫敦單一航段，中途經停曼谷 1h30m（同班機不換機）。"""
    segment = raw_segment(
        "TPE", "LHR", "2026-12-20T08:05:00", "2026-12-20T19:05:00", "PT19H", "BR", "0067"
    )
    segment["stops"] = [
        {
            "airport": {"iata_code": "BKK", "city_name": "Bangkok"},
            "arriving_at": "2026-12-20T11:10:00",
            "departing_at": "2026-12-20T12:40:00",
            "duration": "PT1H30M",
        }
    ]
    return raw_offer(offer_id, amount, [[segment]], owner="BR")


class TestTechnicalStops:
    pytestmark = pytest.mark.unit

    def test_mapper_keeps_stop_but_counts_no_connection(self) -> None:
        [offer] = map_offers([br67_raw()])
        slice_ = offer.slices[0]
        assert slice_.stops == 0  # 沒有換機
        assert slice_.technical_stops == 1
        assert slice_.segments[0].stops[0].airport == "BKK"
        assert slice_.segments[0].stops[0].minutes == 90
        assert offer.stop_airports == frozenset({"BKK"})
        assert not offer.is_nonstop

    def test_stop_minutes_fall_back_to_times(self) -> None:
        raw = br67_raw()
        raw["slices"][0]["segments"][0]["stops"][0]["duration"] = None
        assert map_offers([raw])[0].slices[0].segments[0].stops[0].minutes == 90

    def test_direct_only_excludes_technical_stops(self) -> None:
        from app.domain.topology import TopologyFilter, collect_hubs, offer_matches

        [stopping] = map_offers([br67_raw()])
        [nonstop] = map_offers([direct_raw("ci", "800", owner="CI")])
        assert not offer_matches(stopping, TopologyFilter(direct_only=True))
        assert offer_matches(nonstop, TopologyFilter(direct_only=True))
        # 不勾直飛時，經停航班仍屬「0 次轉機」
        assert offer_matches(stopping, TopologyFilter(max_stops=0))
        # 黑名單會排除經停機場；白名單不要求經停機場在名單內
        assert not offer_matches(stopping, TopologyFilter(excluded_hubs=frozenset({"BKK"})))
        assert offer_matches(stopping, TopologyFilter(allowed_hubs=frozenset({"HKG"})))
        assert collect_hubs([stopping]) == ["BKK"]


class TestTechnicalStopApi:
    @respx.mock
    async def test_search_marks_stop_and_direct_only_filters_it(
        self, client: httpx.AsyncClient
    ) -> None:
        mock_search(br67_raw(), direct_raw("ci", "1000", owner="CI", number="0069"))
        base = {"origin": "TPE", "destination": "LHR", "departure_date": DEP, "currency": "USD"}
        data = (await client.post("/api/search", json=base)).json()["data"]
        br = next(o for o in data["offers"] if o["offer"]["airline_code"] == "BR")
        slice_ = br["offer"]["slices"][0]
        assert (slice_["stops"], slice_["technical_stops"]) == (0, 1)
        assert slice_["segments"][0]["stops"][0]["airport"] == "BKK"

        direct = (await client.post("/api/search", json={**base, "direct_only": True})).json()
        assert [o["offer"]["airline_code"] for o in direct["data"]["offers"]] == ["CI"]

    @respx.mock
    async def test_nonstop_watch_ignores_stopping_flight(self, client: httpx.AsyncClient) -> None:
        mock_search(br67_raw(amount="100"), direct_raw("ci", "300", owner="CI", number="0069"))
        payload = {
            "origin": "TPE",
            "destination": "LHR",
            "departure_date": DEP,
            "target_price": 500,
            "max_stops": 0,
            "currency": "USD",
        }
        watch = (await client.post("/api/watchlists", json=payload, headers=USER)).json()["data"]
        await client.post("/api/patrol/run")
        history = (await client.get(f"/api/watchlists/{watch['id']}/history", headers=USER)).json()
        # 便宜的 BR67 有經停，不符合「僅直飛」，應記錄直飛的 CI 300
        assert [(p["airline_code"], p["price"]) for p in history["data"]] == [("CI", "300.00")]


class TestCodeshare:
    pytestmark = pytest.mark.unit

    def test_operating_carrier_is_kept_for_codeshares(self) -> None:
        segment = raw_segment(
            "TPE", "PVG", "2026-12-20T08:45:00", "2026-12-20T10:30:00", carrier="MU", number="8901"
        )
        segment["operating_carrier"] = {"iata_code": "CI", "name": "China Airlines"}
        [offer] = map_offers([raw_offer("mu", "500", [[segment]], owner="MU")])
        seg = offer.slices[0].segments[0]
        assert (seg.flight_number, seg.operating_code, seg.operating_name) == (
            "MU8901",
            "CI",
            "China Airlines",
        )

    def test_own_metal_has_no_operating_note(self) -> None:
        segment = raw_segment("TPE", "LHR", "2026-12-20T08:05:00", "2026-12-20T19:05:00")
        segment["operating_carrier"] = {"iata_code": "BR", "name": "EVA Air"}
        [offer] = map_offers([raw_offer("br", "500", [[segment]])])
        assert offer.slices[0].segments[0].operating_code is None


class TestSimulatedFlag:
    pytestmark = pytest.mark.unit

    def test_live_mode_false_marks_offer_simulated(self) -> None:
        test_mode = {**direct_raw("t", "100"), "live_mode": False}
        live = {**direct_raw("l", "100", number="200"), "live_mode": True}
        unknown = direct_raw("u", "100", number="300")
        flags = {o.id: o.is_simulated for o in map_offers([test_mode, live, unknown])}
        assert flags == {"t": True, "l": False, "u": False}


class TestSimulatedApi:
    @respx.mock
    async def test_search_and_matrix_expose_simulated_flag(self, client: httpx.AsyncClient) -> None:
        mock_search({**direct_raw("t", "100"), "live_mode": False})
        base = {"origin": "TPE", "destination": "NRT", "departure_date": DEP, "currency": "USD"}
        offer = (await client.post("/api/search", json=base)).json()["data"]["offers"][0]["offer"]
        assert offer["is_simulated"] is True
        lines = (await client.post("/api/fare-matrix", json={**base, "radius_days": 0})).text
        cell = next(json.loads(x) for x in lines.splitlines() if '"cell"' in x)
        assert cell["simulated"] is True
