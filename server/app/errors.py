"""错误码枚举与统一错误信封（规格 §2.2 / tech-plan §2.2）。"""
from __future__ import annotations

from fastapi import HTTPException


class ErrorCode:
    E_PHASE_FORBIDDEN = "E_PHASE_FORBIDDEN"
    E_PHASE_MISMATCH = "E_PHASE_MISMATCH"
    E_ENGINE_UNAVAILABLE = "E_ENGINE_UNAVAILABLE"
    E_MODEL_MISSING = "E_MODEL_MISSING"
    E_ENV_MISSING = "E_ENV_MISSING"
    E_PORT_BUSY = "E_PORT_BUSY"
    E_DISK_FULL = "E_DISK_FULL"
    E_VALIDATION = "E_VALIDATION"
    E_NOT_FOUND = "E_NOT_FOUND"
    E_CONFLICT = "E_CONFLICT"
    E_STYLE_INCOMPLETE = "E_STYLE_INCOMPLETE"
    # R2.0
    E_PROGRAM_INVALID = "E_PROGRAM_INVALID"
    E_ENGINE_API_UNSUPPORTED = "E_ENGINE_API_UNSUPPORTED"
    E_COMPONENT_UNKNOWN = "E_COMPONENT_UNKNOWN"
    E_DOC_CONFLICT = "E_DOC_CONFLICT"
    E_DOC_SCHEMA = "E_DOC_SCHEMA"
    E_DOC_READONLY = "E_DOC_READONLY"
    E_FINAL_REQUIRED = "E_FINAL_REQUIRED"
    E_PREVIEW_BUSY = "E_PREVIEW_BUSY"
    E_SCENE_FAILED = "E_SCENE_FAILED"
    E_JOB_LEASE_LOST = "E_JOB_LEASE_LOST"
    E_LICENSE_MISSING = "E_LICENSE_MISSING"


class ApiError(HTTPException):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(status_code=status, detail={"code": code, "message": message, "details": details or {}})


def not_found(what: str) -> ApiError:
    return ApiError(ErrorCode.E_NOT_FOUND, f"{what} 不存在", status=404)
