"""FilmFlow 服务端配置。所有路径默认值集中在这里，运行时可被环境变量覆盖。"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_style_library() -> Path:
    return Path.home() / "Documents" / "fy-style-library" / "代码动画_341种风格提示词"


def _parse_workspace_roots(value: str | list[str] | list[Path]) -> list[Path]:
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            parts = json.loads(s)
        else:
            parts = [part.strip() for part in re.split(r"[:,;\n]", s) if part.strip()]
        return [Path(p) for p in parts]
    return [Path(p) for p in value]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILMFLOW_", env_file=None)

    host: str = "127.0.0.1"
    port: int = 7860
    frame_port: int = 8787          # F01 帧服务（规格硬约束 8787）
    # P2-32：帧服务进程内随机 token（引擎 URL 以 ?tok= 携带）。绑定 127.0.0.1 之外
    # 再加一道口令：本机其它用户的进程、以及"端口被别的进程占了"的场景都无法冒用。
    frame_token: str = Field(default_factory=lambda: __import__("secrets").token_urlsafe(24))

    home: Path = Path.home() / ".filmflow"
    # 允许登记项目根的目录白名单（规格 §2.3 / §11）
    workspace_roots_raw: str = Field(
        default_factory=lambda: str(Path.home() / "cc-projects" / "ai-v"),
        validation_alias=AliasChoices("FILMFLOW_WORKSPACE_ROOTS", "FILMFLOW_WORKSPACE_ROOTS_RAW"),
    )

    style_library_root: Path = _default_style_library()

    whisper_model: str = "ggml-medium"       # ADR-0001：medium 档
    chrome_queue_limit: int = 1              # Chrome 全局串行（规格 §5.2）
    analysis_concurrency: int = 2            # 纯分析节点并发（规格 §9.3）

    @property
    def workspace_roots(self) -> list[Path]:
        return _parse_workspace_roots(self.workspace_roots_raw)

    @property
    def db_path(self) -> Path:
        return self.home / "filmflow.db"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    @property
    def assets_dir(self) -> Path:
        return self.home / "assets"

    @property
    def index_path_fallback(self) -> Path:
        """风格库目录不可写时索引的回落位置。"""
        return self.home / "index" / "style-index.json"

    def ensure_dirs(self) -> None:
        for d in (self.home, self.logs_dir, self.cache_dir, self.cache_dir / "previs",
                  self.assets_dir):
            d.mkdir(parents=True, exist_ok=True)


def detect_chrome() -> str | None:
    """CHROME_PATH 环境变量优先，其次常见安装位置（规格 §11.1）。"""
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    if sys.platform == "linux":
        candidates += ["/usr/bin/google-chrome", "/usr/bin/chromium-browser"]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def detect_ffmpeg() -> str | None:
    p = shutil.which("ffmpeg")
    return p


def detect_whisper_cli() -> str | None:
    """whisper.cpp CLI（brew: whisper-cpp → whisper-cli）。"""
    for name in ("whisper-cli", "whisper-cpp", "main"):
        p = shutil.which(name)
        if p and "whisper" in Path(p).name or (p and name == "whisper-cli"):
            return p
    return None


settings = Settings()
settings.ensure_dirs()
