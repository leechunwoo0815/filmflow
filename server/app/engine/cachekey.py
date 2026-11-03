"""缓存键与门 content_hash（规格 §5.3）。

缓存键 = sha256(executorVersion | params | inputs.artifactSha | caps)
审批时间/审批人不进缓存键。门键 = 输入 content_hash。
"""
from __future__ import annotations

import hashlib
import json

EXECUTOR_VERSION = "2.9.3"  # P0-2 转场映射统一；P1-02/03/04 缓存键补齐外部/引擎/音频输入


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def node_cache_key(node_id: str, executor_version: str, params: dict,
                   input_hashes: dict[str, str], caps: list[str],
                   doc_snapshot_sha: str = "") -> str:
    payload = {
        "node": node_id,
        "executorVersion": executor_version,
        "params": params,
        "inputs": dict(sorted(input_hashes.items())),
        "caps": sorted(caps),
        "docSnapshotSha": doc_snapshot_sha,
    }
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def gate_content_hash(node_id: str, params: dict, input_hashes: dict[str, str]) -> str:
    payload = {"gate": node_id, "params": params, "inputs": dict(sorted(input_hashes.items()))}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    import pathlib
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
