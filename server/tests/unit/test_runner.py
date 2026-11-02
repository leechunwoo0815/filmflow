"""ProcessRunner 回归：正常退出的进程不能被 _watch_cancel 挂住。"""
import sys

from app.engine.runner import ProcessRunner


async def test_runner_returns_after_normal_exit(tmp_path):
    r = ProcessRunner(tmp_path)
    res = await r.run([sys.executable, "-c", "print('ok')"], timeout=10)
    assert res.exit_code == 0
    assert res.ok
    assert any("ok" in line for line in res.stdout_tail)
