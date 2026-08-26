"""
WebUI测试转换Agent
基于LangChain实现功能测试用例→WebUI自动化脚本的智能转换

核心流程：
1. 解析功能测试步骤
2. 查询知识图谱获取目标系统的页面结构和元素定位器
3. LLM理解步骤语义，映射到UI操作
4. 生成Playwright/Puppeteer/Selenium脚本
5. 保存WebUI测试用例到数据库
"""
from typing import Dict, Any, List, Optional
import json
import re
from uuid import uuid4

from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.knowledge_graph import KnowledgeGraph
from app.core.models.web_ui_test import WebUITestCase, WebUIElementSelector
from app.core.models.test_simple import SimpleTestCase
from app.core.models.requirement import TestCase as ReqTestCase


class WebUITestConversionAgent(BaseAgent):
    """WebUI测试转换Agent — 将功能测试步骤智能转换为Playwright脚本"""

    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "WebUITestConversionAgent")
        self.create_agent()

    def define_tools(self) -> List[Tool]:
        return [
            Tool(
                name="query_knowledge_graph",
                func=self._query_kg,
                description="查询目标系统的知识图谱，获取页面列表、元素定位器和导航流程。输入: project_id"
            ),
            Tool(
                name="get_page_elements",
                func=self._get_page_elements,
                description="获取指定页面的所有元素定位器（按钮、输入框、链接、表格等）。输入格式: {'page_url': '/path', 'project_id': 1}"
            ),
            Tool(
                name="get_navigation_flow",
                func=self._get_navigation_flow,
                description="获取页面间的导航流程，返回操作步骤序列。输入格式: {'from_page': '/login', 'to_page': '/dashboard', 'project_id': 1}"
            ),
            Tool(
                name="map_steps_to_selectors",
                func=self._map_steps_to_selectors,
                description="将功能测试步骤中的自然语言描述映射到页面元素的CSS/XPath选择器。输入: JSON格式的步骤列表和页面元素列表"
            ),
            Tool(
                name="generate_playwright_script",
                func=self._generate_script,
                description="根据映射后的步骤和选择器生成完整Playwright脚本。输入: 步骤映射结果JSON"
            ),
            Tool(
                name="save_web_ui_test_case",
                func=self._save_result,
                description="保存生成的WebUI测试用例和元素选择器到数据库。输入格式: {'test_case_id': 'uuid', 'base_url': '...', 'browser': 'chromium', ...}"
            ),
        ]

    def build_prompt(self) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", """你是WebUI自动化测试专家。你的任务是将功能测试用例转换为Playwright自动化测试脚本。

工作流程：
1. 使用 query_knowledge_graph 获取目标系统的页面结构
2. 使用 get_page_elements 获取相关页面的元素定位器
3. 使用 get_navigation_flow 获取页面跳转流程
4. 使用 map_steps_to_selectors 将功能步骤映射到具体的UI元素
5. 使用 generate_playwright_script 生成完整的测试脚本
6. 使用 save_web_ui_test_case 保存结果

重要规则：
- 优先使用 data-testid、id 等稳定属性作为选择器
- 当无法找到精确元素时，使用文本匹配 text=、has-text()
- 登录等前置操作需要自动处理（从知识图谱获取登录流程）
- 生成的脚本需要包含等待、断言和错误处理
- 变量和测试数据使用有意义的名称
"""),
            ("human", "{input}"),
            ("human", "当前转换上下文: {context}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行WebUI测试转换"""
        context = json.dumps(input_data, ensure_ascii=False, indent=2)
        result = self.agent_executor.invoke({
            "input": f"请将以下功能测试用例转换为WebUI自动化脚本: {json.dumps(input_data.get('test_case', {}), ensure_ascii=False)}",
            "context": context,
        })
        return {"output": result.get("output", ""), "success": True}

    # ===== 工具实现 =====

    def _query_kg(self, input_str: str) -> str:
        """查询知识图谱"""
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
            project_id = data.get("project_id") if isinstance(data, dict) else int(input_str)
        except (ValueError, TypeError):
            return json.dumps({"error": "输入格式错误，需要 project_id"})

        graphs = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
            KnowledgeGraph.exploration_status == "completed"
        ).order_by(KnowledgeGraph.completed_at.desc()).limit(1).all()

        if not graphs:
            return json.dumps({
                "found": False,
                "message": "该项目没有已完成的知识图谱。请先在知识图谱模块中执行系统探索。"
            })

        kg = graphs[0]
        result = {
            "found": True,
            "graph_id": kg.id,
            "base_url": kg.base_url,
            "page_count": kg.page_count,
            "menu_count": kg.menu_count,
            "element_count": kg.element_count,
            "flow_count": kg.flow_count,
            "pages": [{"url": p.get("url", ""), "title": p.get("title", "")}
                      for p in (kg.pages or [])[:20]],
            "menus": kg.menus or [],
            "flows": [{"name": f.get("name", ""), "steps": len(f.get("steps", []))}
                      for f in (kg.flows or [])[:10]],
        }
        return json.dumps(result, ensure_ascii=False)

    def _get_page_elements(self, input_str: str) -> str:
        """获取页面元素"""
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
            page_url = data.get("page_url", "")
            project_id = data.get("project_id")
        except (ValueError, TypeError):
            return json.dumps({"error": "输入格式错误"})

        graphs = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
            KnowledgeGraph.exploration_status == "completed"
        ).order_by(KnowledgeGraph.completed_at.desc()).limit(1).all()

        if not graphs:
            return json.dumps({"found": False, "message": "无知识图谱数据"})

        kg = graphs[0]
        elements_for_page = []
        for elem in (kg.elements or []):
            elem_page = elem.get("page_url", "")
            if page_url in elem_page or elem_page in page_url:
                elements_for_page.append({
                    "name": elem.get("name", elem.get("element_name", "")),
                    "type": elem.get("type", elem.get("element_type", "")),
                    "selector": elem.get("selector", elem.get("primary_locator", "")),
                    "fallback": elem.get("fallback_selectors", elem.get("fallback_locators", [])),
                    "text": elem.get("text", elem.get("text_content", "")),
                    "confidence": elem.get("confidence", elem.get("confidence_score", 0)),
                })

        # Also check pages JSON
        page_elements = []
        for page in (kg.pages or []):
            if page_url in page.get("url", ""):
                page_elements = page.get("elements", [])
                break

        result = {
            "page_url": page_url,
            "total_elements": len(elements_for_page) + len(page_elements),
            "elements": elements_for_page[:50],
        }
        return json.dumps(result, ensure_ascii=False)

    def _get_navigation_flow(self, input_str: str) -> str:
        """获取导航流程"""
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
            from_page = data.get("from_page", "")
            to_page = data.get("to_page", "")
            project_id = data.get("project_id")
        except (ValueError, TypeError):
            return json.dumps({"error": "输入格式错误"})

        graphs = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
            KnowledgeGraph.exploration_status == "completed"
        ).order_by(KnowledgeGraph.completed_at.desc()).limit(1).all()

        if not graphs:
            return json.dumps({"found": False})

        kg = graphs[0]
        matching_flows = []
        for flow in (kg.flows or []):
            steps = flow.get("steps", [])
            for i, step in enumerate(steps):
                if from_page in step.get("from", "") or from_page in step.get("url", ""):
                    matching_flows.append({
                        "flow_name": flow.get("name", ""),
                        "start_index": i,
                        "steps": steps[i:],
                    })
                    break

        result = {
            "from": from_page,
            "to": to_page,
            "matching_flows_count": len(matching_flows),
            "flows": matching_flows[:3],
        }
        return json.dumps(result, ensure_ascii=False)

    def _map_steps_to_selectors(self, input_str: str) -> str:
        """LLM辅助：将功能步骤映射到元素选择器"""
        # 这个工具实际由LLM驱动 — 将功能步骤和页面元素清单传给LLM进行语义匹配
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
        except json.JSONDecodeError:
            data = {"raw_input": input_str}

        # 返回给Agent，由LLM在上下文中完成映射
        return json.dumps({
            "status": "ready_for_llm_mapping",
            "data": data,
            "instruction": "请根据功能步骤中的自然语言描述，匹配到对应的元素选择器。"
                          "例如: '点击登录按钮' → page.click('button[type=\"submit\"]')"
                          "例如: '输入用户名' → page.fill('input[name=\"username\"]', testData.username)"
        }, ensure_ascii=False)

    def _generate_script(self, input_str: str) -> str:
        """生成Playwright脚本"""
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
        except json.JSONDecodeError:
            data = {"raw_input": input_str}

        steps = data.get("steps", data.get("mapped_steps", []))
        base_url = data.get("base_url", "http://localhost:3000")
        test_name = data.get("test_name", "WebUI Test")
        browser = data.get("browser", "chromium")
        headless = data.get("headless", True)
        viewport = data.get("viewport", {"width": 1920, "height": 1080})

        # 生成脚本头部
        script_lines = [
            '"""',
            f'WebUI自动化测试: {test_name}',
            f'由 WebUITestConversionAgent 自动生成',
            f'目标: {base_url}',
            '"""',
            'import asyncio',
            'from playwright.async_api import async_playwright',
            '',
            '',
            'async def run_test():',
            f'    """{test_name}"""',
            '    async with async_playwright() as p:',
            f'        browser = await p.{browser}.launch(headless={str(headless).lower()})',
            f'        context = await browser.new_context(',
            f'            viewport={json.dumps(viewport)}',
            '        )',
            '        page = await context.new_page()',
            '',
            f'        # 导航到目标URL',
            f'        await page.goto("{base_url}")',
            '        await page.wait_for_load_state("networkidle")',
            '',
        ]

        # 生成测试步骤
        for i, step in enumerate(steps):
            action = step.get("action", step.get("ui_action", ""))
            selector = step.get("selector", step.get("css_selector", ""))
            value = step.get("value", step.get("input_value", ""))
            description = step.get("description", f"步骤 {i+1}")

            script_lines.append(f'        # {description}')
            script_lines.append(f'        await page.wait_for_timeout(500)')

            if "导航" in action or "访问" in action or "打开" in action or "goto" in action.lower():
                url = value or step.get("url", base_url)
                script_lines.append(f'        await page.goto("{url}")')
                script_lines.append(f'        await page.wait_for_load_state("networkidle")')
            elif "点击" in action or "click" in action.lower():
                if selector:
                    script_lines.append(f'        await page.click("{selector}")')
                else:
                    script_lines.append(f'        # TODO: 需要提供选择器')
                    script_lines.append(f'        await page.click("text={description}")')
            elif "输入" in action or "填写" in action or "fill" in action.lower() or "type" in action.lower():
                if selector and value:
                    script_lines.append(f'        await page.fill("{selector}", "{value}")')
                elif selector:
                    script_lines.append(f'        await page.fill("{selector}", "测试数据")')
                else:
                    script_lines.append(f'        # TODO: 需要提供选择器和值')
            elif "选择" in action or "select" in action.lower():
                if selector:
                    script_lines.append('        await page.select_option("{}", "{}")'.format(selector, value or ''))
            elif "等待" in action or "wait" in action.lower():
                script_lines.append(f'        await page.wait_for_timeout({value or 1000})')
            elif "断言" in action or "验证" in action or "expect" in action.lower() or "assert" in action.lower():
                if selector:
                    script_lines.append(f'        await page.wait_for_selector("{selector}")')
                    script_lines.append(f'        assert await page.is_visible("{selector}"), f"元素不可见: {selector}"')
                else:
                    script_lines.append(f'        # TODO: 添加断言 - {description}')
            else:
                if selector:
                    script_lines.append(f'        # {action}')
                    script_lines.append(f'        await page.click("{selector}")')

            script_lines.append('')

        # 脚本尾部
        script_lines.extend([
            '        # 测试完成',
            '        print(f"✅ 测试通过: {test_name}")',
            '        await browser.close()',
            '',
            '',
            'if __name__ == "__main__":',
            '    asyncio.run(run_test())',
        ])

        script = '\n'.join(script_lines)

        return json.dumps({
            "script": script,
            "language": "python",
            "framework": "playwright",
            "steps_count": len(steps),
        }, ensure_ascii=False)

    def _save_result(self, input_str: str) -> str:
        """保存WebUI测试用例到数据库"""
        try:
            data = json.loads(input_str) if isinstance(input_str, str) else input_str
        except json.JSONDecodeError:
            return json.dumps({"error": "输入格式错误"})

        test_case_id = data.get("test_case_id", "")
        base_url = data.get("base_url", "http://localhost:3000")
        browser = data.get("browser", "chromium")
        viewport_size = data.get("viewport_size", "1920x1080")
        headless = data.get("headless", True)
        test_script = data.get("test_script", "")
        script_type = data.get("script_type", "playwright")
        script_language = data.get("script_language", "python")
        element_selectors = data.get("element_selectors", {})
        test_data_val = data.get("test_data", {})

        try:
            # 检查是否已存在（方案B：按逻辑 id 兼容历史物理 id 绑定查找）
            from app.core.services.case_versioning import find_existing_wui, wui_binding_id
            existing, _binding_id = find_existing_wui(self.db, project_id, test_case_id)
            test_case_id = wui_binding_id(self.db, test_case_id)

            if existing:
                # 复用已绑定行：(project_id, test_case_id) 唯一约束下重转化不新增行；
                # 派生软删的旧行续命为当前版本
                existing.is_deleted = False
                existing.deleted_at = None
                existing.test_case_id = str(test_case_id)  # 历史物理绑定改写为逻辑 id
                existing.base_url = base_url
                existing.browser = browser
                existing.viewport_size = viewport_size
                existing.headless = headless
                existing.test_script = test_script
                existing.script_type = script_type
                existing.script_language = script_language
                existing.element_selectors = element_selectors
                existing.test_data = test_data_val
                self.db.commit()
                return json.dumps({"saved": True, "id": str(existing.id), "action": "updated"})

            wui = WebUITestCase(
                test_case_id=test_case_id,
                project_id=str(project_id) if project_id else None,
                base_url=base_url,
                browser=browser,
                viewport_size=viewport_size,
                headless=headless,
                test_script=test_script,
                script_type=script_type,
                script_language=script_language,
                element_selectors=element_selectors,
                test_data=test_data_val,
                timeout=30000,
            )
            self.db.add(wui)
            self.db.flush()

            # 保存元素选择器
            for name, selector in element_selectors.items():
                sel = WebUIElementSelector(
                    web_ui_test_case_id=wui.id,
                    element_name=name,
                    css_selector=selector if isinstance(selector, str) else selector.get("primary", ""),
                    primary_locator=selector if isinstance(selector, str) else selector.get("primary", ""),
                    fallback_locators=selector if not isinstance(selector, str) else [selector],
                    page_url=base_url,
                )
                self.db.add(sel)

            self.db.commit()
            return json.dumps({"saved": True, "id": str(wui.id), "action": "created"})

        except Exception as e:
            logger.error(f"保存WebUI测试用例失败: {e}")
            self.db.rollback()
            return json.dumps({"saved": False, "error": str(e)})


def convert_functional_to_web_ui_ai(
    db,
    test_case_id: str,
    base_url: str,
    browser: str = "chromium",
    viewport_size: str = "1920x1080",
    headless: bool = True,
    script_type: str = "playwright",
    script_language: str = "python",
    project_id: int = None,
) -> Dict[str, Any]:
    """
    独立函数：AI驱动的功能→WebUI测试转换

    不依赖LangChain Agent运行时，直接使用LLM和知识图谱进行转换。
    """
    from app.core.models.requirement import TestCase as ReqTestCase
    from app.core.models.test_simple import SimpleTestCase
    from app.core.services.case_versioning import load_effective_case
    from app.core.services.llm_service import LLMService

    # 1. 获取功能测试用例（ReqTestCase 按【生效行】解析——方案B 逻辑 id 绑定）
    test_case = None
    try:
        int(test_case_id)
    except ValueError:
        test_case = db.query(SimpleTestCase).filter(SimpleTestCase.id == test_case_id).first()
    else:
        test_case = load_effective_case(db, test_case_id)

    if not test_case:
        return {"success": False, "error": "功能测试用例不存在"}

    # 1.5 检查项目类型 — APP端不支持 Playwright 转换
    if project_id:
        from app.core.models.project import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if project and project.project_type == "app":
            return {
                "success": False,
                "error": "APP端项目暂不支持转为 WebUI 自动化脚本，请使用WEB端项目。APP端UI转换功能开发中。"
            }

    # 2. 提取测试步骤
    if hasattr(test_case, 'name'):
        case_name = test_case.name
        case_desc = test_case.description or ""
        steps = test_case.test_steps if isinstance(test_case.test_steps, list) else json.loads(test_case.test_steps or "[]")
    else:
        case_name = test_case.title
        case_desc = test_case.description or ""
        steps = test_case.test_steps if isinstance(test_case.test_steps, list) else json.loads(test_case.test_steps or "[]")

    # 3. 查询知识图谱获取页面元素
    kg_elements = []
    if project_id:
        kg = db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
            KnowledgeGraph.exploration_status == "completed"
        ).order_by(KnowledgeGraph.completed_at.desc()).first()

        if kg:
            kg_elements = kg.elements or []
            # 也收集页面中的元素
            for page in (kg.pages or []):
                page_elems = page.get("elements", [])
                kg_elements.extend(page_elems)

    # 4. 构建LLM提示词
    steps_text = "\n".join([
        f"步骤 {s.get('step', i+1)}: {s.get('action', s.get('description', ''))} → 预期: {s.get('expected', '')}"
        for i, s in enumerate(steps)
    ]) if steps else "（无具体步骤，根据用例描述生成）"

    elements_text = "\n".join([
        f"- {e.get('name', e.get('element_name', ''))}: "
        f"类型={e.get('type', e.get('element_type', ''))}, "
        f"选择器={e.get('selector', e.get('primary_locator', ''))}, "
        f"页面={e.get('page_url', '')}"
        for e in kg_elements[:30]
    ]) if kg_elements else "（无知识图谱数据，请根据常识推断元素选择器）"

    prompt = f"""你是一个WebUI自动化测试专家。将功能测试用例转换为 JSON 数据驱动测试步骤（POM模式）。

## 功能测试用例
- 名称: {case_name}
- 描述: {case_desc}
- 前置条件: {getattr(test_case, 'preconditions', '') or '无'}

## 测试步骤
{steps_text}

## 目标系统页面元素（来自知识图谱）
{elements_text}

## 脚本要求
- 使用 Playwright Python async API
- base_url: {base_url}
- 浏览器: {browser}
- 视口: {viewport_size}
- 头模式: {headless}
- 包含适当的等待(wait_for_selector, wait_for_load_state)
- 每个步骤添加断言验证
- 使用 test_data 字典存储测试数据
- 处理登录前置条件（如需要）
- 添加错误处理和截图

## 输出格式
请输出完整的Python脚本，用```python ... ```包裹。同时在脚本前用JSON格式输出步骤到元素选择器的映射关系。

映射格式:
```json
{{"mappings": [{{"step": 1, "action": "点击登录按钮", "selector": "button[type='submit']", "strategy": "css"}}, ...]}}
```
"""

    # 5. 调用LLM
    try:
        llm_service = LLMService(db)
        llm_response = llm_service.call_llm(
            prompt=prompt,
            system_prompt="你是WebUI自动化测试专家。将功能测试用例转换为JSON数据驱动的Pytest测试步骤。只输出JSON。",
            max_tokens=llm_service.get_scaled_max_tokens(),
        )
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        # 不再在此回退规则引擎（原兜底调用签名与 WebUITestService.convert_functional_to_web_ui
        # 不匹配，走到必 TypeError 且无 current_user 可传）——规则引擎兜底统一由端点层
        # （V2/V1 均失败后）调用，返回明确失败让上层决策
        return {
            "success": False,
            "test_case_id": str(test_case_id),
            "case_name": case_name,
            "script": "",
            "error": f"LLM 调用失败: {e}",
        }

    # 6. 解析LLM响应
    script = ""
    mappings = []
    try:
        # 提取JSON映射
        json_match = re.search(r'```json\s*\n(.*?)\n```', llm_response, re.DOTALL)
        if json_match:
            mappings_data = json.loads(json_match.group(1))
            mappings = mappings_data.get("mappings", [])

        # 提取Python脚本
        py_match = re.search(r'```python\s*\n(.*?)\n```', llm_response, re.DOTALL)
        if py_match:
            script = py_match.group(1)
        else:
            script = llm_response
    except Exception as e:
        logger.warning(f"解析LLM响应失败: {e}")
        script = llm_response

    # 7. 构建元素选择器字典
    element_selectors = {}
    for m in mappings:
        name = m.get("action", f"step_{m.get('step', '')}")
        element_selectors[name] = {
            "primary": m.get("selector", ""),
            "strategy": m.get("strategy", "css"),
            "fallback": m.get("fallback", []),
        }

    # 8. 保存到数据库（project_id 存在时按项目隔离查询，防跨项目覆盖同名 ID）
    try:
        # 方案B：按逻辑 id 兼容历史物理 id 绑定查找 + 绑定改写为逻辑 id
        from app.core.services.case_versioning import find_existing_wui, wui_binding_id
        existing, _binding_id = find_existing_wui(db, project_id, test_case_id)
        test_case_id = wui_binding_id(db, test_case_id)

        if existing:
            # 复用已绑定行：(project_id, test_case_id) 唯一约束下重转化不新增行；
            # 派生软删的旧行续命为当前版本
            existing.is_deleted = False
            existing.deleted_at = None
            existing.test_case_id = str(test_case_id)  # 历史物理绑定改写为逻辑 id
            existing.base_url = base_url
            existing.browser = browser
            existing.viewport_size = viewport_size
            existing.headless = headless
            existing.test_script = script
            existing.script_type = script_type
            existing.script_language = script_language
            existing.element_selectors = element_selectors
        else:
            wui = WebUITestCase(
                test_case_id=str(test_case_id),
                project_id=str(project_id) if project_id else None,
                base_url=base_url,
                browser=browser,
                viewport_size=viewport_size,
                headless=headless,
                test_script=script,
                script_type=script_type,
                script_language=script_language,
                element_selectors=element_selectors,
                timeout=30000,
            )
            db.add(wui)

        db.commit()
        saved = True
    except Exception as e:
        logger.error(f"保存失败: {e}")
        db.rollback()
        saved = False

    return {
        "success": True,
        "test_case_id": str(test_case_id),
        "case_name": case_name,
        "script": script,
        "mappings": mappings,
        "element_selectors": element_selectors,
        "saved_to_db": saved,
        "script_type": script_type,
        "script_language": script_language,
    }
