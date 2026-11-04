"""资源锁管理（规格 §5.2）：chrome-queue=1 / ffmpeg=1 / 帧服务端口锁 / disk。

规格把帧服务端口钉在 8787；2026-11-05 起端口可被 `FILMFLOW_FRAME_PORT` 覆盖
（默认仍是 8787，规格端口不偏离），锁名跟着端口走——节点表里写的 `"port-8787"`
在 acquire/holders/release 处统一归一化成 `port-<实际端口>`，规格语义不变。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


def frame_port_lock_name() -> str:
    from ..config import settings
    return f"port-{settings.frame_port}"


def normalize_lock(name: str) -> str:
    """节点表（edges.py）按规格写死 `"port-8787"`；实际锁名跟 `settings.frame_port` 走。"""
    if name == "port-8787":
        return frame_port_lock_name()
    return name


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
            frame_port_lock_name(): 1,
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
        return set(self._holders.get(normalize_lock(name), set()))

    async def acquire(self, name: str, holder: str) -> float:
        """获取锁，返回等待秒数（供甘特图记录 lock_wait）。"""
        name = normalize_lock(name)
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
        name = normalize_lock(name)
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
