"""子进程执行壳（规格 §5）：spawn 非 shell、NDJSON @@PROGRESS 解析、SIGTERM→5s→SIGKILL。"""
from __future__ import annotations

import asyncio
import json
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

ProgressCB = Callable[[float, str], Awaitable[None]]


@dataclass
class RunResult:
    exit_code: int | None
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)
    timed_out: bool = False
    canceled: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.canceled


def parse_progress_line(line: str) -> tuple[float, str] | None:
    """解析 @@PROGRESS {"pct":0.42,"msg":"frame 400/948"}（规格 §5 契约）。"""
    s = line.strip()
    if not s.startswith("@@PROGRESS "):
        return None
    try:
        d = json.loads(s[len("@@PROGRESS "):])
        return float(d.get("pct", 0.0)), str(d.get("msg", ""))
    except (json.JSONDecodeError, ValueError):
        return None


class ProcessRunner:
    """真实子进程执行器外壳。禁 shell 拼接（规格 §11）。"""

    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._proc: asyncio.subprocess.Process | None = None
        self._cancel_requested = False
        self._stdout_buf: list[str] = []
        self._stderr_buf: list[str] = []
        self._log_files: dict[str, object] = {}

    def _open_log(self, name: str):
        if name not in self._log_files:
            self._log_files[name] = (self.workdir / f"{name}.log").open("ab")
        return self._log_files[name]

    def _tail(self, buf: list[str], line: str) -> None:
        buf.append(line)
        if len(buf) > 200:  # 规格 §5：保留尾部 200 行
            buf.pop(0)

    async def _pump(self, stream, buf: list[str], logname: str,
                    on_progress: ProgressCB | None = None) -> None:
        log = self._open_log(logname)
        while True:
            raw = await stream.readline()
            if not raw:
                break
            try:
                line = raw.decode("utf-8", "replace").rstrip("\n")
            except Exception:
                continue
            self._tail(buf, line)
            log.write((line + "\n").encode("utf-8"))
            log.flush()
            if on_progress:
                p = parse_progress_line(line)
                if p:
                    await on_progress(p[0], p[1])

    async def run(self, argv: list[str], *, env: dict | None = None,
                  timeout: float = 60.0, on_progress: ProgressCB | None = None,
                  on_line: Callable[[str, str], Awaitable[None]] | None = None,
                  cancel_event: asyncio.Event | None = None) -> RunResult:
        self._stdout_buf, self._stderr_buf = [], []
        self._cancel_requested = False
        full_env = {**os.environ, **(env or {})}
        self._proc = await asyncio.create_subprocess_exec(
            *argv, cwd=str(self.workdir), env=full_env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        async def forward(buf, name):
            if on_line:
                for ln in buf:
                    await on_line(name, ln)
        tasks = [
            asyncio.create_task(self._pump(self._proc.stdout, self._stdout_buf, "stdout", on_progress)),
            asyncio.create_task(self._pump(self._proc.stderr, self._stderr_buf, "stderr")),
            asyncio.create_task(self._watch_cancel(cancel_event)),
        ]
        timed_out = False
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=timeout if timeout > 0 else None)
        except asyncio.TimeoutError:
            timed_out = True
            await self._terminate()
        if self._cancel_requested and self._proc.returncode is None:
            await self._terminate()
        await asyncio.gather(*tasks, return_exceptions=True)
        for f in self._log_files.values():
            f.close()
        self._log_files.clear()
        return RunResult(
            exit_code=self._proc.returncode,
            stdout_tail=list(self._stdout_buf),
            stderr_tail=list(self._stderr_buf),
            timed_out=timed_out,
            canceled=self._cancel_requested,
        )

    async def _watch_cancel(self, cancel_event: asyncio.Event | None) -> None:
        if cancel_event is None:
            return
        await cancel_event.wait()
        self._cancel_requested = True
        await self._terminate()

    async def _terminate(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        except ProcessLookupError:
            pass
