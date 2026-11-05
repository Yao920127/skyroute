"""領域邏輯單元測試：時長解析、拓撲過濾、代價指標與排序。"""

from decimal import Decimal

import pytest

from app.domain.durations import minutes_between, parse_iso_duration
from app.domain.metrics import cost_index, rank_offers, sort_offers
from app.domain.topology import TopologyFilter, apply_topology, collect_hubs, offer_matches
from tests.factories import make_offer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT3H22M", 202),
        ("P1DT2H", 1560),
        ("PT45M", 45),
        ("PT1H0M30S", 60),
        (None, None),
        ("bad", None),
        ("PT", None),
    ],
)
def test_parse_iso_duration(value: str | None, expected: int | None) -> None:
    assert parse_iso_duration(value) == expected


def test_minutes_between_same_timezone() -> None:
    assert minutes_between("2026-12-20T10:00:00", "2026-12-20T12:30:00") == 150


class TestTopologyFilter:
    direct = make_offer("direct", "300")
    via_hkg = make_offer("hkg", "200", layovers=[("HKG", 120)])
    via_icn_short = make_offer("icn", "150", layovers=[("ICN", 45)])
    two_stops = make_offer("two", "120", layovers=[("HKG", 100), ("BKK", 100)])

    def test_direct_only_removes_any_connection(self) -> None:
        kept = apply_topology([self.direct, self.via_hkg], TopologyFilter(direct_only=True))
        assert [o.id for o in kept] == ["direct"]

    def test_max_stops(self) -> None:
        rule = TopologyFilter(max_stops=1, min_layover_minutes=0)
        assert offer_matches(self.via_hkg, rule)
        assert not offer_matches(self.two_stops, rule)

    def test_allowed_hubs_whitelist(self) -> None:
        rule = TopologyFilter(allowed_hubs=frozenset({"HKG"}), min_layover_minutes=0)
        assert offer_matches(self.via_hkg, rule)
        assert not offer_matches(self.via_icn_short, rule)
        assert offer_matches(self.direct, rule)  # 直飛不受白名單影響

    def test_excluded_hubs_blacklist(self) -> None:
        rule = TopologyFilter(excluded_hubs=frozenset({"HKG"}))
        assert not offer_matches(self.via_hkg, rule)

    def test_layover_window_defaults_90_to_300(self) -> None:
        rule = TopologyFilter()
        assert offer_matches(self.via_hkg, rule)
        assert not offer_matches(self.via_icn_short, rule)
        long_wait = make_offer("long", "90", layovers=[("SIN", 301)])
        assert not offer_matches(long_wait, rule)

    def test_airline_filter(self) -> None:
        assert not offer_matches(self.direct, TopologyFilter(airlines=frozenset({"CI"})))
        assert offer_matches(self.direct, TopologyFilter(airlines=frozenset({"BR"})))

    def test_collect_hubs(self) -> None:
        assert collect_hubs([self.direct, self.two_stops, self.via_hkg]) == ["BKK", "HKG"]


class TestMetrics:
    def test_cost_index_formula(self) -> None:
        # 票價 100 + (飛行 3h + 轉機 2h × 1.5) × 10 = 160
        offer = make_offer(amount="100", layovers=[("HKG", 120)], flight_minutes=180)
        assert cost_index(offer, Decimal("10")) == Decimal("160.00")

    def test_rank_tags_cheapest_fastest_best_value(self) -> None:
        cheap_slow = make_offer("cheap", "100", layovers=[("HKG", 300)], flight_minutes=600)
        fast_pricey = make_offer("fast", "400", flight_minutes=120)
        balanced = make_offer("balanced", "150", flight_minutes=180)
        ranked = {
            r.offer.id: r.tags
            for r in rank_offers([cheap_slow, fast_pricey, balanced], Decimal("20"))
        }
        assert ranked["cheap"] == ("cheapest",)
        assert ranked["fast"] == ("fastest",)
        assert ranked["balanced"] == ("best_value",)

    def test_rank_empty(self) -> None:
        assert rank_offers([]) == []

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("price", ["a", "b", "c"]),
            ("duration", ["c", "b", "a"]),
            ("departure", ["b", "a", "c"]),
            ("airline", ["c", "a", "b"]),
            ("cost", ["a", "b", "c"]),
            ("arrival", ["b", "a", "c"]),
        ],
    )
    def test_sort_offers(self, key: str, expected: list[str]) -> None:
        offers = [
            make_offer(
                "a", "100", airline="CI", flight_minutes=300, departing_at="2026-12-20T09:00:00"
            ),
            make_offer(
                "b", "200", airline="JL", flight_minutes=200, departing_at="2026-12-20T07:00:00"
            ),
            make_offer(
                "c", "300", airline="BR", flight_minutes=100, departing_at="2026-12-20T11:00:00"
            ),
        ]
        ranked = rank_offers(offers, Decimal("1"))
        assert [r.offer.id for r in sort_offers(ranked, key)] == expected  # type: ignore[arg-type]

    def test_sort_descending(self) -> None:
        ranked = rank_offers([make_offer("a", "1"), make_offer("b", "2")])
        assert [r.offer.id for r in sort_offers(ranked, "price", descending=True)] == ["b", "a"]
