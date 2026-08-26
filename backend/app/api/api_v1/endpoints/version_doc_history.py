"""
版本文档历史API
对应需求文档 3.1.2 版本文档历史
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.models.project import Project, Version
from app.core.models.project_ext import VersionDocHistory
from app.core.schemas.project_ext import (
    VersionDocHistoryResponse,
    VersionDocHistoryList,
)
from app.api.api_v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/{project_id}/versions/{version_id}/doc-history", response_model=VersionDocHistoryList)
def list_version_doc_history(
    project_id: int,
    version_id: int,
    doc_type: Optional[str] = Query(None, description="文档类型过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取版本文档历史列表
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 检查版本是否存在
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.project_id == project_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    # 构建查询
    query = db.query(VersionDocHistory).filter(
        VersionDocHistory.version_id == version_id
    )
    
    if doc_type:
        query = query.filter(VersionDocHistory.doc_type == doc_type)
    
    # 统计总数
    total = query.count()
    
    # 分页查询
    history_items = query.order_by(
        desc(VersionDocHistory.uploaded_at)
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    return VersionDocHistoryList(
        items=history_items,
        total=total
    )


@router.get("/{project_id}/versions/{version_id}/doc-history/{history_id}", response_model=VersionDocHistoryResponse)
def get_version_doc_history(
    project_id: int,
    version_id: int,
    history_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取文档历史详情
    """
    # 检查版本是否存在
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.project_id == project_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    history = db.query(VersionDocHistory).filter(
        VersionDocHistory.id == history_id,
        VersionDocHistory.version_id == version_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="文档历史记录不存在")
    
    return history


@router.post("/{project_id}/versions/{version_id}/doc-history", response_model=VersionDocHistoryResponse)
def create_version_doc_history(
    project_id: int,
    version_id: int,
    doc_type: Optional[str] = None,
    doc_url: Optional[str] = None,
    doc_content: Optional[dict] = None,
    change_summary: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    创建版本文档历史记录
    
    通常由系统自动调用，当版本文档更新时记录历史
    """
    # 检查版本是否存在
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.project_id == project_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    # 创建历史记录
    history = VersionDocHistory(
        version_id=version_id,
        doc_type=doc_type,
        doc_url=doc_url,
        doc_content=doc_content,
        change_summary=change_summary,
        uploaded_by=current_user.get("id"),
    )
    
    db.add(history)
    db.commit()
    db.refresh(history)
    
    return history


@router.delete("/{project_id}/versions/{version_id}/doc-history/{history_id}")
def delete_version_doc_history(
    project_id: int,
    version_id: int,
    history_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    删除文档历史记录
    """
    # 检查版本是否存在
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.project_id == project_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    history = db.query(VersionDocHistory).filter(
        VersionDocHistory.id == history_id,
        VersionDocHistory.version_id == version_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="文档历史记录不存在")
    
    db.delete(history)
    db.commit()
    
    return {"message": "文档历史记录已删除"}


@router.get("/{project_id}/versions/{version_id}/doc-history/{history_id}/compare")
def compare_doc_history(
    project_id: int,
    version_id: int,
    history_id: int,
    compare_with_id: Optional[int] = Query(None, description="对比的历史记录ID，不填则对比当前版本"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    对比文档历史版本
    """
    # 检查版本是否存在
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.project_id == project_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    # 获取当前历史记录
    current_history = db.query(VersionDocHistory).filter(
        VersionDocHistory.id == history_id,
        VersionDocHistory.version_id == version_id
    ).first()
    
    if not current_history:
        raise HTTPException(status_code=404, detail="文档历史记录不存在")
    
    # 获取对比的历史记录
    if compare_with_id:
        compare_history = db.query(VersionDocHistory).filter(
            VersionDocHistory.id == compare_with_id,
            VersionDocHistory.version_id == version_id
        ).first()
        
        if not compare_history:
            raise HTTPException(status_code=404, detail="对比的文档历史记录不存在")
    else:
        # 对比当前版本
        compare_history = None
    
    return {
        "current": {
            "id": current_history.id,
            "uploaded_at": current_history.uploaded_at,
            "uploaded_by": current_history.uploaded_by,
            "doc_content": current_history.doc_content,
            "change_summary": current_history.change_summary,
        },
        "compare_with": {
            "id": compare_history.id if compare_history else None,
            "uploaded_at": compare_history.uploaded_at if compare_history else None,
            "uploaded_by": compare_history.uploaded_by if compare_history else None,
            "doc_content": compare_history.doc_content if compare_history else version.requirement_doc_content,
            "change_summary": compare_history.change_summary if compare_history else "当前版本",
        } if compare_history or version.requirement_doc_content else None
    }
