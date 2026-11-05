"""背景巡檢 Worker：每分鐘檢查一次哪些追蹤「到期」需要巡檢（多實例部署時以 Redis 鎖確保只跑一次）。

每筆追蹤有自己的頻率（5 分鐘～每日）；未設定頻率的追蹤沿用每日固定時間（PATROL_DAILY_AT）。

執行：python -m app.worker            # 常駐排程
      python -m app.worker --once     # 立即巡檢全部追蹤一次後結束（可交給系統 cron）
"""

import argparse
import asyncio
import contextlib
import logging
import signal

from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db import init_schema
from app.services.airport_service import seed_airports
from app.services.patrol import run_patrol

log = logging.getLogger("skyroute.worker")

TICK_SECONDS = 60


async def patrol(container: Container, due_only: bool) -> None:
    s = container.settings
    try:
        await run_patrol(
            container.patrol_context(),
            container.cache,
            s.patrol_consumers,
            s.patrol_lock_ttl_s,
            due_only=due_only,
        )
    except Exception:  # 單次巡檢失敗不可讓常駐排程停止
        log.exception("巡檢執行失敗，下一分鐘再試")


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
            await patrol(container, due_only=False)
        if not once:
            log.info("巡檢排程啟動：每 %d 秒檢查一次到期的追蹤", TICK_SECONDS)
        while not once and not stop.is_set():
            await patrol(container, due_only=True)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
    finally:
        await container.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SkyRoute 背景巡檢 Worker")
    parser.add_argument("--once", action="store_true", help="巡檢全部追蹤一次後結束")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve(get_settings(), args.once))


if __name__ == "__main__":
    main()
