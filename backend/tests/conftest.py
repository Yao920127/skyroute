"""整合測試共用 fixture：獨立測試資料庫、記憶體快取、mock 的 Duffel。"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.container import Container, build_container
from app.db import Base
from app.main import create_app
from app.services.airport_service import seed_airports
from app.services.cache import MemoryCache
from app.services.fx import CACHE_KEY, FALLBACK_USD_RATES, FxRates

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://localhost:5432/skyroute_test"
)
DUFFEL = "https://api.duffel.test"
USER = {"X-User-Id": "tester-1"}
TEST_FX = FxRates(
    rates={**FALLBACK_USD_RATES, "TWD": Decimal("30"), "GBP": Decimal("0.8")},
    as_of=datetime(2026, 11, 5, tzinfo=UTC),
    source="test",
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=TEST_DATABASE_URL,
        duffel_access_token=SecretStr("duffel_test_serverdefaultkey"),
        secret_key=SecretStr("test-secret-key"),
        duffel_base_url=DUFFEL,
        outbound_rate_per_s=1000,
        outbound_burst=100,
        webhook_allowed_hosts=["discord.com"],
    )


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    from app import models  # noqa: F401

    built = build_container(settings, cache=MemoryCache())
    async with built.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with built.sessions() as session:
        await seed_airports(session, include_world=False)
    # 固定匯率（1 USD = 30 TWD、0.8 GBP），測試不連外部匯率服務
    await built.cache.set(CACHE_KEY, TEST_FX.model_dump_json(), 3600)
    yield built
    await built.close()


@pytest.fixture
async def client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, container)
    app.state.container = container  # ASGITransport 不觸發 lifespan，手動掛上容器
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
