"""引擎包注册表（T04 / 规格 §3.3）：扫描 engines/*/contract.json，校验 Contract。"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..errors import ApiError, ErrorCode
from ..engine.cachekey import bytes_sha256

REQUIRED_CONTRACT_FIELDS = ["engine_id", "families", "version", "entry", "capabilities", "fixtures"]
REQUIRED_ENTRIES = ["still", "film"]

_contract_cache: dict[str, dict] = {}


def engines_root() -> Path:
    """引擎包根：优先仓库根 engines/，其次项目内 engines/。"""
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "engines"


def load_contract(engine_id: str) -> dict:
    if engine_id in _contract_cache:
        return _contract_cache[engine_id]
    path = engines_root() / engine_id / "contract.json"
    if not path.exists():
        raise ApiError(ErrorCode.E_NOT_FOUND, f"引擎包 {engine_id} 未登记", status=404)
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract, engines_root() / engine_id)
    _contract_cache[engine_id] = contract
    return contract


def validate_contract(contract: dict, pack_root: Path) -> None:
    """缺字段或 entry 文件缺失 → 拒绝登记（bdd engine-registry 场景 1）。"""
    missing = [f for f in REQUIRED_CONTRACT_FIELDS if f not in contract]
    if missing:
        raise ApiError(ErrorCode.E_VALIDATION, f"Engine Contract 缺字段：{missing}")
    for e in REQUIRED_ENTRIES:
        if e not in contract["entry"]:
            raise ApiError(ErrorCode.E_VALIDATION, f"entry 缺 {e}")
    for e, rel in contract["entry"].items():
        base = rel.split("?")[0]
        if not (pack_root / base).exists():
            raise ApiError(ErrorCode.E_VALIDATION, f"entry 文件不存在：{base}")
    for fx in contract.get("fixtures", []):
        p = pack_root / fx.split("?")[0]
        if not p.exists():
            raise ApiError(ErrorCode.E_VALIDATION, f"fixture 不存在：{fx}")


def compute_pack_sha(engine_id: str) -> str:
    root = engines_root() / engine_id
    h = __import__("hashlib").sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".sha" not in p.name:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def list_engines() -> list[dict]:
    out = []
    root = engines_root()
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not (d / "contract.json").exists():
            continue
        try:
            c = load_contract(d.name)
            out.append({**c, "sha256": compute_pack_sha(d.name), "path": str(d)})
        except ApiError as e:
            out.append({"engine_id": d.name, "available": False, "error": e.detail["message"]})
    return out


def engine_for_family(family: str) -> dict | None:
    """族 → 引擎（规格 §3.3：同一引擎可服务多个族，必须声明）。"""
    for c in list_engines():
        if family in (c.get("families") or []):
            return c
    return None


def refresh_style_engine_status() -> None:
    """引擎注册变化后刷新 styles.engine_status / preview_status。"""
    from sqlmodel import Session, select
    from ..db import engine as db_engine
    from ..models import Style
    with Session(db_engine) as session:
        for st in session.exec(select(Style)).all():
            eng = engine_for_family(st.family)
            st.engine_status = "available" if eng else "unavailable"
            if not st.has_cover:
                st.preview_status = ("previs" if (st.tokens_status == "complete" and eng and st.available)
                                     else st.preview_status if not st.available else "no_preview")
            session.add(st)
        session.commit()


def family_engine_matrix() -> list[dict]:
    """9 语义族 → 引擎可用性（tech-plan §7.2 矩阵）。"""
    from .family_map import FAMILY_LABELS
    engines = list_engines()
    covered: dict[str, str] = {}
    for c in engines:
        for f in c.get("families", []):
            covered[f] = c["engine_id"]
    return [
        {"family": f, "label": FAMILY_LABELS.get(f, f), "engine": covered.get(f), "status": "available" if f in covered else "engine_unavailable"}
        for f in ["print", "collage", "handdrawn", "cartoon", "pixel", "threedee", "photo", "ink", "infographic"]
    ]
