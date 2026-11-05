"""使用者自備 Duffel 金鑰：格式、指紋、加密、閘道與 API 行為。"""

import json
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select

from app.integrations.duffel_client import DuffelGateway, MissingCredentialsError
from app.models import TrackedWatchlist
from app.services.credentials import (
    CipherUnavailable,
    InvalidTokenFormat,
    TokenCipher,
    token_fingerprint,
    validate_token,
)
from tests.conftest import DUFFEL, USER
from tests.factories import direct_raw
from tests.test_api import DEP, RET, mock_search

USER_KEY = "duffel_test_userownkey123"
OTHER_KEY = "duffel_live_anotherkey4567"


class TestTokenHelpers:
    pytestmark = pytest.mark.unit

    def test_validate_format_and_mode(self) -> None:
        assert validate_token(USER_KEY) == "test"
        assert validate_token(OTHER_KEY) == "live"
        for bad in (
            "",
            "sk-123",
            "duffel_prod_abcdefghijk",
            "duffel_test_short",
            "duffel_test_有中文字元abc",
        ):
            with pytest.raises(InvalidTokenFormat):
                validate_token(bad)

    def test_fingerprint_is_stable_and_not_the_token(self) -> None:
        fp = token_fingerprint(USER_KEY)
        assert fp == token_fingerprint(USER_KEY) and len(fp) == 16
        assert fp != token_fingerprint(OTHER_KEY) and USER_KEY not in fp

    def test_cipher_round_trip_and_wrong_secret(self) -> None:
        cipher = TokenCipher("secret-a")
        enc = cipher.encrypt(USER_KEY)
        assert USER_KEY not in enc
        assert cipher.decrypt(enc) == USER_KEY
        assert TokenCipher("secret-b").decrypt(enc) is None
        assert TokenCipher(None).decrypt(enc) is None

    def test_cipher_unavailable_without_secret(self) -> None:
        cipher = TokenCipher(None)
        assert cipher.available is False
        with pytest.raises(CipherUnavailable):
            cipher.encrypt(USER_KEY)

    def test_gateway_prefers_user_key_and_isolates_buckets(self) -> None:
        http = httpx.AsyncClient()
        gateway = DuffelGateway(http, "duffel_test_serverdefaultkey", 1, 2, 5000)
        assert gateway.client(None).namespace == "srv"
        user_client = gateway.client(USER_KEY)
        assert user_client.namespace == token_fingerprint(USER_KEY)
        assert gateway._bucket(user_client.namespace) is gateway._bucket(user_client.namespace)
        assert gateway._bucket("srv") is not gateway._bucket(user_client.namespace)

    def test_gateway_without_any_key(self) -> None:
        gateway = DuffelGateway(httpx.AsyncClient(), None, 1, 1, 5000)
        assert gateway.has_server_token is False
        with pytest.raises(MissingCredentialsError):
            gateway.client(None)

    def test_gateway_evicts_old_buckets(self) -> None:
        gateway = DuffelGateway(httpx.AsyncClient(), None, 1, 1, 5000)
        gateway.MAX_BUCKETS = 2
        for ns in ("a", "b", "c"):
            gateway._bucket(ns)
        assert list(gateway._buckets) == ["b", "c"]


pytestmark = pytest.mark.integration


def auth_of(route: respx.Route, index: int = -1) -> str:
    return str(route.calls[index].request.headers["Authorization"])


class TestCredentialApi:
    async def test_config_reports_capabilities(self, client: httpx.AsyncClient) -> None:
        data = (await client.get("/api/config")).json()["data"]
        assert data == {
            "has_server_key": True,
            "can_store_user_key": True,
            "google_client_id": None,
        }

    @respx.mock
    async def test_verify_valid_and_rejected_keys(self, client: httpx.AsyncClient) -> None:
        route = respx.get(f"{DUFFEL}/air/airlines").mock(
            side_effect=[
                httpx.Response(200, json={"data": []}),
                httpx.Response(401, json={"errors": [{"message": "not found"}]}),
            ]
        )
        ok = await client.post("/api/credentials/verify", headers={"X-Duffel-Token": USER_KEY})
        assert ok.json()["data"] == {"valid": True, "mode": "test"}
        assert auth_of(route, 0) == f"Bearer {USER_KEY}"
        bad = await client.post("/api/credentials/verify", headers={"X-Duffel-Token": OTHER_KEY})
        assert bad.status_code == 401 and bad.json()["success"] is False

    async def test_verify_requires_well_formed_key(self, client: httpx.AsyncClient) -> None:
        assert (await client.post("/api/credentials/verify")).status_code == 400
        res = await client.post("/api/credentials/verify", headers={"X-Duffel-Token": "sk-oops"})
        assert res.status_code == 400 and "duffel_test_" in res.json()["error"]

    @respx.mock
    async def test_search_uses_user_key_and_separate_cache(self, client: httpx.AsyncClient) -> None:
        route = mock_search(direct_raw("d1", "100"))
        body = {"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        server = (await client.post("/api/search", json=body)).json()["data"]
        mine = (
            await client.post("/api/search", json=body, headers={"X-Duffel-Token": USER_KEY})
        ).json()["data"]
        again = (
            await client.post("/api/search", json=body, headers={"X-Duffel-Token": USER_KEY})
        ).json()["data"]
        assert route.call_count == 2  # 伺服器金鑰與使用者金鑰各查一次，快取不共用
        assert auth_of(route, 0) == "Bearer duffel_test_serverdefaultkey"
        assert auth_of(route, 1) == f"Bearer {USER_KEY}"
        assert server["cache"]["key"].endswith(":srv")
        assert mine["cache"]["key"].endswith(token_fingerprint(USER_KEY))
        assert again["cache"]["hit"] is True

    @respx.mock
    async def test_rejected_user_key_returns_401(self, client: httpx.AsyncClient) -> None:
        respx.post(f"{DUFFEL}/air/offer_requests").mock(
            return_value=httpx.Response(401, json={"errors": [{"message": "bad token"}]})
        )
        body = {"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        res = await client.post("/api/search", json=body, headers={"X-Duffel-Token": USER_KEY})
        assert res.status_code == 401 and res.json()["meta"]["code"] == "invalid_api_key"

    async def test_missing_server_key_requires_user_key(
        self, client: httpx.AsyncClient, container: Any
    ) -> None:
        container.gateway._server_token = None
        res = await client.post(
            "/api/search", json={"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        )
        assert res.status_code == 401 and res.json()["meta"]["code"] == "missing_api_key"


class TestUserKeyPatrol:
    @respx.mock
    async def test_watchlist_stores_encrypted_key_and_patrol_uses_it(
        self, client: httpx.AsyncClient, container: Any
    ) -> None:
        route = mock_search(direct_raw("d1", "100"))
        payload = {
            "origin": "TPE",
            "destination": "NRT",
            "departure_date": DEP,
            "return_date": RET,
            "target_price": 50,
        }
        mine = (
            await client.post(
                "/api/watchlists", json=payload, headers={**USER, "X-Duffel-Token": USER_KEY}
            )
        ).json()["data"]
        server = (await client.post("/api/watchlists", json=payload, headers=USER)).json()["data"]
        assert mine["uses_own_key"] is True and server["uses_own_key"] is False
        assert USER_KEY not in json.dumps(mine)

        async with container.sessions() as session:
            stored = await session.get(TrackedWatchlist, __import__("uuid").UUID(mine["id"]))
            assert stored.duffel_token_enc and USER_KEY not in stored.duffel_token_enc

        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["route_groups"] == 2  # 同航線但金鑰不同 → 不合併
        assert sorted(auth_of(route, i) for i in range(2)) == sorted(
            [f"Bearer {USER_KEY}", "Bearer duffel_test_serverdefaultkey"]
        )

        await client.delete(f"/api/watchlists/{mine['id']}", headers=USER)
        async with container.sessions() as session:
            rows = (await session.scalars(select(TrackedWatchlist))).all()
            assert all(r.duffel_token_enc is None for r in rows if r.status == "CANCELLED")

    @respx.mock
    async def test_undecryptable_key_counts_as_failure(
        self, client: httpx.AsyncClient, container: Any
    ) -> None:
        mock_search(direct_raw("d1", "100"))
        payload = {"origin": "TPE", "destination": "NRT", "departure_date": DEP, "target_price": 50}
        await client.post(
            "/api/watchlists", json=payload, headers={**USER, "X-Duffel-Token": USER_KEY}
        )
        object.__setattr__(container, "cipher", TokenCipher("rotated-secret"))
        report = (await client.post("/api/patrol/run")).json()["data"]
        assert report["failures"] == 1 and report["prices_recorded"] == 0

    async def test_storing_key_requires_secret(
        self, client: httpx.AsyncClient, container: Any
    ) -> None:
        object.__setattr__(container, "cipher", TokenCipher(None))
        payload = {"origin": "TPE", "destination": "NRT", "departure_date": DEP, "target_price": 50}
        res = await client.post(
            "/api/watchlists", json=payload, headers={**USER, "X-Duffel-Token": USER_KEY}
        )
        assert res.status_code == 422 and "SECRET_KEY" in res.json()["error"]
