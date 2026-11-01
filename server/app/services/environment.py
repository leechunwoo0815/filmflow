"""环境断言（规格 §11.1 / test-strategy §6）：Chrome/ffmpeg/whisper/风格库。缺失 → E_ENV_MISSING。"""
from __future__ import annotations

from ..config import detect_chrome, detect_ffmpeg, detect_whisper_cli, settings


def assert_environment(require_whisper: bool = False) -> dict:
    report = {
        "chrome": detect_chrome(),
        "ffmpeg": detect_ffmpeg(),
        "whisper_cli": detect_whisper_cli(),
        "style_library": str(settings.style_library_root),
        "style_library_exists": settings.style_library_root.is_dir(),
        "db": str(settings.db_path),
    }
    missing = [k for k in ("chrome", "ffmpeg") if not report[k]]
    if require_whisper and not report["whisper_cli"]:
        missing.append("whisper_cli")
    if not report["style_library_exists"]:
        missing.append("style_library")
    if missing:
        from ..errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.E_ENV_MISSING, f"环境缺失：{missing}", details=report)
    return report
