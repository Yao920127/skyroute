"""告警判斷（目標價／相對降幅）、24 小時冷卻機制與 Webhook 推播。"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

import httpx

from app.domain.offers import FlightOffer
from app.models import TrackedWatchlist

log = logging.getLogger(__name__)

AlertReason = Literal["target", "drop"]
_HUNDRED = Decimal(100)


class NotificationError(Exception):
    pass


def threshold_reason(
    price: Decimal,
    target_price: Decimal | None,
    drop_percent: Decimal | None,
    baseline_avg: Decimal | None,
) -> AlertReason | None:
    if target_price is not None and price <= target_price:
        return "target"
    if drop_percent is not None and baseline_avg is not None and baseline_avg > 0:
        limit = baseline_avg * (1 - drop_percent / _HUNDRED)
        if price <= limit:
            return "drop"
    return None


def in_cooldown(
    last_alert_at: datetime | None,
    last_alert_price: Decimal | None,
    price: Decimal,
    now: datetime,
    cooldown_hours: int,
) -> bool:
    """冷卻期內且價格沒有進一步下探 → 不重複通知。"""
    if last_alert_at is None or last_alert_price is None:
        return False
    if now - last_alert_at >= timedelta(hours=cooldown_hours):
        return False
    return price >= last_alert_price


def validate_webhook_url(url: str, allowed_hosts: list[str]) -> str:
    """只允許 https 且（若有設定）主機在白名單內，降低 SSRF 風險。"""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Webhook 網址必須是 https://")
    host = parsed.hostname.lower()
    if allowed_hosts and not any(host == h or host.endswith(f".{h}") for h in allowed_hosts):
        raise ValueError(f"Webhook 主機不在允許清單內：{', '.join(allowed_hosts)}")
    return url.strip()


def format_message(watch: TrackedWatchlist, offer: FlightOffer, reason: AlertReason) -> str:
    trip = f"{watch.origin} → {watch.destination} {watch.departure_date.isoformat()}"
    if watch.return_date:
        trip += f"（回程 {watch.return_date.isoformat()}）"
    why = (
        f"已低於目標價 {watch.target_price}"
        if reason == "target"
        else f"較 7 日均價下跌 ≥ {watch.drop_percent}%"
    )
    first = offer.slices[0]
    flights = " / ".join(seg.flight_number for seg in first.segments)
    return (
        f"✈️ SkyRoute 低價告警：{trip}\n"
        f"最新價格 {offer.total_amount} {offer.currency}，{why}\n"
        f"{offer.airline_name}｜{flights}｜去程 {first.departing_at.replace('T', ' ')}"
        f"｜轉機 {first.stops} 次"
    )


class Notifier:
    def __init__(self, http: httpx.AsyncClient, allowed_hosts: list[str]) -> None:
        self._http = http
        self._allowed_hosts = allowed_hosts

    async def send(self, watch: TrackedWatchlist, offer: FlightOffer, reason: AlertReason) -> str:
        """回傳實際使用的通知管道；Webhook 失敗時拋出 NotificationError。"""
        message = format_message(watch, offer, reason)
        if not watch.webhook_url:
            log.info("告警（未設定 webhook，僅記錄）：%s", message.replace("\n", " | "))
            return "log"
        url = validate_webhook_url(watch.webhook_url, self._allowed_hosts)
        try:
            # content 給 Discord、text 給 Slack；兩者都會忽略不認得的欄位
            resp = await self._http.post(
                url, json={"content": message, "text": message}, timeout=10
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(f"Webhook 推播失敗：{exc}") from exc
        return "webhook"
