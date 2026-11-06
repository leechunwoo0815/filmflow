"""H9 的长期防线：测试的**环境依赖与标记必须对齐**（静态扫描，不是靠 CI 撞出来）。

2026-11-06 CI 首跑实测红了三类，全部是本机看不见、runner 上才暴露的：
`tests/unit/test_audio_v2.py` 真调 ffmpeg 却**没有任何标记**（×3 直接 `FileNotFoundError`）、
风格库 BDD 按纪律硬失败（这是对的，但 `ci.yml` 的子集选择从没跟它对齐）、
`test_assets.py` 两处**静默 `pytest.skip`**（本机字体永远在 → 从没人发现 CI 上少跑了两条）。

规则只有两条，都故意写成"红得有意义"：
1. 模块里出现 `subprocess` 调用且 argv 字面量含 ffmpeg/ffprobe → 该模块（`pytestmark`）
   或**每个能走到那次调用的测试函数**必须声明 `requires_ffmpeg`；chrome/chromium 同理要 `requires_chrome`。
2. `pytest.skip(...)` 只许出现在 conftest 的 `--allow-missing-env` 分支，或下面这张显式豁免表里；
   新增裸 skip 即红——**豁免必须写理由，写理由就等于把它变成一次决定，而不是一个习惯**。

为什么用 `ast` 而不是 grep：注释/文档字符串里出现 "ffmpeg" 不该算违规，真调用才算；
反过来 grep 也会漏掉多行 argv。
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]

# 显式豁免：文件名 → (允许裸 pytest.skip 的行号线索, 理由)
SKIP_EXEMPT: dict[str, str] = {          # 键相对 server/tests/
    "conftest.py": "唯一的合法出口：--allow-missing-env 分支（缺环境时才 skip）",
    "unit/test_frameserver_auth.py":
        "端口竞态（随机空闲端口被别的进程抢用），不是环境缺失；跳过的是这一条 fixture，"
        "且它属于数据面单测，不影响渲染链覆盖",
}

FFMPEG_TOKENS = ("ffmpeg", "ffprobe")
CHROME_TOKENS = ("chrome", "chromium", "headless_shell", "google chrome")
SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_output", "check_call"}


def _iter_test_files() -> list[Path]:
    files = [p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts]
    assert len(files) >= 40, f"扫描面异常缩小：只找到 {len(files)} 个测试文件"
    return sorted(files)


def _argv_tokens(node: ast.Call) -> list[str]:
    """把 subprocess 调用的 argv 拉平成小写字面量列表（`["ffmpeg", "-y", ...]` 或 f-string 片段）。"""
    out: list[str] = []
    if not node.args:
        return out
    first = node.args[0]
    items = first.elts if isinstance(first, (ast.List, ast.Tuple)) else [first]
    for it in items:
        if isinstance(it, ast.Constant) and isinstance(it.value, str):
            out.append(it.value.lower())
        elif isinstance(it, ast.JoinedStr):
            for v in it.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append(v.value.lower())
    return out


def _env_bin_calls(tree: ast.AST) -> set[str]:
    """这棵树（模块或单个函数体）里真调了哪些外部工具。"""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_subprocess = (isinstance(f, ast.Attribute) and f.attr in SUBPROCESS_FUNCS
                         and isinstance(f.value, ast.Name) and f.value.id == "subprocess")
        if not is_subprocess:
            continue
        toks = _argv_tokens(node)
        if any(any(t == b or t.startswith(b + " ") or "/" + b in t for b in FFMPEG_TOKENS) for t in toks):
            found.add("requires_ffmpeg")
        if any(any(b in t for b in CHROME_TOKENS) for t in toks):
            found.add("requires_chrome")
    return found


def _module_marker_names(tree: ast.AST) -> set[str]:
    """模块级 `pytestmark = ...`（单个或列表）里声明的标记名。"""
    out: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Attribute) and sub.attr.startswith("requires_"):
                out.add(sub.attr)
    return out


def _func_markers(fn: ast.FunctionDef) -> set[str]:
    out: set[str] = set()
    for d in fn.decorator_list:
        for sub in ast.walk(d):
            if isinstance(sub, ast.Attribute) and sub.attr.startswith("requires_"):
                out.add(sub.attr)
    return out


def test_env_dependent_tests_declare_markers() -> None:
    """每个真调 ffmpeg/Chrome 的测试都必须有对应标记（模块级或函数级），否则 CI 会红在本机看不见的地方。"""
    missing: list[str] = []
    for path in _iter_test_files():
        rel = str(path.relative_to(TESTS))
        if path.name == "conftest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_needs = _env_bin_calls(tree)
        if not module_needs:
            continue
        mod_marked = _module_marker_names(tree)
        for fn in tree.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_")):
                continue
            needs = _env_bin_calls(fn) or (module_needs if _module_uses_helper(tree, fn) else set())
            uncovered = sorted(m for m in needs if m not in mod_marked and m not in _func_markers(fn))
            if uncovered:
                missing.append(f"{rel}:{fn.lineno} {fn.name} 调了 {uncovered} 却没有标记")
    assert not missing, "测试环境依赖与标记未对齐（H9-a/H9-c 的同类缺陷）：\n  " + "\n  ".join(missing)


def _module_uses_helper(tree: ast.AST, fn: ast.FunctionDef) -> bool:
    """函数体内调用了本模块里某个会 shell out 的辅助函数 → 该函数也算依赖环境。

    这一步是必要的：`test_audio_v2` 的三个用例本身不写 `subprocess.run([...])`，
    它们只调模块级 `_wav()`。只查函数体的话这条防线正好漏掉我们要防的那个案例。
    """
    shell_helpers = {n.name for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and _env_bin_calls(n)}
    if not shell_helpers:
        return False
    return any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in shell_helpers
               for x in ast.walk(fn))


def test_no_bare_pytest_skip_outside_env_gate() -> None:
    """裸 `pytest.skip` 只许在 conftest 的 --allow-missing-env 分支和显式豁免表里。"""
    offenders: list[str] = []
    for path in _iter_test_files():
        rel = str(path.relative_to(TESTS))
        if rel in SKIP_EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "skip"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest"):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, ("发现静默 skip（H9-c 抓到的那类「少跑没人知道」）：\n  " + "\n  ".join(offenders)
                           + "\n要么补 requires_* 标记让它硬失败，要么把文件+理由加进本文件的 SKIP_EXEMPT。")


def test_skip_exempt_table_is_not_stale() -> None:
    """豁免表不许长蘑菇：里面登记的每个文件必须**真的**还有裸 skip。"""
    stale = []
    for rel in SKIP_EXEMPT:
        p = TESTS / rel
        if not p.exists():
            stale.append(f"{rel} 已不存在")
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        has = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "skip"
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "pytest"
                  for n in ast.walk(tree))
        if not has:
            stale.append(f"{rel} 已经没有裸 pytest.skip 了，该从豁免表里删掉")
    assert not stale, "SKIP_EXEMPT 过期：" + "；".join(stale)
