"""首次使用的默认对齐段：音频页在无已存对齐时给「场景窗口 + 场景文本」。

为什么必须是产品能力：对齐段 text 为空 ⇒ 交付字幕 QC 必挂（SRT count=0，
2026-11-07 attempt 14 实测，此前只有 e2e 脚本会回填）；段 [start,end]=场景窗口
天然满足 G06 音画同步（恒等式 last_text_at+read_seconds ≡ end）。这是纯 UI
用户走通「生成 → 交付」的前提，不该依赖脚本。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".."))

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.models import Project, Workflow
from app.services import project_docs as docs
from app.services.project_cleanup import delete_project


def test_default_alignment_carries_scene_text_and_windows(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "workspace_roots_raw", str(tmp_path))
    root = tmp_path / "align-default"
    (root / "card").mkdir(parents=True)
    session = Session(engine)
    p = Project(name="align-default", root=str(root))
    session.add(p)
    session.commit()
    session.refresh(p)
    session.add(Workflow(project_id=p.id, graph_json={"nodes": [], "edges": []}))
    session.commit()
    pid = p.id
    try:
        docs.save_doc(session, pid, "script",
                      {"schema": "filmflow.script/1", "text": "增长三倍是真相吗。", "title": "t",
                       "sentences": [{"id": "L001", "text": "增长三倍是真相吗。",
                                      "source_span": [0, 9]}]},
                      0, "seed")
        docs.save_doc(session, pid, "timeline",
                      {"schema": "filmflow.timeline/2", "fps": 24, "duration": 2.0, "frames": 48,
                       "scenes": [{"id": "S01", "start": 0.0, "end": 2.0,
                                   "last_text_at": 0.0, "read_seconds": 2.0,
                                   "source_span": [0]}]},
                      0, "seed")

        with TestClient(app, base_url="http://127.0.0.1/api",
                        headers={"Origin": "http://127.0.0.1:3000"}) as c:
            data = c.get(f"/projects/{pid}/audio").json()
            segs = data["alignment"]["segments"]
            assert segs and segs[0]["text"] == "增长三倍是真相吗。", segs
            assert (segs[0]["start"], segs[0]["end"]) == (0.0, 2.0), segs[0]
            assert data["alignment"]["source"] == "default", "未落库的默认段不许冒充 manual"

            # 用户点「保存手动对齐」→ 落库带文本（G02 与交付字幕的数据源）
            saved = c.post(f"/projects/{pid}/audio/alignment",
                           json={"segments": segs, "author": "audio-ui"}).json()
            assert saved["segments"][0]["text"] == "增长三倍是真相吗。"
            again = c.get(f"/projects/{pid}/audio").json()["alignment"]
            assert again["source"] == "manual"
            assert again["segments"][0]["text"] == "增长三倍是真相吗。"
    finally:
        session.rollback()
        session.close()
        delete_project(Session(engine), pid, remove_dir=True)
