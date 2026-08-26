"""
RAG知识库管理API端点
"""

import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.rag_service import RAGService

router = APIRouter()


# 请求/响应模型
class RAGKnowledgeBaseCreate(BaseModel):
    """创建知识库请求"""
    name: Optional[str] = Field(None, description="知识库名称")
    description: Optional[str] = Field(None, description="描述")
    project_name: str = Field(..., description="项目名称")
    version: str = Field(..., description="项目版本")


class RAGKnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: int
    name: str
    description: Optional[str]
    project_name: str
    version: str
    file_name: str
    file_size: int
    file_type: str
    status: str
    processing_progress: float
    total_chunks: Optional[int]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class RAGQueryRequest(BaseModel):
    """RAG查询请求"""
    query: str = Field(..., description="查询文本")
    query_type: str = Field("general", description="查询类型: general, test_case, mind_map")
    top_k: int = Field(5, description="返回结果数量")


class RAGQueryResponse(BaseModel):
    """RAG查询响应"""
    query_id: int
    knowledge_base: dict
    query: str
    response: str
    generated_content: Optional[str]
    retrieved_documents: List[dict]
    performance: dict


class TestCaseFromRAGResponse(BaseModel):
    """RAG生成的测试用例响应"""
    id: int
    test_case_id: str
    title: str
    description: Optional[str]
    priority: str
    category: str
    status: str
    created_at: str
    
    class Config:
        from_attributes = True


class MindMapFromRAGResponse(BaseModel):
    """RAG生成的思维导图响应"""
    id: int
    title: str
    description: Optional[str]
    format: str
    created_at: str
    
    class Config:
        from_attributes = True


@router.post("/upload", response_model=RAGKnowledgeBaseResponse)
async def upload_document(
    file: UploadFile = File(...),
    project_name: str = Form(...),
    version: str = Form(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    上传文档到RAG知识库
    
    - **file**: 需求文档文件（支持PDF、DOCX、TXT等格式）
    - **project_name**: 项目名称
    - **version**: 项目版本
    - **name**: 知识库名称（可选）
    - **description**: 描述（可选）
    """
    try:
        # 保存上传的文件
        upload_dir = os.path.join("data", "uploads", "rag")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, file.filename)
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 创建RAG服务实例
        rag_service = RAGService(db)
        
        # 上传文档到知识库
        kb = rag_service.upload_document(
            file_path=file_path,
            project_name=project_name,
            version=version,
            name=name,
            description=description,
            user=current_user
        )
        
        return kb
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传文档失败: {str(e)}")


@router.get("/knowledge-bases", response_model=List[RAGKnowledgeBaseResponse])
async def get_knowledge_bases(
    project_name: Optional[str] = Query(None, description="项目名称过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取RAG知识库列表
    
    - **project_name**: 按项目名称过滤（可选）
    - **status**: 按状态过滤（可选）
    """
    try:
        rag_service = RAGService(db)
        
        knowledge_bases = rag_service.get_knowledge_bases(
            project_name=project_name,
            status=status,
            user_id=current_user.id
        )
        
        return knowledge_bases
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@router.get("/knowledge-bases/{kb_id}", response_model=RAGKnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取RAG知识库详情
    
    - **kb_id**: 知识库ID
    """
    try:
        rag_service = RAGService(db)
        
        kb = rag_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查权限（可选：只允许创建者访问）
        if kb.created_by_id and kb.created_by_id != current_user.id:
            # 这里可以根据需要添加权限检查
            pass
        
        return kb
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识库详情失败: {str(e)}")


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    删除RAG知识库（软删除）
    
    - **kb_id**: 知识库ID
    """
    try:
        rag_service = RAGService(db)
        
        # 检查知识库是否存在
        kb = rag_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查权限（只允许创建者删除）
        if kb.created_by_id and kb.created_by_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权删除此知识库")
        
        # 执行删除
        success = rag_service.delete_knowledge_base(kb_id)
        if not success:
            raise HTTPException(status_code=500, detail="删除失败")
        
        return {"message": "知识库已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


@router.post("/knowledge-bases/{kb_id}/query", response_model=RAGQueryResponse)
async def query_knowledge_base(
    kb_id: int,
    query_request: RAGQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    查询RAG知识库
    
    - **kb_id**: 知识库ID
    - **query**: 查询文本
    - **query_type**: 查询类型（general/test_case/mind_map）
    - **top_k**: 返回结果数量
    """
    try:
        rag_service = RAGService(db)
        
        # 检查知识库是否存在
        kb = rag_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 检查知识库状态
        if kb.status != "completed":
            raise HTTPException(status_code=400, detail=f"知识库状态不可用: {kb.status}")
        
        # 执行查询
        result = rag_service.query_knowledge_base(
            kb_id=kb_id,
            query=query_request.query,
            query_type=query_request.query_type,
            top_k=query_request.top_k,
            user=current_user
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询知识库失败: {str(e)}")


@router.get("/knowledge-bases/{kb_id}/test-cases", response_model=List[TestCaseFromRAGResponse])
async def get_test_cases_from_rag(
    kb_id: int,
    status: Optional[str] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取从RAG生成的测试用例
    
    - **kb_id**: 知识库ID
    - **status**: 测试用例状态过滤（可选）
    """
    try:
        rag_service = RAGService(db)
        
        # 检查知识库是否存在
        kb = rag_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 获取测试用例
        test_cases = rag_service.get_test_cases_from_rag(
            kb_id=kb_id,
            status=status
        )
        
        return test_cases
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取测试用例失败: {str(e)}")


@router.get("/knowledge-bases/{kb_id}/mind-maps", response_model=List[MindMapFromRAGResponse])
async def get_mind_maps_from_rag(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取从RAG生成的思维导图
    
    - **kb_id**: 知识库ID
    """
    try:
        rag_service = RAGService(db)
        
        # 检查知识库是否存在
        kb = rag_service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 获取思维导图
        mind_maps = rag_service.get_mind_maps_from_rag(kb_id=kb_id)
        
        return mind_maps
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取思维导图失败: {str(e)}")


@router.get("/query-history")
async def get_query_history(
    kb_id: Optional[int] = Query(None, description="知识库ID过滤"),
    limit: int = Query(100, description="返回数量限制"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    获取查询历史
    
    - **kb_id**: 按知识库ID过滤（可选）
    - **limit**: 返回数量限制
    """
    try:
        rag_service = RAGService(db)
        
        query_history = rag_service.get_query_history(
            kb_id=kb_id,
            user_id=current_user.id,
            limit=limit
        )
        
        return query_history
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取查询历史失败: {str(e)}")


@router.get("/test-cases/{test_case_id}/export")
async def export_test_case(
    test_case_id: str,
    format: str = Query("json", description="导出格式: json, csv, excel"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    导出测试用例
    
    - **test_case_id**: 测试用例ID
    - **format**: 导出格式
    """
    try:
        rag_service = RAGService(db)
        
        # 获取测试用例
        test_case = db.query(TestCaseFromRAG).filter(
            TestCaseFromRAG.test_case_id == test_case_id
        ).first()
        
        if not test_case:
            raise HTTPException(status_code=404, detail="测试用例不存在")
        
        # 根据格式导出
        if format == "json":
            return JSONResponse(
                content={
                    "test_case_id": test_case.test_case_id,
                    "title": test_case.title,
                    "description": test_case.description,
                    "priority": test_case.priority,
                    "category": test_case.category,
                    "preconditions": test_case.preconditions,
                    "test_steps": test_case.test_steps,
                    "expected_results": test_case.expected_results,
                    "tags": test_case.tags,
                    "status": test_case.status,
                    "created_at": test_case.created_at.isoformat()
                }
            )
        else:
            # 这里可以添加其他格式的导出逻辑
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出测试用例失败: {str(e)}")


@router.get("/health")
async def rag_health_check(db: Session = Depends(get_db)):
    """RAG模块健康检查"""
    try:
        # 检查数据库连接
        rag_service = RAGService(db)
        knowledge_bases = rag_service.get_knowledge_bases(limit=1)
        
        return {
            "status": "healthy",
            "database": "connected",
            "rag_service": "available",
            "knowledge_base_count": len(knowledge_bases)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }