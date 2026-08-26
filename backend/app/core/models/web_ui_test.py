"""
WEB UI自动化测试模型定义
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, validates

from app.core.models.base import BaseModel
from app.core.config import settings


class BrowserType(PyEnum):
    """浏览器类型枚举"""
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"
    SAFARI = "safari"
    EDGE = "edge"
    WEBKIT = "webkit"


class ViewportSize(PyEnum):
    """视口尺寸枚举"""
    DESKTOP_1920x1080 = "1920x1080"
    DESKTOP_1366x768 = "1366x768"
    DESKTOP_1536x864 = "1536x864"
    TABLET_768x1024 = "768x1024"
    TABLET_810x1080 = "810x1080"
    MOBILE_375x667 = "375x667"
    MOBILE_414x896 = "414x896"
    MOBILE_360x640 = "360x640"


class WebUITestCase(BaseModel):
    """WEB UI测试用例模型"""
    
    __tablename__ = 'web_ui_test_case'
    
    # 与基础测试用例的关联
    # 唯一性 = (project_id, test_case_id)：登录用例 __login__ 是固定值，
    # 多项目各自导入登录模块时不得互相冲突（全局唯一会导致第二个项目导入 500）
    test_case_id = Column(
        String(36),
        nullable=False,
        index=True,
        comment="关联的功能用例ID（兼容 test_cases 和 test_case 两种模型；方案B 存逻辑用例 id）"
    )

    # ── 方案B：软删标记（功能用例派生时旧 WUI 置 1 冻结，执行中心按 wui_id 重解析到最新版）──
    is_deleted = Column(Boolean, nullable=False, default=False, comment="软删标记（1=已被新版本取代，从UI用例列表隐藏）")
    
    # 关联项目
    project_id = Column(String(36), nullable=True, index=True, comment="所属项目ID")

    # WEB UI测试配置
    base_url = Column(String(500), nullable=False)  # 基础URL
    browser = Column(
        Enum(BrowserType, name='browser_type_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BrowserType.CHROME.value
    )
    viewport_size = Column(
        Enum(ViewportSize, name='viewport_size_enum', create_type=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ViewportSize.DESKTOP_1920x1080.value
    )
    viewport_width = Column(Integer, default=1920)  # 视口宽度
    viewport_height = Column(Integer, default=1080)  # 视口高度
    headless = Column(Boolean, default=True)  # 无头模式
    timeout = Column(Integer, default=30000)  # 超时时间（毫秒）
    screenshot_on_failure = Column(Boolean, default=True)  # 失败时截图
    screenshot_on_success = Column(Boolean, default=False)  # 成功时截图
    record_video = Column(Boolean, default=False)  # 录制视频
    video_dir = Column(String(500), nullable=True)  # 视频存储目录
    
    # 生成的测试脚本
    test_script = Column(Text)  # 完整的测试脚本（Playwright/Puppeteer）
    script_type = Column(String(50), default='playwright')  # 脚本类型：playwright, selenium, puppeteer
    script_language = Column(String(50), default='python')  # 脚本语言：python, javascript, java
    
    # 元素选择器映射（将自然语言元素映射到CSS选择器）
    element_selectors = Column(JSON, default=dict)  # { "登录按钮": "#login-btn", "用户名输入框": "input[name='username']" }
    
    # 测试数据
    test_data = Column(JSON, default=dict)  # 测试数据，如用户凭证、表单数据等
    
    # 验证点
    validation_points = Column(JSON, default=list)  # 验证点列表

    # 生成模式: "linear" (旧版线性脚本) | "pom_data_driven" (V2 POM+JSON数据驱动)
    generation_mode = Column(String(30), default="linear")

    # POM 页面类代码 (V2): {"PageName": "class PageName: ..."}
    page_objects = Column(JSON, default=dict)

    # 性能指标
    performance_metrics = Column(JSON, default=dict)  # 性能指标配置
    
    # 关系
    # test_case 关系已移除 — test_case_id 现在以字符串形式兼容两种用例模型
    # 需要关联查询时，通过 test_case_id 手动查询 RequirementTestCase 或 SimpleTestCase
    selector_relations = relationship(
        'WebUIElementSelector',
        back_populates='web_ui_test_case',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    
    # 索引
    __table_args__ = (
        Index('idx_web_ui_test_case_test_case_id', 'test_case_id'),
        UniqueConstraint('project_id', 'test_case_id',
                         name='uq_web_ui_test_project_case'),
        Index('idx_web_ui_test_case_browser', 'browser'),
        Index('idx_web_ui_test_case_base_url', 'base_url'),
    )
    
    @validates('base_url')
    def validate_base_url(self, key, base_url):
        """验证基础URL"""
        if not base_url or len(base_url.strip()) < 5:
            raise ValueError('Base URL must be at least 5 characters')
        if not base_url.startswith(('http://', 'https://')):
            raise ValueError('Base URL must start with http:// or https://')
        return base_url.strip()
    
    @validates('timeout')
    def validate_timeout(self, key, timeout):
        """验证超时时间"""
        if timeout < 1000:
            raise ValueError('Timeout must be at least 1000 milliseconds')
        if timeout > 300000:
            raise ValueError('Timeout cannot exceed 300000 milliseconds (5 minutes)')
        return timeout
    
    def parse_viewport_size(self):
        """解析视口尺寸为宽度和高度"""
        if self.viewport_size:
            try:
                width_str, height_str = self.viewport_size.value.split('x')
                self.viewport_width = int(width_str)
                self.viewport_height = int(height_str)
            except (ValueError, AttributeError):
                pass
    
    def to_dict(self, exclude: Optional[list] = None):
        """转换为字典"""
        data = super().to_dict(exclude)

        # 解析视口尺寸
        if 'viewport_width' not in data or 'viewport_height' not in data:
            self.parse_viewport_size()
            data['viewport_width'] = self.viewport_width
            data['viewport_height'] = self.viewport_height

        # 添加测试用例信息
        if self.test_case:
            data['test_case'] = {
                'id': str(self.test_case.id),
                'title': self.test_case.title,
                'description': self.test_case.description,
                'test_type': self.test_case.test_type
            }

        # 前置条件透传（2026-08-25：test_data 是 JSON spec，preconditions 藏在其内，
        # 前端列表/详情要直接展示——提取到顶层字段；存量用例无 preconditions 键时为空）
        try:
            _td = self.test_data or {}
            if isinstance(_td, dict):
                data['preconditions'] = _td.get('preconditions', '') or ''
            else:
                data['preconditions'] = ''
        except Exception:
            data['preconditions'] = ''

        return data


class WebUITestExecution(BaseModel):
    """WEB UI测试执行记录模型"""
    
    __tablename__ = 'web_ui_test_execution'
    
    # 与基础测试执行的关联
    test_execution_id = Column(
        String(36),
        ForeignKey('test_execution.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        unique=True
    )
    
    # 执行详情
    start_url = Column(String(500))  # 实际开始的URL
    final_url = Column(String(500))  # 最终的URL
    page_count = Column(Integer, default=0)  # 访问的页面数量
    network_requests = Column(Integer, default=0)  # 网络请求数量
    dom_size = Column(Integer, default=0)  # DOM大小
    
    # 性能指标
    load_time = Column(Float)  # 页面加载时间（秒）
    first_contentful_paint = Column(Float)  # 首次内容绘制时间（秒）
    largest_contentful_paint = Column(Float)  # 最大内容绘制时间（秒）
    cumulative_layout_shift = Column(Float)  # 累积布局偏移
    first_input_delay = Column(Float)  # 首次输入延迟（秒）
    
    # 截图和视频
    screenshots = Column(JSON, default=list)  # 截图路径列表
    video_path = Column(String(500))  # 视频文件路径
    console_logs = Column(JSON, default=list)  # 控制台日志
    network_logs = Column(JSON, default=list)  # 网络日志
    
    # 错误信息
    browser_console_errors = Column(JSON, default=list)  # 浏览器控制台错误
    network_errors = Column(JSON, default=list)  # 网络错误
    javascript_errors = Column(JSON, default=list)  # JavaScript错误
    
    # 关系
    test_execution = relationship(
        'TestExecution',
        backref='web_ui_test_execution',
        lazy='selectin',
        foreign_keys=[test_execution_id]
    )
    
    # 索引
    __table_args__ = (
        Index('idx_web_ui_test_execution_test_execution_id', 'test_execution_id'),
        Index('idx_web_ui_test_execution_load_time', 'load_time'),
    )
    
    def to_dict(self, exclude: Optional[list] = None):
        """转换为字典"""
        data = super().to_dict(exclude)
        
        # 添加测试执行信息
        if self.test_execution:
            data['test_execution'] = {
                'id': str(self.test_execution.id),
                'status': self.test_execution.status,
                'executed_at': self.test_execution.executed_at.isoformat() if self.test_execution.executed_at else None,
                'duration': self.test_execution.duration
            }
        
        return data


class WebUIElementSelector(BaseModel):
    """WEB UI元素选择器模型"""
    
    __tablename__ = 'web_ui_element_selector'
    
    # 关联信息
    web_ui_test_case_id = Column(
        String(36),
        ForeignKey('web_ui_test_case.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    # project_id column removed due to missing project table
    # project_id = Column(
    #     String(36) if str(settings.DATABASE_URL).startswith("sqlite") else UUID(as_uuid=True),
    #     nullable=True,
    #     index=True
    # )
    
    # 元素信息
    element_name = Column(String(200), nullable=False)  # 元素名称（如"登录按钮"）
    element_description = Column(Text)  # 元素描述
    page_url = Column(String(500))  # 元素所在页面URL
    page_title = Column(String(200))  # 页面标题
    
    # 选择器配置
    css_selector = Column(String(500))  # CSS选择器
    xpath = Column(String(500))  # XPath
    test_id = Column(String(200))  # data-testid属性
    aria_label = Column(String(200))  # aria-label属性
    text_content = Column(String(500))  # 文本内容
    
    # 备用选择器
    alternative_selectors = Column(JSON, default=list)  # 备用选择器列表
    
    # 验证信息
    is_visible = Column(Boolean, default=True)  # 元素是否可见
    is_enabled = Column(Boolean, default=True)  # 元素是否启用
    expected_text = Column(String(500))  # 期望的文本内容
    
    # 关系
    web_ui_test_case = relationship(
        'WebUITestCase',
        back_populates='selector_relations',
        lazy='selectin',
        foreign_keys=[web_ui_test_case_id]
    )
    # project relationship removed due to missing Project table
    # project = relationship(
    #     'Project',
    #     backref='web_ui_element_selectors',
    #     lazy='selectin'
    # )
    
    # 索引
    __table_args__ = (
        Index('idx_web_ui_element_selector_test_case_id', 'web_ui_test_case_id'),
        Index('idx_web_ui_element_selector_element_name', 'element_name'),
        # Index('idx_web_ui_element_selector_project_id', 'project_id'),  # removed
    )
    
    @validates('element_name')
    def validate_element_name(self, key, element_name):
        """验证元素名称"""
        if not element_name or len(element_name.strip()) < 2:
            raise ValueError('Element name must be at least 2 characters')
        return element_name.strip()
    
    def get_best_selector(self) -> str:
        """获取最佳选择器"""
        # 优先级：test_id > css_selector > xpath > text_content > aria_label
        if self.test_id:
            return f'[data-testid="{self.test_id}"]'
        elif self.css_selector:
            return self.css_selector
        elif self.xpath:
            return self.xpath
        elif self.text_content:
            return f'text="{self.text_content}"'
        elif self.aria_label:
            return f'[aria-label="{self.aria_label}"]'
        else:
            return ''
    
    def to_dict(self, exclude: Optional[list] = None):
        """转换为字典"""
        data = super().to_dict(exclude)
        
        # 添加最佳选择器
        data['best_selector'] = self.get_best_selector()
        
        return data


class ElementLocator(BaseModel):
    """智能元素定位器模型"""
    
    __tablename__ = 'element_locator'
    
    project_id = Column(String(36), nullable=False, index=True)
    page_name = Column(String(100))
    page_url = Column(String(500))
    element_name = Column(String(100), nullable=False)
    element_description = Column(Text)
    
    primary_locator = Column(String(500))
    primary_locator_type = Column(String(20))
    fallback_locators = Column(JSON, default=list)
    confidence_score = Column(Float, default=1.0)
    
    auto_healed = Column(Boolean, default=False)
    heal_count = Column(Integer, default=0)
    last_validated_at = Column(DateTime)
    last_success = Column(Boolean, default=True)
    
    screenshot_url = Column(String(500))
    
    __table_args__ = (
        Index('idx_element_locator_project_id', 'project_id'),
        Index('idx_element_locator_element_name', 'element_name'),
    )
    
    def to_dict(self, exclude: Optional[list] = None):
        return super().to_dict(exclude)


class AutoHealRecord(BaseModel):
    """自动修复记录模型"""
    
    __tablename__ = 'auto_heal_record'
    
    locator_id = Column(String(36), nullable=False, index=True)
    execution_id = Column(String(36), index=True)
    
    old_locator = Column(String(500))
    new_locator = Column(String(500))
    old_locator_type = Column(String(20))
    new_locator_type = Column(String(20))
    
    confidence_score = Column(Float)
    match_type = Column(String(20))
    match_details = Column(JSON)
    
    page_html = Column(Text)
    screenshot_url = Column(String(500))
    
    status = Column(String(20), default='pending')
    approved_by = Column(String(36))
    approved_at = Column(DateTime)
    review_comment = Column(Text)
    
    __table_args__ = (
        Index('idx_auto_heal_record_locator_id', 'locator_id'),
        Index('idx_auto_heal_record_status', 'status'),
    )
    
    def to_dict(self, exclude: Optional[list] = None):
        return super().to_dict(exclude)


class PageChangeRecord(BaseModel):
    """页面变更记录模型"""
    
    __tablename__ = 'page_change_record'
    
    project_id = Column(String(36), nullable=False, index=True)
    page_url = Column(String(500), nullable=False)
    page_name = Column(String(100))
    
    change_type = Column(String(20))
    change_severity = Column(String(20), default='low')
    
    affected_locators = Column(JSON, default=list)
    affected_cases = Column(JSON, default=list)
    
    old_snapshot_id = Column(String(36))
    new_snapshot_id = Column(String(36))
    
    screenshot_url = Column(String(500))
    diff_url = Column(String(500))
    details = Column(JSON)
    
    status = Column(String(20), default='pending')
    reviewed_by = Column(String(36))
    reviewed_at = Column(DateTime)
    
    __table_args__ = (
        Index('idx_page_change_record_project_id', 'project_id'),
        Index('idx_page_change_record_page_url', 'page_url'),
    )
    
    def to_dict(self, exclude: Optional[list] = None):
        return super().to_dict(exclude)


class PageSnapshot(BaseModel):
    """页面快照模型"""
    
    __tablename__ = 'page_snapshot'
    
    project_id = Column(String(36), nullable=False, index=True)
    page_url = Column(String(500), nullable=False)
    
    html_content = Column(Text)
    dom_structure = Column(JSON)
    elements = Column(JSON, default=list)
    
    screenshot_url = Column(String(500))
    
    hash = Column(String(64), index=True)
    
    __table_args__ = (
        Index('idx_page_snapshot_project_id', 'project_id'),
        Index('idx_page_snapshot_page_url', 'page_url'),
    )
    
    def to_dict(self, exclude: Optional[list] = None):
        return super().to_dict(exclude)