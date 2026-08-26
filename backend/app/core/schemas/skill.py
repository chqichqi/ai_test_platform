"""
SKILL管理模块 - Pydantic Schemas
对应需求文档 3.16 SKILL管理模块
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== SKILL内容Schema ====================

class SkillRoleSchema(BaseModel):
    """SKILL角色定义"""
    name: str = Field(..., description="角色名称")
    description: str = Field(..., description="角色描述")
    expertise: List[str] = Field(default=[], description="专业知识")
    behavior_rules: List[str] = Field(default=[], description="行为规则")


class SkillInputSchema(BaseModel):
    """SKILL输入定义"""
    required_fields: List[str] = Field(default=[], description="必填字段")
    optional_fields: List[str] = Field(default=[], description="可选字段")


class SkillOutputSchema(BaseModel):
    """SKILL输出规范"""
    format: str = Field(default="json", description="输出格式: json/markdown/xml")
    schema: Dict[str, Any] = Field(default={}, description="JSON Schema定义")


class SkillMethodSchema(BaseModel):
    """测试方法"""
    name: str = Field(..., description="方法名称")
    description: str = Field(..., description="方法描述")
    applicable_scenarios: List[str] = Field(default=[], description="适用场景")


class SkillDomainRuleSchema(BaseModel):
    """领域规则"""
    domain: str = Field(..., description="领域名称")
    must_test: List[str] = Field(default=[], description="必测项")
    security_focus: List[str] = Field(default=[], description="安全关注点")


class SkillPromptTemplateSchema(BaseModel):
    """提示词模板对象格式"""
    system_prompt: str = Field(default="", description="系统提示词（固定不变）")
    user_prompt: str = Field(default="", description="用户提示词模板（含变量占位符）")
    variables: List[Dict[str, Any]] = Field(default=[], description="变量定义列表")

class SkillContentSchema(BaseModel):
    """SKILL完整内容"""
    role: SkillRoleSchema = Field(..., description="角色定义")
    input: SkillInputSchema = Field(default_factory=SkillInputSchema, description="输入定义")
    output: SkillOutputSchema = Field(default_factory=SkillOutputSchema, description="输出规范")
    methods: List[SkillMethodSchema] = Field(default=[], description="测试方法库")
    domain_rules: List[SkillDomainRuleSchema] = Field(default=[], description="领域规则")
    quality_checks: List[str] = Field(default=[], description="质量检查规则")
    prompt_template: Any = Field(default="", description="提示词模板（支持字符串或对象格式）")


# ==================== SKILL基础Schema ====================

class SkillBase(BaseModel):
    """SKILL基础信息"""
    name: str = Field(..., min_length=1, max_length=100, description="SKILL名称")
    code: str = Field(..., min_length=1, max_length=50, description="SKILL编码")
    description: Optional[str] = Field(None, description="SKILL描述")
    skill_type: str = Field(..., description="SKILL类型: functional/api/ui/performance/security")
    tags: Optional[List[str]] = Field(default=[], description="标签列表")
    is_global: bool = Field(default=False, description="是否全局SKILL")
    is_default: bool = Field(default=False, description="是否为项目默认SKILL")


class SkillCreate(SkillBase):
    """创建SKILL请求"""
    content: SkillContentSchema = Field(..., description="SKILL内容")
    project_id: Optional[int] = Field(None, description="所属项目ID（全局SKILL可不传）")


class SkillUpdate(BaseModel):
    """更新SKILL请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None)
    tags: Optional[List[str]] = Field(None)
    content: Optional[SkillContentSchema] = Field(None)
    status: Optional[str] = Field(None, description="状态: active/draft/deprecated")
    is_default: Optional[bool] = Field(None)


class SkillResponse(SkillBase):
    """SKILL响应"""
    id: int
    version: str
    is_latest: bool
    status: str
    usage_count: int = 0
    generation_count: int = 0
    avg_quality_score: Optional[int] = None
    project_id: Optional[int] = None
    created_by: Optional[str] = None  # 改为字符串，匹配数据库UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SkillDetailResponse(SkillResponse):
    """SKILL详情响应"""
    content: SkillContentSchema
    examples: List[Dict[str, Any]] = []


class SkillListResponse(BaseModel):
    """SKILL列表响应"""
    items: List[SkillResponse]
    total: int
    page: int
    page_size: int


# ==================== SKILL示例Schema ====================

class SkillExampleBase(BaseModel):
    """SKILL示例基础信息"""
    name: Optional[str] = Field(None, description="示例名称")
    description: Optional[str] = Field(None, description="示例描述")
    input_example: str = Field(..., description="输入示例")
    output_example: Dict[str, Any] = Field(..., description="输出示例")
    sort_order: int = Field(default=0, description="排序")


class SkillExampleCreate(SkillExampleBase):
    """创建SKILL示例请求"""
    skill_id: int = Field(..., description="所属SKILL ID")


class SkillExampleResponse(SkillExampleBase):
    """SKILL示例响应"""
    id: int
    skill_id: int
    is_active: bool
    created_by: Optional[str] = None  # 改为字符串
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== SKILL查询Schema ====================

class SkillQueryParams(BaseModel):
    """SKILL查询参数"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    skill_type: Optional[str] = Field(None, description="类型筛选")
    status: Optional[str] = Field(None, description="状态筛选")
    project_id: Optional[int] = Field(None, description="项目筛选")
    is_global: Optional[bool] = Field(None, description="是否全局")
    search: Optional[str] = Field(None, description="搜索关键词")


# ==================== SKILL测试Schema ====================

class SkillTestRequest(BaseModel):
    """测试SKILL请求"""
    input_text: str = Field(..., description="测试输入内容")
    requirement_images_ocr: Optional[List[str]] = Field(default=[], description="图片OCR文字")


class SkillTestResponse(BaseModel):
    """测试SKILL响应"""
    success: bool
    generated_count: int
    test_cases: List[Dict[str, Any]]
    analysis_summary: Dict[str, Any]
    generation_time_ms: int
    token_usage: Dict[str, int]


# ==================== 项目SKILL关联Schema ====================

class ProjectSkillCreate(BaseModel):
    """为项目添加SKILL"""
    skill_id: int = Field(..., description="SKILL ID")
    is_default: bool = Field(default=False, description="是否为默认SKILL")


class ProjectSkillResponse(BaseModel):
    """项目SKILL响应"""
    id: int
    project_id: int
    skill: SkillResponse
    is_default: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== SKILL导入导出Schema ====================

class SkillExportResponse(BaseModel):
    """导出SKILL响应"""
    name: str
    code: str
    version: str
    skill_type: str
    description: Optional[str]
    content: SkillContentSchema
    examples: List[SkillExampleBase]
    export_time: datetime


class SkillImportRequest(BaseModel):
    """导入SKILL请求"""
    skill_data: Dict[str, Any] = Field(..., description="SKILL数据")
    project_id: Optional[int] = Field(None, description="导入到项目（NULL表示全局）")
