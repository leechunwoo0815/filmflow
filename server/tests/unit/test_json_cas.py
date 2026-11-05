"""B1/P2-08：JSON 侧读改写的并发安全——真线程并行，不许顺序模拟。

flock 对同进程不同线程（各开各的 fd）与跨进程都互斥；本测试用 ThreadPoolExecutor
真实并发写路径，断言全部写操作都落盘（零丢失）。修复前：两个客户端都 load v1 再
各自 save，后写覆盖先写——批注/Take 无声丢失。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.services import review_comments as review_svc
from app.services import takes as takes_svc


def test_true_parallel_review_comments_zero_lost_update(tmp_path):
    root = tmp_path
    n_threads, n_each = 4, 25

    def worker(i: int) -> None:
        for k in range(n_each):
            review_svc.add(root, {"sceneId": "S01", "kind": "text", "category": "must",
                                  "body": f"w{i}-{k}", "frame": k, "time": k / 24})

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(worker, range(n_threads)))

    data = review_svc.load(root)
    assert len(data["comments"]) == n_threads * n_each, \
        f"并发丢更新：{len(data['comments'])} != {n_threads * n_each}"
    bodies = {c["body"] for c in data["comments"]}
    assert bodies == {f"w{i}-{k}" for i in range(n_threads) for k in range(n_each)}


def test_true_parallel_takes_updates_no_lost_update(tmp_path):
    root = tmp_path
    for rid in (1, 2, 3, 4):
        takes_svc.update(root, rid, {"name": f"take-{rid}", "score": rid % 6})

    def worker(i: int) -> None:
        takes_svc.update(root, i + 1, {"note": f"n{i}"})
        takes_svc.update(root, (i % 4) + 1, {"score": i})

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(worker, range(4)))

    data = takes_svc.load(root)
    notes = {int(rid): raw.get("note") for rid, raw in data["items"].items()}
    assert all(notes[rid] == f"n{rid - 1}" for rid in (1, 2, 3, 4)), notes
    assert all(raw.get("score") is not None for raw in data["items"].values())
