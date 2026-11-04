"""判官 P0-1：删除面必须删不到白名单根 / git 仓库 / 回归基线（HTTP 路由级）。"""
from __future__ import annotations

import uuid


def _create(client, name: str, root):
    return client.post("/projects", json={"name": name, "root": str(root)})


def test_cannot_register_workspace_root(api_client, isolated_api):
    _base, workspace = isolated_api
    r = _create(api_client, "root-probe", workspace)
    assert r.status_code == 400, r.text
    assert "不能作为项目根" in r.text, r.text


def test_cannot_register_git_repo(api_client, isolated_api):
    _base, workspace = isolated_api
    repo = workspace / f"gitrepo-{uuid.uuid4().hex[:6]}"
    (repo / ".git").mkdir(parents=True)
    r = _create(api_client, "repo-probe", repo)
    assert r.status_code == 400, r.text
    assert "git 仓库" in r.text, r.text


def test_delete_without_confirm_deletes_nothing(api_client, project_root):
    created = _create(api_client, "delete-probe-1", project_root)
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["id"]
    plan = api_client.delete(f"/projects/{pid}")
    assert plan.status_code == 200
    body = plan.json()
    assert body["warning"].startswith("这是级联删除")
    assert body["dirDeletable"] is True and body["protected"] is False
    assert api_client.get(f"/projects/{pid}/docs").status_code == 200


def test_protected_name_requires_confirm_name(api_client, isolated_api):
    _base, workspace = isolated_api
    root = workspace / f"rumorprobe-{uuid.uuid4().hex[:6]}"
    root.mkdir()
    pid = _create(api_client, "rumor-probe", root).json()["project"]["id"]
    denied = api_client.delete(f"/projects/{pid}", params={"confirm": "true"})
    assert denied.status_code == 409, denied.text
    assert "confirm_name" in denied.text, denied.text
    assert api_client.get(f"/projects/{pid}/docs").status_code == 200  # 未被删
    allowed = api_client.delete(f"/projects/{pid}",
                                params={"confirm": "true", "confirm_name": "rumor-probe"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["deleted"] == pid
    assert api_client.get(f"/projects/{pid}/docs").status_code == 404


def test_delete_removes_rows_and_dir(api_client, isolated_api):
    _base, workspace = isolated_api
    root = workspace / f"plaindel-{uuid.uuid4().hex[:6]}"
    root.mkdir()
    pid = _create(api_client, "plain-delete", root).json()["project"]["id"]
    res = api_client.delete(f"/projects/{pid}", params={"confirm": "true"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dirRemoved"] is True and not root.exists()
    assert api_client.get(f"/projects/{pid}/docs").status_code == 404
