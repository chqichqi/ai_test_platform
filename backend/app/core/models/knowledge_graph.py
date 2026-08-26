"""
知识图谱数据模型
用于存储系统探索Agent爬取的完整项目信息
"""

from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, JSON, Float, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class KnowledgeGraph(Base):
    """项目知识图谱（主表）"""
    __tablename__ = 'system_exploration_graphs'
    # 项目唯一：知识图谱是项目级资产，任何版本迭代/需求变更都合并进这一份
    __table_args__ = (
        UniqueConstraint('project_id', name='uq_knowledge_graph_project_id'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey('projects.id'), nullable=False)
    version_id = Column(BigInteger, ForeignKey('versions.id'), nullable=True,
                        comment='最近更新来源版本（项目唯一；版本删除时置空）')
    
    # 基本信息
    graph_name = Column(String(200), comment='图谱名称')
    base_url = Column(String(500), comment='项目基础URL')
    exploration_strategy = Column(String(20), default='normal', comment='探索策略：quick/normal/deep')
    
    # 爬取配置
    login_username = Column(String(100), comment='登录用户名')
    login_password = Column(String(100), comment='登录密码（加密）')
    selected_organization = Column(String(200), comment='选择的机构名称')
    
    # 爬取结果（JSON存储）
    pages = Column(JSON, default=list, comment='所有页面信息')
    menus = Column(JSON, default=list, comment='菜单结构（一级、二级）')
    elements = Column(JSON, default=list, comment='所有元素定位器')
    forms = Column(JSON, default=list, comment='所有表单信息')
    tables = Column(JSON, default=list, comment='所有表格信息')
    flows = Column(JSON, default=list, comment='操作流程')
    api_calls = Column(JSON, default=list, comment='API调用记录')
    dependencies = Column(JSON, default=list, comment='依赖关系')
    dropdowns = Column(JSON, default=dict, comment='下拉筛选控件及选项')
    modals = Column(JSON, default=list, comment='弹窗信息')
    
    # 统计信息
    page_count = Column(Integer, default=0, comment='页面总数')
    menu_count = Column(Integer, default=0, comment='菜单总数')
    element_count = Column(Integer, default=0, comment='元素总数')
    flow_count = Column(Integer, default=0, comment='操作流程总数')
    api_count = Column(Integer, default=0, comment='API调用总数')
    
    # 执行状态
    exploration_status = Column(String(20), default='pending', comment='爬取状态：pending/running/completed/failed')
    progress_percentage = Column(Integer, default=0, comment='进度百分比')
    current_page = Column(String(200), comment='当前正在爬取的页面')
    error_message = Column(Text, comment='错误信息')
    
    # 时间信息
    started_at = Column(DateTime, comment='开始时间')
    completed_at = Column(DateTime, comment='完成时间')
    duration_seconds = Column(Integer, comment='耗时（秒）')
    
    # 鉴权持久化 — 登录后保存，后续探索优先复用
    auth_data = Column(JSON, default=dict, comment='鉴权数据: {params:{oId,refresh,token}, cookies:[], saved_at:...}')

    # 质量评估
    confidence_score = Column(Float, default=0.0, comment='准确性评分（0-1）')
    locator_validation_rate = Column(Float, default=0.0, comment='定位器验证成功率')
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 关系
    project = relationship("Project", back_populates="knowledge_graphs")
    version = relationship("Version", back_populates="knowledge_graphs")
    page_snapshots = relationship("ExplorationPageSnapshot", back_populates="knowledge_graph", cascade="all, delete-orphan")
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'version_id': self.version_id,
            'graph_name': self.graph_name,
            'base_url': self.base_url,
            'exploration_strategy': self.exploration_strategy,
            'page_count': self.page_count,
            'menu_count': self.menu_count,
            'element_count': self.element_count,
            'exploration_status': self.exploration_status,
            'progress_percentage': self.progress_percentage,
            'current_page': self.current_page,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ExplorationPageSnapshot(Base):
    """页面快照（系统探索时每个页面的详细信息）"""
    __tablename__ = 'exploration_page_snapshots'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    graph_id = Column(BigInteger, ForeignKey('system_exploration_graphs.id'), nullable=False)
    
    # 页面基本信息
    page_url = Column(String(500), comment='页面URL')
    page_title = Column(String(200), comment='页面标题')
    page_name = Column(String(200), comment='页面名称（功能名）')
    menu_level = Column(Integer, default=1, comment='菜单层级：1=一级，2=二级')
    parent_menu = Column(String(200), comment='父级菜单名称')
    
    # 页面结构
    elements = Column(JSON, default=list, comment='页面元素列表')
    forms = Column(JSON, default=list, comment='表单列表')
    tables = Column(JSON, default=list, comment='表格列表')
    buttons = Column(JSON, default=list, comment='按钮列表')
    links = Column(JSON, default=list, comment='链接列表')
    
    # 页面操作
    operations = Column(JSON, default=list, comment='可执行操作列表')
    api_calls = Column(JSON, default=list, comment='页面API调用')
    
    # 页面截图
    screenshot_path = Column(String(500), comment='截图保存路径')
    dom_snapshot = Column(Text, comment='DOM快照（HTML）')
    
    # 元数据
    visited_at = Column(DateTime, default=datetime.utcnow, comment='访问时间')
    visit_order = Column(Integer, default=0, comment='访问顺序')
    
    # 关系
    knowledge_graph = relationship("KnowledgeGraph", back_populates="page_snapshots")
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'graph_id': self.graph_id,
            'page_url': self.page_url,
            'page_title': self.page_title,
            'page_name': self.page_name,
            'menu_level': self.menu_level,
            'parent_menu': self.parent_menu,
            'element_count': len(self.elements) if self.elements else 0,
            'visited_at': self.visited_at.isoformat() if self.visited_at else None
        }


class ElementLocator(Base):
    """元素定位器（多策略）"""
    __tablename__ = 'element_locators'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    graph_id = Column(BigInteger, ForeignKey('system_exploration_graphs.id'), nullable=False)
    page_id = Column(BigInteger, ForeignKey('exploration_page_snapshots.id'), nullable=False)
    
    # 元素基本信息
    element_name = Column(String(200), comment='元素名称')
    element_type = Column(String(50), comment='元素类型：button/input/link/table/form')
    element_text = Column(String(200), comment='元素显示文本')
    element_description = Column(Text, comment='元素描述')
    
    # 多策略定位器
    locator_id = Column(String(200), comment='ID定位器')
    locator_xpath = Column(Text, comment='XPath定位器')
    locator_css = Column(String(500), comment='CSS选择器')
    locator_text = Column(String(200), comment='Text定位器（Playwright）')
    locator_name = Column(String(200), comment='Name属性定位器')
    locator_class = Column(String(500), comment='Class定位器')
    
    # 优先级定位器
    primary_locator = Column(String(20), default='xpath', comment='首选定位器类型：id/xpath/css/text')
    primary_locator_value = Column(String(500), comment='首选定位器值')
    
    # 验证状态
    is_validated = Column(Boolean, default=False, comment='是否已验证')
    validation_attempts = Column(Integer, default=0, comment='验证尝试次数')
    validation_success = Column(Boolean, default=False, comment='验证是否成功')
    last_validated_at = Column(DateTime, comment='最后验证时间')
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'element_name': self.element_name,
            'element_type': self.element_type,
            'element_text': self.element_text,
            'locators': {
                'id': self.locator_id,
                'xpath': self.locator_xpath,
                'css': self.locator_css,
                'text': self.locator_text,
                'name': self.locator_name,
                'class': self.locator_class
            },
            'primary_locator': {
                'type': self.primary_locator,
                'value': self.primary_locator_value
            },
            'is_validated': self.is_validated,
            'validation_success': self.validation_success
        }


class NavigationFlow(Base):
    """导航流程（操作路径）"""
    __tablename__ = 'navigation_flows'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    graph_id = Column(BigInteger, ForeignKey('system_exploration_graphs.id'), nullable=False)
    
    # 流程基本信息
    flow_name = Column(String(200), comment='流程名称')
    flow_type = Column(String(50), comment='流程类型：login/create/update/delete/view')
    start_page = Column(String(200), comment='起始页面')
    end_page = Column(String(200), comment='结束页面')
    
    # 流程步骤
    steps = Column(JSON, default=list, comment='操作步骤列表')
    
    # 流程依赖
    dependencies = Column(JSON, default=list, comment='前置依赖')
    required_data = Column(JSON, default=dict, comment='所需测试数据')
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'flow_name': self.flow_name,
            'flow_type': self.flow_type,
            'start_page': self.start_page,
            'end_page': self.end_page,
            'step_count': len(self.steps) if self.steps else 0,
            'dependencies': self.dependencies
        }


class APICallRecord(Base):
    """API调用记录"""
    __tablename__ = 'api_call_records'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    graph_id = Column(BigInteger, ForeignKey('system_exploration_graphs.id'), nullable=False)
    page_id = Column(BigInteger, ForeignKey('page_snapshots.id'))
    
    # API信息
    api_url = Column(String(500), comment='API URL')
    api_method = Column(String(10), comment='请求方法：GET/POST/PUT/DELETE')
    api_type = Column(String(20), comment='请求类型：xhr/fetch')
    
    # 请求详情
    request_headers = Column(JSON, default=dict, comment='请求头')
    request_params = Column(JSON, default=dict, comment='请求参数')
    request_body = Column(JSON, default=dict, comment='请求体')
    
    # 响应详情
    response_status = Column(Integer, comment='响应状态码')
    response_headers = Column(JSON, default=dict, comment='响应头')
    response_body = Column(JSON, default=dict, comment='响应体')
    
    # 元数据
    captured_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'api_url': self.api_url,
            'api_method': self.api_method,
            'api_type': self.api_type,
            'response_status': self.response_status
        }