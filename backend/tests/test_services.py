"""服務層單元測試：Duffel 映射、快取搜尋、令牌桶、快取、告警、看盤統計。"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from app.integrations.duffel_client import DuffelClient, DuffelError, retry_delay
from app.integrations.duffel_mapper import map_offers
from app.models import TrackedWatchlist
from app.services.alerts import (
    NotificationError,
    Notifier,
    format_message,
    in_cooldown,
    threshold_reason,
    validate_webhook_url,
)
from app.services.board_stats import PriceSample, compute_stats
from app.services.cache import MemoryCache
from app.services.rate_limit import TokenBucket
from app.services.search_service import RouteQuery, SearchService, dedupe_itineraries
from tests.factories import connecting_raw, direct_raw, make_offer, raw_offer, raw_segment

pytestmark = pytest.mark.unit


class TestMapper:
    def test_flattens_connection_and_computes_layover(self) -> None:
        [offer] = map_offers([connecting_raw("off_c", "250.50", "HKG", "2026-12-20T12:15:00")])
        slice_ = offer.slices[0]
        assert offer.total_amount == Decimal("250.50")
        assert slice_.stops == 1
        assert slice_.layovers[0].airport == "HKG"
        assert slice_.layovers[0].minutes == 135
        assert slice_.flight_minutes == 360
        assert slice_.duration_minutes == 360 + 135  # slice duration 缺漏時以航段 + 轉機推算
        assert offer.refundable is None and offer.changeable is True
        assert offer.emissions_kg == 120

    def test_missing_segment_duration_falls_back_to_local_diff(self) -> None:
        raw = raw_offer(
            "o",
            "1",
            [[raw_segment("TPE", "NRT", "2026-12-20T08:00:00", "2026-12-20T12:00:00", None)]],
        )
        assert map_offers([raw])[0].slices[0].segments[0].duration_minutes == 240

    def test_skips_malformed_offers(self) -> None:
        good = direct_raw("ok", "10")
        assert [
            o.id for o in map_offers([{"id": "bad", "slices": [{"segments": [{}]}]}, good])
        ] == ["ok"]
        assert map_offers([{"id": "empty", "slices": []}]) == []


def test_dedupe_keeps_cheapest_brand_per_itinerary() -> None:
    offers = map_offers(
        [
            direct_raw("basic", "120"),
            direct_raw("flex", "180"),
            direct_raw("other", "150", number="200"),
        ]
    )
    assert [o.id for o in dedupe_itineraries(offers)] == ["basic", "other"]


class TestRouteQuery:
    def test_cache_key_format_and_pax_hash(self) -> None:
        q = RouteQuery(
            origin="TPE",
            destination="TYO",
            departure_date=date(2026, 12, 20),
            cabin_class="business",
        )
        assert q.cache_key.startswith("route:TPE:TYO:2026-12-20:-:business:")
        assert len(q.route_hash) == 64
        assert q.pax_hash != q.model_copy(update={"children": 1}).pax_hash

    def test_to_duffel_round_trip_with_children(self) -> None:
        q = RouteQuery(
            origin="TPE",
            destination="NRT",
            departure_date=date(2026, 12, 20),
            return_date=date(2026, 12, 27),
            adults=2,
            children=1,
        )
        slices, pax = q.to_duffel()
        assert [s["origin"] for s in slices] == ["TPE", "NRT"]
        assert pax == [{"type": "adult"}, {"type": "adult"}, {"age": 10}]


def _client(bucket_rate: float = 1000, token: str = "duffel_test_unitkey00") -> DuffelClient:
    http = DuffelClient.build_http("https://api.duffel.test", 5)
    return DuffelClient(http, token, TokenBucket(bucket_rate, 100), 5000)


class TestSearchServiceCacheAside:
    @respx.mock
    async def test_miss_then_hit_then_refresh(self) -> None:
        route = respx.post("https://api.duffel.test/air/offer_requests").mock(
            return_value=httpx.Response(200, json={"data": {"offers": [direct_raw("o1", "99")]}})
        )
        service = SearchService(MemoryCache(), ttl_s=60)
        client = _client()
        q = RouteQuery(origin="TPE", destination="NRT", departure_date=date(2026, 12, 20))

        first = await service.fetch(q, client)
        second = await service.fetch(q, client)
        third = await service.fetch(q, client, refresh=True)

        assert (first.cache_hit, second.cache_hit, third.cache_hit) == (False, True, False)
        assert second.offers[0].id == "o1"
        assert route.call_count == 2
        body = route.calls[0].request.content.decode()
        assert '"max_connections":1' in body.replace(" ", "")
        assert route.calls[0].request.headers["Duffel-Version"] == "v2"
        assert route.calls[0].request.headers["Authorization"] == "Bearer duffel_test_unitkey00"

    @respx.mock
    async def test_corrupt_cache_entry_is_refetched(self) -> None:
        respx.post("https://api.duffel.test/air/offer_requests").mock(
            return_value=httpx.Response(200, json={"data": {"offers": []}})
        )
        cache = MemoryCache()
        q = RouteQuery(origin="TPE", destination="NRT", departure_date=date(2026, 12, 20))
        client = _client()
        await cache.set(f"{q.cache_key}:{client.namespace}", "not-json", 60)
        assert (await SearchService(cache, 60).fetch(q, client)).cache_hit is False


class TestDuffelClient:
    @respx.mock
    async def test_error_is_raised_with_user_message(self) -> None:
        respx.post("https://api.duffel.test/air/offer_requests").mock(
            return_value=httpx.Response(422, json={"errors": [{"message": "Invalid origin"}]})
        )
        with pytest.raises(DuffelError) as info:
            await _client().create_offer_request([], [], "economy", 1)
        assert info.value.status == 422
        assert info.value.user_message == "Invalid origin"

    @respx.mock
    async def test_retries_on_429(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("app.integrations.duffel_client.asyncio.sleep", no_sleep)
        route = respx.get("https://api.duffel.test/places/suggestions").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"data": [{"iata_code": "LIS"}]}),
            ]
        )
        assert await _client().place_suggestions("LIS") == [{"iata_code": "LIS"}]
        assert route.call_count == 2

    @respx.mock
    async def test_connection_failure_becomes_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr("app.integrations.duffel_client.asyncio.sleep", no_sleep)
        respx.get("https://api.duffel.test/places/suggestions").mock(
            side_effect=httpx.ConnectError("down")
        )
        with pytest.raises(DuffelError) as info:
            await _client().place_suggestions("LIS")
        assert info.value.status == 503

    def test_retry_delay_prefers_headers(self) -> None:
        now = datetime(2026, 11, 5, 8, 21, 30, tzinfo=UTC)
        reset = httpx.Headers({"ratelimit-reset": "Thu, 05 Nov 2026 08:22:00 GMT"})
        assert retry_delay(reset, 1, lambda: now) == 30.5
        assert retry_delay(httpx.Headers({"Retry-After": "3"}), 1) == 3.0
        assert retry_delay(httpx.Headers({"Retry-After": "999"}), 1) == 65.0
        assert retry_delay(httpx.Headers({"ratelimit-reset": "garbage"}), 2) == 2.0
        assert retry_delay(httpx.Headers(), 2) == 2.0

    def test_user_message_fallback(self) -> None:
        assert DuffelError(500, "boom").user_message == "外部航班服務暫時無法使用"


class TestTokenBucket:
    def test_burst_then_refill(self) -> None:
        now = [0.0]
        bucket = TokenBucket(rate_per_s=2, capacity=2, clock=lambda: now[0])
        assert bucket.try_acquire() and bucket.try_acquire()
        assert not bucket.try_acquire()
        now[0] = 0.5
        assert bucket.try_acquire()

    async def test_acquire_waits_for_token(self) -> None:
        bucket = TokenBucket(rate_per_s=100, capacity=1)
        await bucket.acquire()
        await bucket.acquire()  # 需等待約 10ms 補充

    def test_invalid_config(self) -> None:
        with pytest.raises(ValueError):
            TokenBucket(0, 1)


class TestMemoryCache:
    async def test_ttl_and_lock(self) -> None:
        cache = MemoryCache()
        await cache.set("k", "v", ttl_s=0)
        assert await cache.get("k") is None
        token = await cache.acquire_lock("lock", 60)
        assert token is not None
        assert await cache.acquire_lock("lock", 60) is None
        await cache.release_lock("lock", "wrong-token")
        assert await cache.acquire_lock("lock", 60) is None
        await cache.release_lock("lock", token)
        assert await cache.acquire_lock("lock", 60) is not None
        await cache.close()


class TestAlerts:
    def test_threshold_target_and_drop(self) -> None:
        assert threshold_reason(Decimal(90), Decimal(100), None, None) == "target"
        assert threshold_reason(Decimal(110), Decimal(100), None, None) is None
        assert threshold_reason(Decimal(90), None, Decimal(10), Decimal(100)) == "drop"
        assert threshold_reason(Decimal(91), None, Decimal(10), Decimal(100)) is None
        assert threshold_reason(Decimal(50), None, Decimal(10), None) is None

    def test_cooldown(self) -> None:
        now = datetime(2026, 11, 5, tzinfo=UTC)
        recent = now - timedelta(hours=3)
        assert in_cooldown(recent, Decimal(100), Decimal(100), now, 24)
        assert not in_cooldown(recent, Decimal(100), Decimal(99), now, 24)  # 進一步下探
        assert not in_cooldown(now - timedelta(hours=25), Decimal(100), Decimal(100), now, 24)
        assert not in_cooldown(None, None, Decimal(1), now, 24)

    @pytest.mark.parametrize(
        ("url", "ok"),
        [
            ("https://discord.com/api/webhooks/1/x", True),
            ("https://hooks.slack.com/services/a", True),
            ("https://ptb.discord.com/api/webhooks/1", True),
            ("http://discord.com/api", False),
            ("https://evil.com/discord.com", False),
            ("https://discord.com.evil.com/x", False),
        ],
    )
    def test_webhook_validation(self, url: str, ok: bool) -> None:
        hosts = ["discord.com", "hooks.slack.com"]
        if ok:
            assert validate_webhook_url(url, hosts) == url
        else:
            with pytest.raises(ValueError):
                validate_webhook_url(url, hosts)

    def test_empty_allowlist_accepts_any_https(self) -> None:
        assert validate_webhook_url("https://example.com/hook", []) == "https://example.com/hook"

    def _watch(self, webhook: str | None) -> TrackedWatchlist:
        return TrackedWatchlist(
            origin="TPE",
            destination="NRT",
            departure_date=date(2026, 12, 20),
            return_date=date(2026, 12, 27),
            target_price=Decimal(200),
            drop_percent=Decimal(10),
            webhook_url=webhook,
        )

    def test_message_content(self) -> None:
        text = format_message(self._watch(None), make_offer(amount="150"), "drop")
        assert "TPE → NRT" in text and "150" in text and "下跌" in text

    @respx.mock
    async def test_notifier_webhook_success_and_failure(self) -> None:
        route = respx.post("https://discord.com/api/webhooks/1").mock(
            return_value=httpx.Response(204)
        )
        async with httpx.AsyncClient() as http:
            notifier = Notifier(http, ["discord.com"])
            assert await notifier.send(self._watch(None), make_offer(), "target") == "log"
            assert (
                await notifier.send(
                    self._watch("https://discord.com/api/webhooks/1"), make_offer(), "target"
                )
                == "webhook"
            )
            assert "content" in route.calls[0].request.content.decode()
            route.mock(return_value=httpx.Response(500))
            with pytest.raises(NotificationError):
                await notifier.send(
                    self._watch("https://discord.com/api/webhooks/1"), make_offer(), "target"
                )


class TestBoardStats:
    def _s(self, day: int, hour: int, price: str) -> PriceSample:
        return PriceSample(datetime(2026, 11, day, hour, tzinfo=UTC), Decimal(price), "USD")

    def test_empty(self) -> None:
        assert compute_stats([]).latest_price is None

    def test_day_and_week_changes(self) -> None:
        samples = [
            self._s(1, 3, "200"),
            self._s(3, 3, "180"),
            self._s(4, 3, "190"),
            self._s(5, 3, "171"),
            self._s(5, 9, "170"),
        ]
        stats = compute_stats(samples)
        assert stats.latest_price == Decimal("170")
        assert stats.previous_day_price == Decimal("190")
        assert stats.day_change == Decimal("-20")
        assert stats.day_change_pct == Decimal("-10.53")
        assert stats.change_basis == "day"
        assert stats.week_change_pct == Decimal("-15.00")
        assert stats.week_low == Decimal("170")
        assert stats.week_avg == Decimal("182.20")
        assert stats.sparkline[-1] == Decimal("170")

    def test_day_change_uses_24_hours_not_calendar_date(self) -> None:
        # 同一個 UTC 日期內、但已超過 24 小時之前沒有資料 → 與第一筆比較，標示 start
        same_day = compute_stats([self._s(6, 1, "100"), self._s(6, 9, "103")])
        assert same_day.day_change == Decimal("3") and same_day.change_basis == "start"
        # 跨日但不到 24 小時（例如台北凌晨）也一樣，不再因 UTC 換日而時有時無
        overnight = compute_stats([self._s(5, 20, "100"), self._s(6, 2, "99")])
        assert overnight.change_basis == "start" and overnight.day_change == Decimal("-1")
        full_day = compute_stats(
            [self._s(5, 1, "90"), self._s(5, 10, "100"), self._s(6, 10, "110")]
        )
        assert full_day.change_basis == "day" and full_day.previous_day_price == Decimal("100")
        single = compute_stats([self._s(6, 1, "100")])
        assert single.day_change is None and single.change_basis is None

    def test_week_window_excludes_older_points(self) -> None:
        stats = compute_stats([self._s(1, 0, "500"), self._s(20, 0, "100")])
        assert stats.week_low == Decimal("100")
        assert stats.week_change_pct is None
