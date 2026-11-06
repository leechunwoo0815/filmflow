"""H2 防线：本机 httpx 调用**全部**必须显式 `trust_env=False`。

为什么单独一个守卫：F01 类缺陷（`NO_PROXY` 带 IPv6 条目时 httpx 默认客户端解析即炸
`InvalidURL("Invalid port ':1]'")`）只在**进程环境**里出现，作者无代理变量的 shell 永远绿。
原守卫只查 `httpx.Client(` / `httpx.AsyncClient(` 构造器，**漏掉了模块级便捷函数**
`httpx.get/post/head/put/patch/delete/request(options)`——它们内部自己 `Client(...)`，
不带 `trust_env=False` 就吃默认值。实测漏网一处：`scripts/e2e_timeline_100.py` 的
`httpx.get(f"{BASE}/health", timeout=3)`。

本文件用 `ast` 扫源码（不是 grep）：注释/字符串里提 `httpx.get(` 不算违规，真调用才算。
反向验证：把任一处 `trust_env=False` 删掉，本测试必须变红。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCAN_DIRS = ("scripts", "server/app")
CONVENIENCE = {"get", "post", "head", "put", "patch", "delete", "request", "options"}
CTOR = {"Client", "AsyncClient"}


def _calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _httpx_local_clients(tree: ast.AST) -> list[tuple[int, str]]:
    """返回 (行号, 调用名) —— 所有需要 trust_env=False 的 httpx 调用点。"""
    out: list[tuple[int, str]] = []
    for node in _calls(tree):
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        base = fn.value
        if not (isinstance(base, ast.Name) and base.id == "httpx"):
            continue
        name = f"httpx.{fn.attr}"
        if fn.attr not in CTOR and fn.attr not in CONVENIENCE:
            continue
        kwargs = {k.arg for k in node.keywords if k.arg is not None}
        if "trust_env" not in kwargs:
            out.append((node.lineno, name))
    return out


def _sources() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        files.extend(p for p in (ROOT / d).rglob("*.py") if ".venv" not in p.parts)
    assert len(files) > 40, f"扫描面异常缩小：只找到 {len(files)} 个文件"
    return sorted(files)


def test_no_httpx_call_without_explicit_trust_env():
    """数据面/控制面所有本机 httpx 调用必须显式 trust_env=False（H2）。"""
    offenders = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, name in _httpx_local_clients(tree):
            offenders.append(f"{path.relative_to(ROOT)}:{lineno} {name}() 缺 trust_env=False")
    assert not offenders, "本机 httpx 客户端缺 trust_env=False（毒 NO_PROXY 环境必炸）：\n" + "\n".join(offenders)


def test_guard_itself_detects_module_level_convenience_call(tmp_path):
    """守卫必须能抓到 `httpx.get(...)` 这类模块级函数——这是 H2 补的洞，不是装饰。

    构造三个样例：漏 trust_env 的便捷函数 / 带 trust_env 的便捷函数 / 注释里的假调用。
    只有第一个应被点名（顺带证明本守卫不是 grep，也不误报）。
    """
    src = tmp_path / "sample.py"
    src.write_text(
        '''import httpx

def wait():
    # httpx.get("commented out") 不该被算成调用点
    httpx.get("http://127.0.0.1:1/health", timeout=3)
    httpx.get("http://127.0.0.1:1/ok", timeout=3, trust_env=False)
    httpx.Client(base_url="http://127.0.0.1:1")
    httpx.AsyncClient(trust_env=False)
''',
        encoding="utf-8",
    )
    found = _httpx_local_clients(ast.parse(src.read_text(encoding="utf-8")))
    assert found == [(5, "httpx.get"), (7, "httpx.Client")], found


def test_e2e_timeline_100_health_probe_is_trusted_off():
    """H2 点名的那处必须真被修掉（不是只在扫描面上"看起来齐"）。"""
    path = ROOT / "scripts" / "e2e_timeline_100.py"
    text = path.read_text(encoding="utf-8")
    assert "trust_env=False" in text, "e2e_timeline_100 的 health 探针仍未 trust_env=False"
