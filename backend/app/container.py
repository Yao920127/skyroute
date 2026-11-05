"""組裝長生命週期的資源（DB 引擎、快取、HTTP 客戶端、服務），API 與 Worker 共用。"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db import SessionFactory, create_engine, create_session_factory
from app.integrations.duffel_client import DuffelClient, DuffelGateway
from app.services.alerts import Notifier
from app.services.auth import AuthService, GoogleVerifier, SessionSigner
from app.services.cache import Cache, create_cache
from app.services.credentials import TokenCipher
from app.services.fx import FxService
from app.services.patrol import PatrolContext
from app.services.search_service import SearchService


@dataclass(frozen=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: SessionFactory
    cache: Cache
    duffel_http: httpx.AsyncClient
    webhook_http: httpx.AsyncClient
    gateway: DuffelGateway
    cipher: TokenCipher
    search: SearchService
    fx: FxService
    notifier: Notifier
    auth: AuthService

    def patrol_context(self) -> PatrolContext:
        return PatrolContext(
            sessions=self.sessions,
            search=self.search,
            gateway=self.gateway,
            cipher=self.cipher,
            fx=self.fx,
            notifier=self.notifier,
            cooldown_hours=self.settings.alert_cooldown_hours,
        )

    async def close(self) -> None:
        await self.duffel_http.aclose()
        await self.webhook_http.aclose()
        await self.cache.close()
        await self.engine.dispose()


def _secret(value: object) -> str | None:
    getter = getattr(value, "get_secret_value", None)
    return getter() if getter else None


def build_container(settings: Settings, cache: Cache | None = None) -> Container:
    engine = create_engine(settings.database_url)
    cache = cache or create_cache(settings.redis_url)
    duffel_http = DuffelClient.build_http(settings.duffel_base_url, settings.duffel_http_timeout_s)
    gateway = DuffelGateway(
        duffel_http,
        _secret(settings.duffel_access_token),
        settings.outbound_rate_per_s,
        settings.outbound_burst,
        settings.duffel_supplier_timeout_ms,
    )
    webhook_http = httpx.AsyncClient(follow_redirects=False)
    secret = _secret(settings.secret_key)
    client_id = settings.google_client_id
    auth = AuthService(
        verifier=GoogleVerifier(webhook_http, client_id) if client_id and secret else None,
        signer=SessionSigner(secret, settings.session_ttl_days * 86_400) if secret else None,
        client_id=client_id if secret else None,
        cookie_secure=settings.session_cookie_secure,
    )
    return Container(
        settings=settings,
        engine=engine,
        sessions=create_session_factory(engine),
        cache=cache,
        duffel_http=duffel_http,
        webhook_http=webhook_http,
        gateway=gateway,
        cipher=TokenCipher(_secret(settings.secret_key)),
        search=SearchService(
            cache,
            settings.search_cache_ttl_s,
            frozenset(code.upper() for code in settings.excluded_airlines),
        ),
        fx=FxService(webhook_http, cache, settings.fx_source_url, settings.fx_ttl_s),
        notifier=Notifier(webhook_http, settings.webhook_allowed_hosts),
        auth=auth,
    )
