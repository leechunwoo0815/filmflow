"""服务级日志（P2-28）：此前 server/app 零 logging——节点失败、作业 park、
交付成败、删除面动作只活在 DB/响应里，排障只能翻 stdout。

口径：logger 名统一 `filmflow.<域>`；输出 stderr + `~/.filmflow/logs/app.log`
（RotatingFileHandler 5MB × 3）。级别 `FILMFLOW_LOG_LEVEL`（默认 INFO）。
幂等：重复调用不会叠加 handler（uvicorn reload / 多次 import 安全）。
"""
from __future__ import annotations

import logging
import logging.handlers
import os

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    from .config import settings

    level = getattr(logging, os.environ.get("FILMFLOW_LOG_LEVEL", "INFO").upper(),
                    logging.INFO)
    root = logging.getLogger("filmflow")
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    try:
        settings.ensure_dirs()
        file_handler = logging.handlers.RotatingFileHandler(
            settings.home / "logs" / "app.log", maxBytes=5 * 1024 * 1024,
            backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:                       # 日志文件打不开不能挡服务启动
        root.warning("app.log 不可写，只输出到 stderr")
    root.propagate = False
    _CONFIGURED = True


def get(name: str) -> logging.Logger:
    """用 `filmflow.<name>` 取子 logger（setup_logging 之前调用也能用，只是先没输出端）。"""
    setup_logging()
    return logging.getLogger(f"filmflow.{name}")
