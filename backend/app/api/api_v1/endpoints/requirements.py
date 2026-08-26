"""
需求文档管理 API 端点
对应需求文档 3.3.1 需求文档导入
"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.models.requirement import RequirementDocument, DocumentStatus, DocumentType
from app.core.models.project import Version
from app.core.schemas.requirement import (
    RequirementDocumentCreate, RequirementDocumentUpdate,
    RequirementDocumentResponse, RequirementDocumentListResponse
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


def _require_login_module(db: Session, project_id: int = None) -> None:
    """检查登录模块是否已导入（按项目校验）；未导入则拒绝"""
    from app.core.models.web_ui_test import WebUITestCase
    from app.core.models.requirement import RequirementDocument
    from app.core.models.project import Version

    _login_q = db.query(WebUITestCase).filter(
        WebUITestCase.test_case_id == '__login__',
        WebUITestCase.deleted_at.is_(None)
    )
    if project_id:
        _login_q = _login_q.filter(WebUITestCase.project_id == str(project_id))
    login = _login_q.first()
    if not login:
        raise HTTPException(
            status_code=400,
            detail="请先导入登录模块：在「项目配置 → 登录模块」中导入登录流程后再进行操作"
        )

    if project_id:
        login_doc = db.query(RequirementDocument).join(
            Version, RequirementDocument.version_id == Version.id
        ).filter(
            Version.project_id == project_id,
            RequirementDocument.type == 'business_flow',
            RequirementDocument.name == '登录模块',
            RequirementDocument.content != '',
            RequirementDocument.status != 'pending',
        ).first()
        if not login_doc:
            raise HTTPException(
                status_code=400,
                detail="请先在「项目配置 → 登录模块」中导入并验证登录流程后再进行操作"
            )


@router.post("/", response_model=RequirementDocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    doc_in: RequirementDocumentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """
    创建需求文档
    
    功能要求（需求文档3.3.1）:
    - 支持Word、PDF、Markdown格式
    - 在线链接输入
    - 文档内容存储
    """
    version = db.query(Version).filter(Version.id == doc_in.version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本ID {doc_in.version_id} 不存在")
    _require_login_module(db, version.project_id)

    doc = RequirementDocument(
        version_id=doc_in.version_id,
        name=doc_in.name,
        type=doc_in.type,
        content=doc_in.content,
        file_url=doc_in.file_url,
        status=DocumentStatus.PENDING.value,
        created_by=current_user["user"].id
    )
    
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    logger.info(f"创建需求文档: {doc.name}")
    
    return RequirementDocumentResponse.model_validate(doc)


@router.post("/upload", response_model=RequirementDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    version_id: int = Query(..., description="版本 ID"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """
    上传需求文档
    
    支持：Word(.docx/.doc), PDF(.pdf), Markdown(.md/.markdown), Text(.txt)
    自动解析文档内容，包括图片 OCR 识别
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本 ID {version_id} 不存在")
    _require_login_module(db, version.project_id)

    filename = file.filename or "unknown"
    file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
    
    type_mapping = {
        'docx': DocumentType.WORD.value,
        'doc': DocumentType.WORD.value,
        'pdf': DocumentType.PDF.value,
        'md': DocumentType.MARKDOWN.value,
        'markdown': DocumentType.MARKDOWN.value,
        'txt': DocumentType.TEXT.value,
    }
    
    doc_type = type_mapping.get(file_ext, DocumentType.TEXT.value)
    
    # 保存上传的文件
    import tempfile
    import shutil
    
    try:
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(suffix=f'.{file_ext}', delete=False) as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        # 解析文档
        from app.core.services.document_parser import document_parser
        
        parse_result = document_parser.parse_file(tmp_path, filename)
        content = parse_result['content']
        file_size = len(content.encode('utf-8'))
        
        # 如果有图片 OCR 文本，合并到内容中
        if parse_result.get('images'):
            content = document_parser.merge_content(
                content, 
                parse_result['images']
            )
        
        doc = RequirementDocument(
            version_id=version_id,
            name=filename,
            type=doc_type,
            content=content,
            file_size=file_size,
            parsed_content=parse_result.get('metadata', {}),
            status=DocumentStatus.PARSED.value,
            created_by=current_user["user"].id
        )
        
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        logger.info(f"上传并解析需求文档：{filename}")
        
        # 清理临时文件
        os.unlink(tmp_path)
        
        return RequirementDocumentResponse.model_validate(doc)
        
    except Exception as e:
        logger.error(f"上传需求文档失败：{str(e)}")
        raise HTTPException(status_code=400, detail=f"文件解析失败：{str(e)}")


@router.get("/", response_model=RequirementDocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    version_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """需求文档列表"""
    query = db.query(RequirementDocument)
    
    if version_id:
        query = query.filter(RequirementDocument.version_id == version_id)
    
    if status_filter:
        query = query.filter(RequirementDocument.status == status_filter)
    
    if search:
        pattern = f"%{search}%"
        query = query.filter(RequirementDocument.name.ilike(pattern))
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    docs = query.order_by(RequirementDocument.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return RequirementDocumentListResponse(
        items=[RequirementDocumentResponse.model_validate(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{doc_id}", response_model=RequirementDocumentResponse)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取需求文档详情"""
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档ID {doc_id} 不存在")
    return RequirementDocumentResponse.model_validate(doc)


@router.put("/{doc_id}", response_model=RequirementDocumentResponse)
def update_document(
    doc_id: int,
    doc_in: RequirementDocumentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新需求文档"""
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档 ID {doc_id} 不存在")
    
    update_data = doc_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doc, field, value)
    
    db.commit()
    db.refresh(doc)
    
    logger.info(f"更新需求文档：{doc.name}")
    
    return RequirementDocumentResponse.model_validate(doc)


@router.post("/{doc_id}/update-and-regenerate")
async def update_and_regenerate(
    doc_id: int,
    doc_in: RequirementDocumentUpdate,
    regenerate: bool = Query(True, description="是否重新生成测试用例"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """
    更新需求文档并重新生成测试用例
    
    功能说明:
    - 更新需求文档内容
    - 可选：根据新需求重新生成测试用例
    - 保留原有测试用例（不删除）
    """
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档 ID {doc_id} 不存在")

    # 更新需求文档
    update_data = doc_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doc, field, value)

    db.commit()
    db.refresh(doc)

    result = {
        "document_updated": True,
        "regenerated": False,
        "test_cases_count": 0
    }

    # 如果需要重新生成测试用例
    if regenerate and doc.content:
        version = db.query(Version).filter(Version.id == doc.version_id).first()
        if version:
            project = version.project
            if project:
                from app.core.services.version_generator import VersionGeneratorService

                generator = VersionGeneratorService(db)
                gen_result = await generator.generate_test_assets(
                    version_id=version.id,
                    requirement_doc_content=doc.content,
                    project_name=project.name,
                    version_number=version.version_number
                )

                if gen_result.get("success"):
                    result["regenerated"] = True
                    result["test_cases_count"] = gen_result.get("test_cases_count", 0)
                    result["analysis_summary"] = gen_result.get("analysis_summary", {})
    
    logger.info(f"需求文档更新并重新生成：{result}")
    
    return {
        "success": True,
        "message": "需求文档更新成功" + ("，测试用例已重新生成" if regenerate else ""),
        "data": result,
        "document": RequirementDocumentResponse.model_validate(doc).model_dump()
    }


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除需求文档"""
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档ID {doc_id} 不存在")
    
    db.delete(doc)
    db.commit()
    
    logger.info(f"删除需求文档: {doc.name}")
    
    return None


@router.post("/{doc_id}/parse", response_model=RequirementDocumentResponse)
def parse_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """
    解析需求文档
    
    AI自动解析需求内容，提取结构化信息
    """
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档ID {doc_id} 不存在")
    
    doc.status = DocumentStatus.PARSING.value
    db.commit()
    
    try:
        parsed = _parse_content(doc.content or "", doc.type)
        
        doc.parsed_content = parsed
        doc.status = DocumentStatus.PARSED.value
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        
        logger.info(f"解析需求文档成功: {doc.name}")
    except Exception as e:
        doc.status = DocumentStatus.FAILED.value
        doc.error_message = str(e)
        db.commit()
        logger.error(f"解析需求文档失败: {str(e)}")
    
    return RequirementDocumentResponse.model_validate(doc)


def _parse_content(content: str, doc_type: str) -> dict:
    """解析文档内容"""
    import re
    
    modules = []
    current_module = None
    current_feature = None
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if re.match(r'^#{1,2}\s+', line):
            if current_module:
                modules.append(current_module)
            current_module = {
                'name': re.sub(r'^#+\s+', '', line),
                'features': []
            }
            current_feature = None
        elif re.match(r'^#{3}\s+', line):
            if current_module:
                current_feature = {
                    'name': re.sub(r'^#+\s+', '', line),
                    'points': []
                }
                current_module['features'].append(current_feature)
        elif re.match(r'^[-*]\s+', line):
            point = re.sub(r'^[-*]\s+', '', line)
            if current_feature:
                current_feature['points'].append(point)
            elif current_module:
                if not current_module.get('points'):
                    current_module['points'] = []
                current_module['points'].append(point)
    
    if current_module:
        modules.append(current_module)
    
    return {
        'modules': modules,
        'raw_content': content,
        'doc_type': doc_type
    }