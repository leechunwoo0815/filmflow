"""产物内容寻址存储（规格 §10）：artifacts/<sha前2>/<sha>.<ext>，DB 只存指针。"""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlmodel import Session

from ..engine.cachekey import bytes_sha256, file_sha256
from ..models import Artifact

EXT_BY_TYPE = {"PNG": "png", "MP4": "mp4", "JSON": "json", "WOFF2": "woff2", "CSS": "css",
               "ZIP": "zip", "WAV": "wav", "TXT": "txt", "MD": "md", "FRAME": "png"}


def project_artifacts_dir(project_root: str) -> Path:
    d = Path(project_root) / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_bytes(project_root: str, data: bytes, type_: str) -> tuple[Path, str]:
    sha = bytes_sha256(data)
    ext = EXT_BY_TYPE.get(type_, "bin")
    dst = project_artifacts_dir(project_root) / sha[:2] / f"{sha}.{ext}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        dst.write_bytes(data)
    return dst, sha


def store_file(project_root: str, src: Path, type_: str) -> tuple[Path, str]:
    sha = file_sha256(str(src))
    ext = EXT_BY_TYPE.get(type_, src.suffix.lstrip(".") or "bin")
    dst = project_artifacts_dir(project_root) / sha[:2] / f"{sha}.{ext}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst, sha


def register(session: Session, run_id: int, node_run_id: int | None, node_id: str,
             type_: str, path: str, sha256: str, meta: dict | None = None) -> Artifact:
    a = Artifact(run_id=run_id, node_run_id=node_run_id, node_id=node_id, type=type_,
                 path=str(path), sha256=sha256, bytes=Path(path).stat().st_size,
                 meta_json=meta or {})
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def node_output_hashes(session: Session, run_id: int, node_id: str) -> dict[str, str]:
    """节点全部产物 sha（作为下游缓存键的 inputs.artifactSha）。"""
    rows = session.exec(
        select(Artifact).where(Artifact.run_id == run_id, Artifact.node_id == node_id)  # type: ignore[arg-type]
    ).all()
    return {f"{i}": r.sha256 for i, r in enumerate(sorted(rows, key=lambda x: (x.type, x.path)))}
