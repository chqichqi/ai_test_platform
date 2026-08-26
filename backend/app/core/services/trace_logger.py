"""
管道追踪日志 — 记录探索+转化全链路数据，供调试和分析。

输出: tests/exploration/trace/trace_{timestamp}.json
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class TraceLogger:
    """全链路追踪记录器。同模块覆盖保存，避免文件堆积。"""

    def __init__(self, module_name: str = "", output_dir: str = None):
        self._module = module_name or "default"
        self._dir = output_dir or os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "tests", "exploration", "trace"
        ))
        os.makedirs(self._dir, exist_ok=True)
        self._ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        _safe_name = self._module.replace("/", "_").replace("\\", "_").replace(" ", "_")[:50]
        self._path = os.path.join(self._dir, f"trace_{_safe_name}.json")
        # 同模块新旧文件命名不同（探索/转化分开），避免覆盖
        self._explore_path = os.path.join(self._dir, f"explore_{_safe_name}.json")
        self._conv_path = os.path.join(self._dir, f"conv_{_safe_name}.json")

        self._data = {
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline": "functional_to_ui",
            "test_cases_total": 0,
            "exploration": {},
            "conversions": [],
            "summary": {},
        }

    # ═══════════════════════════════════════════════════════════
    # 探索阶段
    # ═══════════════════════════════════════════════════════════

    def log_exploration_start(self, module_name: str, steps_count: int, start_url: str):
        self._data["exploration"] = {
            "module": module_name,
            "steps_total": steps_count,
            "start_url": start_url,
            "steps": [],
            "summary": {"found": 0, "clicked": 0, "navigated": 0, "missed": 0},
        }

    def log_step_attempt(self, seq: int, target: str, action: str, role: str,
                         ui_pattern: str, found: bool, actual_text: str = "",
                         strategy: str = "", clicked: bool = False,
                         url_changed: bool = False, jump_url: str = "",
                         page_text_len: int = 0, current_url: str = ""):
        """记录单步探索结果。"""
        entry = {
            "seq": seq,
            "target": target,
            "action": action,
            "role": role,
            "ui_pattern": ui_pattern,
            "found": found,
            "actual_text": actual_text,
            "strategy": strategy,
            "page_text_len": page_text_len,
            "current_url": current_url[-80:] if current_url else "",
        }
        if found:
            entry["clicked"] = clicked
            entry["url_changed"] = url_changed
            if url_changed:
                entry["jump_url"] = jump_url
            self._data["exploration"]["summary"]["found"] += 1
            if clicked:
                self._data["exploration"]["summary"]["clicked"] += 1
            if url_changed:
                self._data["exploration"]["summary"]["navigated"] += 1
        else:
            self._data["exploration"]["summary"]["missed"] += 1

        self._data["exploration"]["steps"].append(entry)

    def log_exploration_done(self, stats: dict):
        self._data["exploration"]["stats"] = stats

    # ═══════════════════════════════════════════════════════════
    # 转化阶段
    # ═══════════════════════════════════════════════════════════

    def log_conversion(self, test_case_id: str, case_name: str, module: str,
                       before_steps: List[Dict], after_spec: Optional[Dict],
                       mode: str, status: str, diagnostics: Optional[Dict] = None,
                       error: str = ""):
        """记录单条用例的转化前后。"""
        entry = {
            "test_case_id": str(test_case_id),
            "case_name": case_name,
            "module": module,
            "mode": mode,
            "status": status,
            "error": error,
            "before": {
                "steps_count": len(before_steps) if before_steps else 0,
                "steps": before_steps or [],
            },
            "after": {
                "steps_count": len(after_spec.get("steps", [])) if after_spec else 0,
                "title": after_spec.get("title", "") if after_spec else "",
                "steps": after_spec.get("steps", []) if after_spec else [],
            } if after_spec else None,
            "diagnostics": diagnostics or {},
        }
        self._data["conversions"].append(entry)

    # ═══════════════════════════════════════════════════════════
    # 汇总
    # ═══════════════════════════════════════════════════════════

    def log_summary(self, summary: dict):
        self._data["summary"] = summary
        self._data["test_cases_total"] = summary.get("total_count", len(self._data["conversions"]))

    # ═══════════════════════════════════════════════════════════
    # 写入文件
    # ═══════════════════════════════════════════════════════════

    def save(self) -> str:
        # 根据数据类型选文件名：有 exploration 数据 → explore，有 conversions → conv
        has_exp = bool(self._data.get("exploration", {}).get("steps"))
        has_conv = bool(self._data.get("conversions"))
        if has_exp and not has_conv:
            _out = self._explore_path
        elif has_conv and not has_exp:
            _out = self._conv_path
        else:
            _out = self._path  # 两者都有，用带时间戳的
        with open(_out, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        return _out

    @property
    def path(self) -> str:
        return self._path
