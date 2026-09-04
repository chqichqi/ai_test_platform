"""
Allure 报告生成器 — 测试执行时实时生成 Allure JSON 结果文件。

输出目录结构:
  test-reports/{project_key}/{version}/{run_ts}/
    allure-results/
      {uuid}-result.json      ← 每条用例
      {uuid}-container.json   ← fixture
      {uuid}-attachment.png   ← 截图
    allure-report/            ← allure generate 产出（可选）
    summary.json              ← 快速摘要
"""

from __future__ import annotations

import json
import os
import shutil
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logger import logger

# ═══════════════════════════════════════════════════════════
# Allure 结果模型
# ═══════════════════════════════════════════════════════════

class AllureStatus:
    PASSED = "passed"
    FAILED = "failed"
    BROKEN = "broken"
    SKIPPED = "skipped"


class AllureStep:
    """单个测试步骤"""
    def __init__(self, name: str, status: str = AllureStatus.PASSED):
        self.name = name
        self.status = status
        self.start = int(datetime.utcnow().timestamp() * 1000)
        self.stop: Optional[int] = None
        self.steps: List[AllureStep] = []
        self.attachments: List[dict] = []
        self.status_details: Optional[dict] = None

    def add_step(self, name: str) -> "AllureStep":
        sub = AllureStep(name)
        self.steps.append(sub)
        return sub

    def add_attachment(self, name: str, source: str, mime: str = "image/png"):
        self.attachments.append({"name": name, "type": mime, "source": source})

    def fail(self, message: str, trace: str = ""):
        self.status = AllureStatus.FAILED
        self.status_details = {"message": message, "trace": trace}

    def finish(self):
        self.stop = int(datetime.utcnow().timestamp() * 1000)
        for s in self.steps:
            if s.stop is None:
                s.finish()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "stage": "finished",
            "start": self.start,
            "stop": self.stop or self.start,
            "steps": [s.to_dict() for s in self.steps],
            "attachments": self.attachments,
            "statusDetails": self.status_details,
        }


class AllureTestResult:
    """单条 Allure 测试结果"""
    def __init__(self, name: str, uuid: str = None):
        self.uuid = uuid or str(_uuid.uuid4())
        self.name = name
        self.full_name = name
        self.status = AllureStatus.PASSED
        self.start = int(datetime.utcnow().timestamp() * 1000)
        self.stop: Optional[int] = None
        self.steps: List[AllureStep] = []
        self.labels: List[dict] = []
        self.links: List[dict] = []
        self.attachments: List[dict] = []
        self.description: str = ""
        self.status_details: Optional[dict] = None
        self.parameters: List[dict] = []

    def add_label(self, name: str, value: str):
        self.labels.append({"name": name, "value": str(value)})

    def add_link(self, url: str, name: str = "", link_type: str = "link"):
        self.links.append({"name": name, "url": url, "type": link_type})

    def add_step(self, name: str) -> AllureStep:
        step = AllureStep(name)
        self.steps.append(step)
        return step

    def add_attachment(self, name: str, source: str, mime: str = "image/png"):
        self.attachments.append({"name": name, "type": mime, "source": source})

    def set_status(self, status: str, message: str = "", trace: str = ""):
        self.status = status
        if message:
            self.status_details = {"message": message, "trace": trace}

    def finish(self):
        self.stop = int(datetime.utcnow().timestamp() * 1000)
        for s in self.steps:
            if s.stop is None:
                s.finish()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "uuid": self.uuid,
            "fullName": self.full_name,
            "status": self.status,
            "stage": "finished",
            "start": self.start,
            "stop": self.stop or self.start,
            "steps": [s.to_dict() for s in self.steps],
            "labels": self.labels,
            "links": self.links,
            "attachments": self.attachments,
            "description": self.description,
            "statusDetails": self.status_details,
            "parameters": self.parameters,
        }


# ═══════════════════════════════════════════════════════════
# Allure 报告器
# ═══════════════════════════════════════════════════════════

class AllureReporter:
    """测试执行时生成 Allure JSON 文件"""

    def __init__(
        self,
        results_dir: str,
        project_name: str = "",
        version_name: str = "",
        environment: dict = None,
    ):
        """
        Args:
            results_dir: allure-results 输出目录
            project_name: 项目名称
            version_name: 版本名称
            environment: 环境信息（OS / Python / Browser 等）
        """
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.version_name = version_name
        self.environment = environment or {}
        self._current_results: Dict[str, AllureTestResult] = {}
        self._containers: List[dict] = []
        self._screenshot_dir = self.results_dir / "screenshots"
        self._screenshot_dir.mkdir(exist_ok=True)

    # ═══════════════════════════════════════════════════════
    # 用例生命周期
    # ═══════════════════════════════════════════════════════

    def start_case(
        self,
        case_id: str,
        name: str,
        module: str = "",
        priority: str = "medium",
        description: str = "",
        params: dict = None,
    ) -> AllureTestResult:
        """开始一条用例"""
        result = AllureTestResult(name, case_id)
        result.full_name = f"{module}.{name}" if module else name
        result.description = description

        # 标签 — Allure 分类依据
        result.add_label("suite", module or "默认模块")
        result.add_label("epic", self.project_name)
        result.add_label("feature", module or "默认模块")
        result.add_label("severity", priority)
        result.add_label("host", self.environment.get("host", ""))
        result.add_label("thread", self.environment.get("browser", "chromium"))

        if params:
            result.parameters = [
                {"name": k, "value": str(v)} for k, v in params.items()
            ]

        self._current_results[case_id] = result
        return result

    def end_case(self, case_id: str, status: str = AllureStatus.PASSED,
                 message: str = "", trace: str = ""):
        """结束一条用例并写入 JSON 文件"""
        result = self._current_results.pop(case_id, None)
        if not result:
            return
        result.set_status(status, message, trace)
        result.finish()
        self._write_result(result)

    def skip_case(self, case_id: str, name: str, reason: str = "",
                  module: str = ""):
        """记录一条跳过的用例"""
        result = AllureTestResult(name, case_id)
        result.full_name = f"{module}.{name}" if module else name
        result.add_label("suite", module or "默认模块")
        result.add_label("epic", self.project_name)
        result.set_status(AllureStatus.SKIPPED, reason)
        result.finish()
        self._write_result(result)

    # ═══════════════════════════════════════════════════════
    # 步骤与附件
    # ═══════════════════════════════════════════════════════

    def start_step(self, case_id: str, step_name: str) -> Optional[AllureStep]:
        """在用例中添加一个步骤"""
        result = self._current_results.get(case_id)
        if result:
            return result.add_step(step_name)
        return None

    def end_step(self, step: Optional[AllureStep], status: str = AllureStatus.PASSED,
                 message: str = ""):
        """结束步骤"""
        if step:
            if status == AllureStatus.FAILED:
                step.fail(message)
            step.finish()

    def add_screenshot(self, case_id: str, png_bytes: bytes, name: str = "screenshot"):
        """添加失败截图"""
        result = self._current_results.get(case_id)
        if not result:
            return
        filename = f"{case_id}-{_uuid.uuid4().hex[:8]}.png"
        filepath = self._screenshot_dir / filename
        filepath.write_bytes(png_bytes)

        result.add_attachment(name, f"screenshots/{filename}", "image/png")
        # 也加到当前最后一个步骤
        if result.steps:
            result.steps[-1].add_attachment(name, f"screenshots/{filename}", "image/png")

    # ═══════════════════════════════════════════════════════
    # 环境 / 分类
    # ═══════════════════════════════════════════════════════

    def write_environment(self):
        """写入 environment.properties"""
        lines = []
        for k, v in self.environment.items():
            lines.append(f"{k}={v}")
        (self.results_dir / "environment.properties").write_text(
            "\n".join(lines), encoding="utf-8"
        )

    def write_categories(self):
        """写入 categories.json（失败分类）"""
        cats = [
            {"name": "断言失败", "matchedStatuses": ["failed"],
             "messageRegex": ".*assert.*"},
            {"name": "元素未找到", "matchedStatuses": ["broken"],
             "messageRegex": ".*(not found|visible|selector).*"},
            {"name": "超时", "matchedStatuses": ["broken"],
             "messageRegex": ".*(timeout|TimeOut).*"},
            {"name": "跳过的测试", "matchedStatuses": ["skipped"]},
        ]
        (self.results_dir / "categories.json").write_text(
            json.dumps(cats, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def write_executor(self):
        """写入 executor.json"""
        info = {
            "name": "AI Test Platform",
            "type": "ai-test-platform",
            "buildName": f"{self.project_name} {self.version_name}",
            "reportUrl": "",
        }
        (self.results_dir / "executor.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def finalize(self):
        """写入所有元数据文件"""
        self.write_environment()
        self.write_categories()
        self.write_executor()

    # ═══════════════════════════════════════════════════════
    # 内部
    # ═══════════════════════════════════════════════════════

    def _write_result(self, result: AllureTestResult):
        """写入单个 result JSON 文件"""
        path = self.results_dir / f"{result.uuid}-result.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ═══════════════════════════════════════════════════════
    # 生成 HTML 报告
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def generate_html(results_dir: str, report_dir: str) -> bool:
        """调用 allure CLI 生成 HTML 报告

        兼容后端进程 PATH 未含 allure 的情况：按候选路径定位 allure（.bat / 无后缀脚本 /
        exe），Windows 下用 cmd /c 执行 .bat。
        """
        import subprocess, shutil, os as _os
        # 1) PATH 中已有 allure
        cmd = shutil.which("allure")
        # 2) 候选绝对路径（含 .bat）
        if not cmd:
            cands = [
                _os.environ.get("ALLURE_HOME", ""),
                r"D:/Program Files/allure-commandline-2.20.0/allure-2.20.0/bin/allure",
                r"C:/Program Files/allure/bin/allure",
            ]
            for c in cands:
                if not c:
                    continue
                for probe in (c + ".bat", c):
                    if _os.path.exists(probe):
                        cmd = probe
                        break
                if cmd:
                    break
        if not cmd:
            logger.warning("[Allure] allure CLI 未找到（PATH/ALLURE_HOME/候选路径），仅保留 JSON 结果")
            return False

        # Windows 下统一经 shell 执行（cmd.exe 解析，能运行 .bat），避免列表式直接调用
        # 对 .bat 失效的问题（allure 位于 PATH 目录时 which 返回 .BAT）。
        import subprocess as _sp
        _shell_str = f'"{cmd}" generate "{results_dir}" -o "{report_dir}" --clean'
        try:
            _res = _sp.run(_shell_str, shell=True, capture_output=True, timeout=120)
            if _res.returncode == 0:
                logger.info(f"[Allure] HTML 报告已生成: {report_dir}")
                return True
            logger.warning(f"[Allure] HTML 生成失败: {_res.returncode}")
            return False
        except FileNotFoundError:
            logger.warning("[Allure] allure CLI 未找到（仅保留 JSON 结果）")
            return False
        except Exception as _e:
            logger.warning(f"[Allure] HTML 生成异常: {_e}")
            return False


# ═══════════════════════════════════════════════════════════
# 报告管理器 — 存储 / 查询 / 删除
# ═══════════════════════════════════════════════════════════

class ReportManager:
    """管理测试报告的生命周期"""

    BASE_DIR = Path("test-reports")

    @classmethod
    def create_run_dir(cls, project_key: str, version: str) -> Path:
        """创建本次运行的目录（时间戳，不覆盖）"""
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        run_dir = cls.BASE_DIR / project_key / version / ts
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    @classmethod
    def list_reports(cls, project_key: str = None) -> List[dict]:
        """列出所有报告"""
        reports = []
        base = cls.BASE_DIR
        if not base.exists():
            return []

        projects = [base] if project_key else sorted(base.iterdir())
        for proj_dir in projects:
            if not proj_dir.is_dir():
                continue
            for ver_dir in sorted(proj_dir.iterdir(), reverse=True):
                if not ver_dir.is_dir():
                    continue
                for run_dir in sorted(ver_dir.iterdir(), reverse=True):
                    summary_path = run_dir / "summary.json"
                    summary = {}
                    if summary_path.exists():
                        try:
                            summary = json.loads(summary_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    reports.append({
                        "project": proj_dir.name,
                        "version": ver_dir.name,
                        "run_id": run_dir.name,
                        "run_ts": cls._parse_ts(run_dir.name),
                        "path": str(run_dir),
                        "has_html": (run_dir / "allure-report" / "index.html").exists(),
                        "has_results": (run_dir / "allure-results").exists(),
                        "summary": summary,
                    })
        return reports

    @classmethod
    def get_report(cls, project_key: str, version: str, run_id: str) -> Optional[dict]:
        """获取单个报告详情"""
        run_dir = cls.BASE_DIR / project_key / version / run_id
        if not run_dir.exists():
            return None
        results_dir = run_dir / "allure-results"
        results = []
        if results_dir.exists():
            for f in sorted(results_dir.glob("*-result.json")):
                try:
                    results.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass

        passed = sum(1 for r in results if r.get("status") == "passed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        broken = sum(1 for r in results if r.get("status") == "broken")
        skipped = sum(1 for r in results if r.get("status") == "skipped")

        return {
            "project": project_key,
            "version": version,
            "run_id": run_id,
            "path": str(run_dir),
            "has_html": (run_dir / "allure-report" / "index.html").exists(),
            "summary": {
                "total": len(results), "passed": passed,
                "failed": failed, "broken": broken, "skipped": skipped,
            },
            "results": results,
        }

    @classmethod
    def delete_report(cls, project_key: str, version: str, run_id: str) -> dict:
        """
        安全删除报告 — 多层防护：
        1. 校验路径必须在 test-reports/ 下（防止误删系统文件）
        2. 校验目录下存在 allure-results/ 或 allure-report/（确认是报告目录）
        3. 校验 project_key/version/run_id 不含路径穿越字符（../ 等）
        """
        # 三重防护
        for component in [project_key, version, run_id]:
            if not component or ".." in component or "/" in component or "\\" in component:
                return {"success": False, "error": f"路径包含非法字符: {component}"}

        run_dir = (cls.BASE_DIR / project_key / version / run_id).resolve()

        # 必须严格在 BASE_DIR 下（防止符号链接绕过）
        if not str(run_dir).startswith(str(cls.BASE_DIR.resolve())):
            return {"success": False, "error": "路径不在报告目录范围内"}

        if not run_dir.exists():
            return {"success": False, "error": "报告目录不存在"}

        # 必须是报告目录（包含 allure-results 或 allure-report）
        has_results = (run_dir / "allure-results").is_dir()
        has_report = (run_dir / "allure-report").is_dir()
        if not has_results and not has_report:
            return {"success": False, "error": "不是有效的报告目录（缺少 allure-results / allure-report）"}

        # 安全删除
        try:
            shutil.rmtree(run_dir)
            logger.info(f"[ReportManager] 已删除报告: {run_dir}")
            return {"success": True, "message": f"报告 {run_id} 已删除"}
        except Exception as e:
            return {"success": False, "error": f"删除失败: {str(e)}"}

    @classmethod
    def write_summary(cls, run_dir: Path, summary: dict):
        """写入报告摘要"""
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _parse_ts(run_id: str) -> str:
        """从目录名解析时间戳"""
        try:
            dt = datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return run_id
