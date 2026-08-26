"""
CLI 入口 — UI 测试命令行执行

用法:
    # 执行场景（浏览器复用 + 无头）
    python -m app.cli run-scene --scene-id 1 --headless --browser-mode reuse

    # 执行指定用例（隔离模式 + 有头）
    python -m app.cli run-tests --ids 1,2,3 --headed --browser-mode isolated

    # 输出 JUnit 报告
    python -m app.cli run-scene --scene-id 1 --report-format junit --output-dir ./results

    # 开启 trace + slow_mo 调试
    python -m app.cli run-tests --ids 1 --headed --slow-mo 500 --trace

    # 查看帮助
    python -m app.cli --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

# 确保项目根在 sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器"""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="AI Test Platform — UI 测试命令行执行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m app.cli run-scene --scene-id 1 --headless --browser-mode reuse
  python -m app.cli run-tests --ids 1,2,3 --headed --slow-mo 100
  python -m app.cli run-scene --scene-id 1 --report-format junit
""",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── run-scene ──
    scene = sub.add_parser("run-scene", help="执行场景中的所有 UI 用例")
    scene.add_argument("--scene-id", type=int, required=True, help="场景 ID")
    scene.add_argument("--version-id", type=int, default=None, help="版本 ID（可选）")
    _add_execution_args(scene)

    # ── run-tests ──
    tests = sub.add_parser("run-tests", help="执行指定的 UI 用例")
    tests.add_argument("--ids", type=str, required=True,
                       help="用例 ID，逗号分隔，如 1,2,3")
    _add_execution_args(tests)

    # ── list-scenes ──
    ls = sub.add_parser("list-scenes", help="列出可执行的场景")
    ls.add_argument("--type", type=str, default="ui", help="场景类型: ui / api / performance")

    return parser


def _add_execution_args(p: argparse.ArgumentParser):
    """添加执行参数（run-scene 和 run-tests 共用）"""
    from app.core.services.execution_config import ExecutionConfig

    p.add_argument("--headless", action="store_true", default=None,
                   help="无头模式")
    p.add_argument("--headed", action="store_true", default=None,
                   help="有头模式（显示浏览器窗口）")
    p.add_argument("--browser-mode", type=str, default="reuse",
                   choices=["isolated", "reuse"],
                   help="浏览器模式: isolated=每条独立 / reuse=共享（默认）")
    p.add_argument("--browser-type", type=str, default="chromium",
                   choices=["chromium", "firefox", "webkit"],
                   help="浏览器类型（默认 chromium）")
    p.add_argument("--viewport", type=str, default="1920x1080",
                   help="视口尺寸 WxH")
    p.add_argument("--timeout", type=int, default=60000,
                   help="单条用例超时（毫秒）")
    p.add_argument("--scene-timeout", type=int, default=600000,
                   help="场景总超时（毫秒）")
    p.add_argument("--screenshot-on-failure", action="store_true", default=True,
                   help="失败截图")
    p.add_argument("--no-screenshot", action="store_true", default=False,
                   help="禁用失败截图")
    p.add_argument("--record-video", action="store_true", default=False,
                   help="录制视频")
    p.add_argument("--output-dir", type=str, default="./test-results",
                   help="输出目录")
    p.add_argument("--slow-mo", type=int, default=0,
                   help="Playwright slow_mo（毫秒），调试用")
    p.add_argument("--trace", action="store_true", default=False,
                   help="开启 Playwright trace 记录")
    p.add_argument("--report-format", type=str, default="json",
                   choices=["json", "junit", "html"],
                   help="报告格式")


def _parse_viewport(viewport_str: str) -> tuple:
    """解析 --viewport 1920x1080"""
    parts = viewport_str.lower().replace("x", " ").split()
    w = int(parts[0]) if parts else 1920
    h = int(parts[1]) if len(parts) > 1 else 1080
    return w, h


def _build_config(args) -> "ExecutionConfig":
    """从 CLI args 构建 ExecutionConfig"""
    from app.core.services.execution_config import ExecutionConfig, BrowserMode

    headless = True
    if args.headed:
        headless = False
    elif args.headless:
        headless = True

    vp_w, vp_h = _parse_viewport(args.viewport)
    screenshot = not args.no_screenshot

    return ExecutionConfig(
        headless=headless,
        browser_mode=BrowserMode(args.browser_mode),
        browser_type=args.browser_type,
        viewport_width=vp_w,
        viewport_height=vp_h,
        timeout_ms=args.timeout,
        scene_timeout_ms=args.scene_timeout,
        screenshot_on_failure=screenshot,
        screenshot_on_success=False,
        record_video=args.record_video,
        output_dir=args.output_dir,
        slow_mo=args.slow_mo,
        trace=args.trace,
        report_format=args.report_format,
    )


# ═══════════════════════════════════════════════════════════════
# 命令实现
# ═══════════════════════════════════════════════════════════════

async def _cmd_run_scene(args):
    """执行场景"""
    from app.core.database import SessionLocal
    from app.core.models.scene import Scene
    from app.core.models.web_ui_test import WebUITestCase
    from app.core.services.ui_test_executor import UITestExecutor

    config = _build_config(args)
    print(f"执行场景 {args.scene_id}")
    print(f"配置: headless={config.headless}, mode={config.browser_mode.value}, "
          f"viewport={config.viewport_width}x{config.viewport_height}")

    db = SessionLocal()
    try:
        scene = db.query(Scene).filter(Scene.id == args.scene_id).first()
        if not scene:
            print(f"错误: 场景 {args.scene_id} 不存在")
            sys.exit(1)

        items = [i for i in (scene.items or []) if i.enabled]
        items.sort(key=lambda x: x.sort_order)

        # 加载 UI 用例
        test_cases = []
        for item in items:
            if item.case_type == "ui":
                wui = db.query(WebUITestCase).filter(
                    WebUITestCase.id == str(item.case_id)
                ).first()
                if wui:
                    test_cases.append(wui)

        if not test_cases:
            print("没有可执行的 UI 用例")
            return

        print(f"共 {len(test_cases)} 条用例，开始执行...\n")

        def show_progress(stage, msg, idx, total):
            if stage == "running":
                tc = test_cases[idx]
                mode = getattr(tc, 'generation_mode', 'linear')
                print(f"  [{idx+1}/{total}] {getattr(tc, 'id', '?')} ({mode}) — {msg}")

        start = time.time()
        executor = UITestExecutor(config)
        results = await executor.execute_batch(test_cases, show_progress)

        # 输出结果
        elapsed = time.time() - start
        passed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") in ("failed", "error"))

        print(f"\n{'='*50}")
        print(f"结果: {passed} 通过, {failed} 失败, {len(results)} 总计, {elapsed:.1f}s")
        print(f"{'='*50}")

        for r in results:
            status_icon = "✅" if r.get("status") == "completed" else "❌"
            case_id = r.get("test_case_id", "?")
            mode = r.get("generation_mode", "?")
            err = r.get("error", "")
            dur = r.get("duration_ms", 0)
            print(f"  {status_icon} {case_id} ({mode}) [{r.get('browser_mode')}] "
                  f"{dur}ms {err if err else ''}")

        # 保存报告
        _save_report(results, config, elapsed)

        if failed > 0:
            sys.exit(1)

    finally:
        db.close()


async def _cmd_run_tests(args):
    """执行指定用例"""
    from app.core.database import SessionLocal
    from app.core.models.web_ui_test import WebUITestCase
    from app.core.services.ui_test_executor import UITestExecutor

    config = _build_config(args)
    ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]

    print(f"执行用例: {ids}")
    print(f"配置: headless={config.headless}, mode={config.browser_mode.value}")

    db = SessionLocal()
    try:
        test_cases = []
        for tid in ids:
            wui = db.query(WebUITestCase).filter(WebUITestCase.id == str(tid)).first()
            if wui:
                test_cases.append(wui)
            else:
                print(f"  警告: 用例 {tid} 不存在，跳过")

        if not test_cases:
            print("没有找到有效用例")
            sys.exit(1)

        print(f"共 {len(test_cases)} 条用例，开始执行...\n")

        start = time.time()
        executor = UITestExecutor(config)
        results = await executor.execute_batch(test_cases)

        elapsed = time.time() - start
        passed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") in ("failed", "error"))

        print(f"\n{'='*50}")
        print(f"结果: {passed} 通过, {failed} 失败, {len(results)} 总计, {elapsed:.1f}s")

        for r in results:
            icon = "OK" if r.get("status") == "completed" else "FAIL"
            print(f"  [{icon}] {r.get('test_case_id')} ({r.get('generation_mode')}) "
                  f"{r.get('duration_ms', 0)}ms {r.get('error', '')}")

        _save_report(results, config, elapsed)

        if failed > 0:
            sys.exit(1)

    finally:
        db.close()


async def _cmd_list_scenes(args):
    """列出场景"""
    from app.core.database import SessionLocal
    from app.core.models.scene import Scene

    db = SessionLocal()
    try:
        scenes = db.query(Scene).filter(Scene.scene_type == args.type).all()
        if not scenes:
            print(f"没有 {args.type} 类型的场景")
            return
        for s in scenes:
            items = [i for i in (s.items or []) if i.enabled]
            print(f"  [{s.id}] {s.name} — {len(items)} 条用例")
    finally:
        db.close()


def _save_report(results: List[dict], config, elapsed: float):
    """保存测试报告"""
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    passed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))

    report = {
        "config": config.to_dict(),
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "elapsed_seconds": round(elapsed, 1),
        },
        "results": results,
    }

    if config.report_format == "json":
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已保存: {report_path}")

    elif config.report_format == "junit":
        _write_junit(results, output_dir / "report.xml", elapsed)

    elif config.report_format == "html":
        # 简单 HTML 报告
        html = _build_html_report(results, config, elapsed)
        (output_dir / "report.html").write_text(html, encoding="utf-8")
        print(f"\n报告已保存: {output_dir / 'report.html'}")


def _write_junit(results: List[dict], path: Path, elapsed: float):
    """生成 JUnit XML 报告"""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    total = len(results)
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
    lines.append(f'<testsuite name="ui-tests" tests="{total}" failures="{failed}" '
                 f'time="{elapsed:.1f}">')
    for r in results:
        case_id = r.get("test_case_id", "?")
        status = r.get("status", "error")
        dur = (r.get("duration_ms", 0) or 0) / 1000
        lines.append(f'  <testcase name="{case_id}" time="{dur:.2f}">')
        if status in ("failed", "error"):
            err = r.get("error", "")
            lines.append(f'    <failure message="{err}"/>')
        lines.append('  </testcase>')
    lines.append('</testsuite>')
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nJUnit 报告已保存: {path}")


def _build_html_report(results: List[dict], config, elapsed: float) -> str:
    """生成简单 HTML 报告"""
    rows = []
    for r in results:
        icon = "✅" if r.get("status") == "completed" else "❌"
        rows.append(
            f'<tr><td>{icon}</td><td>{r.get("test_case_id")}</td>'
            f'<td>{r.get("generation_mode")}</td><td>{r.get("browser_mode")}</td>'
            f'<td>{r.get("duration_ms", 0)}ms</td>'
            f'<td>{r.get("error", "")}</td></tr>'
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>测试报告</title>
<style>body{{font-family:monospace;max-width:1200px;margin:20px auto}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f5f5}}tr:hover{{background:#fafafa}}</style></head>
<body>
<h1>UI 测试报告</h1>
<p>headless={config.headless}, mode={config.browser_mode.value},
viewport={config.viewport_width}x{config.viewport_height}</p>
<p>总计 {len(results)} 条, 耗时 {elapsed:.1f}s</p>
<table>
<tr><th></th><th>用例ID</th><th>模式</th><th>浏览器</th><th>耗时</th><th>错误</th></tr>
{''.join(rows)}
</table></body></html>"""


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "run-scene":
        asyncio.run(_cmd_run_scene(args))
    elif args.command == "run-tests":
        asyncio.run(_cmd_run_tests(args))
    elif args.command == "list-scenes":
        asyncio.run(_cmd_list_scenes(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
