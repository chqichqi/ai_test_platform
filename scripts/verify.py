# -*- coding: utf-8 -*-
"""一键验证脚本：Python 语法 + 冒烟基线 + 前端 tsc，一条命令全绿才能收尾。

用法（项目根下任意位置）:
    python scripts/verify.py          # 全量验证
    python scripts/verify.py --no-tsc # 跳过前端 tsc（快速回归）

退出码：0 = 全绿；1 = 任一步失败（供 CI / 收尾判断）。
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Windows GBK 控制台/管道下强制 UTF-8 输出，避免 ✓/中文 print 崩溃
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = sys.executable

# 子进程强制 UTF-8（smoke 脚本 print ✓ 在 GBK 环境下会 UnicodeEncodeError）
_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

OK = "✓"
BAD = "✗"
results = []  # (步骤名, 是否通过, 详情)


def run(cmd, cwd=None, timeout=None, shell=False):
    """跑外部命令，返回 (exit_code, stdout+stderr)。失败用 try 兜底防单步异常中断。"""
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=_ENV)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"[TIMEOUT {timeout}s]"
    except Exception as e:
        return -1, str(e)


def step_compile():
    """全量 py_compile backend/app（排除 __pycache__ 与 *.bak；不扫 venv/site-packages）。"""
    app_dir = BACKEND / "app"
    files = [p for p in app_dir.rglob("*.py")
             if "__pycache__" not in p.parts and not p.name.endswith(".bak")]
    if not files:
        results.append(("Python 语法", False, "backend/app 无 .py 文件"))
        return
    import py_compile
    bad = []
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            bad.append(f"{f.relative_to(BACKEND)}: {e}")
    if bad:
        results.append(("Python 语法", False, "\n".join(bad[:10])))
    else:
        results.append(("Python 语法", True, f"{len(files)} 个文件 OK"))


def step_smoke():
    """跑 backend/logs/smoke_*.py 全部冒烟（内存 sqlite，秒级），单步失败不阻断。"""
    smokes = sorted(BACKEND.glob("logs/smoke_*.py"))
    if not smokes:
        results.append(("冒烟脚本", False, "未找到 backend/logs/smoke_*.py"))
        return
    ok = True
    detail = []
    for s in smokes:
        # cwd=backend：smoke 脚本依赖从 backend/.env 加载配置（JWT_SECRET_KEY 等）
        code, out = run([PYTHON, str(s)], timeout=300, cwd=str(BACKEND))
        # 解析最后一行 "结果: N 通过 / M 失败"
        m = re.search(r"结果:\s*(\d+)\s*通过\s*/\s*(\d+)\s*失败", out)
        name = s.name
        if code == 0 and m:
            passed, failed = int(m.group(1)), int(m.group(2))
            ok = ok and failed == 0
            detail.append(f"{OK if failed == 0 else BAD} {name}: {passed} 通过 / {failed} 失败")
        else:
            ok = False
            tail = out.strip().splitlines()
            tail = tail[-3:] if tail else []
            detail.append(f"{BAD} {name}: 非零退出码 {code}\n      " + "\n      ".join(tail))
    results.append(("冒烟脚本", ok, "\n".join(detail)))


def step_tsc():
    """前端类型检查（较慢，--no-tsc 可跳过）。"""
    if not (FRONTEND / "package.json").exists():
        results.append(("前端 tsc", False, "frontend/package.json 不存在"))
        return
    # Windows 下 npx 是 npx.cmd，需 shell=True；cwd 定位到 frontend
    code, out = run("npx tsc --noEmit", cwd=str(FRONTEND), timeout=900, shell=True)
    if code == 0:
        results.append(("前端 tsc", True, "0 errors"))
    else:
        err_lines = [l for l in out.splitlines() if "error TS" in l]
        shown = err_lines[:15] if err_lines else out.strip().splitlines()[-5:]
        results.append(("前端 tsc", False, "\n".join(shown) if shown else f"退出码 {code}"))


def main():
    no_tsc = "--no-tsc" in sys.argv
    t0 = time.time()
    print("═══ 一键验证 ═══")
    print(f"项目根: {ROOT}")

    print("\n[1/3] Python 语法 (backend/app) ...")
    step_compile()
    print(f"  {results[-1][0]}: {results[-1][2] if results[-1][1] else 'FAIL'}")

    print("\n[2/3] 冒烟脚本 (backend/logs/smoke_*.py) ...")
    step_smoke()
    for line in results[-1][2].splitlines():
        print(f"  {line}")

    if no_tsc:
        print("\n[3/3] 前端 tsc ... 跳过 (--no-tsc)")
    else:
        print("\n[3/3] 前端 tsc (frontend) ...")
        step_tsc()
        ok = results[-1][1]
        print(f"  {OK if ok else BAD} {results[-1][2]}")

    all_ok = all(r[1] for r in results)
    print(f"\n═══ 结果: {'全绿 ✓' if all_ok else '未全绿 ✗ 见上方明细'} "
          f"({time.time() - t0:.0f}s) ═══")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
