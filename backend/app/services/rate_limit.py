"""非同步令牌桶：限制對第三方 API 的呼叫頻率。"""

import asyncio
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self,
        rate_per_s: float,
        capacity: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_s <= 0 or capacity < 1:
            raise ValueError("rate_per_s 必須 > 0，capacity 必須 >= 1")
        self._rate = rate_per_s
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._clock = clock
        self._updated = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
        self._updated = now

    def try_acquire(self) -> bool:
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    async def acquire(self) -> None:
        """取得一個令牌；令牌不足時等待補充（序列化等待者，避免搶奪）。"""
        async with self._lock:
            # 等待的是「時間經過」而非事件，因此以 sleep 計算令牌補充時間
            while not self.try_acquire():  # noqa: ASYNC110
                await asyncio.sleep((1 - self._tokens) / self._rate)
