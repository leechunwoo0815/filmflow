"""H3：磁盘/库卫生棘轮的判据单测（孤儿目录 + 僵尸 draft + destroy 回收条件）。

这一族的意义不是"清理动作"，而是**让无声增长变得有声**：11-06 一夜里先漏了一个 65MB 的
孤儿目录 `r3-camera-260`，又漏了 4 条指向已删目录的 draft，两边都是"报告模式没人看"造成的。
所以治理第 18 项是 fail-closed，而它的判据本身必须有单测钉住（判据错了，棘轮就是假绿）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlmodel import Session

SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(SERVER.parent / "scripts"))

from _acceptance import _draft_points_at
from cleanup_projects import hygiene_counts, orphan_dirs

from app.db import engine
from app.models import Draft, Project


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    """把 workspace 根指到 tmp，避免单测扫真实 `~/cc-projects`。"""
    base = tmp_path / "ws" / "filmflow-projects"
    base.mkdir(parents=True)
    import app.config as cfg

    monkeypatch.setattr(type(cfg.settings), "workspace_roots",
                        property(lambda self: [tmp_path / "ws"]), raising=False)
    return base


def _add_project(session: Session, root: Path) -> Project:
    p = Project(name=f"p-{root.name}", root=str(root))
    session.add(p)
    session.commit()
    return p


def test_orphan_dirs_flags_unreferenced_directory(ws):
    """没有 Project 行指向的目录 = 孤儿；登记成行以后就不该再报；`.acceptance` 由第 14 项管。"""
    live = ws / "live-project"
    live.mkdir()
    orphan = ws / "orphan-leftover"
    orphan.mkdir()
    (ws / ".acceptance").mkdir()
    with Session(engine) as s:
        p1 = _add_project(s, live)
        p2 = None
        try:
            assert [d.name for d in orphan_dirs(s)] == ["orphan-leftover"]
            p2 = _add_project(s, orphan)
            assert orphan_dirs(s) == []      # 判据跟着库走，不是跟着目录名猜
        finally:
            for p in (p1, p2):
                if p is not None:
                    s.delete(p)
            s.commit()


def test_zombie_draft_counted_and_named(ws):
    """僵尸 draft 判据 = payload["root"] 指向已不存在的目录；ids 必须能拿去逐条核对。

    断言用**增量**而不是绝对值：unit 库跨测试共享，别的测试也会留下指向已删目录的草稿，
    写死 `== 1` 会随执行顺序飘（单跑绿、全量红）。判据本身照样钉住。
    """
    gone = ws / "deleted-project"
    alive = ws / "still-here"
    with Session(engine) as s:
        before = hygiene_counts(s)          # 基线必须在**造任何东西之前**取，否则增量断言自己骗自己
        alive.mkdir()
        z = Draft(name="僵尸一枚", payload_json={"root": str(gone)})
        keep = Draft(name="还活着", payload_json={"root": str(alive)})
        empty = Draft(name="向导没走完", payload_json={})
        s.add_all([z, keep, empty])
        s.commit()
        try:
            after = hygiene_counts(s)
            assert after["zombieDrafts"] == before["zombieDrafts"] + 1, (before, after)
            assert int(z.id) in after["zombieIds"], after
            assert after["orphanDirs"] == before["orphanDirs"] + 1, after   # still-here 存在但无行指向
            assert "still-here" in after["orphanNames"], after              # gone 只是空路径，不算目录
        finally:
            for d in (z, keep, empty):
                s.delete(d)
            s.commit()


def test_cleanup_track_draft_reclaims_step_one_drafts(ws):
    """H8 实测缺口：向导第 1 步建的草稿 payload 里还没有 root，`destroy()` 的 root 判据永远收不到它。

    `Cleanup.track_draft()` 补的就是这一格——登记过的 id 在退出时必须消失，
    没登记的不能顺手动（那是用户真的想留的 resumable 草稿）。
    """
    sys.path.insert(0, str(SERVER.parent / "scripts"))
    from _acceptance import Cleanup

    with Session(engine) as s:
        mine = Draft(name="脚本自建草稿", payload_json={})
        theirs = Draft(name="用户留着的草稿", payload_json={})
        s.add_all([mine, theirs])
        s.commit()
        ids = (int(mine.id), int(theirs.id))
    try:
        with Cleanup(client=None, keep=False) as clean:
            clean.track_draft(ids[0])
        with Session(engine) as s:
            assert s.get(Draft, ids[0]) is None, "登记过的草稿必须被回收"
            assert s.get(Draft, ids[1]) is not None, "没登记的草稿不许被顺手删掉"
    finally:
        with Session(engine) as s:
            for did in ids:
                d = s.get(Draft, did)
                if d is not None:
                    s.delete(d)
            s.commit()


def test_cleanup_keep_flag_preserves_drafts(ws, capsys):
    """--keep 是"留现场"的语义：草稿也必须留下，不能一边打印保留一边删掉。"""
    sys.path.insert(0, str(SERVER.parent / "scripts"))
    from _acceptance import Cleanup

    with Session(engine) as s:
        d = Draft(name="keep 现场草稿", payload_json={})
        s.add(d)
        s.commit()
        did = int(d.id)
    try:
        with Cleanup(client=None, keep=True) as clean:
            clean.track_draft(did)
        out = capsys.readouterr().out
        assert str(did) in out, out
        with Session(engine) as s:
            assert s.get(Draft, did) is not None, "--keep 却删了草稿就是自相矛盾"
    finally:
        with Session(engine) as s:
            row = s.get(Draft, did)
            if row is not None:
                s.delete(row)
            s.commit()


def test_draft_points_at_covers_nested_and_listed_paths(tmp_path):
    """H3 的回收条件：路径出现在任意深度/任意键都要认出来（防向导以后挪键名）。"""
    root = tmp_path / "scratch-1"
    assert _draft_points_at({"root": str(root)}, root)
    assert _draft_points_at({"draft": {"projectRoot": str(root)}}, root)
    assert _draft_points_at({"history": [{"target": str(root)}]}, root)
    assert _draft_points_at({"root": f"{root}/sub/dir"}, root), "子目录也属于这个项目"


def test_draft_points_at_rejects_other_projects(tmp_path):
    """反向：别的根、空值、以及**前缀相似但不是子目录**的路径不许误命中。

    `/a/scratch-1` 与 `/a/scratch-10` 是典型的 startswith 陷阱——命中就会删掉别人项目的草稿。
    """
    root = tmp_path / "scratch-1"
    assert not _draft_points_at({"root": str(tmp_path / "other")}, root)
    assert not _draft_points_at({"root": str(tmp_path / "scratch-10")}, root)
    assert not _draft_points_at({"root": ""}, root)
    assert not _draft_points_at({"title": "scratch-1 的文案"}, root)
    assert not _draft_points_at({}, root)


def test_item_18_fails_closed_when_something_leaks(ws, monkeypatch):
    """反向验证：真有泄漏时第 18 项必须**变红**，不是打印一行报告就继续跑绿。

    做法是在 tmp 里造一个"目录存在、库里没有行"的孤儿，然后把治理脚本的判据指过来。
    （不动生产库——这条测试只验证判据与抛出行为，生产库面由治理脚本自己实跑。）
    """
    import verify_p1_governance as g

    (ws / "leaked-after-crash").mkdir()
    with pytest.raises(AssertionError, match="孤儿目录"):
        g.check_disk_hygiene()


def test_governance_item_18_is_wired():
    """第 18 项必须在治理脚本里真实存在并调用同源判据，不能只写在文档里。"""
    src = (SERVER.parent / "scripts" / "verify_p1_governance.py").read_text(encoding="utf-8")
    assert 'ok("18 磁盘/库卫生棘轮"' in src, "第 18 项的 ok() 标签丢了——守卫数步数会退回 17"
    assert "check_disk_hygiene()" in src, "第 18 项没有接进 main()"
    assert "hygiene_counts" in src, "第 18 项必须复用 cleanup_projects 的同一份判据"
