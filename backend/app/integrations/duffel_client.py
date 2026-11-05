"""Duffel Flights REST API 的非同步 httpx 客戶端（防腐層的傳輸部分）。"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.services.credentials import token_fingerprint
from app.services.rate_limit import TokenBucket

log = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_S = 65.0


def retry_delay(
    headers: httpx.Headers, attempt: int, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> float:
    """依 Retry-After 或 Duffel 的 ratelimit-reset（HTTP 日期）決定重試等待秒數。"""
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), MAX_RETRY_DELAY_S)
        except ValueError:
            pass
    reset = headers.get("ratelimit-reset")
    if reset:
        try:
            wait = (parsedate_to_datetime(reset) - now()).total_seconds() + 0.5
            return min(max(wait, 0.5), MAX_RETRY_DELAY_S)
        except (TypeError, ValueError):
            pass
    return float(attempt)


class DuffelError(Exception):
    """Duffel 回傳非 2xx 或連線失敗時拋出。"""

    def __init__(self, status: int, errors: Any) -> None:
        super().__init__(f"Duffel HTTP {status}: {errors}")
        self.status = status
        self.errors = errors

    @property
    def user_message(self) -> str:
        if isinstance(self.errors, list) and self.errors:
            first = self.errors[0]
            if isinstance(first, dict):
                return str(first.get("message") or first.get("title") or "外部航班服務錯誤")
        return "外部航班服務暫時無法使用"


class DuffelClient:
    """綁定單一 Duffel 金鑰的客戶端；金鑰只放在每次請求的 Authorization 標頭，不寫入日誌。"""

    def __init__(
        self,
        http: httpx.AsyncClient,
        token: str,
        bucket: TokenBucket,
        supplier_timeout_ms: int,
        namespace: str = "srv",
    ) -> None:
        self._http = http
        self._auth = {"Authorization": f"Bearer {token}"}
        self._bucket = bucket
        self._supplier_timeout_ms = supplier_timeout_ms
        self.namespace = namespace  # 快取與巡檢分組用的金鑰指紋（不可逆）

    @staticmethod
    def build_http(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "Content-Type": "application/json",
                "Duffel-Version": "v2",
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        payload = {"data": data} if data is not None else None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._bucket.acquire()
            try:
                resp = await self._http.request(
                    method, path, params=params, json=payload, headers=self._auth
                )
            except httpx.HTTPError as exc:
                log.warning("Duffel 連線失敗 %s %s（第 %d 次）：%s", method, path, attempt, exc)
                if attempt == MAX_ATTEMPTS:
                    raise DuffelError(503, [{"message": "無法連線到外部航班服務"}]) from exc
                await asyncio.sleep(attempt)
                continue

            if resp.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                delay = retry_delay(resp.headers, attempt)
                log.warning("Duffel %s，%.1f 秒後重試", resp.status_code, delay)
                await asyncio.sleep(delay)
                continue

            body = resp.json() if resp.content else {}
            if not resp.is_success:
                raise DuffelError(resp.status_code, body.get("errors", body))
            return body.get("data")
        raise DuffelError(503, [{"message": "外部航班服務重試次數用盡"}])  # pragma: no cover

    async def create_offer_request(
        self,
        slices: list[dict[str, str]],
        passengers: list[dict[str, Any]],
        cabin_class: str,
        max_connections: int,
    ) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(
            "POST",
            "/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": self._supplier_timeout_ms},
            data={
                "slices": slices,
                "passengers": passengers,
                "cabin_class": cabin_class,
                "max_connections": max_connections,
            },
        )
        return result

    async def place_suggestions(self, query: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self._request(
            "GET", "/places/suggestions", params={"query": query}
        )
        return result or []

    async def verify(self) -> None:
        """以最輕量的端點確認金鑰有效；無效時拋出 DuffelError(401)。"""
        await self._request("GET", "/air/airlines", params={"limit": 1})


class MissingCredentialsError(Exception):
    """既沒有使用者金鑰、伺服器也沒有設定預設金鑰。"""


class DuffelGateway:
    """依金鑰產生 DuffelClient；共用一個連線池，但每把金鑰有各自的令牌桶（配額各自計算）。"""

    MAX_BUCKETS = 1024

    def __init__(
        self,
        http: httpx.AsyncClient,
        server_token: str | None,
        rate_per_s: float,
        burst: int,
        supplier_timeout_ms: int,
    ) -> None:
        self._http = http
        self._server_token = server_token
        self._rate = rate_per_s
        self._burst = burst
        self._timeout_ms = supplier_timeout_ms
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()

    @property
    def has_server_token(self) -> bool:
        return bool(self._server_token)

    def _bucket(self, namespace: str) -> TokenBucket:
        bucket = self._buckets.get(namespace)
        if bucket is None:
            bucket = TokenBucket(self._rate, self._burst)
            self._buckets[namespace] = bucket
            while len(self._buckets) > self.MAX_BUCKETS:
                self._buckets.popitem(last=False)
        self._buckets.move_to_end(namespace)
        return bucket

    def client(self, user_token: str | None = None) -> DuffelClient:
        """使用者金鑰優先；沒有則退回伺服器預設金鑰。"""
        if user_token:
            namespace = token_fingerprint(user_token)
            return DuffelClient(
                self._http, user_token, self._bucket(namespace), self._timeout_ms, namespace
            )
        if not self._server_token:
            raise MissingCredentialsError("請先設定 Duffel API 金鑰")
        return DuffelClient(
            self._http, self._server_token, self._bucket("srv"), self._timeout_ms, "srv"
        )
