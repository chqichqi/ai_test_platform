"""
执行配置模型 — REST API 和 CLI 共用

Usage:
    # REST API (Pydantic)
    config = ExecutionConfig(headless=True, browser_mode="reuse")

    # CLI
    python -m app.cli run-scene --headless --browser-mode reuse --slow-mo 100

    # 程序化
    config = ExecutionConfig.from_cli_args(headless=True, browser_mode="reuse")
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class BrowserMode(str, enum.Enum):
    """浏览器模式"""
    ISOLATED = "isolated"   # 每条用例独立浏览器（默认）
    REUSE = "reuse"         # 同场景用例共享浏览器


@dataclass
class ExecutionConfig:
    """
    执行配置 — 所有执行参数集中管理。

    可通过 REST JSON body、CLI 参数、或代码直接构造。
    """

    # ── 浏览器 ──
    headless: bool = True
    browser_mode: BrowserMode = BrowserMode.ISOLATED
    browser_type: str = "chromium"          # chromium / firefox / webkit

    # ── 视口 ──
    viewport_width: int = 1920
    viewport_height: int = 1080

    # ── 超时与重试 ──
    timeout_ms: int = 60000                 # 单条用例超时
    scene_timeout_ms: int = 600000          # 整个场景超时（10分钟）

    # ── 截图/录像 ──
    screenshot_on_failure: bool = True
    screenshot_on_success: bool = False
    record_video: bool = False
    output_dir: str = "./test-results"      # 截图/录像/报告输出目录

    # ── 调试 ──
    slow_mo: int = 0                        # Playwright slow_mo（毫秒），0=全速
    trace: bool = False                     # Playwright trace 记录

    # ── 过滤 ──
    enabled_only: bool = True               # 只执行 enabled=True 的条目

    # ── 报告 ──
    report_format: str = "json"             # json / junit / html

    # ═══════════════════════════════════════════════════════════
    # 工厂方法
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionConfig":
        """从字典构造（REST JSON body）"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "browser_mode" in filtered and isinstance(filtered["browser_mode"], str):
            filtered["browser_mode"] = BrowserMode(filtered["browser_mode"])
        return cls(**filtered)

    @classmethod
    def from_cli_args(cls, **kwargs) -> "ExecutionConfig":
        """从 CLI 参数构造"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in kwargs.items() if k in valid_keys and v is not None}
        if "browser_mode" in filtered and isinstance(filtered["browser_mode"], str):
            filtered["browser_mode"] = BrowserMode(filtered["browser_mode"])
        return cls(**filtered)

    def to_dict(self) -> dict:
        """转为字典（序列化/JSON 响应）"""
        d = asdict(self)
        d["browser_mode"] = self.browser_mode.value
        return d

    def merge_with_case(self, test_case) -> "ExecutionConfig":
        """
        用单条用例的配置覆盖全局配置。
        用例级 headless / timeout / viewport 优先。
        返回新 ExecutionConfig（不修改原对象）。
        """
        data = self.to_dict()
        if hasattr(test_case, 'headless') and test_case.headless is not None:
            data["headless"] = test_case.headless
        if hasattr(test_case, 'timeout') and test_case.timeout:
            data["timeout_ms"] = test_case.timeout
        if hasattr(test_case, 'viewport_width') and test_case.viewport_width:
            data["viewport_width"] = test_case.viewport_width
        if hasattr(test_case, 'viewport_height') and test_case.viewport_height:
            data["viewport_height"] = test_case.viewport_height
        return ExecutionConfig.from_dict(data)

    # ═══════════════════════════════════════════════════════════
    # CLI 参数声明（供 argparse / click 使用）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def cli_flags() -> dict:
        """
        返回 CLI 参数名 → (类型, 默认值, help) 映射。
        供 argparse 或 click 自动生成 CLI 接口。
        """
        return {
            "--headless":        (bool, True,  "无头模式（默认开启）"),
            "--headed":          (bool, False, "有头模式（显示浏览器）"),
            "--browser-mode":    (str,  "isolated", "浏览器模式: isolated | reuse"),
            "--browser-type":    (str,  "chromium", "浏览器类型: chromium | firefox | webkit"),
            "--viewport":        (str,  "1920x1080", "视口尺寸 WxH"),
            "--timeout":         (int,  60000, "单条用例超时（毫秒）"),
            "--scene-timeout":   (int,  600000, "场景总超时（毫秒）"),
            "--screenshot-on-failure": (bool, True,  "失败截图"),
            "--screenshot-on-success": (bool, False, "成功也截图"),
            "--record-video":    (bool, False, "录制视频"),
            "--output-dir":      (str,  "./test-results", "输出目录"),
            "--slow-mo":         (int,  0,    "Playwright slow_mo（毫秒）"),
            "--trace":           (bool, False, "Playwright trace 记录"),
            "--enabled-only":    (bool, True,  "只执行启用的用例"),
            "--report-format":   (str,  "json", "报告格式: json | junit | html"),
        }
