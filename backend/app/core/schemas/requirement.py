"""
需求分析与测试用例生成相关Schema
"""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator


class RequirementDocumentCreate(BaseModel):
    version_id: int = Field(..., description="版本ID")
    name: str = Field(..., max_length=200, description="文档名称")
    type: str = Field(default="text", description="文档类型")
    content: Optional[str] = Field(None, description="文档内容")
    file_url: Optional[str] = Field(None, description="文件URL")


class RequirementDocumentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None


class RequirementDocumentResponse(BaseModel):
    id: int
    version_id: int
    name: str
    type: str
    content: Optional[str]
    file_url: Optional[str]
    file_size: Optional[int]
    parsed_content: Optional[dict]
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RequirementDocumentListResponse(BaseModel):
    items: List[RequirementDocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TestStep(BaseModel):
    step: int = Field(..., description="步骤序号")
    action: str = Field(..., description="操作步骤")
    expected: str = Field(..., description="预期结果")


class TestCaseCreate(BaseModel):
    project_id: int = Field(..., description="项目ID")
    version_id: Optional[int] = Field(None, description="版本ID")
    module: Optional[str] = Field(None, max_length=100, description="所属模块")
    name: str = Field(..., max_length=200, description="用例名称")
    description: Optional[str] = Field(None, description="用例描述")
    preconditions: Optional[str] = Field(None, description="前置条件")
    test_steps: Optional[List[TestStep]] = Field(None, description="测试步骤")
    expected_result: Optional[str] = Field(None, description="预期结果")
    test_data: Optional[dict] = Field(None, description="测试数据")
    priority: str = Field(default="P2", description="优先级")
    case_type: str = Field(default="functional", description="用例类型")
    execution_type: str = Field(default="manual", description="执行方式")
    sort_order: Optional[int] = Field(default=0, description="执行顺序(10间隔递增)")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    depends_on: Optional[List[int]] = Field(None, description="前置用例 logical_case_id 列表（执行前先跑）")
    is_setup: Optional[int] = Field(0, description="是否共享准备/setup 用例(1=是)")


class TestCaseUpdate(BaseModel):
    module: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    preconditions: Optional[str] = None
    test_steps: Optional[List[TestStep]] = None
    expected_result: Optional[str] = None
    test_data: Optional[dict] = None
    priority: Optional[str] = None
    case_type: Optional[str] = None
    execution_type: Optional[str] = None
    sort_order: Optional[int] = None
    tags: Optional[List[str]] = None
    depends_on: Optional[List[int]] = None
    is_setup: Optional[int] = None
    status: Optional[str] = None


class TestCaseResponse(BaseModel):
    id: int
    project_id: int
    version_id: Optional[int]
    module: Optional[str]
    name: str
    description: Optional[str]
    preconditions: Optional[str]
    test_steps: Optional[List[Any]]
    expected_result: Optional[str]
    test_data: Optional[dict]
    priority: str
    case_type: str
    execution_type: str
    sort_order: Optional[int] = 0
    status: str
    tags: Optional[List[str]]
    generated_by: str
    reviewer_id: Optional[str]
    reviewed_at: Optional[datetime]
    review_comment: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    # 方案B 版本化：逻辑用例 id / 修订号 / 派生来源（前端 v-badge + 继承提示）
    logical_case_id: Optional[int] = None
    revision_no: Optional[int] = None
    derived_from_id: Optional[int] = None
    depends_on: Optional[List[int]] = None
    is_setup: Optional[int] = 0

    @field_validator('test_steps', mode='before')
    @classmethod
    def parse_test_steps(cls, v):
        if v is None or v == '':
            return []
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return []
        return v

    @field_validator('test_data', mode='before')
    @classmethod
    def parse_test_data(cls, v):
        if v is None or v == '':
            return {}
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return {}
        return v

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        if v is None or v == '':
            return []
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return []
        return v

    class Config:
        from_attributes = True


class TestCaseListResponse(BaseModel):
    items: List[TestCaseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


