"""
功能测试生成API端点
支持通过聊天、Swagger、需求文档等方式生成测试用例
"""

import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.functional_test_service import FunctionalTestService

router = APIRouter()


# 请求/响应模型
class ChatGenerateRequest(BaseModel):
    """聊天生成测试用例请求"""
    message: str = Field(..., description="聊天消息")
    project_name: Optional[str] = Field(None, description="项目名称")


class SwaggerGenerateRequest(BaseModel):
    """Swagger生成测试用例请求"""
    swagger_url: str = Field(..., description="Swagger文档URL")
    project_name: Optional[str] = Field(None, description="项目名称")


class RequirementsGenerateRequest(BaseModel):
    """需求文档生成测试用例请求"""
    requirements_text: str = Field(..., description="需求文档文本")
    project_name: str = Field(..., description="项目名称")
    version: str = Field("1.0.0", description="版本号")


class TestCaseResponse(BaseModel):
    """测试用例响应"""
    test_case_id: str
    title: str
    description: str
    priority: str
    category: str
    preconditions: List[str]
    test_steps: List[dict]
    expected_results: str
    tags: List[str]


class GenerateResponse(BaseModel):
    """生成响应"""
    success: bool
    message: str
    test_cases: List[TestCaseResponse]
    count: int
    metadata: Optional[dict] = None


@router.post("/generate/chat", response_model=GenerateResponse)
async def generate_from_chat(
    request: ChatGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    从聊天消息生成测试用例
    
    - **message**: 聊天消息（可以包含测试需求、功能描述等）
    - **project_name**: 项目名称（可选）
    """
    try:
        service = FunctionalTestService(db)
        
        result = service.generate_from_chat(
            chat_message=request.message,
            project_name=request.project_name,
            user=current_user
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成测试用例失败: {str(e)}")


@router.post("/generate/swagger", response_model=GenerateResponse)
async def generate_from_swagger(
    request: SwaggerGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    从Swagger文档生成测试用例
    
    - **swagger_url**: Swagger文档URL（支持JSON/YAML格式）
    - **project_name**: 项目名称（可选）
    """
    try:
        service = FunctionalTestService(db)
        
        result = service.generate_from_swagger(
            swagger_url=request.swagger_url,
            project_name=request.project_name,
            user=current_user
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"从Swagger生成测试用例失败: {str(e)}")


@router.post("/generate/requirements", response_model=GenerateResponse)
async def generate_from_requirements(
    request: RequirementsGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    从需求文档文本生成测试用例
    
    - **requirements_text**: 需求文档文本
    - **project_name**: 项目名称
    - **version**: 版本号
    """
    try:
        service = FunctionalTestService(db)
        
        result = service.generate_from_requirements(
            requirements_text=request.requirements_text,
            project_name=request.project_name,
            version=request.version,
            user=current_user
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"从需求文档生成测试用例失败: {str(e)}")


@router.post("/generate/combined")
async def generate_combined(
    chat_message: Optional[str] = Body(None, description="聊天消息"),
    swagger_url: Optional[str] = Body(None, description="Swagger文档URL"),
    requirements_text: Optional[str] = Body(None, description="需求文档文本"),
    project_name: str = Body(..., description="项目名称"),
    version: str = Body("1.0.0", description="版本号"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    组合多种方式生成测试用例
    
    - **chat_message**: 聊天消息（可选）
    - **swagger_url**: Swagger文档URL（可选）
    - **requirements_text**: 需求文档文本（可选）
    - **project_name**: 项目名称
    - **version**: 版本号
    
    注意：至少需要提供一种输入方式
    """
    try:
        if not any([chat_message, swagger_url, requirements_text]):
            raise HTTPException(
                status_code=400,
                detail="至少需要提供一种输入方式（聊天消息、Swagger URL或需求文档）"
            )
        
        service = FunctionalTestService(db)
        all_test_cases = []
        metadata = {
            "sources": [],
            "counts": {}
        }
        
        # 从聊天生成
        if chat_message:
            chat_result = service.generate_from_chat(
                chat_message=chat_message,
                project_name=project_name,
                user=current_user
            )
            
            if chat_result["success"]:
                all_test_cases.extend(chat_result["test_cases"])
                metadata["sources"].append("chat")
                metadata["counts"]["chat"] = len(chat_result["test_cases"])
        
        # 从Swagger生成
        if swagger_url:
            swagger_result = service.generate_from_swagger(
                swagger_url=swagger_url,
                project_name=project_name,
                user=current_user
            )
            
            if swagger_result["success"]:
                all_test_cases.extend(swagger_result["test_cases"])
                metadata["sources"].append("swagger")
                metadata["counts"]["swagger"] = len(swagger_result["test_cases"])
        
        # 从需求文档生成
        if requirements_text:
            requirements_result = service.generate_from_requirements(
                requirements_text=requirements_text,
                project_name=project_name,
                version=version,
                user=current_user
            )
            
            if requirements_result["success"]:
                all_test_cases.extend(requirements_result["test_cases"])
                metadata["sources"].append("requirements")
                metadata["counts"]["requirements"] = len(requirements_result["test_cases"])
        
        # 去重（基于test_case_id）
        unique_cases = {}
        for case in all_test_cases:
            case_id = case.get("test_case_id")
            if case_id and case_id not in unique_cases:
                unique_cases[case_id] = case
        
        final_cases = list(unique_cases.values())
        
        return {
            "success": True,
            "message": f"从{len(metadata['sources'])}种来源生成测试用例成功",
            "test_cases": final_cases,
            "count": len(final_cases),
            "metadata": metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"组合生成测试用例失败: {str(e)}")


@router.post("/analyze/chat")
async def analyze_chat_message(
    message: str = Body(..., description="聊天消息"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    分析聊天消息，提取测试需求
    
    - **message**: 聊天消息
    """
    try:
        service = FunctionalTestService(db)
        
        # 直接调用内部方法进行分析
        analysis = service._analyze_chat_message(message)
        
        return {
            "success": True,
            "message": "聊天消息分析完成",
            "analysis": analysis,
            "recommendations": _generate_recommendations(analysis)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析聊天消息失败: {str(e)}")


def _generate_recommendations(analysis: dict) -> List[str]:
    """根据分析结果生成推荐"""
    recommendations = []
    
    if analysis.get("has_swagger_url"):
        recommendations.append("检测到Swagger URL，建议使用Swagger生成API测试用例")
    
    if analysis.get("has_rag_query"):
        recommendations.append("检测到知识库查询关键词，建议关联RAG知识库生成测试用例")
    
    if analysis.get("has_skill_request"):
        recommendations.append(f"检测到SKILL请求: {analysis.get('skill_name')}，将应用该SKILL增强测试用例")
    
    if analysis.get("has_test_requirements"):
        recommendations.append("检测到测试需求关键词，将生成功能测试用例")
    
    if not recommendations:
        recommendations.append("未检测到特定模式，将生成基础功能测试用例")
    
    return recommendations


@router.get("/templates")
async def get_test_case_templates(
    category: Optional[str] = Query(None, description="测试类别过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取测试用例模板
    
    - **category**: 测试类别过滤（可选）
    """
    try:
        templates = [
            {
                "id": "template-functional-basic",
                "name": "基础功能测试模板",
                "description": "包含基本功能验证的测试用例模板",
                "category": "功能测试",
                "template": {
                    "test_case_id": "TC-FUNC-{序号}",
                    "title": "{功能名称}功能测试",
                    "description": "验证{功能名称}功能是否符合需求",
                    "priority": "medium",
                    "category": "功能测试",
                    "preconditions": ["系统已部署", "测试环境准备就绪"],
                    "test_steps": [
                        {"step": 1, "action": "执行{功能名称}相关操作", "expected": "操作执行成功"},
                        {"step": 2, "action": "验证操作结果", "expected": "结果符合需求定义"},
                        {"step": 3, "action": "检查系统状态", "expected": "系统状态正常"}
                    ],
                    "expected_results": "{功能名称}功能正常工作，符合需求定义",
                    "tags": ["functional", "basic"]
                }
            },
            {
                "id": "template-api-basic",
                "name": "基础API测试模板",
                "description": "包含API基本验证的测试用例模板",
                "category": "API测试",
                "template": {
                    "test_case_id": "TC-API-{序号}",
                    "title": "{API方法} {API路径}接口测试",
                    "description": "测试{API方法} {API路径}接口",
                    "priority": "medium",
                    "category": "API测试",
                    "preconditions": ["API服务已启动", "测试环境配置正确"],
                    "test_steps": [
                        {"step": 1, "action": "准备{API方法}请求到{API路径}", "expected": "请求参数准备完成"},
                        {"step": 2, "action": "发送{API方法}请求", "expected": "收到服务器响应"},
                        {"step": 3, "action": "验证响应状态码", "expected": "状态码为2xx（成功）"},
                        {"step": 4, "action": "验证响应数据格式和内容", "expected": "响应数据符合预期格式"}
                    ],
                    "expected_results": "API调用成功，响应符合预期",
                    "tags": ["api", "basic"]
                }
            },
            {
                "id": "template-ui-basic",
                "name": "基础UI测试模板",
                "description": "包含UI基本验证的测试用例模板",
                "category": "UI测试",
                "template": {
                    "test_case_id": "TC-UI-{序号}",
                    "title": "{页面名称}页面测试",
                    "description": "验证{页面名称}页面的UI和交互",
                    "priority": "medium",
                    "category": "UI测试",
                    "preconditions": ["浏览器已打开", "测试环境准备就绪"],
                    "test_steps": [
                        {"step": 1, "action": "访问{页面名称}页面", "expected": "页面正常加载"},
                        {"step": 2, "action": "验证页面布局和元素", "expected": "布局正确，元素可见"},
                        {"step": 3, "action": "执行页面交互操作", "expected": "交互响应正常"},
                        {"step": 4, "action": "验证操作结果", "expected": "结果符合预期"}
                    ],
                    "expected_results": "{页面名称}页面UI和交互功能正常",
                    "tags": ["ui", "basic"]
                }
            }
        ]
        
        if category:
            templates = [t for t in templates if t["category"] == category]
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模板失败: {str(e)}")


@router.post("/apply-template")
async def apply_template(
    template_id: str = Body(..., description="模板ID"),
    parameters: dict = Body(..., description="模板参数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    应用测试用例模板
    
    - **template_id**: 模板ID
    - **parameters**: 模板参数
    """
    try:
        # 这里可以调用模板服务应用模板
        # 简化实现：直接返回示例
        template_result = {
            "test_case_id": "TC-APPLIED-001",
            "title": f"应用模板生成的测试用例",
            "description": f"使用模板{template_id}生成的测试用例",
            "priority": "medium",
            "category": "功能测试",
            "preconditions": ["系统已部署"],
            "test_steps": [
                {"step": 1, "action": "执行测试操作", "expected": "操作成功"},
                {"step": 2, "action": "验证结果", "expected": "结果符合预期"}
            ],
            "expected_results": "测试通过",
            "tags": ["template", "applied"]
        }
        
        return {
            "success": True,
            "message": "模板应用成功",
            "test_case": template_result,
            "template_id": template_id,
            "parameters": parameters
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用模板失败: {str(e)}")


@router.get("/health")
async def functional_test_health_check(db: Session = Depends(get_db)):
    """功能测试模块健康检查"""
    try:
        service = FunctionalTestService(db)
        
        # 简单测试服务是否可用
        test_result = service.generate_from_chat("测试健康检查", "test_project")
        
        return {
            "status": "healthy",
            "service": "available",
            "test_generation": "working" if test_result["success"] else "failed",
            "test_case_count": test_result.get("count", 0)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }