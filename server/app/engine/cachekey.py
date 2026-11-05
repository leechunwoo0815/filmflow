"""缓存键与门 content_hash（规格 §5.3）。

缓存键 = sha256(executorVersion | params | inputs.artifactSha | caps)
审批时间/审批人不进缓存键。门键 = 输入 content_hash。
"""
from __future__ import annotations

import hashlib
import json

EXECUTOR_VERSION = "2.16.0"  # B2/P2-12：mix 与 Take 两遍 loudnorm（实测回灌 linear）+ f04 成片 bt709 色彩标签
# 2.15.0：P2-02/P2-03 节点 timeout/retries 强制执行 + 同项目 Run 互斥（调度行为变化）
# 2.14.0：帧服务端口可配置（FILMFLOW_FRAME_PORT，默认仍 8787）+ 快照补 caps/params
# 2.13.0：C02 字体下载加 sha 钉 + 报告记 pinMatches，旧缓存自动失效
# 2.12.0：帧/program/manifest/快照落盘改唯一临时名 + fsync + os.replace（app/atomicwrite），
# 崩溃不再留下被当成有效产物的半文件；读取路径不变，但产物写入行为变了，必须升版。


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
