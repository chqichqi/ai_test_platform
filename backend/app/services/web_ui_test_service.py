"""
WEB UI自动化测试服务
支持将功能测试用例转换为WEB UI自动化测试用例，并执行WEB UI测试
"""

import re
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models.test_simple import TestType, TestStatus
from app.core.models.web_ui_test import (
    WebUITestCase, WebUIElementSelector,
    BrowserType, ViewportSize
)
from app.core.schemas.web_ui_test import (
    FunctionalToWebUITestConversion, WebUITestGenerationResult,
    WebUITestCaseCreate
)
from app.core.logger import logger
from app.core.models.user import User
from app.services.functional_test_service import FunctionalTestService


class WebUITestService:
    """WEB UI测试服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def convert_functional_to_web_ui(
        self,
        conversion_data: FunctionalToWebUITestConversion,
        current_user: User
    ) -> WebUITestGenerationResult:
        """
        将功能测试用例转换为WEB UI测试用例
        
        Args:
            conversion_data: 转换配置数据
            current_user: 当前用户
            
        Returns:
            转换结果
        """
        try:
            logger.info(f"开始转换功能测试用例到WEB UI测试用例: {conversion_data.functional_test_case_id}")
            logger.info(f"Conversion data: {conversion_data.dict()}")

            # 获取功能测试用例（方案B：按【生效行】解析——物理/逻辑 id 均映射到生效行，
            # 派生冻结的旧行不会被取到）
            test_case_id_str = str(conversion_data.functional_test_case_id)
            from app.core.services.case_versioning import load_effective_case
            functional_test_case = load_effective_case(self.db, test_case_id_str)

            if not functional_test_case:
                logger.warning(f"No test case found with ID: {test_case_id_str}")
                return WebUITestGenerationResult(
                    success=False,
                    errors=[f"功能测试用例不存在: {conversion_data.functional_test_case_id}"]
                )
            
            if functional_test_case.test_type != TestType.FUNCTIONAL:
                return WebUITestGenerationResult(
                    success=False,
                    errors=["只能转换功能测试用例"]
                )
            
            # 解析测试步骤
            test_steps = functional_test_case.test_steps
            if test_steps is None or (isinstance(test_steps, list) and len(test_steps) == 0):
                return WebUITestGenerationResult(
                    success=False,
                    errors=["功能测试用例没有测试步骤"]
                )
            
            # 生成元素选择器
            element_selectors = {}
            if conversion_data.generate_element_selectors:
                element_selectors = self._generate_element_selectors(test_steps)
            
            # 生成测试脚本
            test_script = None
            if conversion_data.generate_test_script:
                test_script = self._generate_test_script(
                    test_steps=test_steps,
                    element_selectors=element_selectors,
                    base_url=conversion_data.base_url,
                    browser=conversion_data.browser.value,
                    headless=conversion_data.headless,
                    script_type=conversion_data.script_type,
                    script_language=conversion_data.script_language
                )
            
            # 创建WEB UI测试用例（方案B：WUI 绑定逻辑 id + project_id 透传，与 V2/V1 保存路径同源）
            from app.core.services.case_versioning import wui_binding_id
            _wui_test_case_id = wui_binding_id(self.db, str(functional_test_case.id))
            web_ui_test_case_create = WebUITestCaseCreate(
                test_case_id=_wui_test_case_id,
                project_id=str(functional_test_case.project_id) if functional_test_case.project_id else None,
                base_url=conversion_data.base_url,
                browser=conversion_data.browser,
                viewport_size=conversion_data.viewport_size,
                headless=conversion_data.headless,
                script_type=conversion_data.script_type,
                script_language=conversion_data.script_language,
                element_selectors=element_selectors,
                test_script=test_script
            )
            
            # 保存到数据库
            web_ui_test_case = self._create_web_ui_test_case(
                web_ui_test_case_create, current_user
            )
            
            # 创建元素选择器记录
            if element_selectors:
                self._create_element_selectors(
                    element_selectors, web_ui_test_case.id,
                    functional_test_case.project_id
                )
            
            logger.info(f"成功转换功能测试用例到WEB UI测试用例: {web_ui_test_case.id}")
            
            return WebUITestGenerationResult(
                success=True,
                web_ui_test_case_id=web_ui_test_case.id,
                test_script=test_script,
                element_selectors=element_selectors,
                warnings=self._generate_warnings(test_steps, element_selectors)
            )
            
        except Exception as e:
            logger.error(f"转换功能测试用例到WEB UI测试用例失败: {str(e)}", exc_info=True)
            return WebUITestGenerationResult(
                success=False,
                errors=[f"转换失败: {str(e)}"]
            )
    
    def _generate_element_selectors(self, test_steps: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        从测试步骤生成元素选择器
        
        Args:
            test_steps: 测试步骤列表
            
        Returns:
            元素选择器映射 {元素名称: 选择器}
        """
        element_selectors = {}
        
        for i, step in enumerate(test_steps):
            # 标准化步骤格式
            step_data = self._normalize_test_step(step)
            action = step_data.get('action', '')
            
            # 提取元素名称
            element_name = self._extract_element_name(action, i)
            
            # 生成选择器
            selector = self._generate_selector_from_action(action, element_name)
            
            if element_name and selector:
                element_selectors[element_name] = selector
        
        return element_selectors
    
    def _normalize_test_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """标准化测试步骤格式"""
        # 支持两种格式: {"step": 1, "action": "...", "expected": "..."}
        # 或 {"step_number": 1, "action": "...", "expected_result": "..."}
        normalized = {}
        
        # 步骤编号
        if 'step' in step:
            normalized['step_number'] = step['step']
        elif 'step_number' in step:
            normalized['step_number'] = step['step_number']
        
        # 操作描述
        if 'action' in step:
            normalized['action'] = step['action']
        
        # 预期结果
        if 'expected' in step:
            normalized['expected_result'] = step['expected']
        elif 'expected_result' in step:
            normalized['expected_result'] = step['expected_result']
        
        # 测试数据
        if 'data' in step:
            normalized['data'] = step['data']
        
        return normalized
    
    def _extract_element_name(self, action: str, step_index: int) -> str:
        """
        从操作描述中提取元素名称
        
        Args:
            action: 操作描述
            step_index: 步骤索引
            
        Returns:
            元素名称
        """
        # 常见UI元素关键词
        ui_elements = ['按钮', '链接', '输入框', '文本框', '下拉框', '复选框', '单选框',
                      '表格', '列表', '图片', '图标', '菜单', '选项卡', '弹窗', '对话框',
                      '按钮', '链接', '输入框', '下拉列表', '复选框', '单选框', '滑块',
                      '日期选择器', '时间选择器', '文件上传', '搜索框', '提交按钮',
                      '取消按钮', '确定按钮', '关闭按钮', '下一步按钮', '上一步按钮']
        
        # 查找包含UI元素的描述
        for element in ui_elements:
            if element in action:
                # 提取元素上下文
                pattern = rf'(.{{0,30}}){element}(.{{0,30}})'
                match = re.search(pattern, action)
                if match:
                    context = match.group(0).strip()
                    # 清理上下文
                    context = re.sub(r'[^\w\u4e00-\u9fff]', '_', context)
                    return f"{context}_{step_index + 1}"
        
        # 如果没有找到特定元素，使用通用名称
        # 提取动词后的名词
        verbs = ['点击', '输入', '选择', '勾选', '取消', '拖拽', '滚动', '悬停',
                '验证', '检查', '确认', '等待', '导航', '刷新', '返回']
        
        for verb in verbs:
            if action.startswith(verb):
                # 提取动词后的内容
                rest = action[len(verb):].strip()
                if rest:
                    # 取前20个字符作为名称
                    name = re.sub(r'[^\w\u4e00-\u9fff]', '_', rest[:20])
                    return f"{name}_{step_index + 1}"
        
        # 默认名称
        return f"element_{step_index + 1}"
    
    def _generate_selector_from_action(self, action: str, element_name: str) -> str:
        """
        从操作描述生成选择器
        
        Args:
            action: 操作描述
            element_name: 元素名称
            
        Returns:
            CSS选择器
        """
        # 常见选择器模式 - 基于操作描述
        patterns = [
            # 按钮: text=按钮文本
            (r'点击[「"“]?(.+?)[」"」]?按钮', lambda m: f'button:has-text("{m.group(1)}")'),
            (r'点击(.+?)按钮', lambda m: f'button:has-text("{m.group(1)}")'),
            (r'登录按钮', lambda m: 'button[type="submit"]'),
            (r'提交按钮', lambda m: 'button[type="submit"]'),
            (r'注册按钮', lambda m: 'button:has-text("注册")'),
            
            # 链接: text=链接文本
            (r'点击[「"“]?(.+?)[」"」]?链接', lambda m: f'a:has-text("{m.group(1)}")'),
            (r'点击(.+?)链接', lambda m: f'a:has-text("{m.group(1)}")'),
            
            # 输入框: placeholder或name
            (r'在[「"“]?(.+?)[」"」]?输入框', lambda m: f'input[placeholder*="{m.group(1)}"]'),
            (r'在(.+?)输入框', lambda m: f'input[placeholder*="{m.group(1)}"]'),
            (r'用户名输入框', lambda m: 'input[name="username"], input[type="text"][placeholder*="用户名"], #username'),
            (r'密码输入框', lambda m: 'input[type="password"], input[name="password"], #password'),
            (r'邮箱输入框', lambda m: 'input[type="email"], input[name="email"], #email'),
            (r'搜索框', lambda m: 'input[type="search"], input[name="search"], .search-input'),
            
            # 复选框和单选框
            (r'复选框', lambda m: 'input[type="checkbox"]'),
            (r'单选框', lambda m: 'input[type="radio"]'),
            
            # 下拉框
            (r'下拉框', lambda m: 'select, .dropdown, [role="combobox"]'),
            (r'下拉列表', lambda m: 'select, .dropdown, [role="combobox"]'),
            
            # 通用文本元素
            (r'[「"“](.+?)[」"」]', lambda m: f':has-text("{m.group(1)}")'),
        ]
        
        for pattern, generator in patterns:
            match = re.search(pattern, action, re.IGNORECASE)
            if match:
                return generator(match)
        
        # 基于元素名称生成选择器
        element_lower = element_name.lower()
        
        # 常见元素名称映射
        element_mappings = {
            'username': ['username', 'user', '用户名', '账号'],
            'password': ['password', 'pass', '密码'],
            'email': ['email', '邮箱'],
            'login': ['login', '登录'],
            'submit': ['submit', '提交'],
            'search': ['search', '搜索'],
            'menu': ['menu', '导航', '菜单'],
            'button': ['button', '按钮'],
            'link': ['link', '链接'],
            'input': ['input', '输入框'],
            'form': ['form', '表单'],
        }
        
        for selector_key, keywords in element_mappings.items():
            for keyword in keywords:
                if keyword in element_lower:
                    # 根据元素类型生成选择器
                    if selector_key == 'username':
                        return 'input[name="username"], input[type="text"][placeholder*="用户名"], #username'
                    elif selector_key == 'password':
                        return 'input[type="password"], input[name="password"], #password'
                    elif selector_key == 'email':
                        return 'input[type="email"], input[name="email"], #email'
                    elif selector_key == 'login':
                        return 'button:has-text("登录"), button[type="submit"], #login-btn'
                    elif selector_key == 'submit':
                        return 'button[type="submit"], input[type="submit"], .submit-btn'
                    elif selector_key == 'search':
                        return 'input[type="search"], input[name="search"], .search-input'
                    elif selector_key == 'button':
                        return 'button, .btn, [role="button"]'
                    elif selector_key == 'link':
                        return 'a, [role="link"]'
                    elif selector_key == 'input':
                        return 'input, textarea, select'
                    elif selector_key == 'form':
                        return 'form, .form'
        
        # 默认选择器
        # 如果是中文元素名称，使用data-testid
        if any('\u4e00-\u9fff' in char for char in element_name):
            return f'[data-testid="{element_name}"]'
        else:
            # 清理元素名称作为ID或类名
            clean_name = re.sub(r'[^\w]', '_', element_name)
            return f'#{clean_name}, .{clean_name}'
    
    def _generate_test_script(
        self,
        test_steps: List[Dict[str, Any]],
        element_selectors: Dict[str, str],
        base_url: str,
        browser: str,
        headless: bool,
        script_type: str,
        script_language: str
    ) -> str:
        """
        生成测试脚本
        
        Args:
            test_steps: 测试步骤列表
            element_selectors: 元素选择器映射
            base_url: 基础URL
            browser: 浏览器类型
            headless: 是否无头模式
            script_type: 脚本类型
            script_language: 脚本语言
            
        Returns:
            生成的测试脚本
        """
        # 只支持Playwright
        if script_type != 'playwright':
            script_type = 'playwright'
        
        if script_language == 'javascript':
            return self._generate_playwright_javascript_script(
                test_steps, element_selectors, base_url, browser, headless
            )
        else:
            # 默认使用Playwright Python
            return self._generate_playwright_python_script(
                test_steps, element_selectors, base_url, browser, headless
            )
    
    def _generate_playwright_python_script(
        self,
        test_steps: List[Dict[str, Any]],
        element_selectors: Dict[str, str],
        base_url: str,
        browser: str,
        headless: bool
    ) -> str:
        """生成Playwright Python脚本"""
        script_lines = [
            "import asyncio",
            "from playwright.async_api import async_playwright",
            "",
            "",
            "async def run_test():",
            f'    """自动生成的WEB UI测试脚本 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""',
            "    async with async_playwright() as p:",
            f"        browser = await p.{browser}.launch(headless={headless})",
            "        context = await browser.new_context()",
            "        page = await context.new_page()",
            "",
            f'        print("开始测试: 访问 {base_url}")',
            f'        await page.goto("{base_url}")',
            "",
        ]
        
        # 添加测试步骤
        for i, step in enumerate(test_steps):
            step_data = self._normalize_test_step(step)
            action = step_data.get('action', '')
            expected = step_data.get('expected_result', '')
            step_num = step_data.get('step_number', i + 1)
            
            script_lines.append(f'        # 步骤 {step_num}: {action}')
            
            # 解析操作类型
            if '点击' in action:
                # 查找对应的元素选择器
                element_name = self._extract_element_name(action, i)
                selector = element_selectors.get(element_name, 'button')
                script_lines.append(f'        await page.click("{selector}")')
            
            elif '输入' in action or '填写' in action:
                # 提取输入文本
                text_match = re.search(r'输入[「"“]?(.+?)[」"」]', action)
                if text_match:
                    text = text_match.group(1)
                    element_name = self._extract_element_name(action, i)
                    selector = element_selectors.get(element_name, 'input')
                    script_lines.append(f'        await page.fill("{selector}", "{text}")')
                else:
                    element_name = self._extract_element_name(action, i)
                    selector = element_selectors.get(element_name, 'input')
                    script_lines.append(f'        await page.fill("{selector}", "测试文本")')
            
            elif '验证' in action or '检查' in action or '确认' in action:
                if expected:
                    script_lines.append(f'        # 预期: {expected}')
                    # 简单的文本验证
                    script_lines.append(f'        await page.wait_for_selector(":has-text(\\"{expected}\\")")')
            
            elif '等待' in action:
                script_lines.append('        await page.wait_for_timeout(1000)')
            
            elif '导航' in action or '访问' in action:
                url_match = re.search(r'(https?://\S+|/\S+)', action)
                if url_match:
                    url = url_match.group(0)
                    script_lines.append(f'        await page.goto("{url}")')
            
            else:
                # 默认操作: 等待
                script_lines.append('        await page.wait_for_timeout(500)')
            
            script_lines.append('')
        
        # 添加断言和清理
        script_lines.extend([
            '        # 验证页面加载正常',
            '        await page.wait_for_load_state("networkidle")',
            '',
            '        # 截图保存',
            '        await page.screenshot(path="test_result.png", full_page=True)',
            '        print("测试完成，截图已保存: test_result.png")',
            '',
            '        await browser.close()',
            '',
            "",
            'if __name__ == "__main__":',
            '    asyncio.run(run_test())',
            ""
        ])
        
        return "\n".join(script_lines)
    
    def _generate_playwright_javascript_script(
        self,
        test_steps: List[Dict[str, Any]],
        element_selectors: Dict[str, str],
        base_url: str,
        browser: str,
        headless: bool
    ) -> str:
        """生成Playwright JavaScript脚本"""
        script_lines = [
            "const { chromium } = require('playwright');",
            "",
            f'// 自动生成的WEB UI测试脚本 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            "",
            "(async () => {",
            f"  const browser = await chromium.launch({{ headless: {str(headless).lower()} }});",
            "  const context = await browser.newContext();",
            "  const page = await context.newPage();",
            "",
            f'  console.log("开始测试: 访问 {base_url}");',
            f'  await page.goto("{base_url}");',
            "",
        ]
        
        # 添加测试步骤
        for i, step in enumerate(test_steps):
            step_data = self._normalize_test_step(step)
            action = step_data.get('action', '')
            expected = step_data.get('expected_result', '')
            step_num = step_data.get('step_number', i + 1)
            
            script_lines.append(f'  // 步骤 {step_num}: {action}')
            
            if '点击' in action:
                element_name = self._extract_element_name(action, i)
                selector = element_selectors.get(element_name, 'button')
                script_lines.append(f'  await page.click("{selector}");')
            
            elif '输入' in action or '填写' in action:
                text_match = re.search(r'输入[「"“]?(.+?)[」"」]', action)
                if text_match:
                    text = text_match.group(1)
                    element_name = self._extract_element_name(action, i)
                    selector = element_selectors.get(element_name, 'input')
                    script_lines.append(f'  await page.fill("{selector}", "{text}");')
                else:
                    element_name = self._extract_element_name(action, i)
                    selector = element_selectors.get(element_name, 'input')
                    script_lines.append(f'  await page.fill("{selector}", "测试文本");')
            
            elif '验证' in action or '检查' in action or '确认' in action:
                if expected:
                    script_lines.append(f'  // 预期: {expected}')
                    script_lines.append(f'  await page.waitForSelector(`:has-text("{expected}")`);')
            
            elif '等待' in action:
                script_lines.append('  await page.waitForTimeout(1000);')
            
            elif '导航' in action or '访问' in action:
                url_match = re.search(r'(https?://\S+|/\S+)', action)
                if url_match:
                    url = url_match.group(0)
                    script_lines.append(f'  await page.goto("{url}");')
            
            else:
                script_lines.append('  await page.waitForTimeout(500);')
            
            script_lines.append('')
        
        # 添加断言和清理
        script_lines.extend([
            '  // 验证页面加载正常',
            '  await page.waitForLoadState("networkidle");',
            '',
            '  // 截图保存',
            '  await page.screenshot({ path: "test_result.png", fullPage: true });',
            '  console.log("测试完成，截图已保存: test_result.png");',
            '',
            '  await browser.close();',
            '})();',
            ""
        ])
        
        return "\n".join(script_lines)
    

    
    def _generate_warnings(
        self,
        test_steps: List[Dict[str, Any]],
        element_selectors: Dict[str, str]
    ) -> List[str]:
        """生成警告信息"""
        warnings = []
        
        # 检查测试步骤数量
        if len(test_steps) > 20:
            warnings.append("测试步骤较多，建议拆分为多个测试用例")
        
        # 检查元素选择器覆盖率
        total_steps = len(test_steps)
        if element_selectors:
            coverage = len(element_selectors) / total_steps if total_steps > 0 else 0
            if coverage < 0.5:
                warnings.append(f"元素选择器覆盖率较低 ({coverage:.0%})，可能需要手动调整")
        
        # 检查复杂的操作
        complex_keywords = ['拖拽', '滚动', '悬停', '上传文件', '下载']
        for step in test_steps:
            action = step.get('action', '') if isinstance(step, dict) else ''
            for keyword in complex_keywords:
                if keyword in action:
                    warnings.append(f"包含复杂操作 '{keyword}'，可能需要特殊处理")
                    break
        
        return warnings
    
    def _create_web_ui_test_case(
        self,
        web_ui_test_case_create: WebUITestCaseCreate,
        current_user: User
    ) -> WebUITestCase:
        """创建WEB UI测试用例"""
        # 检查是否已存在（project_id 隔离：跨项目同名 test_case_id 不得互相覆盖）
        _existing_q = self.db.query(WebUITestCase).filter(
            WebUITestCase.test_case_id == web_ui_test_case_create.test_case_id,
            WebUITestCase.deleted_at.is_(None)
        )
        if web_ui_test_case_create.project_id:
            _existing_q = _existing_q.filter(
                WebUITestCase.project_id == str(web_ui_test_case_create.project_id)
            )
        existing = _existing_q.first()
        
        if existing:
            # 更新现有记录
            update_dict = web_ui_test_case_create.model_dump(exclude={'test_case_id'}, exclude_unset=True)
            for field, value in update_dict.items():
                setattr(existing, field, value)
            existing.updated_at = datetime.utcnow()
        else:
            # 创建新记录
            import uuid
            create_dict = web_ui_test_case_create.model_dump()
            # Convert UUID objects to strings for SQLite compatibility
            for key, value in create_dict.items():
                if isinstance(value, uuid.UUID):
                    create_dict[key] = str(value)
            existing = WebUITestCase(**create_dict)
            self.db.add(existing)
        
        self.db.commit()
        self.db.refresh(existing)
        
        return existing
    
    def _create_element_selectors(
        self,
        element_selectors: Dict[str, str],
        web_ui_test_case_id: uuid.UUID,
        project_id: Optional[uuid.UUID] = None
    ):
        """创建元素选择器记录"""
        for element_name, selector in element_selectors.items():
            kwargs = {
                "web_ui_test_case_id": web_ui_test_case_id,
                "element_name": element_name,
                "css_selector": selector
            }
            if project_id is not None:
                kwargs["project_id"] = project_id
            element_selector = WebUIElementSelector(**kwargs)
            self.db.add(element_selector)
        
        self.db.commit()
    
    
    def generate_from_chat(
        self,
        chat_message: str,
        project_name: Optional[str] = None,
        base_url: str = "http://localhost:3000",
        browser: str = "chromium",
        viewport_size: str = "1920x1080",
        headless: bool = True,
        generate_element_selectors: bool = True,
        generate_test_script: bool = True,
        script_type: str = "playwright",
        script_language: str = "python",
        current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        从聊天消息或需求文档生成WEB UI测试用例
        
        Args:
            chat_message: 聊天消息或需求文档内容
            project_name: 项目名称
            base_url: 基础URL
            browser: 浏览器类型
            viewport_size: 视口尺寸
            headless: 是否无头模式
            generate_element_selectors: 是否生成元素选择器
            generate_test_script: 是否生成测试脚本
            script_type: 脚本类型
            script_language: 脚本语言
            current_user: 当前用户
            
        Returns:
            生成的WEB UI测试用例结果
        """
        import sys
        
        try:
            logger.info(f"从聊天生成WEB UI测试用例: {chat_message[:100]}...")
            print(f"[DEBUG] Starting generate_from_chat with message: {chat_message[:100]}...", file=sys.stderr)
            
            # 使用FunctionalTestService生成功能测试用例
            functional_service = FunctionalTestService(self.db)
            functional_result = functional_service.generate_from_chat(
                chat_message=chat_message,
                project_name=project_name,
                user=current_user
            )
            
            if not functional_result.get("success"):
                return WebUITestGenerationResult(
                    success=False,
                    errors=[functional_result.get("message", "生成功能测试用例失败")],
                    warnings=[]
                )
            
            # 获取生成的功能测试用例
            functional_test_cases = functional_result.get("test_cases", [])
            
            if not functional_test_cases:
                return WebUITestGenerationResult(
                    success=False,
                    errors=["未生成任何功能测试用例"],
                    warnings=[]
                )
            
            logger.info(f"生成了 {len(functional_test_cases)} 个功能测试用例，开始转换为WEB UI测试用例")
            print(f"[DEBUG] Generated {len(functional_test_cases)} functional test cases", file=sys.stderr)
            
            paired_cases = []
            all_errors = []
            all_warnings = []
            
            for func_case in functional_test_cases:
                try:
                    # 提取功能测试用例信息
                    title = func_case.get("title", f"WEB UI Test from Chat")
                    description = func_case.get("description", "Generated from chat message")
                    test_steps = func_case.get("test_steps", [])
                    priority = func_case.get("priority", "medium")
                    
                    # 创建功能测试用例记录
                    print(f"[DEBUG] Creating TestCase with title: {title}", file=sys.stderr)
                    
                    # 获取用户ID（确保是字符串）
                    user_id = None
                    if current_user and hasattr(current_user, 'id'):
                        user_id = str(current_user.id)
                    
                    # 创建TestCase - 只使用模型支持的字段
                    test_case = TestCase(
                        title=title,
                        description=description,
                        test_type=TestType.FUNCTIONAL,
                        priority=priority,
                        status=TestStatus.DRAFT,
                        test_steps=test_steps,
                        created_by=user_id if user_id else "system"
                    )
                    self.db.add(test_case)
                    self.db.flush()  # 获取ID但不提交
                    self.db.refresh(test_case)
                    
                    print(f"[DEBUG] Created TestCase with ID: {test_case.id}", file=sys.stderr)
                    
                    # 生成元素选择器
                    element_selectors = {}
                    if generate_element_selectors:
                        element_selectors = self._generate_element_selectors(test_steps)
                    
                    # 生成测试脚本
                    test_script = None
                    if generate_test_script:
                        test_script = self._generate_test_script(
                            test_steps=test_steps,
                            element_selectors=element_selectors,
                            base_url=base_url,
                            browser=browser,
                            headless=headless,
                            script_type=script_type,
                            script_language=script_language
                        )
                    
                    # 解析视口尺寸
                    viewport_width = 1920
                    viewport_height = 1080
                    if viewport_size and 'x' in viewport_size:
                        try:
                            width_str, height_str = viewport_size.split('x')
                            viewport_width = int(width_str)
                            viewport_height = int(height_str)
                        except:
                            pass
                    
                    # 转换浏览器和视口尺寸为枚举类型
                    try:
                        browser_enum = BrowserType[browser.upper()]
                    except KeyError:
                        browser_enum = BrowserType.CHROME
                    
                    try:
                        viewport_enum = ViewportSize[viewport_size.upper()]
                    except KeyError:
                        # 尝试匹配值而不是名称
                        viewport_enum = ViewportSize.DESKTOP_1920x1080
                    
                    print(f"[DEBUG] Creating WebUITestCase for test_case_id: {test_case.id}", file=sys.stderr)
                    
                    # 创建WEB UI测试用例
                    web_ui_case = WebUITestCase(
                        test_case_id=test_case.id,
                        base_url=base_url,
                        browser=browser_enum.value,
                        viewport_size=viewport_enum.value,
                        viewport_width=viewport_width,
                        viewport_height=viewport_height,
                        headless=headless,
                        timeout=30000,
                        screenshot_on_failure=True,
                        screenshot_on_success=False,
                        record_video=False,
                        video_dir=None,
                        test_script=test_script,
                        script_type=script_type,
                        script_language=script_language,
                        element_selectors=element_selectors,
                        test_data={},
                        validation_points=[],
                        performance_metrics={}
                    )
                    self.db.add(web_ui_case)
                    self.db.flush()
                    self.db.refresh(web_ui_case)
                    
                    print(f"[DEBUG] Created WebUITestCase with ID: {web_ui_case.id}", file=sys.stderr)
                    
                    # 创建元素选择器记录
                    if element_selectors:
                        self._create_element_selectors(
                            element_selectors, web_ui_case.id, None
                        )
                    
                    paired_cases.append((test_case, web_ui_case))
                    logger.info(f"成功创建WEB UI测试用例: {test_case.title}")
                    
                except Exception as e:
                    error_msg = f"转换功能测试用例失败: {str(e)}"
                    logger.exception(error_msg)
                    all_errors.append(error_msg)
                    # 回滚当前事务，继续处理下一个
                    self.db.rollback()
                    continue
            
            # 提交所有成功的操作
            if paired_cases:
                self.db.commit()
            
            if not paired_cases:
                return WebUITestGenerationResult(
                    success=False,
                    errors=all_errors,
                    warnings=all_warnings
                )
            
            # 构建响应
            web_ui_test_case_responses = []
            for test_case, web_ui_case in paired_cases:
                # 转换test_case为字典
                test_case_dict = {
                    "id": str(test_case.id),
                    "title": test_case.title,
                    "description": test_case.description,
                    "summary": test_case.summary,
                    "test_type": test_case.test_type.value if hasattr(test_case.test_type, 'value') else test_case.test_type,
                    "priority": test_case.priority.value if hasattr(test_case.priority, 'value') else test_case.priority,
                    "status": test_case.status.value if hasattr(test_case.status, 'value') else test_case.status,
                    "preconditions": test_case.preconditions,
                    "test_steps": test_case.test_steps,
                    "expected_results": test_case.expected_results,
                    "postconditions": test_case.postconditions,
                    "project_id": test_case.project_id,
                    "module": test_case.module,
                    "component": test_case.component,
                    "tags": test_case.tags,
                    "created_by": test_case.created_by,
                    "assigned_to": test_case.assigned_to,
                    "estimated_time": test_case.estimated_time,
                    "actual_time": test_case.actual_time,
                    "execution_count": test_case.execution_count,
                    "last_executed_at": test_case.last_executed_at,
                    "attachments": test_case.attachments,
                    "custom_fields": test_case.custom_fields,
                    "notes": test_case.notes,
                    "created_at": test_case.created_at.isoformat() if test_case.created_at else None,
                    "updated_at": test_case.updated_at.isoformat() if test_case.updated_at else None,
                    "deleted_at": test_case.deleted_at.isoformat() if test_case.deleted_at else None
                }
                # 创建WebUITestCaseResponse
                web_ui_case_dict = web_ui_case.to_dict()
                web_ui_case_dict.pop('test_case', None)
                web_ui_case_response = WebUITestCaseResponse.model_validate(web_ui_case_dict)
                web_ui_case_response.test_case = test_case_dict
                web_ui_test_case_responses.append(web_ui_case_response)
            
            return WebUITestGenerationResult(
                success=True,
                web_ui_test_cases=web_ui_test_case_responses,
                count=len(web_ui_test_case_responses),
                errors=all_errors,
                warnings=all_warnings,
                metadata={
                    "source": "chat",
                    "functional_test_cases_count": len(functional_test_cases),
                    "conversion_rate": f"{len(web_ui_test_case_responses)}/{len(functional_test_cases)}"
                }
            )
            
        except Exception as e:
            logger.error(f"从聊天生成WEB UI测试用例失败: {str(e)}")
            self.db.rollback()
            return WebUITestGenerationResult(
                success=False,
                errors=[f"生成失败: {str(e)}"],
                warnings=[]
            )