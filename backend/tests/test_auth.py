"""Google 登入：ID Token 驗證、工作階段 Cookie、清單隔離、帳號金鑰與匿名清單轉移。"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.container import Container, build_container
from app.db import Base
from app.main import create_app
from app.models import TrackedWatchlist, User
from app.services.airport_service import seed_airports
from app.services.auth import GOOGLE_CERTS_URL, SESSION_COOKIE, SessionSigner
from app.services.cache import MemoryCache
from app.services.fx import CACHE_KEY
from tests.conftest import DUFFEL, TEST_DATABASE_URL, TEST_FX
from tests.factories import direct_raw
from tests.test_api import DEP, RET, mock_search

CLIENT_ID = "test-client.apps.googleusercontent.com"
KID = "test-kid"
ACCOUNT_KEY = "duffel_test_accountkey12345"
SERVER_KEY = "duffel_test_serverdefaultkey"
WATCH = {
    "origin": "TPE",
    "destination": "NRT",
    "departure_date": DEP,
    "return_date": RET,
    "target_price": 50,
}

_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_PRIVATE.public_key()))


def google_token(sub: str = "sub-alice", **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": sub,
        "email": f"{sub}@example.com",
        "email_verified": True,
        "name": sub.title(),
        "iat": now,
        "exp": now + 600,
        **overrides,
    }
    return jwt.encode(claims, _PRIVATE, algorithm="RS256", headers={"kid": KID})


def mock_google() -> respx.Route:
    return respx.get(GOOGLE_CERTS_URL).mock(
        return_value=httpx.Response(200, json={"keys": [{**_JWK, "kid": KID, "alg": "RS256"}]})
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=TEST_DATABASE_URL,
        duffel_access_token=SecretStr(SERVER_KEY),
        secret_key=SecretStr("test-secret-key"),
        duffel_base_url=DUFFEL,
        outbound_rate_per_s=1000,
        outbound_burst=100,
        google_client_id=CLIENT_ID,
        session_cookie_secure=False,
    )


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    from app import models  # noqa: F401

    built = build_container(settings, cache=MemoryCache())
    async with built.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with built.sessions() as session:
        await seed_airports(session)
    await built.cache.set(CACHE_KEY, TEST_FX.model_dump_json(), 3600)
    yield built
    await built.close()


def make_client(settings: Settings, container: Container) -> httpx.AsyncClient:
    app = create_app(settings, container)
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    async with make_client(settings, container) as http:
        yield http


async def login(client: httpx.AsyncClient, sub: str = "sub-alice", **headers: str) -> Any:
    response = await client.post(
        "/api/auth/google", json={"credential": google_token(sub)}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_of(route: respx.Route, index: int = -1) -> str:
    return str(route.calls[index].request.headers["Authorization"])


class TestSessionSigner:
    pytestmark = pytest.mark.unit

    def test_roundtrip_expiry_and_tampering(self) -> None:
        signer = SessionSigner("secret", ttl_s=60)
        user_id = uuid.uuid4()
        value = signer.issue(user_id, now=1000)
        assert signer.verify(value, now=1030) == user_id
        assert signer.verify(value, now=1061) is None
        assert signer.verify(value.replace(str(user_id), str(uuid.uuid4())), now=1030) is None
        assert SessionSigner("other", ttl_s=60).verify(value, now=1030) is None
        assert signer.verify("garbage", now=1030) is None


class TestGoogleLogin:
    async def test_config_exposes_client_id(self, client: httpx.AsyncClient) -> None:
        data = (await client.get("/api/config")).json()["data"]
        assert data["google_client_id"] == CLIENT_ID

    @respx.mock
    async def test_login_sets_http_only_cookie_and_me(self, client: httpx.AsyncClient) -> None:
        mock_google()
        assert (await client.get("/api/auth/me")).json()["data"] is None
        response = await client.post("/api/auth/google", json={"credential": google_token()})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert (
            SESSION_COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
        )
        me = (await client.get("/api/auth/me")).json()["data"]
        assert me["email"] == "sub-alice@example.com" and me["key_mask"] is None

    @respx.mock
    @pytest.mark.parametrize(
        "overrides",
        [
            {"aud": "someone-else.apps.googleusercontent.com"},
            {"iss": "https://evil.example.com"},
            {"exp": int(time.time()) - 10},
            {"email_verified": False},
        ],
    )
    async def test_rejects_invalid_tokens(
        self, client: httpx.AsyncClient, overrides: dict[str, Any]
    ) -> None:
        mock_google()
        response = await client.post(
            "/api/auth/google", json={"credential": google_token(**overrides)}
        )
        assert response.status_code == 401
        assert response.json()["meta"]["code"] == "login_failed"
        assert SESSION_COOKIE not in response.headers.get("set-cookie", "")

    @respx.mock
    async def test_logout_and_tampered_cookie(self, client: httpx.AsyncClient) -> None:
        mock_google()
        await login(client)
        await client.post("/api/auth/logout")
        assert (await client.get("/api/auth/me")).json()["data"] is None
        client.cookies.set(SESSION_COOKIE, f"{uuid.uuid4()}.9999999999.forged")
        assert (await client.get("/api/auth/me")).json()["data"] is None

    async def test_disabled_without_client_id(self, container: Container) -> None:
        plain = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=TEST_DATABASE_URL,
            secret_key=SecretStr("test-secret-key"),
        )
        async with make_client(plain, build_container(plain, cache=MemoryCache())) as http:
            response = await http.post("/api/auth/google", json={"credential": google_token()})
            assert response.status_code == 404


class TestAccountIsolation:
    async def test_watchlists_require_login(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/watchlists", headers={"X-User-Id": "anon-1"})
        assert response.status_code == 401
        assert response.json()["meta"]["code"] == "login_required"

    @respx.mock
    async def test_each_account_sees_only_its_watchlists(
        self, settings: Settings, container: Container
    ) -> None:
        mock_google()
        mock_search(direct_raw("d1", "100"))
        async with (
            make_client(settings, container) as alice,
            make_client(settings, container) as bob,
        ):
            await login(alice, "sub-alice")
            await login(bob, "sub-bob")
            created = (await alice.post("/api/watchlists", json=WATCH)).json()["data"]
            assert [w["id"] for w in (await alice.get("/api/watchlists")).json()["data"]] == [
                created["id"]
            ]
            assert (await bob.get("/api/watchlists")).json()["data"] == []
            denied = await bob.delete(f"/api/watchlists/{created['id']}")
            assert denied.status_code == 404

    @respx.mock
    async def test_login_claims_anonymous_watchlists(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        mock_google()
        async with container.sessions() as session:
            session.add(
                TrackedWatchlist(
                    user_identifier="anon-browser-1",
                    origin="TPE",
                    destination="NRT",
                    departure_date=__import__("datetime").date.fromisoformat(DEP),
                    target_price=50,
                )
            )
            await session.commit()
        body = await login(client, **{"X-User-Id": "anon-browser-1"})
        assert body["meta"]["claimed_watchlists"] == 1
        assert len((await client.get("/api/watchlists")).json()["data"]) == 1


class TestAccountKey:
    @respx.mock
    async def test_account_key_is_used_then_falls_back_to_server_key(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        mock_google()
        respx.get(f"{DUFFEL}/air/airlines").mock(return_value=httpx.Response(200, json={}))
        search = mock_search(direct_raw("d1", "100"))
        await login(client)

        saved = (await client.put("/api/me/duffel-key", json={"token": ACCOUNT_KEY})).json()
        assert saved["data"]["key_mask"] == "duffel_test_••••2345"
        assert saved["data"]["key_mode"] == "test"
        async with container.sessions() as session:
            user = await session.scalar(select(User))
            assert user and user.duffel_token_enc and ACCOUNT_KEY not in user.duffel_token_enc

        trip = {"origin": "TPE", "destination": "NRT", "departure_date": DEP}
        await client.post("/api/search", json=trip)
        assert auth_of(search) == f"Bearer {ACCOUNT_KEY}"
        watch = (await client.post("/api/watchlists", json=WATCH)).json()["data"]
        assert watch["uses_own_key"] is True

        cleared = (await client.delete("/api/me/duffel-key")).json()["data"]
        assert cleared["key_mask"] is None
        await client.post("/api/search", json={**trip, "adults": 2})
        assert auth_of(search) == f"Bearer {SERVER_KEY}"
        async with container.sessions() as session:
            stored = await session.get(TrackedWatchlist, uuid.UUID(watch["id"]))
            assert stored and stored.duffel_token_enc is None  # 巡檢改回伺服器預設金鑰

    @respx.mock
    async def test_rejected_key_is_not_saved(self, client: httpx.AsyncClient) -> None:
        mock_google()
        respx.get(f"{DUFFEL}/air/airlines").mock(return_value=httpx.Response(401, json={}))
        await login(client)
        response = await client.put("/api/me/duffel-key", json={"token": ACCOUNT_KEY})
        assert response.status_code == 401
        assert (await client.get("/api/auth/me")).json()["data"]["key_mask"] is None

    async def test_key_endpoints_require_login(self, client: httpx.AsyncClient) -> None:
        response = await client.put("/api/me/duffel-key", json={"token": ACCOUNT_KEY})
        assert response.status_code == 401
        assert response.json()["meta"]["code"] == "login_required"


class TestUserPatrol:
    @respx.mock
    async def test_patrols_only_own_watchlists_with_cooldown(
        self, settings: Settings, container: Container
    ) -> None:
        mock_google()
        search = mock_search(direct_raw("d1", "100"))
        async with (
            make_client(settings, container) as alice,
            make_client(settings, container) as bob,
        ):
            await login(alice, "sub-alice")
            await login(bob, "sub-bob")
            await alice.post("/api/watchlists", json=WATCH)
            await bob.post("/api/watchlists", json={**WATCH, "destination": "KIX"})
            calls_before = len(search.calls)

            report = (await alice.post("/api/watchlists/patrol")).json()["data"]
            assert report["active"] == 1 and report["prices_recorded"] == 1
            assert len(search.calls) == calls_before + 1
            sent = json.loads(search.calls[-1].request.content)["data"]["slices"][0]
            assert sent["destination"] == "NRT"  # 沒有查到 Bob 的 KIX

            again = await alice.post("/api/watchlists/patrol")
            assert again.status_code == 429
            # 冷卻是每位使用者各自計算
            assert (await bob.post("/api/watchlists/patrol")).status_code == 200

    async def test_requires_login(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/watchlists/patrol")
        assert response.status_code == 401
        assert response.json()["meta"]["code"] == "login_required"


class TestKeyRemovalRelaxesInterval:
    @respx.mock
    async def test_clearing_account_key_bumps_short_intervals(
        self, client: httpx.AsyncClient
    ) -> None:
        mock_google()
        respx.get(f"{DUFFEL}/air/airlines").mock(return_value=httpx.Response(200, json={}))
        await login(client)
        await client.put("/api/me/duffel-key", json={"token": ACCOUNT_KEY})
        fast = (
            await client.post("/api/watchlists", json={**WATCH, "patrol_interval_minutes": 5})
        ).json()["data"]
        assert fast["patrol_interval_minutes"] == 5

        await client.delete("/api/me/duffel-key")
        after = (await client.get("/api/watchlists")).json()["data"][0]
        assert after["patrol_interval_minutes"] == 30
