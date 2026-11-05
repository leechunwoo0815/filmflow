"""A7：`jobs.expire_parked` 的真实演练（隔离 FILMFLOW_HOME，零生产接触）。

为什么不在生产库上练：那 7 条 retry_wait 是「等人工门」的正常态、不许动，而且
job#85 的心跳距 72h 红线只剩约 2 小时——在生产库上跑这个函数随时会误收保护作业。
本脚本起**隔离实例**（独立 FILMFLOW_HOME/DB；TestClient 走真实 API 与真实启动
路径），在自建 scratch 项目上：

  1) 跑到 B08 人工门 → 作业 park 成 retry_wait（「等人工门」的正常态）；
  2) 把该作业心跳拨老 73h（直接 SQL，隔离库无备份仪式）；
  3) 真调 `jobs.expire_parked()`（72h 默认）→ 断言**只收我这一条**、
     canceled + `E_JOB_EXPIRED`，其余作业分毫不动；
  4) 签门 + `POST /runs/{id}/start` → 断言作业按 `ensure_run_job` 重建（可恢复性）。

用法：`uv run --project server python scripts/verify_expire_parked.py`
"""
from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlmodel import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

_HOME = Path(tempfile.mkdtemp(prefix="ff-expire-drill-"))
os.environ["FILMFLOW_HOME"] = str(_HOME)      # 必须先于任何 app.* 导入
# 项目根白名单也指到隔离家目录（否则 materialize 会被「根必须在白名单内」拒绝；
# 隔离实例登记自己的根，生产实例的白名单不受影响）
os.environ["FILMFLOW_WORKSPACE_ROOTS"] = str(_HOME)

from _acceptance import destroy
from app.db import engine
from app.main import app
from app.services import jobs as jobs_svc

DB = _HOME / "filmflow.db"
COPY = "风从纸上起。纸不动，风先动。"
PROFILE = {"width": 1920, "height": 1080, "fps": 24, "duration": 5.0}


def _db(sql: str, args: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(DB)
    try:
        rows = list(con.execute(sql, args))
        con.commit()          # DML 不 commit 会在 close 时被隐式事务回滚
        return rows
    finally:
        con.close()


def _serve_isolated() -> tuple[object, int, threading.Thread]:
    """隔离实例 = 本进程内的真实 uvicorn 线程（TestClient 的 per-request portal
    没有持久事件循环，start_run 的 Run 任务永远不推进——实测 180s 都到不了 B08）。"""
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    return server, port, th


def main() -> int:
    t0 = time.time()
    server, port, th = _serve_isolated()
    # Host 必须是 127.0.0.1（P0-1 Host 校验）、写请求必须带合法 Origin（跨源写 403）
    c = httpx.Client(base_url=f"http://127.0.0.1:{port}/api", timeout=60, trust_env=False,
                     headers={"Origin": "http://127.0.0.1:3000"})
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if c.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        else:
            raise SystemExit("隔离实例 30s 未就绪")
        # 隔离库没有风格索引（{home}/index/style-index.json 是 HOME 相对的）——
        # 用真实 builder 现建一份，再取可生产风格
        from app.services import style_index
        style_index.scan_library()
        styles = c.get("/styles", params={"chips": "可生产", "family": "print", "limit": 5}).json()
        assert styles.get("items"), f"隔离实例里没有可生产风格：{styles}"
        primary = styles["items"][0]["id"]

        d = c.post("/drafts", json={"name": "a7-expire-drill", "step": 1}).json()
        root = _HOME / "projects" / f"a7-expire-drill-{d['id']}"
        root.mkdir(parents=True, exist_ok=True)
        c.patch(f"/drafts/{d['id']}", json={"step": 5, "payload": {
            "root": str(root), "copy": COPY, "profile": PROFILE,
            "pick": {"primary": primary, "alternates": [], "reason": "a7-drill"},
            "brief": {"title": "A7 过期回收演练"}}})
        mat = c.post(f"/drafts/{d['id']}/materialize", json={}).json()
        rid, pid = int(mat["run_id"]), int(mat["project"]["id"])
        print(f"scratch 项目 {pid}（{root.name}）/ run {rid}", flush=True)
        r = c.post(f"/runs/{rid}/start")
        assert r.status_code == 200, f"start_run 失败：{r.status_code} {r.text[:200]}"

        # 1) 跑到 B08 人工门 → 作业 park
        deadline = time.time() + 180
        while time.time() < deadline:
            pending = c.get(f"/gates/{rid}/pending").json().get("items", [])
            if any(p["gate"] == "B08" for p in pending):
                break
            st = {n["id"]: n["status"] for n in c.get(f"/runs/{rid}/graph").json()["nodes"]}
            assert st.get("A01") not in ("failed",), st
            time.sleep(1)
        else:
            raise SystemExit(f"180s 内没到 B08 门：{pending}")
        # 门标记与作业置 retry_wait 之间有几毫秒差——轮询到 park 为止
        deadline2 = time.time() + 15
        while time.time() < deadline2:
            jobs = _db("select id, status from job where run_id=?", (rid,))
            if jobs and jobs[0][1] == "retry_wait":
                break
            time.sleep(0.2)
        assert len(jobs) == 1 and jobs[0][1] == "retry_wait", \
            f"到门后作业应 park 成 retry_wait，实际 {jobs}"
        jid = int(jobs[0][0])
        print(f"✓ 1) B08 待批，作业 {jid} park 成 retry_wait", flush=True)

        before = _db("select id from job where status='retry_wait'")
        assert [x[0] for x in before] == [jid], f"隔离库里应只有这一条 parked：{before}"

        # 2) 心跳拨老 73h（隔离库）
        aged = (datetime.now(UTC) - timedelta(hours=73)).strftime("%Y-%m-%d %H:%M:%S.%f")
        _db("update job set heartbeat_at=? where id=?", (aged, jid))

        # 3) 真调 expire_parked（72h 默认）——只许收我这一条
        with Session(engine) as s:
            expired = jobs_svc.expire_parked(s)
        assert expired == [jid], f"应且仅应回收本演练作业 {jid}，实际 {expired}"
        status, code = _db("select status, error_code from job where id=?", (jid,))[0]
        assert status == "canceled" and code == "E_JOB_EXPIRED", (status, code)
        remaining = _db("select id from job where status='retry_wait'")
        print(f"✓ 3) expire_parked 收走作业 {jid}：canceled / E_JOB_EXPIRED"
              f"（其余 retry_wait：{len(remaining)} 条）", flush=True)

        # 4) 签门 + start_run → 作业按 ensure_run_job 重建
        r = c.post("/gates/B08/decide", json={"runId": rid, "decision": "approved",
                                              "author": "a7-drill"})
        assert r.status_code == 200, r.text
        r = c.post(f"/runs/{rid}/start")
        assert r.status_code == 200, r.text
        deadline = time.time() + 30
        while time.time() < deadline:
            rows = _db("select id, status from job where run_id=? and id<>?", (rid, jid))
            if rows:
                break
            time.sleep(1)
        assert rows, "签门 + start_run 后必须重建作业（ensure_run_job）"
        print(f"✓ 4) 作业重建：新作业 {rows[0][0]}（{rows[0][1]}）≠ 被收的 {jid}", flush=True)

        destroy(c, pid, root)
        print(f"  已自删 scratch 项目 {pid}", flush=True)
    finally:
        c.close()
        server.should_exit = True
        th.join(timeout=10)
    shutil.rmtree(_HOME, ignore_errors=True)
    print(f"PASS: expire_parked 真实演练（隔离实例 {_HOME.name}，wall {time.time() - t0:.1f}s，"
          f"生产库零接触）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
