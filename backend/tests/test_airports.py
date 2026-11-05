"""全球機場對照：資料合併、去重音搜尋、排序、城市代碼展開、Duffel 補齊與查無快取。"""

import httpx
import pytest
import respx

from app.container import Container
from app.services.airport_service import (
    expand_code,
    fold,
    load_seed_rows,
    search_airports,
    seed_airports,
)
from tests.conftest import DUFFEL


@pytest.mark.unit
class TestSeedRows:
    def test_merge_world_chinese_names_and_curated(self) -> None:
        rows = {r["iata_code"]: r for r in load_seed_rows()}
        assert len(rows) > 3500
        assert rows["TPE"]["name_zh"] == "臺灣桃園國際機場" and rows["TPE"]["size_rank"] == 0
        assert rows["CNX"]["name_zh"] == "清邁國際機場"
        assert rows["KEF"]["city_name"] == "Reykjavík"
        assert rows["PEK"]["city_code"] == "BJS" and rows["BJS"]["kind"] == "city"
        assert "reykjavik" in rows["KEF"]["search_text"]

    def test_fold_removes_accents(self) -> None:
        assert fold("São Paulo") == "sao paulo"
        assert fold("Reykjavík") == "reykjavik"


class TestWorldSearch:
    @pytest.fixture(autouse=True)
    async def _world(self, container: Container) -> None:
        async with container.sessions() as session:
            await seed_airports(session)

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("reykjavik", "KEF"),
            ("清邁", "CNX"),
            ("Phuket", "HKT"),
            ("TPE", "TPE"),
            ("london", "LON"),
        ],
    )
    async def test_finds_and_ranks(self, container: Container, query: str, expected: str) -> None:
        async with container.sessions() as session:
            found = await search_airports(session, query)
        assert found and found[0].iata_code == expected

    async def test_new_metro_codes_expand(self, container: Container) -> None:
        async with container.sessions() as session:
            assert await expand_code(session, "BJS") == ["PEK", "PKX"]


class TestDuffelFallback:
    @respx.mock
    async def test_unknown_term_asks_duffel_once(self, client: httpx.AsyncClient) -> None:
        place = {
            "type": "airport",
            "iata_code": "ZZQ",
            "iata_city_code": "ZZQ",
            "iata_country_code": "NZ",
            "name": "Faraway Strip",
            "city_name": "Nowhere",
        }
        route = respx.get(f"{DUFFEL}/places/suggestions").mock(
            side_effect=[
                httpx.Response(200, json={"data": [place]}),
                httpx.Response(200, json={"data": []}),
            ]
        )
        first = (await client.get("/api/airports", params={"q": "faraway"})).json()["data"]
        assert first[0]["iata_code"] == "ZZQ" and first[0]["city_name"] == "Nowhere"
        # 已存入對照表，再查不必問 Duffel
        again = (await client.get("/api/airports", params={"q": "faraway"})).json()["data"]
        assert again[0]["iata_code"] == "ZZQ" and route.call_count == 1

        # 查不到的字只問一次，之後直接回空清單
        assert (await client.get("/api/airports", params={"q": "qqqqq"})).json()["data"] == []
        assert (await client.get("/api/airports", params={"q": "qqqqq"})).json()["data"] == []
        assert route.call_count == 2
