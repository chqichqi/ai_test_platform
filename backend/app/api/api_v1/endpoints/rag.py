"""
RAG知识库API端点
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import success_response, error_response
from app.core.schemas.document import (
    DocumentResponse, 
    DocumentListResponse,
    DocumentUploadRequest,
    DocumentChunkResponse,
    DocumentProcessRequest,
    DocumentSearchRequest,
    DocumentSearchResponse
)
from app.core.services.document_service import get_document_service, DocumentService
from app.core.middleware.permission_middleware import Permissions, require_permissions

router = APIRouter()


@router.get("/", response_model=DocumentListResponse)
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    auth_data: dict = Depends(Permissions.RAG_ACCESS),
    db: Session = Depends(get_db),
):
    """
    获取当前用户的文档列表
    
    Args:
        skip: 跳过的记录数
        limit: 返回的最大记录数
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        文档列表
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        documents = document_service.get_user_documents(user.id, skip, limit)
        total_count = len(documents)
        
        # 转换为响应模型
        document_responses = [
            DocumentResponse.from_orm(doc) for doc in documents
        ]
        
        return success_response(
            data={
                "data": document_responses,
                "total": total_count,
                "skip": skip,
                "limit": limit,
            },
            message="Documents retrieved successfully",
        )
    
    except Exception as e:
        logger.error(f"Failed to get documents: {str(e)}")
        return error_response(
            code=500,
            message="Failed to retrieve documents",
            error=str(e),
        )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    metadata: Optional[str] = Form("{}"),
    auth_data: dict = Depends(Permissions.RAG_UPLOAD),
    db: Session = Depends(get_db),
):
    """
    上传文档到RAG知识库
    
    Args:
        file: 上传的文件
        title: 文档标题
        description: 文档描述
        metadata: 文档元数据（JSON字符串）
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        上传的文档信息
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        # 验证文件
        document_service.validate_file(file)
        
        # 保存文件
        file_path = document_service.save_upload_file(file)
        
        # 解析元数据
        import json
        try:
            metadata_dict = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            metadata_dict = {}
        
        # 获取文件信息
        file.file.seek(0, 2)  # 移动到文件末尾
        file_size = file.file.tell()
        file.file.seek(0)  # 重置文件指针
        
        # 创建文档记录
        from app.core.schemas.document import DocumentCreate
        
        document_data = DocumentCreate(
            title=title,
            description=description,
            file_path=file_path,
            file_name=file.filename,
            file_size=file_size,
            file_type=file.content_type or "application/octet-stream",
            metadata=metadata_dict,
        )
        
        db_document = document_service.create_document(document_data, user.id)
        
        logger.info(f"Document uploaded by user {user.username}: {db_document.id}")
        
        return success_response(
            data=DocumentResponse.from_orm(db_document),
            message="Document uploaded successfully",
            status_code=status.HTTP_201_CREATED,
        )
    
    except HTTPException as e:
        logger.error(f"Upload failed: {str(e.detail)}")
        return error_response(
            code=e.status_code,
            message="Upload failed",
            error=str(e.detail),
        )
    
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return error_response(
            code=500,
            message="Upload failed",
            error=str(e),
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    auth_data: dict = Depends(Permissions.RAG_ACCESS),
    db: Session = Depends(get_db),
):
    """
    获取特定文档的详细信息
    
    Args:
        document_id: 文档ID
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        文档信息
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        db_document = document_service.get_document(document_id, user.id)
        
        if not db_document:
            return error_response(
                code=404,
                message="Document not found",
                error="The requested document does not exist or you don't have permission to access it",
            )
        
        return success_response(
            data=DocumentResponse.from_orm(db_document),
            message="Document retrieved successfully",
        )
    
    except Exception as e:
        logger.error(f"Failed to get document: {str(e)}")
        return error_response(
            code=500,
            message="Failed to retrieve document",
            error=str(e),
        )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    auth_data: dict = Depends(Permissions.RAG_DELETE),
    db: Session = Depends(get_db),
):
    """
    删除文档
    
    Args:
        document_id: 文档ID
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        success = document_service.delete_document(document_id, user.id)
        
        if not success:
            return error_response(
                code=404,
                message="Document not found",
                error="The requested document does not exist or you don't have permission to delete it",
            )
        
        return success_response(
            data=None,
            message="Document deleted successfully",
        )
    
    except HTTPException as e:
        logger.error(f"Delete failed: {str(e.detail)}")
        return error_response(
            code=e.status_code,
            message="Delete failed",
            error=str(e.detail),
        )
    
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        return error_response(
            code=500,
            message="Delete failed",
            error=str(e),
        )


@router.get("/{document_id}/chunks", response_model=List[DocumentChunkResponse])
async def get_document_chunks(
    document_id: str,
    skip: int = 0,
    limit: int = 100,
    auth_data: dict = Depends(Permissions.RAG_ACCESS),
    db: Session = Depends(get_db),
):
    """
    获取文档的分块列表
    
    Args:
        document_id: 文档ID
        skip: 跳过的记录数
        limit: 返回的最大记录数
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        分块列表
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        # 检查文档是否存在且用户有权限
        db_document = document_service.get_document(document_id, user.id)
        
        if not db_document:
            return error_response(
                code=404,
                message="Document not found",
                error="The requested document does not exist or you don't have permission to access it",
            )
        
        # 获取分块
        chunks = document_service.get_document_chunks(document_id, skip, limit)
        
        # 转换为响应模型
        chunk_responses = [
            DocumentChunkResponse.from_orm(chunk) for chunk in chunks
        ]
        
        return success_response(
            data=chunk_responses,
            message="Document chunks retrieved successfully",
        )
    
    except Exception as e:
        logger.error(f"Failed to get document chunks: {str(e)}")
        return error_response(
            code=500,
            message="Failed to retrieve document chunks",
            error=str(e),
        )


@router.post("/{document_id}/process")
async def process_document(
    document_id: str,
    auth_data: dict = Depends(Permissions.RAG_PROCESS),
    db: Session = Depends(get_db),
):
    """
    处理文档：加载、分割、生成嵌入向量并存储到向量数据库
    
    Args:
        document_id: 文档ID
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        处理结果
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        # 检查文档是否存在且用户有权限
        db_document = document_service.get_document(document_id, user.id)
        
        if not db_document:
            return error_response(
                code=404,
                message="Document not found",
                error="The requested document does not exist or you don't have permission to access it",
            )
        
        # 处理文档
        chunks_count = document_service.process_document(document_id, db_document.file_path)
        
        return success_response(
            data={
                "document_id": document_id,
                "chunks_processed": chunks_count,
                "status": "processed"
            },
            message=f"Document processed successfully. {chunks_count} chunks created.",
        )
    
    except HTTPException as e:
        logger.error(f"Document processing failed: {str(e.detail)}")
        return error_response(
            code=e.status_code,
            message="Document processing failed",
            error=str(e.detail),
        )
    
    except Exception as e:
        logger.error(f"Document processing failed: {str(e)}")
        return error_response(
            code=500,
            message="Document processing failed",
            error=str(e),
        )


@router.post("/search")
async def search_documents(
    search_request: DocumentSearchRequest,
    auth_data: dict = Depends(Permissions.RAG_SEARCH),
    db: Session = Depends(get_db),
):
    """
    搜索相似的文档块
    
    Args:
        search_request: 搜索请求
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        搜索结果
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        # 执行搜索
        results = document_service.search_similar_chunks(
            query=search_request.query,
            document_id=search_request.document_id,
            top_k=search_request.top_k
        )
        
        return success_response(
            data={
                "query": search_request.query,
                "results": results,
                "total_results": len(results)
            },
            message="Search completed successfully",
        )
    
    except HTTPException as e:
        logger.error(f"Search failed: {str(e.detail)}")
        return error_response(
            code=e.status_code,
            message="Search failed",
            error=str(e.detail),
        )
    
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return error_response(
            code=500,
            message="Search failed",
            error=str(e),
        )


@router.delete("/{document_id}/vector")
async def delete_document_from_vector_db(
    document_id: str,
    auth_data: dict = Depends(Permissions.RAG_DELETE),
    db: Session = Depends(get_db),
):
    """
    从向量数据库中删除文档的所有块
    
    Args:
        document_id: 文档ID
        auth_data: 认证数据
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        user = auth_data["user"]
        document_service = get_document_service(db)
        
        # 检查文档是否存在且用户有权限
        db_document = document_service.get_document(document_id, user.id)
        
        if not db_document:
            return error_response(
                code=404,
                message="Document not found",
                error="The requested document does not exist or you don't have permission to access it",
            )
        
        # 从向量数据库中删除
        success = document_service.delete_document_from_vector_db(document_id)
        
        if success:
            return success_response(
                data=None,
                message="Document removed from vector database successfully",
            )
        else:
            return error_response(
                code=500,
                message="Failed to remove document from vector database",
                error="Unknown error occurred",
            )
    
    except HTTPException as e:
        logger.error(f"Vector deletion failed: {str(e.detail)}")
        return error_response(
            code=e.status_code,
            message="Vector deletion failed",
            error=str(e.detail),
        )
    
    except Exception as e:
        logger.error(f"Vector deletion failed: {str(e)}")
        return error_response(
            code=500,
            message="Vector deletion failed",
            error=str(e),
        )