"""
GuidedExplorationAgent — 步骤驱动探索引擎

继承 MCPExplorationAgent，复用其 Action Vocabulary、浏览器管理、
弹窗处理、状态捕获等全部基础设施。

核心改动：将 `_phase1_discover`（盲发现）→ `_phase2_execute`（全量点击）
替换为 `explore_guided(steps)`（按测试步骤逐条定位+执行）。

关键差异 vs 盲探索:
  1. 元素定位: 文本/角色精确搜索（ElementLocator），而非 CSS 选择器全量扫描
  2. 流程线性: 步骤顺序执行，URL 随导航自然前进（不回起点重扫）
  3. 上下文感知: 弹窗内/表格行内搜索，自适应 scope
  4. 兜底保留: 当步骤解析失败或无可用步骤时，回退到盲探索
"""

import json
import time
import logging
from typing import Any, Dict, List, Optional

from app.core.services.mcp_exploration_agent import (
    MCPExplorationAgent, Action, ActionType, ActionResult, StateNode,
)
from app.core.services.element_locator import ElementLocator, LocateResult

logger = logging.getLogger(__name__)


class GuidedExplorationAgent(MCPExplorationAgent):
    """步骤驱动探索引擎——按测试用例步骤顺序在浏览器中定位并操作元素。

    继承 MCPExplorationAgent 的全部能力：
      - Action Vocabulary + _execute_action() 分发
      - _handle_click / _handle_fill / _handle_select / handle_tab_switch 等
      - _capture_state() / _save_results()
      - _setup_dialog_handlers() / _interact_modal()
      - _return_to_page() / _is_within_module()
      - MCPClient 浏览器操作
    """

    def __init__(self, client, config, llm_service=None, module_name="", platform_type="web"):
        super().__init__(client, config, llm_service, module_name)
        self._guided_steps: List[Any] = []     # 当前批次的 GuidedStep 列表
        self._locator = ElementLocator(client.page, config)
        self.platform_type = platform_type     # "web" | "app"

    # ═══════════════════════════════════════════════════════════
    # 主入口: 步骤驱动探索
    # ═══════════════════════════════════════════════════════════

    def explore_guided(self,
                       guided_steps: List,
                       start_url: str = '',
                       trace_logger=None,   # TraceLogger 实例
                       progress_cb=None,    # callable(dict) → 每步进度事件 {step_done, step_total}
                       cancel_check=None,   # callable → bool, True=用户已取消转化，探索立即停止
                       ) -> Dict[str, Any]:
        """按 GuidedStep 列表顺序探索。

        Args:
            guided_steps: GuidedStep 对象列表（来自 StepParser.parse_steps()）
            start_url: 起始页面 URL
            trace_logger: 可选 TraceLogger，记录每步探索结果
            progress_cb: 可选进度回调，每执行一步调用一次
                {"step_done": 当前步骤序号(1起), "step_total": 步骤总数}——前端进度条在
                长耗时探索期间保持可见移动（2026-08-25 用户反馈：探索期进度条不动像死机）
            cancel_check: 可选取消回调（每步执行前检查）——用户点击「取消转化」时
                后端置取消标志，探索在此停止（stats.interrupted='cancelled'），
                finally 关浏览器结束整个生成流程

        Returns:
            与 explore() 相同格式的结果 dict:
            {site_map, element_jumps, deep_dive, stats, pages_visited,
             error_events, state_graph, module_docs, site_map_md, page_object_code}
        """
        t0 = time.time()
        self.client.inject_console_hook()
        self._guided_steps = guided_steps
        self._trace = trace_logger

        # 重置状态（与 explore() 相同）
        self._visited_urls = set()
        self._pages_explored = []
        self._all_element_jumps = []
        self._click_log = []
        self._state_counter = 0
        self._error_events = []
        self._site_map = {"modules": []}
        self._state_graph = []
        self._scope_element = None
        self._observer_injected = False

        # 清理旧 state 目录
        self._clean_state_dir()

        # 设置模块边界
        current_url = start_url or self.client.get_url()
        self._set_module_boundary(current_url)

        # 注入弹窗处理器
        self._setup_dialog_handlers()

        # ── 执行引导探索 ──
        _interrupted: str = ""
        try:
            self._run_guided_exploration(current_url, guided_steps,
                                         progress_cb=progress_cb, cancel_check=cancel_check)
            if getattr(self, '_cancelled', False):
                _interrupted = "cancelled"
        except Exception as e:
            # 2026-08-24 实证：循环中途异常（如 state 快照写盘 Errno 22）会让剩余步骤
            # 全部丢失且上层无从知晓——记录中断原因，stats 带 interrupted 字段供转化层感知
            _interrupted = f"{type(e).__name__}: {e}"
            self._error_events.append({
                "stage": "guided_explore", "error": str(e), "url": current_url
            })
            logger.error(f"[GuidedAgent] Fatal error: {e}")

        # ── Phase 3: 深度探索（仅步骤涉及的页面）──
        try:
            self._restore_first_page(current_url)
            self._scope_element = self.client.get_main_content()
            deep_dive = self._phase3_deep_dive(
                interactive=getattr(self.config, 'guided_p3_interactive', False)
            )
        except Exception as e:
            logger.warning(f"[GuidedAgent] Phase 3 deep dive failed: {e}")
            deep_dive = {}

        # 合并引导探索中扫描到的下拉选项 + 让 _p3_dropdowns 也扫描引导发现的 SELECT 目标
        _guided_dd = getattr(self, '_p3_dropdown_options', {})
        if isinstance(deep_dive, dict):
            _dd = deep_dive.setdefault("dropdowns", {})
            # 引导探索中 _guided_select 扫描到的选项
            for k, v in _guided_dd.items():
                if k not in _dd:
                    _dd[k] = {"options": v, "option_count": len(v)}
            # 对引导探索识别出的 SELECT 目标但 _p3_dropdowns 没覆盖到的, 补扫
            _all_select_targets = set()
            for gs in self._guided_steps:
                at = getattr(gs, 'action_type', '') or gs.get('action_type', '') if isinstance(gs, dict) else ''
                tt = getattr(gs, 'target_text', '') or gs.get('target_text', '') if isinstance(gs, dict) else ''
                if at in ('select', 'SELECT') and tt and tt not in _dd and tt not in _guided_dd:
                    _all_select_targets.add(tt)
            if _all_select_targets:
                logger.info(f"[GuidedAgent] 补扫 {len(_all_select_targets)} 个 SELECT 目标: {_all_select_targets}")
                for _st in _all_select_targets:
                    try:
                        trigger = self.page.get_by_text(_st, exact=False).first
                        if trigger.is_visible():
                            trigger.click(force=True, timeout=2000)
                            self.client.wait(getattr(self.config, 'dropdown_wait', 1.0))
                            found = list(self._scan_dropdown_options())
                            if found:
                                _dd[_st] = {"options": found, "option_count": len(found)}
                                logger.info(f"[GuidedAgent] 补扫 '{_st}' → {len(found)} options: {found[:10]}")
                            self.page.keyboard.press("Escape")
                    except Exception:
                        pass

        # ── 汇总 ──
        elapsed = time.time() - t0
        stats = {
            "total_elements": self.action_count,
            "navigated_elements": sum(1 for e in self._all_element_jumps if e.get("navigated")),
            "pages_explored": len(self._pages_explored),
            "visited_states": len(self.visited_states),
            "elapsed_seconds": round(elapsed, 1),
            "errors": len(self._error_events),
            "guided_steps_total": len(guided_steps),
            "guided_steps_executed": sum(1 for c in self._click_log if c.get("status") != "not_found"),
            "exploration_mode": "guided",
            "platform_type": self.platform_type,
            "interrupted": _interrupted or None,
        }
        logger.info(f"[GuidedAgent] Done: {json.dumps(stats, ensure_ascii=False)}")

        # Phase 4: LLM 文档生成
        phase4 = {}
        if self.llm:
            try:
                phase4 = self._phase4_synthesis(start_url, self._site_map,
                                                self._all_element_jumps, deep_dive)
            except Exception:
                pass

        # 保存文件
        self._save_results(start_url)

        # 序列化 state_graph
        state_graph_dicts = []
        for sn in self._state_graph:
            state_graph_dicts.append({
                "url": sn.url,
                "title": sn.title,
                "fingerprint": sn.fingerprint,
                "actions": sn.actions,
                "children": sn.children,
                "deep_dive": sn.deep_dive,
            })

        # 构建 elements 列表（向后兼容——转换管线检查此键）
        elements_list = []
        for jump in self._all_element_jumps:
            elements_list.append({
                "name": jump.get("name", ""),
                "role": jump.get("role", ""),
                "navigated": jump.get("navigated", False),
                "jump_url": jump.get("jump_url", ""),
            })
        # 也从未跳转的 click_log 补充
        for click in self._click_log:
            if not click.get("navigated") and click.get("name"):
                elements_list.append({
                    "name": click.get("name", ""),
                    "role": click.get("action", ""),
                })

        # 构建 pages 列表（向后兼容——转换管线检查此键）
        pages_list = []
        for url in self._visited_urls:
            pages_list.append({"url": url})

        # 构建步骤诊断列表（供转化管线逐用例报告）
        step_diagnostics = []
        for entry in self._click_log:
            diag = {
                "seq": entry.get("seq", 0),
                "target": entry.get("name", ""),
                "action": entry.get("action", ""),
                "status": entry.get("status", "unknown"),
                "strategy": entry.get("strategy", ""),
                "error": entry.get("error", ""),
                "navigated": entry.get("result") == "jump",
            }
            # 携带探索到的实际页面文本（评分引擎找到的相似/精确匹配文本）
            _act = entry.get("actual_text", "")
            if _act:
                diag["actual_text"] = _act
            step_diagnostics.append(diag)

        return {
            "site_map": self._site_map,
            "element_jumps": {"_main": {"url": start_url, "elements": self._all_element_jumps}},
            "deep_dive": deep_dive,
            "stats": stats,
            "pages_visited": list(self._visited_urls),
            "error_events": self._error_events,
            "state_graph": state_graph_dicts,
            "module_docs": phase4.get("module_docs", ""),
            "site_map_md": phase4.get("site_map_md", ""),
            "page_object_code": phase4.get("page_object_code", ""),
            # 向后兼容键
            "elements": elements_list,
            "pages": pages_list,
            # 步骤诊断
            "step_diagnostics": step_diagnostics,
        }

    # ═══════════════════════════════════════════════════════════
    # 引导探索核心循环
    # ═══════════════════════════════════════════════════════════

    def _run_guided_exploration(self, start_url: str, guided_steps: List, progress_cb=None,
                                cancel_check=None):
        """逐步骤执行引导探索。cancel_check: callable→bool，True=用户取消，立即停止。"""
        c = self.config
        current_url = start_url
        last_success_page = start_url  # 用于恢复（当元素找不到时回到此页）

        # 初始状态
        self._visited_urls.add(self._norm_url_key(current_url))
        self._scope_element = self.client.get_main_content()
        self.client.wait_for_page_ready(max_wait=getattr(c, 'page_ready_timeout', 12.0))
        self.client.scroll_to_load()

        # ── Phase 1 (简化): 收集站点地图（仅 depth=0）──
        site_map = self._phase1_site_map()
        self._site_map = site_map
        self._nav_names = {self._norm(m["name"]) for m in site_map.get("modules", [])}

        self._capture_state("guided_start", current_url)

        for i, gs in enumerate(guided_steps):
            if self.action_count >= c.max_clicks:
                logger.warning(f"[GuidedAgent] 达到最大点击数 {c.max_clicks}，停止")
                break

            # 取消检查：用户点击「取消转化」→ cancel_check()=True → 立即停止探索
            # （上层 finally 会关浏览器，整个生成流程随之结束）
            if cancel_check:
                try:
                    if cancel_check():
                        logger.warning(f"[GuidedAgent] Step {i + 1}: 收到取消信号，停止探索")
                        self._cancelled = True
                        break
                except Exception:
                    pass

            # 进度事件：每步一报（前端进度条在长探索期间保持移动）
            if progress_cb:
                try:
                    progress_cb({"step_done": i + 1, "step_total": len(guided_steps)})
                except Exception:
                    pass

            # 从 GuidedStep 提取字段（兼容 dataclass 和 dict）
            seq, target, role, action_type, fill_value, select_option, context, ui_pattern = \
                self._unpack_step(gs)

            # ── go_back（浏览器后退）：无目标元素，直接后退并等待导航完成 ──
            # 2026-08-23：此前 go_back 无实现，被当 CLICK「()」执行——用例收尾的
            # 「使用 page.go_back() 返回工作台」从不真正后退，页面残留患者详情页，
            # 后续用例全部在错误页面找元素（批量转化 30 条 steps_missing 连锁根因）。
            if action_type in ('go_back', 'GO_BACK'):
                logger.info(f"[GuidedAgent] Step {seq}/{len(guided_steps)}: go_back 后退 "
                            f"url={current_url[-50:]}")
                try:
                    # back_safe 的 target_url 是「后退后期望 URL」——探索器不知道目标，
                    # 用简单 back()（内含 0.8s 等待）；后退后由 wait_for_page_ready + 后续
                    # 步骤的定位/恢复机制兜底页面状态。
                    before_url = self.client.get_url()
                    self.client.back()
                    self.client.wait_for_page_ready(
                        max_wait=getattr(c, 'page_ready_timeout_fast', 8.0)
                    )
                    self.client.scroll_to_load()
                    current_url = self.client.get_url()
                    # 浏览器历史后退可能退回初始 about:blank（new_page 初始页=history[0]，
                    # 2026-08-25 22:02 真机实证：go_back 后整轮探索废在空白页、
                    # 后续所有步骤定位失败）——白屏自愈：回到后退前页面继续探索
                    # （与点击检测段 about:blank 恢复同源）
                    if current_url == "about:blank" and before_url and before_url != "about:blank":
                        try:
                            logger.warning(f"[GuidedAgent] Step {seq}: go_back 后退到 about:blank"
                                           f"（历史栈浅），恢复到后退前 {before_url[-50:]}")
                            self.page.goto(before_url, wait_until="domcontentloaded", timeout=10000)
                            self.client.wait(0.5)
                            current_url = self.client.get_url()
                        except Exception as _ab_e:
                            logger.warning(f"[GuidedAgent] Step {seq}: go_back about:blank 恢复失败: {_ab_e}")
                    if current_url == "about:blank":
                        # 恢复失败也不把空白页写进 last_success_page
                        # （否则后续步骤的恢复目标全是 about:blank，探索整轮作废）
                        current_url = before_url or current_url
                    last_success_page = current_url
                    self._scope_element = self.client.get_main_content()
                    self._click_log.append({
                        "seq": seq, "name": target, "actual_text": "",
                        "action": "go_back", "status": "success",
                        "before": current_url, "after": current_url,
                        "result": "jump", "strategy": "go_back",
                        "error": "",
                    })
                except Exception as _be:
                    logger.warning(f"[GuidedAgent] Step {seq}: go_back 执行失败: {_be}")
                    self._record_step_error(seq, target, 'go_back', 'go_back_failed')
                continue

            if not target:
                logger.info(f"[GuidedAgent] Step {seq}: 跳过（无可定位目标）")
                continue

            logger.info(f"[GuidedAgent] Step {seq}/{len(guided_steps)}: "
                       f"{action_type}:{target[:40] if target else '?'} "
                       f"| role={role} | ui={ui_pattern} | context={context} | url={current_url[-50:]}")

            # ── 1. 定位元素 ──
            # 不传 scope_element：评分引擎在页面全文搜索，scope 限制会漏掉
            # Portal 弹窗、React 浮层等 DOM 节点可能在 <main> 外
            locate_result = self._locator.locate(
                target=target,
                role=role,
                context_hint=context,
                ui_pattern=ui_pattern,
            )

            if not locate_result.found:
                cur_url = self.client.get_url()
                cur_key = self._norm_url_key(cur_url)
                on_success_page = (cur_key == self._norm_url_key(last_success_page))

                if not on_success_page:
                    # 恢复 1: 回到上一个成功页面
                    logger.info(f"[GuidedAgent] Step {seq}: '{target}' not found on {cur_url[-50:]}, "
                               f"recovering to last_success_page")
                    self._return_to_page(last_success_page)
                    if self._norm_url_key(self.client.get_url()) == self._norm_url_key(last_success_page):
                        self.client.wait_for_page_ready(
                            max_wait=getattr(c, 'page_ready_timeout_fast', 8.0)
                        )
                        self.client.scroll_to_load()
                        self._scope_element = self.client.get_main_content()
                        # 2026-08-24 实证：SPA 异步数据（工作台统计卡片「总数」等）未渲染时
                        # 定位必失败——等待目标文本出现后再重试定位
                        if not self._wait_for_target_text(target):
                            logger.info(f"[GuidedAgent] Step {seq}: '{target}' 等待 {getattr(c, 'target_wait_timeout', 6.0)}s 未渲染出现，按原逻辑重试定位")
                        locate_result = self._locator.locate(
                            target=target, role=role, context_hint=context,
                        )
                elif last_success_page != start_url:
                    # 恢复 2: 已在"成功页"但仍然找不到 → 尝试回到模块起始页
                    # 场景：前一步点击导航走了，last_success_page 被更新到新页面，
                    #       但当前步骤的元素在模块起始页上。
                    logger.info(f"[GuidedAgent] Step {seq}: '{target}' not found on success page "
                               f"{cur_url[-50:]}, recovering to module start {start_url[-50:]}")
                    self._return_to_page(start_url)
                    if self._norm_url_key(self.client.get_url()) == self._norm_url_key(start_url):
                        self._scope_element = self.client.get_main_content()
                        self.client.wait_for_page_ready(
                            max_wait=getattr(c, 'page_ready_timeout_fast', 8.0)
                        )
                        self.client.scroll_to_load()
                        # 更新 last_success_page 到起始页（后续步骤从这里开始）
                        last_success_page = start_url
                        if not self._wait_for_target_text(target):
                            logger.info(f"[GuidedAgent] Step {seq}: '{target}' 等待 {getattr(c, 'target_wait_timeout', 6.0)}s 未渲染出现，按原逻辑重试定位")
                        locate_result = self._locator.locate(
                            target=target, role=role, context_hint=context,
                        )
                else:
                    logger.info(f"[GuidedAgent] Step {seq}: '{target}' not found on current page, "
                               f"already at module start '{start_url[-50:]}'")

            if not locate_result.found:
                self._record_step_error(seq, target, action_type, "element_not_found")
                continue

            # ── 2. 执行动作 ──
            before_url = self.client.get_url()
            before_fp = self.client.get_fingerprint_dict()

            # 构建 Action 对象（复用现有 V6 类型）
            action = Action(
                type=self._str_to_action_type(action_type),
                label=target,
                target_text=target,
                target_role=role,
                target_selector=locate_result.element_info.get('selector', ''),
                source=locate_result.strategy,
            )

            # 特殊处理 FILL/SELECT（传值）
            result = self._execute_guided_action(action, gs, locate_result)

            self.client.wait(c.click_wait)

            # ── 3. 检测结果 ──
            # 点击后清理：target=_blank / window.open 会弹新 tab（初始 URL 为 about:blank，
            # 用户看到的「探索中空白页闪现」）——关闭多余页面，保持探索单页
            self._close_extra_pages()
            after_url = self.client.get_url()
            # about:blank 恢复：当前页被 JS 置空/导航失败时回到点击前 URL（白屏自愈）
            if after_url == "about:blank" and before_url and before_url != "about:blank":
                try:
                    logger.warning(f"[GuidedAgent] Step {seq}: 页面变为 about:blank，"
                                   f"恢复到点击前 {before_url[-50:]}")
                    self.page.goto(before_url, wait_until="domcontentloaded", timeout=10000)
                    self.client.wait(0.5)
                    after_url = self.client.get_url()
                except Exception as _ab_e:
                    logger.warning(f"[GuidedAgent] Step {seq}: about:blank 恢复失败: {_ab_e}")
            if after_url == "about:blank":
                # 恢复失败兜底：以点击前 URL 代替空白页（防止 last_success_page/visited_urls
                # 被 about:blank 污染——2026-08-25 22:02 真机实证的连锁作废根因）
                after_url = before_url
            after_fp = self.client.get_fingerprint_dict()
            diff = self._fingerprint_diff(before_fp, after_fp)

            url_changed = (
                self._norm_url_key(after_url) != self._norm_url_key(before_url)
                and after_url != "about:blank"
            )
            overlay = (
                diff is not None
                and before_fp.get("nodes", 0) != after_fp.get("nodes", 0)
            )

            # ── 4. 记录结果 ──
            # 提取探索到的实际页面文本（评分引擎可能找到相似匹配）
            _actual_text = ""
            if locate_result.found and locate_result.element_info:
                _actual_text = (locate_result.element_info.get('text', '') or '').strip()

            jump_result = "jump" if url_changed else ("overlay" if overlay else "static")
            click_entry = {
                "seq": seq,
                "name": target,
                "actual_text": _actual_text,
                "action": action_type,
                "status": "success" if result.success else "failed",
                "before": before_url,
                "after": after_url,
                "result": jump_result,
                "strategy": locate_result.strategy,
                "error": result.error if not result.success else "",
            }
            self._click_log.append(click_entry)

            # ── 追踪日志：记录每步探索情况 ──
            if getattr(self, '_trace', None):
                try:
                    _page_len = self.page.evaluate(
                        "() => document.body ? document.body.innerText.length : 0"
                    )
                except Exception:
                    _page_len = 0
                self._trace.log_step_attempt(
                    seq=seq, target=target, action=action_type,
                    role=role, ui_pattern=ui_pattern or "",
                    found=True,
                    actual_text=_actual_text,
                    strategy=locate_result.strategy,
                    clicked=result.success,
                    url_changed=url_changed,
                    jump_url=after_url if url_changed else "",
                    page_text_len=_page_len,
                    current_url=before_url,
                )

            if url_changed:
                self._capture_state(f"step{seq:03d}_{target[:20]}", after_url)
                self._all_element_jumps.append({
                    "name": target,
                    "actual_text": _actual_text,
                    "clicked": True,
                    "navigated": True,
                    "jump_url": after_url,
                    "role": role,
                    "action_type": action_type,
                    "diff": diff,
                })

                # 记录 StateNode
                self._state_graph.append(StateNode(
                    url=after_url,
                    fingerprint=self.client.get_fingerprint(),
                    actions=[target],
                    children=[],
                ))

                current_url = after_url
                last_success_page = after_url
                self._visited_urls.add(self._norm_url_key(after_url))

                # 更新 scope
                self._scope_element = self.client.get_main_content()
                self.client.wait_for_page_ready(
                    max_wait=getattr(c, 'page_ready_timeout_fast', 8.0)
                )
                self.client.scroll_to_load()

            elif overlay:
                # 弹窗/浮层：交互后关闭
                self._interact_modal()
                try:
                    self.page.keyboard.press("Escape")
                    self.client.wait(0.5)
                except Exception:
                    pass
            else:
                # 静态交互（填表/选下拉/切换 Tab）
                pass
            # 注意: action_count 已由各 handler 内部递增 (_handle_click/_handle_fill 等)
            # 此处不再重复递增，避免重复计数

        # 标记所有访问页面
        self._pages_explored.append({
            "url": start_url,
            "depth": 0,
            "elements": len(guided_steps),
            "jumps": len(self._all_element_jumps),
            "guided": True,
        })

    # ═══════════════════════════════════════════════════════════
    # 单步动作执行
    # ═══════════════════════════════════════════════════════════

    def _execute_guided_action(self, action: Action, gs, locate_result: LocateResult
                               ) -> ActionResult:
        """执行单步引导动作。FILL/SELECT 需要额外传值。"""
        action_type_str = action.type.value if hasattr(action.type, 'value') else str(action.type)

        if action_type_str in ('fill', 'FILL'):
            return self._guided_fill(action, gs, locate_result)

        if action_type_str in ('select', 'SELECT'):
            return self._guided_select(action, gs, locate_result)

        if action_type_str in ('validate', 'VALIDATE', 'wait_for', 'WAIT_FOR'):
            # 验证/等待：不做实际操作，只标记成功
            return ActionResult(action=action, success=True)

        # CLICK / NAVIGATE / TAB_SWITCH / HOVER / RIGHT_CLICK
        # 使用定位结果直接操作——不丢弃 ElementLocator 的成果
        return self._guided_click(action, gs, locate_result)

    def _guided_fill(self, action: Action, gs, locate_result: LocateResult) -> ActionResult:
        """引导式填写：用定位器填入指定值。"""
        fill_value = self._unpack_value(gs, 'fill_value')

        if locate_result.locator and fill_value:
            try:
                locate_result.locator.fill(fill_value)
                return ActionResult(action=action, success=True)
            except Exception as e:
                logger.warning(f"[GuidedAgent] Fill via locator failed: {e}")

        # 回退到 handler
        if fill_value:
            return self._handle_fill(action)

        # 无填充值：使用 config 默认值
        default_val = (getattr(self.config, 'form_fill_values', ['test']) or ['test'])[0]
        try:
            if locate_result.locator:
                locate_result.locator.fill(default_val)
                return ActionResult(action=action, success=True)
        except Exception:
            pass
        return self._handle_fill(action)

    def _guided_select(self, action: Action, gs, locate_result: LocateResult) -> ActionResult:
        """引导式选择：点击 combobox → 等待下拉展开 → 定位选项 → 点击。

        复用旧模式 _select_combobox 的成熟策略：
        - 多选择器回退定位 trigger
        - Portal 选项扫描（Ant Design / Element UI 的 option 在 body 下）
        - 文本包含匹配 + role 匹配
        """
        c = self.config
        select_option = self._unpack_value(gs, 'select_option')

        # ── Step 1: 打开下拉 ──
        # 关键：locate_result.locator 指向的是目标文字（如"房颤预警"标题），
        # 不是下拉触发器（.ant-select-selector）。不能直接 click 标题文字。
        # 必须像旧 POM _warning_filter_trigger 那样：从文字 → 祖先容器 → 找到触发器。
        _trigger_clicked = False
        target = action.target_text

        # 策略0: Playwright 原生 — 用 locate_result 的文字定位，xpath 上溯找触发器
        # 等价于旧 POM: title.locator("xpath=ancestor::*[.//*[contains(@class,'select')]][1]//*[contains(@class,'select')][1]")
        if locate_result.locator:
            try:
                # 检查 locate_result 本身是否就是 trigger（原生 select / role=combobox）
                tag_js = "el => ({tag: el.tagName.toLowerCase(), cls: (el.className||''), role: el.getAttribute('role')||''})"
                info = locate_result.locator.evaluate(tag_js)
                is_trigger = (
                    info['tag'] == 'select'
                    or 'combobox' in info['role']
                    or 'listbox' in info['role']
                    or 'select' in info['cls'].lower()
                    or 'picker' in info['cls'].lower()
                )
                if is_trigger:
                    locate_result.locator.scroll_into_view_if_needed()
                    locate_result.locator.click(force=True, timeout=3000)
                    _trigger_clicked = True
                    logger.info(f"[GuidedAgent] SELECT trigger: locate_result itself is trigger '{target}'")
                else:
                    # locate_result 是标题文字，用 xpath 在同祖先容器内找触发器
                    trigger = locate_result.locator.locator(
                        "xpath=ancestor::*[.//*[contains(@class,'ant-select-selector') "
                        "or contains(@class,'el-select') "
                        "or contains(@class,'ant-cascader') "
                        "or @role='combobox' "
                        "or @role='listbox']][1]"
                        "//*[contains(@class,'ant-select-selector') "
                        "or contains(@class,'el-select__input') "
                        "or @role='combobox' "
                        "or @role='listbox'][1]"
                    ).first
                    if trigger.count() > 0:
                        trigger.scroll_into_view_if_needed()
                        trigger.click(force=True, timeout=3000)
                        _trigger_clicked = True
                        logger.info(f"[GuidedAgent] SELECT trigger: xpath ancestor search from '{target}'")
            except Exception as e:
                logger.debug(f"[GuidedAgent] SELECT trigger strategy0 failed: {e}")

        # 策略1: Playwright — 在 locate_result 所在容器内找 trigger（CSS fallback）
        if not _trigger_clicked and locate_result.locator:
            try:
                trigger = locate_result.locator.locator(
                    "xpath=ancestor::*[self::div or self::li][1]"
                ).first.locator(
                    '[class*="select"]:not([class*="option"]):not([class*="dropdown"]), '
                    '[role="combobox"], [role="listbox"], select'
                ).first
                if trigger.count() > 0 and trigger.is_visible():
                    trigger.click(force=True, timeout=2000)
                    _trigger_clicked = True
                    logger.info(f"[GuidedAgent] SELECT trigger: container CSS from '{target}'")
            except Exception:
                pass

        # 策略2: JS TreeWalker 全页扫描 → 在匹配文字元素的同容器内找触发器
        if not _trigger_clicked:
            try:
                trigger_selectors_js = (
                    '.ant-select-selector, .ant-select, '
                    '[class*="select"]:not([class*="option"]):not([class*="dropdown"]), '
                    '[class*="picker"], [role="combobox"], [role="listbox"], select'
                )
                _trigger_clicked = self.page.evaluate("""
                    (params) => {
                        const text = params.text;
                        const trigSel = params.trigSel;
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                        while (walker.nextNode()) {
                            const el = walker.currentNode;
                            if (el.offsetParent === null) continue;
                            const t = (el.textContent || '').trim();
                            if (t === text || t.startsWith(text)) {
                                // 找到文字元素 → 向上找附近的触发器
                                let ancestor = el;
                                for (let i = 0; i < 8; i++) {
                                    ancestor = ancestor.parentElement;
                                    if (!ancestor) break;
                                    const trigger = ancestor.querySelector(trigSel);
                                    if (trigger) {
                                        trigger.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                        trigger.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                        trigger.click();
                                        return true;
                                    }
                                }
                                // 兜底：点击文字元素本身
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """, {'text': target, 'trigSel': trigger_selectors_js})
            except Exception:
                pass

        # 策略3: CSS 全页回退
        if not _trigger_clicked:
            try:
                fb = getattr(c, 'combobox_fallback', '[class*="select"]')
                trigger = self.page.locator(f'{fb}:has-text("{target}")').first
                if trigger.is_visible():
                    trigger.click(force=True, timeout=2000)
                    _trigger_clicked = True
            except Exception:
                pass

        if _trigger_clicked:
            self.client.wait(c.dropdown_wait)
            logger.info(f"[GuidedAgent] SELECT trigger clicked: '{target}'")
        else:
            logger.warning(f"[GuidedAgent] SELECT trigger ALL strategies failed: '{target}'")

        # ── Step 2: 扫描下拉选项（无论是否指定 select_option 都扫）──
        found_opts = []
        for _retry in range(6):
            self.client.wait(0.5)
            opts = self._scan_dropdown_options()
            if opts:
                found_opts = list(opts)
                break
        if found_opts:
            logger.info(f"[GuidedAgent] SELECT '{action.target_text}' → {len(found_opts)} options: {found_opts[:10]}")
            self._p3_dropdown_options = getattr(self, '_p3_dropdown_options', {})
            self._p3_dropdown_options[action.target_text] = found_opts
        else:
            logger.warning(f"[GuidedAgent] SELECT '{action.target_text}' opened but _scan_dropdown_options returned empty")

        if not select_option:
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            # F36 修复（2026-08-25）：trigger 全部策略失败仍报 success → 探索诊断
            # status=success → 转化方误信「已探索」→ 执行时 select 必失败（假成功）。
            # 未点开下拉如实报失败；点开但无选项也算失败（下拉未展开=交互无效）
            if not _trigger_clicked or not found_opts:
                return ActionResult(
                    action=action, success=False,
                    error=(f"SELECT 触发器定位失败: '{target}'" if not _trigger_clicked
                           else f"SELECT 下拉已点开但未扫描到选项: '{target}'"))
            self.action_count += 1
            return ActionResult(action=action, success=True)

        # ── Step 3: 定位指定选项（多层回退）──
        select_retries = getattr(c, 'select_option_retries', 4)
        select_interval = getattr(c, 'select_option_interval', 0.3)
        opt_fb = getattr(c, 'option_fallback', '[class*="option"]')

        for attempt in range(select_retries):
            try:
                # 策略1: role="option" 精确文本
                opt = self.page.get_by_role("option", name=select_option, exact=True).first
                if opt.is_visible():
                    opt.click(force=True, timeout=2000)
                    logger.info(f"[GuidedAgent] SELECT '{select_option}' via role option")
                    return ActionResult(action=action, success=True)
            except Exception:
                pass

            try:
                # 策略2: 文本包含匹配
                opt = self.page.get_by_text(select_option, exact=False).first
                if opt.is_visible():
                    opt.click(force=True, timeout=2000)
                    logger.info(f"[GuidedAgent] SELECT '{select_option}' via text match")
                    return ActionResult(action=action, success=True)
            except Exception:
                pass

            try:
                # 策略3: option fallback 选择器 + 文本
                opts = self.page.locator(f'[role="option"]:visible, {opt_fb}:visible')
                cnt = opts.count()
                for i in range(min(cnt, 20)):
                    o = opts.nth(i)
                    txt = (o.inner_text() or '').strip()
                    if select_option in txt or txt in select_option:
                        o.click(force=True, timeout=2000)
                        logger.info(f"[GuidedAgent] SELECT '{select_option}' via option fallback")
                        return ActionResult(action=action, success=True)
            except Exception:
                pass

            self.client.wait(select_interval)

        # 关闭下拉
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

        return self._handle_select(action)

    def _guided_click(self, action: Action, gs, locate_result: LocateResult) -> ActionResult:
        """引导式点击：使用 ElementLocator 的定位结果直接操作，不重新搜索。

        三级回退:
          1. locate_result.locator.click() — Playwright Locator（最可靠）
          2. element_info 坐标/选择器 JS 点击 — 评分引擎找到但无法构建 Locator
          3. _handle_click(action) — 基类自愈回退（兜底）
        """
        loc = locate_result.locator
        info = locate_result.element_info

        # ── 第 1 级：有 Playwright Locator，直接点击 ──
        if loc:
            try:
                if loc.is_visible():
                    # target=_blank 链接：移除 target 强制同页导航，防浏览器弹新 tab
                    # （新 tab 初始 URL=about:blank——「探索中空白页闪现」的根因之一）
                    try:
                        loc.evaluate(
                            "el => { if (el.tagName === 'A' && el.getAttribute('target') === '_blank') "
                            "el.removeAttribute('target'); }"
                        )
                    except Exception:
                        pass
                    loc.click(force=True, timeout=3000)
                    self.action_count += 1
                    logger.info(f"[GuidedAgent] Guided click via locator: '{action.label}' "
                               f"strategy={locate_result.strategy}")
                    return ActionResult(action=action, success=True)
            except Exception as e:
                logger.warning(f"[GuidedAgent] Locator click failed for '{action.label}': {e}")

        # ── 第 2 级：只有 element_info（评分引擎返回 scored_info）──
        if info:
            # 2a: 尝试用 info 中的坐标做 JS 点击
            x, y = info.get('x'), info.get('y')
            if x is not None and y is not None and (x > 0 or y > 0):
                try:
                    clicked = self.page.evaluate(f"""
                        (() => {{
                            const el = document.elementFromPoint({x}, {y});
                            if (el) {{ el.click(); return true; }}
                            return false;
                        }})()
                    """)
                    if clicked:
                        self.action_count += 1
                        logger.info(f"[GuidedAgent] Guided click via coords ({x},{y}): "
                                   f"'{action.label}' strategy={locate_result.strategy}")
                        return ActionResult(action=action, success=True)
                except Exception as e:
                    logger.warning(f"[GuidedAgent] Coord click failed: {e}")

            # 2b: 用 info 中的 selector + text 重新尝试
            selector = info.get('selector', '')
            info_text = info.get('text', '')
            if info_text:
                try:
                    el = self.page.get_by_text(info_text, exact=False).first
                    if el.is_visible():
                        el.click(force=True, timeout=2000)
                        self.action_count += 1
                        logger.info(f"[GuidedAgent] Guided click via info_text='{info_text[:30]}'")
                        return ActionResult(action=action, success=True)
                except Exception as e:
                    logger.warning(f"[GuidedAgent] Info text click failed: {e}")
            if selector:
                try:
                    el = self.page.locator(selector).first
                    if el.is_visible():
                        el.click(force=True, timeout=2000)
                        self.action_count += 1
                        logger.info(f"[GuidedAgent] Guided click via info_selector='{selector}'")
                        return ActionResult(action=action, success=True)
                except Exception as e:
                    logger.warning(f"[GuidedAgent] Info selector click failed: {e}")

        # ── 第 3 级：回退到基类 _handle_click（自愈式重搜索）──
        logger.info(f"[GuidedAgent] Falling back to _handle_click for '{action.label}'")
        return self._handle_click(action)

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _unpack_step(self, gs) -> tuple:
        """从 GuidedStep（dataclass 或 dict）提取字段。返回 8 元组，末尾为 ui_pattern。"""
        if hasattr(gs, 'seq'):
            return (
                gs.seq,
                getattr(gs, 'target_text', ''),
                getattr(gs, 'role_hint', ''),
                getattr(gs, 'action_type', 'click'),
                getattr(gs, 'fill_value', ''),
                getattr(gs, 'select_option', ''),
                getattr(gs, 'context_hint', ''),
                getattr(gs, 'ui_pattern', ''),
            )
        elif isinstance(gs, dict):
            return (
                gs.get('seq', 0),
                gs.get('target_text', ''),
                gs.get('role_hint', ''),
                gs.get('action_type', 'click'),
                gs.get('fill_value', ''),
                gs.get('select_option', ''),
                gs.get('context_hint', ''),
                gs.get('ui_pattern', ''),
            )
        return (0, str(gs), '', 'click', '', '', '', '')

    def _unpack_value(self, gs, field: str) -> str:
        """从 GuidedStep 提取值字段。"""
        if hasattr(gs, field):
            return getattr(gs, field, '') or ''
        elif isinstance(gs, dict):
            return gs.get(field, '') or ''
        return ''

    @staticmethod
    def _str_to_action_type(s: str) -> ActionType:
        """字符串 → ActionType 枚举。"""
        mapping = {
            'click': ActionType.CLICK,
            'fill': ActionType.FILL,
            'select': ActionType.SELECT,
            'navigate': ActionType.NAVIGATE,
            'hover': ActionType.HOVER,
            'right_click': ActionType.RIGHT_CLICK,
            'key_press': ActionType.KEY_PRESS,
            'wait_for': ActionType.WAIT_FOR,
            'validate': ActionType.VALIDATE,
            'table_row': ActionType.TABLE_ROW,
            'tab_switch': ActionType.TAB_SWITCH,
            'go_back': ActionType.GO_BACK,
        }
        return mapping.get(s, ActionType.CLICK)

    def _wait_for_target_text(self, target: str, max_wait: float = None) -> bool:
        """等待目标文本渲染出现（SPA 异步数据场景：统计卡片/列表数据接口返回后才渲染）。

        2026-08-24 实证：工作台统计卡片（「总数」等）数据异步加载，探索器在页面
        骨架态（body 文本仅 512 字符）定位必然失败；数据渲染后文本才出现。
        返回 target 是否在页面文本中出现（等不到也返回 False，由恢复逻辑兜底重试定位）。
        """
        if not target:
            return True
        max_wait = max_wait if max_wait is not None else getattr(self.config, 'target_wait_timeout', 6.0)
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                txt = self.page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                ) or ""
                if target in txt:
                    return True
            except Exception:
                pass
            self.client.wait(0.5)
        return False

    def _close_extra_pages(self):
        """关闭探索中弹出的多余页面（target=_blank / window.open 新 tab）。

        新 tab 初始 URL 为 about:blank——用户看到「探索中跳转空白页、过一会恢复」
        的根因。点击后立即清理，保持探索始终单页。
        """
        try:
            ctx = self.page.context
            pages = ctx.pages if ctx else []
            if len(pages) > 1:
                for _p in list(pages):
                    if _p != self.page:
                        try:
                            _p.close()
                        except Exception:
                            pass
                logger.info(f"[GuidedAgent] 已关闭 {len(pages) - 1} 个多余页面（弹窗新 tab）")
        except Exception:
            pass

    def _record_step_error(self, seq: int, target: str, action_type: str, error: str):
        """记录步骤执行错误（含页面上下文，方便用户排查）。"""
        current_url = self.client.get_url()
        # ── 追踪日志：记录未找到的步骤 ──
        if getattr(self, '_trace', None):
            try:
                _pl = self.page.evaluate(
                    "() => document.body ? document.body.innerText.length : 0"
                )
            except Exception:
                _pl = 0
            self._trace.log_step_attempt(
                seq=seq, target=target, action=action_type,
                role="", ui_pattern="",
                found=False,
                page_text_len=_pl,
                current_url=current_url,
            )
        self._error_events.append({
            "stage": f"guided_step_{seq}",
            "error": error,
            "target": target,
            "action": action_type,
            "current_url": current_url,
        })
        self._click_log.append({
            "seq": seq,
            "name": target,
            "actual_text": "",
            "action": action_type,
            "status": "not_found",
            "result": "static",
            "error": error,
            "strategy": "",
            "current_url": current_url,
            "message": f"步骤 {seq}: 未找到「{target}」— 请检查用例描述是否与当前页面匹配",
        })
        logger.warning(f"[GuidedAgent] Step {seq}: {error} - '{target}' @ {current_url[-60:]}")

    def _clean_state_dir(self):
        """清理旧状态目录。"""
        import os as _os
        import shutil as _shutil
        _state_dir = _os.path.abspath(_os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "..", "..", "..", "..", "tests", "exploration", "states", self._module
        ))
        if _os.path.exists(_state_dir):
            try:
                _shutil.rmtree(_state_dir)
            except Exception:
                pass

    def _set_module_boundary(self, url: str):
        """设置模块 URL 边界。"""
        url_key = self._norm_url_key(url)
        if url_key.startswith("/"):
            parts = url_key.split("/")
            self._module_url_root = parts[1] if len(parts) > 1 else url_key.strip("/")
        else:
            from urllib.parse import urlparse as _up
            self._module_url_root = (
                _up(url).path.strip("/").split("/")[0]
                if _up(url).path else url_key
            )
        logger.info(f"[GuidedAgent] Module boundary root=/{self._module_url_root}")

    def _restore_first_page(self, start_url: str):
        """回到起始页（Phase 3 前调用）。"""
        if not start_url:
            return
        try:
            cur = self.client.get_url()
            if self._norm_url_key(cur) != self._norm_url_key(start_url):
                self.client.goto(start_url)
                self.client.wait_for_page_ready(
                    max_wait=getattr(self.config, 'page_ready_timeout_fast', 8.0)
                )
        except Exception as e:
            logger.warning(f"[GuidedAgent] Restore to start page failed: {e}")
