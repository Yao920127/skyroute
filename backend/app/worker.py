"""背景巡檢 Worker：每日固定時間觸發巡檢（多實例部署時以 Redis 鎖確保只跑一次）。

執行：python -m app.worker            # 常駐排程
      python -m app.worker --once     # 立即跑一次後結束（可交給系統 cron）
"""

import argparse
import asyncio
import logging
import signal
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db import init_schema
from app.services.airport_service import seed_airports
from app.services.patrol import run_patrol

log = logging.getLogger("skyroute.worker")


def next_run_at(now: datetime, daily_at: str, tz: ZoneInfo) -> datetime:
    hour, minute = (int(x) for x in daily_at.split(":"))
    local_now = now.astimezone(tz)
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=tz)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


async def patrol_once(container: Container) -> None:
    s = container.settings
    await run_patrol(
        container.patrol_context(), container.cache, s.patrol_consumers, s.patrol_lock_ttl_s
    )


async def serve(settings: Settings, once: bool) -> None:
    container = build_container(settings)
    await init_schema(container.engine)
    async with container.sessions() as session:
        await seed_airports(session)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        if once or settings.patrol_run_on_start:
            await patrol_once(container)
        tz = ZoneInfo(settings.patrol_timezone)
        while not once and not stop.is_set():
            target = next_run_at(datetime.now(tz), settings.patrol_daily_at, tz)
            wait_s = (target - datetime.now(tz)).total_seconds()
            log.info("下一次巡檢：%s（%.0f 秒後）", target.isoformat(), wait_s)
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait_s)
            except TimeoutError:
                await patrol_once(container)
    finally:
        await container.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SkyRoute 背景巡檢 Worker")
    parser.add_argument("--once", action="store_true", help="執行一次巡檢後結束")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve(get_settings(), args.once))


if __name__ == "__main__":
    main()
