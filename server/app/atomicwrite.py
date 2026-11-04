"""原子落盘：唯一临时名 + fsync + os.replace，避免半文件被读者当成有效产物。

`Path.write_text()` 直写目标路径时，崩溃/并发会留下 0 字节或截断文件，而渲染链上的
判据多为 `path.exists()`（F03 收帧、快照读取、交付包），于是"半张帧"会被当成好帧编码进片子里。
`with_suffix(".tmp")` 也不安全：同一目标并发的两个写者会互相踩临时名。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path


def _fsync_dir(d: Path) -> None:
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:  # 某些文件系统不支持目录 fsync；rename 本身仍是原子的
        pass
    finally:
        os.close(fd)


def write_atomic(path: str | Path, data: bytes | str, *, encoding: str = "utf-8") -> Path:
    """写 `path`：临时名唯一，写完 fsync 再 rename，最后 fsync 父目录。"""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode(encoding) if isinstance(data, str) else data
    tmp = dst.parent / f".{dst.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)
        _fsync_dir(dst.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dst


def prune_tmp(dirs: list[Path], *, older_than_s: int = 3600) -> int:
    """清掉崩溃遗留的 `. *.tmp`（只删本模块命名形态，且够老的），返回删除数。"""
    cutoff = older_than_s
    removed = 0
    import time

    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob(".*.tmp"):
            try:
                if time.time() - f.stat().st_mtime > cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
    return removed
