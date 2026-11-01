"""资源锁管理（规格 §5.2）：chrome-queue=1 / ffmpeg=1 / port-8787 / disk。"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class LockStats:
    name: str
    waiters: int = 0
    total_wait_s: float = 0.0
    acquisitions: int = 0


class LockManager:
    def __init__(self, limits: dict[str, int] | None = None):
        self.limits = limits or {
            "chrome-queue": 1,   # Chrome 全局串行（规格 §5.2）
            "ffmpeg": 1,
            "port-8787": 1,
        }
        self._sem: dict[str, asyncio.Semaphore] = {
            k: asyncio.Semaphore(v) for k, v in self.limits.items()
        }
        self._stats: dict[str, LockStats] = {k: LockStats(k) for k in self.limits}
        self._holders: dict[str, set[str]] = {k: set() for k in self.limits}

    @property
    def stats(self) -> list[LockStats]:
        return list(self._stats.values())

    def holders(self, name: str) -> set[str]:
        return set(self._holders.get(name, set()))

    async def acquire(self, name: str, holder: str) -> float:
        """获取锁，返回等待秒数（供甘特图记录 lock_wait）。"""
        sem = self._sem.get(name)
        if sem is None:
            raise KeyError(f"未知锁 {name}")
        st = self._stats[name]
        st.waiters += 1
        t0 = time.monotonic()
        try:
            await sem.acquire()
        finally:
            st.waiters -= 1
        waited = time.monotonic() - t0
        st.total_wait_s += waited
        st.acquisitions += 1
        self._holders.setdefault(name, set()).add(holder)
        return waited

    def release(self, name: str, holder: str) -> None:
        self._holders.get(name, set()).discard(holder)
        self._sem[name].release()

    async def check_disk(self, path: str, min_gb: float = 5.0) -> None:
        """F02 写帧前磁盘检查（规格 §5.2）。"""
        import shutil
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1 << 30)
        if free_gb < min_gb:
            from ..errors import ApiError, ErrorCode
            raise ApiError(ErrorCode.E_DISK_FULL, f"磁盘剩余 {free_gb:.1f}GB < {min_gb}GB")
