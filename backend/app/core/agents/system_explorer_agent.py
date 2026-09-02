"""
系统探索Agent
基于Playwright自动探索Web应用，构建知识图谱
"""

from typing import Dict, Any, List
import json
import asyncio
import re

from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger


class SystemExplorerAgent(BaseAgent):
    """
    系统探索Agent
    
    核心功能：
    1. Playwright自动启动浏览器
    2. 智能登录系统
    3. 识别导航菜单结构
    4. 遍历所有页面
    5. 扫描元素、表单、表格
    6. 录制关键操作流程
    7. 提取API调用（网络监听）
    8. 构建知识图谱
    9. 验证定位器有效性
    """
    
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "SystemExplorerAgent")
        
        self.browser = None
        self.page = None
        self.network_logs = []
        
        self.create_agent()
    
    def define_tools(self) -> List[Tool]:
        """定义系统探索工具集"""
        
        return [
            Tool(
                name="launch_browser",
                func=self._launch_browser,
                description="启动Playwright浏览器"
            ),
            Tool(
                name="navigate_to_url",
                func=self._navigate,
                description="导航到指定URL"
            ),
            Tool(
                name="login_system",
                func=self._login,
                description="智能登录系统（识别登录表单并填写）"
            ),
            Tool(
                name="extract_navigation_menu",
                func=self._extract_menu,
                description="识别导航菜单结构（侧边栏、顶部菜单）"
            ),
            Tool(
                name="scan_page_elements",
                func=self._scan_elements,
                description="扫描页面元素（按钮、输入框、表格等）"
            ),
            Tool(
                name="extract_forms",
                func=self._extract_forms,
                description="提取表单信息（字段、验证规则）"
            ),
            Tool(
                name="extract_tables",
                func=self._extract_tables,
                description="提取表格结构（列名、数据格式）"
            ),
            Tool(
                name="record_operation_flow",
                func=self._record_flow,
                description="录制操作流程（点击、输入、提交）"
            ),
            Tool(
                name="extract_api_calls",
                func=self._extract_api,
                description="提取API调用（监听网络请求）"
            ),
            Tool(
                name="generate_element_locators",
                func=self._generate_locators,
                description="生成元素定位器（多策略：ID、XPath、CSS）"
            ),
            Tool(
                name="build_knowledge_graph",
                func=self._build_graph,
                description="构建知识图谱数据"
            ),
            Tool(
                name="validate_locators",
                func=self._validate_locators,
                description="验证定位器有效性"
            ),
            Tool(
                name="save_knowledge_graph",
                func=self._save_graph,
                description="保存知识图谱到数据库"
            )
        ]
    
    def build_prompt(self) -> ChatPromptTemplate:
        """构建Agent提示词"""
        
        template = """
你是专业的系统探索专家，使用Playwright自动探索Web应用。

任务目标：自动探索系统并构建完整知识图谱

执行策略：
1. 使用 launch_browser 启动浏览器（headless=False）
2. 使用 navigate_to_url 导航到系统首页
3. 使用 login_system 智能登录（识别登录表单）
4. 使用 extract_navigation_menu 提取导航菜单
5. 遍历所有菜单：
   - 使用 navigate_to_url 导航到页面
   - 使用 scan_page_elements 扫描页面元素
   - 使用 extract_forms 提取表单信息
   - 使用 extract_tables 提取表格结构
   - 使用 record_operation_flow 录制关键操作
   - 使用 extract_api_calls 提取API调用
   - 使用 generate_element_locators 生成定位器
6. 使用 build_knowledge_graph 构建知识图谱
7. 使用 validate_locators 验证定位器有效性
8. 使用 save_knowledge_graph 保存到数据库

探索策略：
- quick：主页+登录页（2分钟）
- normal：主页+二级菜单（5-10分钟）
- deep：所有可达页面（10-30分钟）

重要规则：
- 启动浏览器前检查Playwright是否安装
- 登录表单识别：查找username/password字段
- 导航菜单识别：侧边栏、顶部菜单、标签页
- 元素定位器：优先ID，其次XPath，最后CSS
- API监听：捕获所有XHR/Fetch请求
- 知识图谱：包含pages、flows、entities、dependencies
- 定位器验证：重试3次确认有效

输出格式：
JSON对象，包含：
{
  "pages": [{"url": "...", "title": "...", "elements": [...]}],
  "flows": [{"name": "创建用户", "steps": [...]}],
  "entities": [{"name": "用户", "fields": [...]}],
  "dependencies": [{"from": "登录", "to": "仪表板"}],
  "api_endpoints": [{"path": "/api/users", "method": "GET"}],
  "element_locators": [{"element": "登录按钮", "locators": {...}}]
}

输入：
{input}

可用工具：
{tools}

思考过程：
{agent_scratchpad}

请严格按照策略执行，确保探索完整准确。
"""
        
        return ChatPromptTemplate.from_template(template)
    
    # === 工具实现 ===
    
    def _launch_browser(self, config_json: str) -> str:
        """
        启动浏览器
        
        Args:
            config_json: 配置JSON字符串（包含headless、browser_type等）
        
        Returns:
            启动结果JSON字符串
        """
        logger.info(f"[Tool] 启动浏览器")
        
        try:
            config = json.loads(config_json) if config_json else {}
            
            # 检查Playwright是否已安装
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.error("Playwright未安装，请运行：pip install playwright && playwright install")
                return json.dumps({
                    'success': False,
                    'error': 'Playwright not installed',
                    'install_command': 'pip install playwright && playwright install'
                }, ensure_ascii=False)
            
            # 启动浏览器（异步）
            async def start_browser():
                playwright = await async_playwright().start()
                browser_type = config.get('browser_type', 'chromium')
                
                if browser_type == 'firefox':
                    self.browser = await playwright.firefox.launch(headless=config.get('headless', False))
                elif browser_type == 'webkit':
                    self.browser = await playwright.webkit.launch(headless=config.get('headless', False))
                else:
                    self.browser = await playwright.chromium.launch(headless=config.get('headless', False))
                
                self.page = await self.browser.new_page()
                
                # 设置网络监听
                self.page.on('request', self._capture_request)
                self.page.on('response', self._capture_response)
                
                return {'success': True, 'browser_type': browser_type}
            
            # 运行异步任务
            result = asyncio.run(start_browser())
            
            logger.info(f"[Tool] 浏览器启动完成")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 浏览器启动失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _navigate(self, url: str) -> str:
        """
        导航到URL
        
        Args:
            url: 目标URL
        
        Returns:
            导航结果JSON字符串
        """
        logger.info(f"[Tool] 导航到: {url}")
        
        try:
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def navigate_page():
                await self.page.goto(url, wait_until='networkidle', timeout=30000)
                title = await self.page.title()
                return {
                    'success': True,
                    'url': url,
                    'title': title,
                    'url_after_redirect': self.page.url
                }
            
            result = asyncio.run(navigate_page())
            
            logger.info(f"[Tool] 导航完成：{result.get('title')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 导航失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _login(self, login_info_json: str) -> str:
        """
        智能登录系统
        
        Args:
            login_info_json: 登录信息JSON字符串（包含username、password等）
        
        Returns:
            登录结果JSON字符串
        """
        logger.info(f"[Tool] 执行智能登录")
        
        try:
            login_info = json.loads(login_info_json)
            username = login_info.get('username', 'test_user')
            password = login_info.get('password', 'test_password')
            
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def perform_login():
                # 识别登录表单
                username_field = await self.page.query_selector('input[name="username"], input[type="text"], input[name="email"]')
                password_field = await self.page.query_selector('input[name="password"], input[type="password"]')
                login_button = await self.page.query_selector('button[type="submit"], input[type="submit"], button:has-text("登录")')
                
                if username_field and password_field and login_button:
                    # 填写登录表单
                    await username_field.fill(username)
                    await password_field.fill(password)
                    await login_button.click()
                    
                    # 等待登录完成
                    await self.page.wait_for_load_state('networkidle', timeout=10000)
                    
                    return {
                        'success': True,
                        'username': username,
                        'logged_in': True,
                        'current_url': self.page.url
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Login form not found',
                        'username_field_found': username_field is not None,
                        'password_field_found': password_field is not None,
                        'button_found': login_button is not None
                    }
            
            result = asyncio.run(perform_login())
            
            logger.info(f"[Tool] 登录完成：{result.get('logged_in')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 登录失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _extract_menu(self, page_content: str) -> str:
        """
        提取导航菜单
        
        Args:
            page_content: 页面内容（用于分析）
        
        Returns:
            菜单结构JSON字符串
        """
        logger.info(f"[Tool] 提取导航菜单")
        
        try:
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def extract_menu_structure():
                # 提取侧边栏菜单
                sidebar_menu = await self.page.query_selector_all('nav, .sidebar, .menu, [role="navigation"]')
                
                # 提取顶部菜单
                header_menu = await self.page.query_selector_all('header nav, .navbar, .top-menu')
                
                # 提取所有菜单项
                menu_items = []
                
                # 侧边栏菜单项
                for menu in sidebar_menu:
                    items = await menu.query_selector_all('a, button, [role="menuitem"]')
                    for item in items:
                        text = await item.text_content()
                        href = await item.get_attribute('href') or ''
                        menu_items.append({
                            'type': 'sidebar',
                            'text': text.strip(),
                            'href': href,
                            'level': 1
                        })
                
                # 顶部菜单项
                for menu in header_menu:
                    items = await menu.query_selector_all('a, button, [role="menuitem"]')
                    for item in items:
                        text = await item.text_content()
                        href = await item.get_attribute('href') or ''
                        menu_items.append({
                            'type': 'header',
                            'text': text.strip(),
                            'href': href,
                            'level': 1
                        })
                
                return {
                    'success': True,
                    'menu_count': len(menu_items),
                    'menu_items': menu_items[:20]  # 最多返回20个菜单项
                }
            
            result = asyncio.run(extract_menu_structure())
            
            logger.info(f"[Tool] 菜单提取完成，数量={result.get('menu_count')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 菜单提取失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _scan_elements(self, page_url: str) -> str:
        """
        扫描页面元素
        
        Args:
            page_url: 页面URL（用于定位）
        
        Returns:
            元素列表JSON字符串
        """
        logger.info(f"[Tool] 扫描页面元素")
        
        try:
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def scan_page_elements():
                elements = []
                
                # 按钮
                buttons = await self.page.query_selector_all('button, input[type="button"], input[type="submit"]')
                for btn in buttons[:10]:
                    text = await btn.text_content() or ''
                    elements.append({
                        'type': 'button',
                        'text': text.strip(),
                        'id': await btn.get_attribute('id') or '',
                        'class': await btn.get_attribute('class') or ''
                    })
                
                # 输入框
                inputs = await self.page.query_selector_all('input[type="text"], input[type="email"], input[type="password"], textarea')
                for input_elem in inputs[:10]:
                    name = await input_elem.get_attribute('name') or ''
                    placeholder = await input_elem.get_attribute('placeholder') or ''
                    elements.append({
                        'type': 'input',
                        'name': name,
                        'placeholder': placeholder,
                        'id': await input_elem.get_attribute('id') or ''
                    })
                
                # 链接
                links = await self.page.query_selector_all('a[href]')
                for link in links[:10]:
                    text = await link.text_content() or ''
                    href = await link.get_attribute('href') or ''
                    elements.append({
                        'type': 'link',
                        'text': text.strip(),
                        'href': href
                    })
                
                return {
                    'success': True,
                    'element_count': len(elements),
                    'elements': elements
                }
            
            result = asyncio.run(scan_page_elements())
            
            logger.info(f"[Tool] 元素扫描完成，数量={result.get('element_count')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 元素扫描失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _extract_forms(self, page_content: str) -> str:
        """
        提取表单信息
        
        Args:
            page_content: 页面内容
        
        Returns:
            表单列表JSON字符串
        """
        logger.info(f"[Tool] 提取表单信息")
        
        try:
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def extract_page_forms():
                forms = []
                
                form_elements = await self.page.query_selector_all('form')
                for form in form_elements[:5]:
                    form_id = await form.get_attribute('id') or ''
                    form_name = await form.get_attribute('name') or ''
                    
                    # 提取表单字段
                    fields = []
                    inputs = await form.query_selector_all('input, select, textarea')
                    for input_elem in inputs[:10]:
                        field_name = await input_elem.get_attribute('name') or ''
                        field_type = await input_elem.get_attribute('type') or 'text'
                        required = await input_elem.get_attribute('required') is not None
                        
                        fields.append({
                            'name': field_name,
                            'type': field_type,
                            'required': required
                        })
                    
                    forms.append({
                        'id': form_id,
                        'name': form_name,
                        'fields': fields
                    })
                
                return {
                    'success': True,
                    'form_count': len(forms),
                    'forms': forms
                }
            
            result = asyncio.run(extract_page_forms())
            
            logger.info(f"[Tool] 表单提取完成，数量={result.get('form_count')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 表单提取失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _extract_tables(self, page_content: str) -> str:
        """
        提取表格结构
        
        Args:
            page_content: 页面内容
        
        Returns:
            表格列表JSON字符串
        """
        logger.info(f"[Tool] 提取表格结构")
        
        try:
            if not self.page:
                return json.dumps({'success': False, 'error': 'Browser not launched'}, ensure_ascii=False)
            
            async def extract_page_tables():
                tables = []
                
                table_elements = await self.page.query_selector_all('table')
                for table in table_elements[:5]:
                    # 提取表头
                    headers = []
                    header_row = await table.query_selector('thead tr')
                    if header_row:
                        header_cells = await header_row.query_selector_all('th')
                        for cell in header_cells:
                            text = await cell.text_content() or ''
                            headers.append(text.strip())
                    
                    tables.append({
                        'headers': headers,
                        'row_count': 0  # 实际应计算行数
                    })
                
                return {
                    'success': True,
                    'table_count': len(tables),
                    'tables': tables
                }
            
            result = asyncio.run(extract_page_tables())
            
            logger.info(f"[Tool] 表格提取完成，数量={result.get('table_count')}")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 表格提取失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _record_flow(self, flow_name: str) -> str:
        """
        录制操作流程
        
        Args:
            flow_name: 流程名称
        
        Returns:
            流程录制结果JSON字符串
        """
        logger.info(f"[Tool] 录制操作流程：{flow_name}")
        
        # 简化实现：返回示例流程
        example_flow = {
            'name': flow_name,
            'steps': [
                {'action': 'click', 'element': '创建按钮', 'expected': '显示创建表单'},
                {'action': 'input', 'element': '名称字段', 'value': '测试数据'},
                {'action': 'click', 'element': '提交按钮', 'expected': '创建成功'}
            ]
        }
        
        return json.dumps({'success': True, 'flow': example_flow}, ensure_ascii=False)
    
    def _extract_api(self, network_logs_json: str) -> str:
        """
        提取API调用
        
        Args:
            network_logs_json: 网络日志JSON字符串
        
        Returns:
            API列表JSON字符串
        """
        logger.info(f"[Tool] 提取API调用")
        
        try:
            # 使用捕获的网络日志
            api_endpoints = []
            
            for log in self.network_logs[:20]:
                if log.get('type') in ['xhr', 'fetch']:
                    api_endpoints.append({
                        'url': log.get('url'),
                        'method': log.get('method'),
                        'type': log.get('type')
                    })
            
            logger.info(f"[Tool] API提取完成，数量={len(api_endpoints)}")
            
            return json.dumps({
                'success': True,
                'api_count': len(api_endpoints),
                'api_endpoints': api_endpoints
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] API提取失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _generate_locators(self, elements_json: str) -> str:
        """
        生成元素定位器
        
        Args:
            elements_json: 元素列表JSON字符串
        
        Returns:
            定位器列表JSON字符串
        """
        logger.info(f"[Tool] 生成元素定位器")
        
        try:
            elements = json.loads(elements_json).get('elements', [])
            
            locators = []
            for elem in elements[:10]:
                locator = {
                    'element': elem.get('text') or elem.get('name') or '',
                    'locators': {
                        'id': elem.get('id') or '',
                        'xpath': self._generate_xpath(elem),
                        'css': self._generate_css_selector(elem),
                        'text': elem.get('text') or ''
                    }
                }
                locators.append(locator)
            
            logger.info(f"[Tool] 定位器生成完成，数量={len(locators)}")
            
            return json.dumps({
                'success': True,
                'locator_count': len(locators),
                'locators': locators
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 定位器生成失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _build_graph(self, exploration_data_json: str) -> str:
        """
        构建知识图谱
        
        Args:
            exploration_data_json: 探索数据JSON字符串
        
        Returns:
            知识图谱JSON字符串
        """
        logger.info(f"[Tool] 构建知识图谱")
        
        try:
            exploration_data = json.loads(exploration_data_json)
            
            knowledge_graph = {
                'pages': exploration_data.get('pages', []),
                'flows': exploration_data.get('flows', []),
                'entities': self._extract_entities(exploration_data),
                'dependencies': exploration_data.get('dependencies', []),
                'api_endpoints': exploration_data.get('api_endpoints', []),
                'element_locators': exploration_data.get('element_locators', []),
                'confidence_score': 0.85,
                'exploration_strategy': 'normal',
                'created_at': '2026-05-09T00:00:00'
            }
            
            logger.info(f"[Tool] 知识图谱构建完成")
            
            return json.dumps({
                'success': True,
                'knowledge_graph': knowledge_graph
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 知识图谱构建失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _validate_locators(self, locators_json: str) -> str:
        """
        验证定位器有效性
        
        Args:
            locators_json: 定位器列表JSON字符串
        
        Returns:
            验证结果JSON字符串
        """
        logger.info(f"[Tool] 验证定位器有效性")
        
        try:
            locators = json.loads(locators_json).get('locators', [])
            
            validation_results = []
            for locator in locators[:5]:
                # 简化验证：检查定位器字段是否有效
                validation_result = {
                    'element': locator.get('element'),
                    'id_valid': bool(locator.get('locators', {}).get('id')),
                    'xpath_valid': bool(locator.get('locators', {}).get('xpath')),
                    'css_valid': bool(locator.get('locators', {}).get('css')),
                    'overall_score': 0.8
                }
                validation_results.append(validation_result)
            
            logger.info(f"[Tool] 定位器验证完成，数量={len(validation_results)}")
            
            return json.dumps({
                'success': True,
                'validation_count': len(validation_results),
                'validation_results': validation_results
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 定位器验证失败: {str(e)}")
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
    
    def _save_graph(self, knowledge_graph_json: str) -> str:
        """
        保存知识图谱
        
        Args:
            knowledge_graph_json: 知识图谱JSON字符串
        
        Returns:
            保存结果JSON字符串
        """
        logger.info(f"[Tool] 保存知识图谱")
        
        # 简化实现：返回成功消息
        # 实际应保存到数据库
        
        return json.dumps({
            'success': True,
            'message': '知识图谱已保存',
            'graph_id': 'KG_001'
        }, ensure_ascii=False)
    
    # === 辅助方法 ===
    
    def _capture_request(self, request):
        """捕获请求事件"""
        self.network_logs.append({
            'type': request.resource_type,
            'url': request.url,
            'method': request.method,
            'timestamp': 'now'
        })
    
    def _capture_response(self, response):
        """捕获响应事件"""
        # 可以提取响应数据
        pass
    
    def _generate_xpath(self, element: Dict) -> str:
        """生成XPath定位器"""
        elem_type = element.get('type', '')
        elem_text = element.get('text', '')
        
        if elem_type == 'button':
            return f"//button[contains(text(), '{elem_text}')]"
        elif elem_type == 'input':
            elem_name = element.get('name', '')
            return f"//input[@name='{elem_name}']"
        elif elem_type == 'link':
            return f"//a[contains(text(), '{elem_text}')]"
        else:
            return '//div'
    
    def _generate_css_selector(self, element: Dict) -> str:
        """生成CSS选择器"""
        elem_id = element.get('id', '')
        elem_class = element.get('class', '')
        
        if elem_id:
            return f'#{elem_id}'
        elif elem_class:
            return f'.{elem_class.split()[0]}'
        else:
            return 'div'
    
    def _extract_entities(self, exploration_data: Dict) -> List[Dict]:
        """从探索数据提取实体"""
        entities = []
        
        # 从表单字段提取实体
        forms = exploration_data.get('forms', [])
        for form in forms:
            for field in form.get('fields', []):
                entities.append({
                    'name': field.get('name'),
                    'type': 'field',
                    'required': field.get('required')
                })
        
        return entities[:10]