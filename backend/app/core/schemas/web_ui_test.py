"""
WEB UI自动化测试Pydantic模式定义
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict, computed_field
from app.core.models.web_ui_test import BrowserType, ViewportSize


# ========== 枚举模式 ==========

class BrowserTypeEnum(str, Enum):
    """浏览器类型枚举"""
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"
    SAFARI = "safari"
    EDGE = "edge"
    WEBKIT = "webkit"


class ViewportSizeEnum(str, Enum):
    """视口尺寸枚举"""
    DESKTOP_1920x1080 = "1920x1080"
    DESKTOP_1366x768 = "1366x768"
    DESKTOP_1536x864 = "1536x864"
    TABLET_768x1024 = "768x1024"
    TABLET_810x1080 = "810x1080"
    MOBILE_375x667 = "375x667"
    MOBILE_414x896 = "414x896"
    MOBILE_360x640 = "360x640"


# ========== WEB UI测试用例模式 ==========

class WebUITestCaseBase(BaseModel):
    """WEB UI测试用例基础模式"""
    base_url: str = Field(..., min_length=5, max_length=500, description="基础URL")
    browser: BrowserTypeEnum = Field(default=BrowserTypeEnum.CHROME, description="浏览器类型")
    viewport_size: ViewportSizeEnum = Field(default=ViewportSizeEnum.DESKTOP_1920x1080, description="视口尺寸")
    viewport_width: Optional[int] = Field(default=1920, description="视口宽度")
    viewport_height: Optional[int] = Field(default=1080, description="视口高度")
    headless: bool = Field(default=True, description="无头模式")
    timeout: int = Field(default=30000, ge=1000, le=300000, description="超时时间（毫秒）")
    screenshot_on_failure: bool = Field(default=True, description="失败时截图")
    screenshot_on_success: bool = Field(default=False, description="成功时截图")
    record_video: bool = Field(default=False, description="录制视频")
    video_dir: Optional[str] = Field(default=None, max_length=500, description="视频存储目录")
    script_type: str = Field(default="playwright", description="脚本类型")
    script_language: str = Field(default="python", description="脚本语言")
    element_selectors: Optional[Dict[str, Any]] = Field(default=None, description="元素选择器映射")
    test_data: Optional[Dict[str, Any]] = Field(default=None, description="测试数据")
    validation_points: Optional[List[Dict[str, Any]]] = Field(default=None, description="验证点")
    performance_metrics: Optional[Dict[str, Any]] = Field(default=None, description="性能指标")
    
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    
    @field_validator('base_url')
    def validate_base_url(cls, v):
        """验证基础URL"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Base URL must start with http:// or https://')
        return v
    
    @field_validator('viewport_width', 'viewport_height')
    def parse_viewport_size(cls, v, info):
        """解析视口尺寸"""
        if 'viewport_size' in info.data and info.data['viewport_size']:
            viewport_size = info.data['viewport_size']
            try:
                width_str, height_str = viewport_size.split('x')
                if info.field_name == 'viewport_width':
                    return int(width_str)
                elif info.field_name == 'viewport_height':
                    return int(height_str)
            except (ValueError, AttributeError):
                pass
        return v


class WebUITestCaseCreate(WebUITestCaseBase):
    """创建WEB UI测试用例模式"""
    test_case_id: str = Field(..., description="测试用例ID（兼容整数ID和UUID）")
    test_script: Optional[str] = Field(default=None, description="测试脚本")
    project_id: Optional[str] = Field(default=None, description="项目ID（项目隔离：防跨项目覆盖）")


class WebUITestCaseUpdate(BaseModel):
    """更新WEB UI测试用例模式"""
    base_url: Optional[str] = Field(default=None, min_length=5, max_length=500, description="基础URL")
    browser: Optional[BrowserTypeEnum] = Field(default=None, description="浏览器类型")
    viewport_size: Optional[ViewportSizeEnum] = Field(default=None, description="视口尺寸")
    viewport_width: Optional[int] = Field(default=None, description="视口宽度")
    viewport_height: Optional[int] = Field(default=None, description="视口高度")
    headless: Optional[bool] = Field(default=None, description="无头模式")
    timeout: Optional[int] = Field(default=None, ge=1000, le=300000, description="超时时间（毫秒）")
    screenshot_on_failure: Optional[bool] = Field(default=None, description="失败时截图")
    screenshot_on_success: Optional[bool] = Field(default=None, description="成功时截图")
    record_video: Optional[bool] = Field(default=None, description="录制视频")
    video_dir: Optional[str] = Field(default=None, max_length=500, description="视频存储目录")
    test_script: Optional[str] = Field(default=None, description="测试脚本")
    script_type: Optional[str] = Field(default=None, description="脚本类型")
    script_language: Optional[str] = Field(default=None, description="脚本语言")
    element_selectors: Optional[Dict[str, Any]] = Field(default=None, description="元素选择器映射")
    test_data: Optional[Dict[str, Any]] = Field(default=None, description="测试数据")
    validation_points: Optional[List[Dict[str, Any]]] = Field(default=None, description="验证点")
    performance_metrics: Optional[Dict[str, Any]] = Field(default=None, description="性能指标")
    
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class WebUITestCaseInDB(WebUITestCaseBase):
    """数据库中的WEB UI测试用例模式"""
    id: UUID
    test_case_id: str  # 兼容整数ID和UUID
    test_script: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class WebUITestCaseResponse(WebUITestCaseInDB):
    """WEB UI测试用例响应模式"""
    test_case: Optional[Dict[str, Any]] = None
    # 功能用例前置条件：由 endpoint 从原功能用例原文兜底，
    # 不依赖 LLM 是否把它写进 test_data。
    preconditions: Optional[str] = None
    # 声明 ORM 字段供 model_validate 透传（前端详情展示按生成模式区分 V1/V2）
    generation_mode: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def test_steps(self) -> Optional[List[Dict[str, Any]]]:
        """前端展示用：从 test_data(V2) 或 test_script(V1) 提取，归一化字段名"""
        raw = None
        mode = getattr(self, 'generation_mode', '') or ''

        if isinstance(self.test_data, dict) and 'steps' in self.test_data:
            raw = self.test_data['steps']
            mode = 'pom_data_driven'
        elif self.test_script:
            import json, re
            try:
                cleaned = re.sub(r'^```(?:json|python|javascript)?\s*', '', self.test_script.strip())
                cleaned = re.sub(r'\s*```$', '', cleaned)
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and 'steps' in parsed:
                    raw = parsed['steps']
            except (json.JSONDecodeError, TypeError):
                pass

        if not raw:
            return None

        normalized = []
        for s in raw:
            if not isinstance(s, dict):
                continue
            step = dict(s)

            if mode == 'pom_data_driven' and step.get('desc'):
                tech = step.get('action', '')
                desc = step['desc']
                args = step.get('args', {})

                # ── 操作步骤：描述 + [技术动作(参数)] ──
                args_str = ''
                if isinstance(args, dict) and args:
                    args_str = ', '.join(f'{k}={v}' for k, v in args.items())
                if args_str:
                    step['action'] = f"{desc}  [{tech}({args_str})]"
                else:
                    step['action'] = f"{desc}  [{tech}]"

                # ── 预期结果：从动作类型推导 ──
                if 'expected' not in step or not step['expected']:
                    if tech == 'goto':
                        target = desc.replace('进入', '').replace('返回', '').replace('页面', '').strip()
                        step['expected'] = f"成功跳转至{target}页面" if target else "页面跳转成功"
                    elif tech.startswith('assert_'):
                        # assert 类：desc 就是期望结果，去掉"验证"前缀
                        step['expected'] = desc.replace('验证', '').replace('确认', '').replace('检查', '').strip()
                    elif tech.startswith('click_') or tech == 'click':
                        step['expected'] = '点击成功，元素响应'
                    elif tech in ('get_all_items', 'get_selected_items', 'get_dropdown_options',
                                  'get_first_row_data', 'check_data_exists'):
                        save = step.get('save_as', '')
                        step['expected'] = f"成功获取数据" + (f"，保存为 ${save}" if save else "")
                    elif tech == 'wait_for_render':
                        step['expected'] = '页面渲染完成'
                    elif tech == 'scroll_to_bottom':
                        step['expected'] = '滚动至页面底部'
                    elif tech == 'skip_if_empty':
                        step['expected'] = '数据为空时跳过后续步骤'
                    elif tech == 'guard_dynamic_data':
                        step['expected'] = '动态数据为空时跳过本用例'
                    elif tech == 'click_dynamic_item':
                        step['expected'] = '点击动态数据区中的真实可操作数据项'
                    elif tech == 'foreach':
                        step['expected'] = '遍历列表，每项执行子步骤'
                    elif desc:
                        step['expected'] = desc
                    else:
                        step['expected'] = '-'
            else:
                # V1 / 非标准格式
                if 'expected' not in step:
                    step['expected'] = step.get('expected_result', '-')

            normalized.append(step)
        return normalized

    @field_validator('test_case', mode='before')
    @classmethod
    def coerce_test_case(cls, v):
        """将 ORM 对象转为 dict"""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        # ORM 对象 → 手动提取字段
        if hasattr(v, '__dict__'):
            return {
                'id': str(getattr(v, 'id', '')),
                'title': getattr(v, 'title', '') or getattr(v, 'name', ''),
                'description': getattr(v, 'description', '') or '',
                'test_type': getattr(v, 'test_type', 'functional'),
                'priority': getattr(v, 'priority', 'P2'),
                'status': getattr(v, 'status', 'draft'),
                'module': getattr(v, 'module', ''),
                'project_id': getattr(v, 'project_id', None),
            }
        return v


# ========== WEB UI测试执行模式 ==========

class WebUITestExecutionBase(BaseModel):
    """WEB UI测试执行基础模式"""
    start_url: Optional[str] = Field(default=None, max_length=500, description="实际开始的URL")
    final_url: Optional[str] = Field(default=None, max_length=500, description="最终的URL")
    page_count: Optional[int] = Field(default=0, description="访问的页面数量")
    network_requests: Optional[int] = Field(default=0, description="网络请求数量")
    dom_size: Optional[int] = Field(default=0, description="DOM大小")
    load_time: Optional[float] = Field(default=None, description="页面加载时间（秒）")
    first_contentful_paint: Optional[float] = Field(default=None, description="首次内容绘制时间（秒）")
    largest_contentful_paint: Optional[float] = Field(default=None, description="最大内容绘制时间（秒）")
    cumulative_layout_shift: Optional[float] = Field(default=None, description="累积布局偏移")
    first_input_delay: Optional[float] = Field(default=None, description="首次输入延迟（秒）")
    screenshots: Optional[List[Dict[str, str]]] = Field(default=None, description="截图信息")
    video_path: Optional[str] = Field(default=None, description="视频文件路径")
    console_logs: Optional[List[Dict[str, Any]]] = Field(default=None, description="控制台日志")
    network_logs: Optional[List[Dict[str, Any]]] = Field(default=None, description="网络日志")
    browser_console_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="浏览器控制台错误")
    network_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="网络错误")
    javascript_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="JavaScript错误")
    
    model_config = ConfigDict(from_attributes=True)


class WebUITestExecutionCreate(WebUITestExecutionBase):
    """创建WEB UI测试执行模式"""
    test_execution_id: UUID = Field(..., description="测试执行ID")


class WebUITestExecutionUpdate(BaseModel):
    """更新WEB UI测试执行模式"""
    start_url: Optional[str] = Field(default=None, max_length=500, description="实际开始的URL")
    final_url: Optional[str] = Field(default=None, max_length=500, description="最终的URL")
    page_count: Optional[int] = Field(default=None, description="访问的页面数量")
    network_requests: Optional[int] = Field(default=None, description="网络请求数量")
    dom_size: Optional[int] = Field(default=None, description="DOM大小")
    load_time: Optional[float] = Field(default=None, description="页面加载时间（秒）")
    first_contentful_paint: Optional[float] = Field(default=None, description="首次内容绘制时间（秒）")
    largest_contentful_paint: Optional[float] = Field(default=None, description="最大内容绘制时间（秒）")
    cumulative_layout_shift: Optional[float] = Field(default=None, description="累积布局偏移")
    first_input_delay: Optional[float] = Field(default=None, description="首次输入延迟（秒）")
    screenshots: Optional[List[Dict[str, str]]] = Field(default=None, description="截图信息")
    video_path: Optional[str] = Field(default=None, description="视频文件路径")
    console_logs: Optional[List[Dict[str, Any]]] = Field(default=None, description="控制台日志")
    network_logs: Optional[List[Dict[str, Any]]] = Field(default=None, description="网络日志")
    browser_console_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="浏览器控制台错误")
    network_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="网络错误")
    javascript_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="JavaScript错误")
    
    model_config = ConfigDict(from_attributes=True)


class WebUITestExecutionInDB(WebUITestExecutionBase):
    """数据库中的WEB UI测试执行模式"""
    id: UUID
    test_execution_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class WebUITestExecutionResponse(WebUITestExecutionInDB):
    """WEB UI测试执行响应模式"""
    test_execution: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


# ========== WEB UI元素选择器模式 ==========

class WebUIElementSelectorBase(BaseModel):
    """WEB UI元素选择器基础模式"""
    element_name: str = Field(..., min_length=2, max_length=200, description="元素名称")
    element_description: Optional[str] = Field(default=None, description="元素描述")
    page_url: Optional[str] = Field(default=None, max_length=500, description="页面URL")
    page_title: Optional[str] = Field(default=None, max_length=200, description="页面标题")
    css_selector: Optional[str] = Field(default=None, max_length=500, description="CSS选择器")
    xpath: Optional[str] = Field(default=None, max_length=500, description="XPath")
    test_id: Optional[str] = Field(default=None, max_length=200, description="data-testid属性")
    aria_label: Optional[str] = Field(default=None, max_length=200, description="aria-label属性")
    text_content: Optional[str] = Field(default=None, max_length=500, description="文本内容")
    alternative_selectors: Optional[List[Dict[str, str]]] = Field(default=None, description="备用选择器")
    is_visible: bool = Field(default=True, description="元素是否可见")
    is_enabled: bool = Field(default=True, description="元素是否启用")
    expected_text: Optional[str] = Field(default=None, max_length=500, description="期望的文本内容")
    
    model_config = ConfigDict(from_attributes=True)


class WebUIElementSelectorCreate(WebUIElementSelectorBase):
    """创建WEB UI元素选择器模式"""
    web_ui_test_case_id: UUID = Field(..., description="WEB UI测试用例ID")
    project_id: Optional[UUID] = Field(default=None, description="项目ID")


class WebUIElementSelectorUpdate(BaseModel):
    """更新WEB UI元素选择器模式"""
    element_name: Optional[str] = Field(default=None, min_length=2, max_length=200, description="元素名称")
    element_description: Optional[str] = Field(default=None, description="元素描述")
    page_url: Optional[str] = Field(default=None, max_length=500, description="页面URL")
    page_title: Optional[str] = Field(default=None, max_length=200, description="页面标题")
    css_selector: Optional[str] = Field(default=None, max_length=500, description="CSS选择器")
    xpath: Optional[str] = Field(default=None, max_length=500, description="XPath")
    test_id: Optional[str] = Field(default=None, max_length=200, description="data-testid属性")
    aria_label: Optional[str] = Field(default=None, max_length=200, description="aria-label属性")
    text_content: Optional[str] = Field(default=None, max_length=500, description="文本内容")
    alternative_selectors: Optional[List[Dict[str, str]]] = Field(default=None, description="备用选择器")
    is_visible: Optional[bool] = Field(default=None, description="元素是否可见")
    is_enabled: Optional[bool] = Field(default=None, description="元素是否启用")
    expected_text: Optional[str] = Field(default=None, max_length=500, description="期望的文本内容")
    
    model_config = ConfigDict(from_attributes=True)


class WebUIElementSelectorInDB(WebUIElementSelectorBase):
    """数据库中的WEB UI元素选择器模式"""
    id: UUID
    web_ui_test_case_id: UUID
    project_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class WebUIElementSelectorResponse(WebUIElementSelectorInDB):
    """WEB UI元素选择器响应模式"""
    best_selector: str = Field(..., description="最佳选择器")
    
    model_config = ConfigDict(from_attributes=True)


# ========== 功能测试到WEB UI测试转换模式 ==========

class FunctionalToWebUITestConversion(BaseModel):
    """功能测试到WEB UI测试转换模式"""
    functional_test_case_id: str = Field(..., description="功能测试用例ID（支持整数ID和UUID）")
    base_url: str = Field(..., description="基础URL")
    browser: BrowserTypeEnum = Field(default=BrowserTypeEnum.CHROMIUM, description="浏览器类型")
    viewport_size: ViewportSizeEnum = Field(default=ViewportSizeEnum.DESKTOP_1920x1080, description="视口尺寸")
    headless: bool = Field(default=True, description="无头模式")
    generate_element_selectors: bool = Field(default=True, description="生成元素选择器")
    generate_test_script: bool = Field(default=True, description="生成测试脚本")
    script_type: str = Field(default="playwright", description="脚本类型")
    script_language: str = Field(default="python", description="脚本语言")
    force_explore: Optional[bool] = Field(default=False, description="是否强制重新探索（忽略缓存）")

    model_config = ConfigDict(from_attributes=True)


class WebUITestGenerationResult(BaseModel):
    """WEB UI测试生成结果模式"""
    success: bool = Field(..., description="是否成功")
    web_ui_test_case_id: Optional[UUID] = Field(default=None, description="生成的WEB UI测试用例ID")
    web_ui_test_cases: Optional[List[WebUITestCaseResponse]] = Field(default=None, description="生成的WEB UI测试用例列表")
    test_script: Optional[str] = Field(default=None, description="生成的测试脚本")
    element_selectors: Optional[Dict[str, str]] = Field(default=None, description="生成的元素选择器")
    warnings: Optional[List[str]] = Field(default=None, description="警告信息")
    errors: Optional[List[str]] = Field(default=None, description="错误信息")
    count: Optional[int] = Field(default=None, description="生成的测试用例数量")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    
    model_config = ConfigDict(from_attributes=True)


# ========== WEB UI测试执行请求模式 ==========

class WebUITestExecutionRequest(BaseModel):
    """WEB UI测试执行请求模式"""
    web_ui_test_case_id: UUID = Field(..., description="WEB UI测试用例ID")
    environment: Optional[str] = Field(default="development", description="测试环境")
    browser: Optional[BrowserTypeEnum] = Field(default=None, description="浏览器类型（覆盖测试用例配置）")
    headless: Optional[bool] = Field(default=None, description="无头模式（覆盖测试用例配置）")
    timeout: Optional[int] = Field(default=None, description="超时时间（覆盖测试用例配置）")
    
    model_config = ConfigDict(from_attributes=True)


class WebUITestExecutionResult(BaseModel):
    """WEB UI测试执行结果模式"""
    execution_id: UUID = Field(..., description="测试执行ID")
    status: str = Field(..., description="执行状态")
    duration: Optional[float] = Field(default=None, description="执行时长（秒）")
    screenshots: Optional[List[Dict[str, str]]] = Field(default=None, description="截图信息")
    video_path: Optional[str] = Field(default=None, description="视频文件路径")
    performance_metrics: Optional[Dict[str, Any]] = Field(default=None, description="性能指标")
    console_errors: Optional[List[Dict[str, Any]]] = Field(default=None, description="控制台错误")
    error: Optional[str] = Field(default=None, description="失败原因（status != completed 时）")
    
    model_config = ConfigDict(from_attributes=True)