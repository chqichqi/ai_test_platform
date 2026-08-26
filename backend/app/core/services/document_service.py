"""
文档上传和处理服务
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.core.models.document import Document, DocumentChunk
from app.core.schemas.document import DocumentCreate, DocumentUpdate, DocumentChunkCreate
from app.core.services.vector_service import get_vector_service


class DocumentService:
    """文档服务类"""
    
    def __init__(self, db: Session):
        self.db = db
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def save_upload_file(self, file: UploadFile) -> str:
        """
        保存上传的文件
        
        Args:
            file: 上传的文件对象
            
        Returns:
            保存的文件路径
        """
        # 生成唯一文件名
        file_ext = Path(file.filename).suffix if file.filename else ""
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = self.upload_dir / unique_filename
        
        try:
            # 保存文件
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            logger.info(f"File saved: {file_path}")
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to save file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    def validate_file(self, file: UploadFile) -> bool:
        """
        验证上传的文件
        
        Args:
            file: 上传的文件对象
            
        Returns:
            是否有效
        """
        # 检查文件大小
        file.file.seek(0, 2)  # 移动到文件末尾
        file_size = file.file.tell()
        file.file.seek(0)  # 重置文件指针
        
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE} bytes"
            )
        
        # 检查文件扩展名
        if file.filename:
            file_ext = Path(file.filename).suffix.lower().lstrip(".")
            if file_ext not in settings.ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"File extension '{file_ext}' not allowed. Allowed extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}"
                )
        
        return True
    
    def create_document(self, document_data: DocumentCreate, user_id: str) -> Document:
        """
        创建文档记录
        
        Args:
            document_data: 文档数据
            user_id: 用户ID
            
        Returns:
            创建的文档对象
        """
        try:
            # 创建文档记录
            # 处理metadata字段名冲突
            document_dict = document_data.dict()
            metadata_value = document_dict.pop("metadata", {})
            
            db_document = Document(
                **document_dict,
                doc_metadata=metadata_value,
                user_id=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(db_document)
            self.db.commit()
            self.db.refresh(db_document)
            
            logger.info(f"Document created: {db_document.id}")
            return db_document
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create document: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")
    
    def get_document(self, document_id: str, user_id: Optional[str] = None) -> Optional[Document]:
        """
        获取文档
        
        Args:
            document_id: 文档ID
            user_id: 用户ID（可选，用于权限检查）
            
        Returns:
            文档对象或None
        """
        query = self.db.query(Document).filter(Document.id == document_id, Document.deleted_at.is_(None))
        
        if user_id:
            query = query.filter(Document.user_id == user_id)
        
        return query.first()
    
    def get_user_documents(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Document]:
        """
        获取用户的文档列表
        
        Args:
            user_id: 用户ID
            skip: 跳过的记录数
            limit: 返回的最大记录数
            
        Returns:
            文档列表
        """
        return (
            self.db.query(Document)
            .filter(Document.user_id == user_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def update_document(self, document_id: str, document_data: DocumentUpdate, user_id: str) -> Optional[Document]:
        """
        更新文档
        
        Args:
            document_id: 文档ID
            document_data: 更新数据
            user_id: 用户ID
            
        Returns:
            更新后的文档对象或None
        """
        db_document = self.get_document(document_id, user_id)
        
        if not db_document:
            return None
        
        try:
            # 更新字段
            update_data = document_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_document, field, value)
            
            db_document.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(db_document)
            
            logger.info(f"Document updated: {document_id}")
            return db_document
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update document: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to update document: {str(e)}")
    
    def delete_document(self, document_id: str, user_id: str) -> bool:
        """
        软删除文档
        
        Args:
            document_id: 文档ID
            user_id: 用户ID
            
        Returns:
            是否成功删除
        """
        db_document = self.get_document(document_id, user_id)
        
        if not db_document:
            return False
        
        try:
            # 软删除
            db_document.deleted_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Document deleted: {document_id}")
            return True
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete document: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
    
    def add_chunk(self, document_id: str, chunk_data: DocumentChunkCreate) -> DocumentChunk:
        """
        添加文档分块
        
        Args:
            document_id: 文档ID
            chunk_data: 分块数据
            
        Returns:
            创建的分块对象
        """
        try:
            # 创建分块记录
            # 处理metadata字段名冲突
            chunk_dict = chunk_data.dict()
            metadata_value = chunk_dict.pop("metadata", {})
            
            db_chunk = DocumentChunk(
                **chunk_dict,
                chunk_metadata=metadata_value,
                document_id=document_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(db_chunk)
            self.db.commit()
            self.db.refresh(db_chunk)
            
            logger.info(f"Document chunk created for document: {document_id}")
            return db_chunk
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create document chunk: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create document chunk: {str(e)}")
    
    def get_document_chunks(self, document_id: str, skip: int = 0, limit: int = 100) -> List[DocumentChunk]:
        """
        获取文档的分块列表
        
        Args:
            document_id: 文档ID
            skip: 跳过的记录数
            limit: 返回的最大记录数
            
        Returns:
            分块列表
        """
        return (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id, DocumentChunk.deleted_at.is_(None))
            .order_by(DocumentChunk.chunk_index)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def process_document(self, document_id: str, file_path: str) -> int:
        """
        处理文档：加载、分割、生成嵌入向量并存储到向量数据库
        
        Args:
            document_id: 文档ID
            file_path: 文档文件路径
            
        Returns:
            处理的块数量
        """
        try:
            # 获取向量服务
            vector_service = get_vector_service()
            
            # 获取文档记录
            db_document = self.get_document(document_id)
            if not db_document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # 处理文档并存储到向量数据库
            chunks_count = vector_service.process_and_store_document(
                file_path=file_path,
                document_id=document_id,
                metadata={
                    "title": db_document.title,
                    "description": db_document.description,
                    "user_id": db_document.user_id,
                    "file_type": db_document.file_type,
                }
            )
            
            # 更新文档状态
            db_document.status = "processed"
            db_document.processed_chunks = chunks_count
            db_document.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(db_document)
            
            logger.info(f"Document {document_id} processed successfully. Chunks: {chunks_count}")
            return chunks_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to process document {document_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    
    def search_similar_chunks(self, query: str, document_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索相似的文档块
        
        Args:
            query: 查询文本
            document_id: 文档ID（可选，用于限制搜索范围）
            top_k: 返回的最相似结果数量
            
        Returns:
            相似文档块列表
        """
        try:
            vector_service = get_vector_service()
            results = vector_service.search_similar(query, document_id, top_k)
            return results
        except Exception as e:
            logger.error(f"Failed to search similar chunks: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to search similar chunks: {str(e)}")
    
    def delete_document_from_vector_db(self, document_id: str) -> bool:
        """
        从向量数据库中删除文档的所有块
        
        Args:
            document_id: 文档ID
            
        Returns:
            是否成功删除
        """
        try:
            vector_service = get_vector_service()
            success = vector_service.delete_document_chunks(document_id)
            
            if success:
                # 更新文档状态
                db_document = self.get_document(document_id)
                if db_document:
                    db_document.status = "deleted_from_vector"
                    db_document.processed_chunks = 0
                    db_document.updated_at = datetime.utcnow()
                    self.db.commit()
            
            return success
        except Exception as e:
            logger.error(f"Failed to delete document from vector DB {document_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to delete document from vector DB: {str(e)}")


# 创建全局实例
document_service = None

def get_document_service(db: Session) -> DocumentService:
    """获取文档服务实例"""
    global document_service
    if document_service is None:
        document_service = DocumentService(db)
    return document_service