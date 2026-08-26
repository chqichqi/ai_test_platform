"""
Business Flow -> Exploration -> UI Cases orchestration service.
Primary exploration path: see POST /explore-workbench endpoint (business_flow.py).
This service remains for backward compatibility with generate-ui-from-business-flow endpoint.
"""

import json
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.services.llm_service import LLMService
from app.core.services.kg_populator import RUNNING_STALE_SECONDS, KGPopulator
from app.core.models.knowledge_graph import KnowledgeGraph, ExplorationPageSnapshot
from app.core.models.requirement import TestCase as RequirementTestCase, TestCaseStatus, TestCasePriority


UI_GENERATION_SYSTEM_PROMPT = """You are a Web UI automation testing expert. Generate JSON-driven UI test cases based on page exploration results and business flow descriptions.

## Core Rules
1. [MUST] All element references must come from exploration results
2. [MUST] Dropdown option values must come from exploration filter_options
3. [MUST] Test data extracted from page runtime, no hardcoding
4. [MUST] Output JSON data-driven format (action + args + desc)
5. [MUST] Each step action must exist in exploration results

## Output Format
{
  "ui_cases": [
    {
      "case_id": "TC-{module}-0001",
      "title": "Verify {feature}",
      "module": "{module}",
      "steps": [
        {"seq": 1, "action": "goto", "desc": "Navigate to {page}"},
        {"seq": 2, "action": "click", "args": {"name": "{element}"}, "desc": "Click {element}"},
        {"seq": 3, "action": "assert_visible", "args": {"name": "{element}"}, "assert": true, "desc": "Assert visible"}
      ]
    }
  ]
}
"""


class BusinessFlowUIService:

    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)

    @staticmethod
    def _notify(callback, stage: str, message: str, pct: int, total: int, **extra):
        if callback:
            try:
                callback({"stage": stage, "message": message, "progress": pct, "total": total, **extra})
            except Exception:
                pass

    # ========================================================================
    # Main entry point
    # ========================================================================

    async def generate(
        self,
        version_id: int,
        business_flow_text: str,
        project_id: int,
        base_url: str,
        username: str,
        password: str,
        force_explore: bool = False,
        headless: bool = False,
        progress_callback=None,
        debug_skip_explore: bool = False,
    ) -> Dict[str, Any]:
        """Generate UI test cases from business flow text.

        Uses BFS exploration via _generate_with_bfs.
        For the V6 MCP exploration, use the explore-workbench endpoint instead.
        """
        logger.info(f"[BusinessFlowUI] Start: project={project_id}, version={version_id}, text_len={len(business_flow_text)}")
        start_time = datetime.utcnow()

        from app.core.models.project import Project
        from app.core.models.project_ext import ProjectSetting
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"success": False, "error": "Project not found", "ui_cases": []}

        if project.project_type == "app":
            return {"success": False, "error": "APP not supported", "ui_cases": []}

        psetting = self.db.query(ProjectSetting).filter(ProjectSetting.project_id == project_id).first()
        explore_cfg = (psetting.exploration_config or {}).get("web", {}) if psetting else {}
        # 多环境支持
        _env_url = explore_cfg.get("base_url", "")
        if not _env_url and explore_cfg.get("environments"):
            _envs = explore_cfg.get("environments", [])
            _active = explore_cfg.get("active_environment", "")
            _env = next((e for e in _envs if e.get("name") == _active), _envs[0] if _envs else None)
            if _env: _env_url = _env.get("url", "")
        base_url = base_url or _env_url
        username = username or explore_cfg.get("username", "")
        password = password or explore_cfg.get("password", "")

        # CoT extraction
        self._notify(progress_callback, "extracting", "CoT analyzing business flow...", 0, 0)
        test_cases = await self._extract_test_cases(business_flow_text)
        if not test_cases:
            logger.warning("[BusinessFlowUI] CoT extraction failed, falling back to BFS")
            if debug_skip_explore:
                return {
                    "success": False,
                    "error": "CoT extraction failed (LLM returned empty or JSON parse error), check backend logs",
                    "ui_cases": [], "ui_cases_count": 0, "saved_case_ids": [],
                    "explored_modules": [], "elapsed_seconds": (datetime.utcnow() - start_time).total_seconds(),
                }
            self._notify(progress_callback, "fallback", "CoT extraction failed, falling back to BFS...", 10, 0)
            return await self._generate_with_bfs(
                version_id, business_flow_text, project_id, base_url,
                username, password, force_explore, headless, start_time,
                progress_callback,
            )

        logger.info(f"[BusinessFlowUI] CoT extracted {len(test_cases)} cases")
        self._notify(progress_callback, "extracted", f"Extracted {len(test_cases)} cases", 5, len(test_cases))

        # Debug mode: skip exploration
        if debug_skip_explore:
            self._notify(progress_callback, "debug", f"Debug mode: skip exploration, return {len(test_cases)} extracted cases", 100, len(test_cases))
            debug_cases = []
            for c in test_cases:
                debug_cases.append({
                    "case_id": c.get("case_id", ""),
                    "title": c.get("title", ""),
                    "module": c.get("module", ""),
                    "priority": c.get("priority", "medium"),
                    "steps": c.get("steps", []),
                })
            return {
                "success": True,
                "ui_cases": debug_cases,
                "ui_cases_count": len(debug_cases),
                "saved_case_ids": [],
                "explored_modules": [c.get("module", "") for c in test_cases],
                "cached_modules": [],
                "elapsed_seconds": (datetime.utcnow() - start_time).total_seconds(),
                "exploration_method": "cot_debug_skip_explore",
                "debug_raw_cases": test_cases,
            }

        # BFS exploration (V6 MCP exploration available via explore-workbench endpoint)
        logger.info("[BusinessFlowUI] Using BFS exploration...")
        return await self._generate_with_bfs(
            version_id, business_flow_text, project_id, base_url,
            username, password, force_explore, headless, start_time,
            progress_callback,
        )

    # ========================================================================
    # CoT test case extraction
    # ========================================================================

    async def _extract_test_cases(self, text: str) -> List[Dict[str, Any]]:
        """Two-phase extraction: list all UI operations first, then generate test cases."""
        use_text = text[:6000]
        if len(text) > 6000:
            logger.warning(f"[BusinessFlowUI] Text too long ({len(text)} chars), truncated to 6000")

        prompt = f"""You are a test case design expert. Process this business flow document in two phases.

## Business Flow Document
{use_text}

---

## UI Element Naming Convention (CRITICAL)

When naming UI elements in "target" fields, use ONLY the actual visible text on the page, without type descriptors:
- "card", "button", "input", "dropdown", "link", "icon", "menu", "tab", "page" are DESCRIPTORS — do NOT include them in target
- ✅ target="室早" (correct — just the element name)
- ❌ target="室早卡片" (wrong — "卡片" is a descriptor)
- ✅ target="新增" | ❌ target="新增按钮"
- ✅ target="患者姓名" | ❌ target="患者姓名输入框"
- For validation/assertion steps, use action="assert_visible" or action="validate", with target=element name
- The "desc" field can include descriptors for human readability; "target" must be clean
- Each step: exactly ONE UI operation

## Phase 1: Enumerate ALL UI Operations
List every specific UI operation mentioned (use clean element names):

Operation List:
1. Click [clean element name] card -> navigate to [page]
2. ...
(continue until exhaustive)

## Phase 2: Generate Test Cases
For EACH operation, generate a test case in JSON (note: target field = clean element name, desc field = human-readable):

{{"cases": [
  {{"case_id": "TC-0001", "title": "Verify {{operation}}", "module": "{{module}}",
   "priority": "high", "steps": [
    {{"seq": 1, "action": "goto", "desc": "Navigate to page"}},
    {{"seq": 2, "action": "click", "target": "室早", "desc": "Click 室早 card"}},
    {{"seq": 3, "action": "assert_visible", "target": "疾病类型", "desc": "Assert 疾病类型 dropdown visible"}}
  ]}}
]}}

Output ONLY the JSON (no markdown code blocks)."""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(), json_mode=True,
            )
            if not response:
                return []
            return self._extract_cases_from_chunk(response, "generic")
        except Exception as e:
            logger.error(f"[BusinessFlowUI] CoT extraction error: {e}")
            return []

    def _extract_cases_from_chunk(self, chunk_text: str, module_hint: str) -> List[Dict]:
        """Parse LLM response into test case list."""
        try:
            json_str = chunk_text.strip()
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', json_str, re.DOTALL)
            if m:
                json_str = m.group(1)
            else:
                m = re.search(r'\{.*\}', json_str, re.DOTALL)
                if m:
                    json_str = m.group(0)
            data = json.loads(json_str)
            cases = data.get("cases", [])
            for i, c in enumerate(cases):
                c["case_id"] = f"TC-{i+1:03d}"
                c.setdefault("module", "workbench")
                c.setdefault("priority", "medium")
            logger.info(f"[BusinessFlowUI] Extracted {len(cases)} cases")
            return cases
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[BusinessFlowUI] Parse error: {e}")
            return []

    @staticmethod
    def _parse_json_safe(json_str: str) -> Optional[dict]:
        """Safely parse JSON with fixup attempts."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        try:
            fixed = json_str[json_str.index('{'):json_str.rindex('}')+1]
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    # ========================================================================
    # BFS exploration
    # ========================================================================

    async def _generate_with_bfs(
        self, version_id, text, project_id, base_url, username, password,
        force_explore, headless, start_time, progress_callback=None
    ):
        """BFS full exploration -> LLM generate UI cases -> save and return."""
        elapsed = (datetime.utcnow() - start_time).total_seconds()

        # 1. Parse modules
        self._notify(progress_callback, "parsing", "Parsing business flow for modules...", 10, 0)
        modules_info = await self._parse_modules(text)
        if not modules_info:
            return {
                "success": False, "error": "Module parsing failed",
                "ui_cases": [], "ui_cases_count": 0, "saved_case_ids": [],
                "explored_modules": [], "cached_modules": [],
                "elapsed_seconds": elapsed,
            }

        required_modules = list(modules_info.keys())
        required_elements = []
        for elems in modules_info.values():
            required_elements.extend(elems)
        logger.info(f"[BusinessFlowUI] Parsed {len(required_modules)} modules: {required_modules}")

        # 2. Check cache
        self._notify(progress_callback, "cache_check", "Checking exploration cache...", 15, len(required_modules))
        kg_result = self._query_existing_kg(project_id, version_id, required_modules)
        cached = kg_result.get("cached_modules", [])

        if not force_explore and self._coverage_sufficient(kg_result, required_elements):
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            return {
                "success": True, "ui_cases": [], "ui_cases_count": 0, "saved_case_ids": [],
                "explored_modules": cached, "cached_modules": cached,
                "elapsed_seconds": elapsed, "exploration_method": "cached",
            }

        # 3. Explore missing modules
        missing = [m for m in required_modules if m not in cached]
        explored_info = list(cached)
        exploration_results = {}

        if missing:
            self._notify(progress_callback, "exploring",
                         f"Exploring {len(missing)} modules: {', '.join(missing)}...",
                         20, len(required_modules))
            exploration_results = await self._explore_modules(
                missing, base_url, username, password,
                project_id, version_id, headless,
            )
            explored_info.extend(list(exploration_results.keys()))

        for cached_module in cached:
            kg_data = kg_result.get("module_data", {}).get(cached_module, {})
            if kg_data:
                exploration_results[cached_module] = kg_data

        # 4. Generate UI cases
        if exploration_results and self.llm_service:
            self._notify(progress_callback, "generating", "LLM generating UI cases...", 70, len(required_modules))
            result = await self._generate_ui_cases(
                text, exploration_results, project_id, version_id, base_url,
            )
            if isinstance(result, tuple) and len(result) == 2:
                ui_cases, saved_ids = result
            else:
                ui_cases = result if isinstance(result, list) else []
                saved_ids = []
        else:
            ui_cases, saved_ids = [], []

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"[BusinessFlowUI] Done: {len(ui_cases)} UI cases, explored={explored_info}, cached={cached}, elapsed={elapsed:.1f}s")

        return {
            "success": True,
            "ui_cases": ui_cases,
            "ui_cases_count": len(ui_cases),
            "saved_case_ids": saved_ids,
            "explored_modules": explored_info,
            "cached_modules": cached,
            "elapsed_seconds": elapsed,
        }

    # ========================================================================
    # Module parsing
    # ========================================================================

    async def _parse_modules(self, text: str) -> Dict[str, List[str]]:
        """Use LLM to extract module names and required elements from business flow text."""
        if not self.llm_service:
            return self._fallback_parse_modules(text)

        prompt = f"""Extract module names and their required UI elements from this business flow document.
Return JSON: {{"modules": {{"module_name": ["element1", "element2", ...]}}}}

Document:
{text[:4000]}
"""
        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(0.05, 4000), json_mode=True,
            )
            if response:
                data = self._parse_json_safe(response)
                if data and "modules" in data:
                    return data["modules"]
        except Exception as e:
            logger.warning(f"[BusinessFlowUI] Module parsing failed: {e}")
        return self._fallback_parse_modules(text)

    def _fallback_parse_modules(self, text: str) -> Dict[str, List[str]]:
        """Fallback: regex-based module extraction."""
        import re
        modules = {}
        for line in text.split('\n'):
            m = re.match(r'(\S+).*module[：:]', line)
            if m:
                name = m.group(1).strip()
                modules[name] = []
        return modules

    def _query_existing_kg(self, project_id: int, version_id: int, required_modules: List[str]):
        """Query KnowledgeGraph for existing exploration data (project-level, 项目唯一行)."""
        try:
            kg = self.db.query(KnowledgeGraph).filter(
                KnowledgeGraph.project_id == project_id,
                KnowledgeGraph.exploration_status == "completed",
            ).order_by(KnowledgeGraph.completed_at.desc()).first()

            if not kg:
                return {"cached_modules": [], "module_data": {}}

            cached = []
            module_data = {}
            if kg.pages:
                for page in (kg.pages if isinstance(kg.pages, list) else []):
                    if isinstance(page, dict):
                        module_name = page.get("module", "")
                        if module_name in required_modules:
                            cached.append(module_name)
                            module_data[module_name] = page
            return {"cached_modules": cached, "module_data": module_data}
        except Exception as e:
            logger.warning(f"[BusinessFlowUI] KG query failed: {e}")
            return {"cached_modules": [], "module_data": {}}

    def _coverage_sufficient(self, kg_result: Dict, required_elements: List[str]) -> bool:
        """Check if cached exploration data covers required elements."""
        if not required_elements:
            return True
        cached = kg_result.get("cached_modules", [])
        return len(cached) >= len(required_elements) * 0.8

    async def _explore_modules(
        self, module_names, base_url, username, password,
        project_id, version_id, headless=False,
    ) -> Dict[str, Dict]:
        """Execute BFS exploration for missing modules."""
        import concurrent.futures

        def _do_explore():
            import asyncio as _aio
            _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
            loop = _aio.new_event_loop()
            _aio.set_event_loop(loop)
            return loop.run_until_complete(
                self._explore_async(module_names, base_url, username, password,
                                    project_id, version_id, headless)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return await asyncio.get_event_loop().run_in_executor(pool, _do_explore)

    async def _explore_async(self, module_names, base_url, username, password,
                              project_id, version_id, headless):
        """Async exploration using BFSExplorer."""
        from playwright.async_api import async_playwright
        from app.core.services.bfs_explorer import BFSExplorer
        from app.core.services.exploration_config import WebExplorationConfig as ExplorationConfig
        from app.core.services.login_engine import login_with_ui_case
        from app.core.database import SessionLocal

        results = {}
        db = SessionLocal()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=headless,
                    args=["--start-maximized"] if not headless else [],
                )
                ctx = await browser.new_context(
                    viewport={"width": config.viewport_width,
                              "height": config.viewport_height} if not headless else None
                )
                page = await ctx.new_page()

                login_ok, wb_url = await login_with_ui_case(page, base_url, username, password,
                                                            project_id=project_id)
                if not login_ok:
                    logger.error("[BusinessFlowUI] Login failed")
                    return results

                config = ExplorationConfig()
                # BFSExplorer 不再需要 LoginEngine
                explorer = BFSExplorer(page, base_url, config)

                # 并发仲裁：KG running 由其他管线（全站 BFS/手动生成）持有时跳过本次探索，
                # 避免双管线并发写乱同一行（stale-running >2h 视为死任务，允许接管）
                kg = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.project_id == project_id,
                ).first()
                if kg and kg.exploration_status == 'running' and not (
                    kg.started_at and
                    (datetime.utcnow() - kg.started_at).total_seconds() > RUNNING_STALE_SECONDS
                ):
                    logger.info("[BusinessFlowUI] 项目KG探索进行中（running），跳过本次探索")
                    return results

                for module_name in module_names:
                    logger.info(f"[BusinessFlowUI] BFS exploring module: {module_name}")
                    try:
                        result = await explorer.explore_module(module_name)
                        results[module_name] = result
                    except Exception as e:
                        logger.error(f"[BusinessFlowUI] Module '{module_name}' exploration failed: {e}")

                # 登录态：浏览器 storage_state（后续执行/探索直接复用登录态）
                auth_state = None
                try:
                    auth_state = json.loads(json.dumps(await page.context.storage_state()))
                except Exception:
                    pass

                # 统一写路径：KGPopulator.populate 负责创建/复用行、JSON 列 merge、
                # 快照写入与清理、page_count 精确重算、状态仲裁（prev_status + stale 兜底）——
                # 与增量探索器同一写路径，_query_existing_kg 缓存才真正闭环
                populator = KGPopulator(db)
                for module_name, result in results.items():
                    if not result or result.get('error'):
                        continue
                    try:
                        populator.populate(
                            project_id=project_id, version_id=version_id,
                            module_name=module_name,
                            exploration_result={
                                'pages_visited': [
                                    p for p in result.get('pages', []) if isinstance(p, str)
                                ],
                                'site_map': {
                                    'modules': [{
                                        'name': module_name, 'href': '',
                                        'source': 'bfs',
                                    }],
                                },
                                'deep_dive': {
                                    'dropdowns': result.get('filter_options', {}) or {},
                                    'modals': result.get('modals', []) or [],
                                },
                            },
                            base_url=base_url, username=username,
                            auth_data=auth_state,
                            replace_mode='auto',
                            explored_modules=[module_name],
                        )
                    except Exception as e:
                        logger.error(f"[BusinessFlowUI] 模块 '{module_name}' KG 落库失败: {e}")

                # 探索完成：进度置 100（状态与计数已由 populate 仲裁）
                _final_kg = db.query(KnowledgeGraph).filter(
                    KnowledgeGraph.project_id == project_id,
                ).first()
                if _final_kg:
                    _final_kg.progress_percentage = 100
                    db.commit()

            return results
        except Exception as e:
            import traceback as _tb
            logger.error(f"[BusinessFlowUI] Exploration error: {type(e).__name__}: {e}\n{_tb.format_exc()}")
            return results
        finally:
            db.close()

    # ========================================================================
    # UI case generation
    # ========================================================================

    async def _generate_ui_cases(
        self, business_flow_text, exploration_results, project_id, version_id, base_url="",
    ) -> List[Dict[str, Any]]:
        """Inject exploration results into prompt and let LLM generate UI cases."""
        from app.core.services.bfs_explorer import BFSExplorer

        formatted_parts = []
        for module_name, result in exploration_results.items():
            explorer = BFSExplorer.__new__(BFSExplorer)
            formatted = explorer.format_for_llm(result)
            formatted_parts.append(formatted)

        exploration_text = "\n\n---\n\n".join(formatted_parts)

        user_prompt = f"""# Business Flow Description
{business_flow_text[:8000]}

# Page Exploration Results
{exploration_text[:12000]}

# Generation Requirements
Generate UI test cases for each feature in the business flow.
- Steps must strictly reference elements from exploration results
- Output raw JSON (no markdown code blocks)
- Format: {{"ui_cases": [...]}}
"""
        try:
            response = await self.llm_service.async_call_llm(
                prompt=user_prompt,
                system_prompt=UI_GENERATION_SYSTEM_PROMPT,
                temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(), json_mode=True,
            )
            if not response:
                logger.error("[BusinessFlowUI] LLM generation returned empty")
                return []

            ui_cases = self._parse_ui_cases_response(response)
            saved_ids = []
            if ui_cases:
                saved_ids = self._save_ui_cases(ui_cases, project_id, version_id, base_url)

            logger.info(f"[BusinessFlowUI] Generated {len(ui_cases)} UI cases, saved {len(saved_ids)}")
            return ui_cases, saved_ids

        except Exception as e:
            logger.error(f"[BusinessFlowUI] LLM generation failed: {e}")
            return []

    def _parse_ui_cases_response(self, response: str) -> List[Dict]:
        """Parse LLM JSON response into UI case list."""
        try:
            json_str = response.strip()
            m = re.search(r'```(?:json)?\s*(.*?)\s*```', json_str, re.DOTALL)
            if m:
                json_str = m.group(1)
            else:
                m = re.search(r'\{.*\}', json_str, re.DOTALL)
                if m:
                    json_str = m.group(0)

            data = json.loads(json_str)
            cases = data.get("ui_cases", [])
            logger.info(f"[BusinessFlowUI] Parsed {len(cases)} UI cases")
            return cases
        except json.JSONDecodeError as e:
            logger.error(f"[BusinessFlowUI] JSON parse failed: {e}")
            return []

    def _save_ui_cases(self, ui_cases, project_id, version_id, base_url=""):
        """Persist UI test cases to database."""
        saved = 0
        saved_ids = []
        for case in ui_cases:
            try:
                test_case = RequirementTestCase(
                    project_id=project_id,
                    version_id=version_id,
                    title=case.get("title", "Untitled"),
                    module=case.get("module", ""),
                    priority=TestCasePriority(case.get("priority", "medium")),
                    status=TestCaseStatus.DRAFT,
                    source="ai_generated",
                    steps=case.get("steps", []),
                )
                self.db.add(test_case)
                self.db.commit()
                self.db.refresh(test_case)
                # 方案B：新建用例逻辑=物理（logical_case_id=自身id，变更派生时新行共享此 id）
                if not test_case.logical_case_id:
                    test_case.logical_case_id = test_case.id
                    self.db.commit()
                saved_ids.append((test_case.id, None))
                saved += 1
            except Exception as e:
                logger.warning(f"[BusinessFlowUI] Save case failed: {e}")
                self.db.rollback()
        logger.info(f"[BusinessFlowUI] Saved {saved}/{len(ui_cases)} cases")
        return saved_ids
