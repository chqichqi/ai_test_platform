"""
需求变更管理 API 端点
用于分析需求变更、上传补充需求、审核变更等
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.requirement_change import (
    RequirementChangeRecord, RequirementChangeBatch,
    ChangeRecordStatus
)
from app.core.models.project import Version
from app.core.models.requirement import TestCase
from app.core.schemas.requirement_change import (
    AnalyzeChangeRequest, AnalyzeChangeResponse,
    RequirementChangeRecordResponse, RequirementChangeRecordListResponse,
    RequirementChangeBatchResponse, RequirementChangeBatchListResponse,
    ApproveChangeRequest, BatchApproveRequest,
    UploadSupplementRequest,
    ChangeSummary, ModuleChangeAnalysis
)
from app.core.services.requirement_change_service import RequirementChangeAnalyzer
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions


router = APIRouter()


@router.post("/analyze")
async def analyze_requirement_change(
    request: AnalyzeChangeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_CREATE)
):
    """
    分析需求变更
    
    对比原需求文档和补充需求文档，识别变更并生成处理建议
    
    需要权限：requirement_change:create
    """
    version = db.query(Version).filter(Version.id == request.version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本ID {request.version_id} 不存在")

    if not request.supplement_requirement:
        raise HTTPException(status_code=400, detail="请提供补充需求文档内容")

    from app.core.models.requirement import TestCase, RequirementDocument
    import datetime as dt

    # 1) 收集所有已保存的原始文档，合并为完整需求上下文
    saved_docs = db.query(RequirementDocument).filter(
        RequirementDocument.version_id == request.version_id
    ).order_by(RequirementDocument.created_at.asc()).all()

    merged_original = ""
    if saved_docs:
        merged_original = "\n\n---\n\n".join([
            f"## {d.name or '原始文档'}\n{d.content or ''}"
            for d in saved_docs
        ])
    else:
        merged_original = version.requirement_doc or ""

    # 2) 合并补充文档到现有需求文档（同版本唯一文档）
    merged_full = (merged_original + "\n\n---\n\n## 补充变更\n\n" + request.supplement_requirement) if merged_original else request.supplement_requirement
    existing_doc = db.query(RequirementDocument).filter(
        RequirementDocument.version_id == request.version_id,
        RequirementDocument.type != 'swagger',
    ).order_by(RequirementDocument.created_at.desc()).first()
    if existing_doc:
        existing_doc.content = merged_full
        existing_doc.name = f"需求文档_{dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        logger.info(f"更新现有文档 id={existing_doc.id}, 合并后长度={len(merged_full)}")
    else:
        existing_doc = RequirementDocument(
            version_id=request.version_id,
            name=f"需求文档_{dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            type="text",
            content=merged_full,
            status="completed",
        )
        db.add(existing_doc)
    # 删除其他旧文档（保持唯一）
    db.query(RequirementDocument).filter(
        RequirementDocument.version_id == request.version_id,
        RequirementDocument.type != 'swagger',
        RequirementDocument.id != existing_doc.id,
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(existing_doc)
    supplement_doc = existing_doc  # 后续引用

    # 3) 检查是否有AI生成的用例
    ai_case_count = db.query(TestCase).filter(
        TestCase.version_id == request.version_id,
        TestCase.generated_by.in_(["ai", "business_flow"])
    ).count()

    if ai_case_count == 0:
        # 首次导入：合并新文档，生成用例
        merged = (merged_original + "\n\n" + request.supplement_requirement) if merged_original else request.supplement_requirement
        version.requirement_doc = merged
        db.commit()

        from app.core.services.version_generator import VersionGeneratorService
        project = version.project
        generator = VersionGeneratorService(db)
        gen_result = await generator.generate_test_assets(
            version_id=request.version_id,
            requirement_doc_content=merged,
            project_name=project.name,
            version_number=version.version_number,
        )
        count = gen_result.get("test_cases_count", 0)
        return {
            "success": True,
            "message": f"首次导入完成，已生成 {count} 条功能用例",
            "change_summary": {"added_count": count, "modified_count": 0, "deleted_count": 0, "unchanged_count": 0,
                               "added_modules": [], "modified_modules": [], "removed_modules": []},
            "detail_analysis": [],
            "total_affected_cases": count,
            "is_first_import": True,
            "merged_document": merged,
            "saved_doc_id": supplement_doc.id,
        }

    # 4) 真正的变更分析：原文档 vs 合并后的完整文档（已包含补充变更）
    analyzer = RequirementChangeAnalyzer(db)
    try:
        result = await analyzer.analyze_change(
            version_id=request.version_id,
            original_doc=merged_original,
            supplement_doc=merged_full,  # 用合并后的完整文档，保证 diff 正确
            user_id=current_user["user"].id,
            supplement_doc_id=supplement_doc.id,
        )

        return AnalyzeChangeResponse(**result)

    except Exception as e:
        logger.error(f"分析需求变更失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败：{str(e)}")


@router.post("/upload-supplement")
async def upload_supplement_requirement(
    version_id: int = Query(..., description="版本ID"),
    file: Optional[UploadFile] = File(None),
    content: Optional[str] = Form(None, description="补充需求内容（文本）"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_CREATE)
):
    """
    上传补充需求文档
    
    支持文件上传或文本内容
    
    需要权限：requirement_change:create
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本ID {version_id} 不存在")
    
    supplement_content = ""
    supplement_file_type = None
    
    if file:
        allowed_extensions = ['docx', 'doc', 'pdf', 'md', 'txt', 'markdown', 
                              'png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp']
        filename = file.filename or ""
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        
        if file_ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持文件类型：{file_ext}，支持的格式：文档(docx,doc,pdf,md,txt) 或 图片(png,jpg,jpeg,bmp,gif,webp)")
        
        supplement_file_type = file_ext
        
        try:
            file_content = await file.read()
            
            if file_ext in ['md', 'txt', 'markdown']:
                supplement_content = file_content.decode('utf-8')
            elif file_ext in ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp']:
                supplement_content = await _process_image_with_ocr(file_content, filename)
            else:
                supplement_content = await _process_document_file(file_content, file_ext, filename)
        except Exception as e:
            logger.error(f"读取上传文件失败：{str(e)}")
            raise HTTPException(status_code=400, detail=f"文件读取失败：{str(e)}")
    
    elif content:
        supplement_content = content
    
    else:
        raise HTTPException(status_code=400, detail="请上传文件或提供文本内容")
    
    original_doc = version.requirement_doc or ""
    
    if not original_doc:
        raise HTTPException(status_code=400, detail="该版本没有原需求文档")
    
    analyzer = RequirementChangeAnalyzer(db)
    
    try:
        result = await analyzer.analyze_change(
            version_id=version_id,
            original_doc=original_doc,
            supplement_doc=supplement_content,
            user_id=current_user["user"].id
        )
        
        return {
            "success": True,
            "message": "补充需求上传成功，变更分析已完成",
            "data": result
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"分析补充需求变更失败：{str(e)}")
        logger.error(f"完整堆栈：\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"分析失败：{str(e)}")


@router.post("/upload-supplement-with-images")
async def upload_supplement_with_images(
    version_id: int = Query(..., description="版本ID"),
    doc_file: Optional[UploadFile] = File(None, description="需求文档文件"),
    images: Optional[List[UploadFile]] = File(None, description="图片文件列表"),
    content: Optional[str] = Form(None, description="补充需求内容（文本）"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_CREATE)
):
    """
    上传补充需求文档（支持文档+图片组合）
    
    可以同时上传文档文件和图片文件，图片会通过OCR提取文字后合并到需求内容中
    
    需要权限：requirement_change:create
    """
    version = db.query(Version).filter(Version.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail=f"版本ID {version_id} 不存在")
    
    supplement_parts = []
    
    if doc_file:
        allowed_doc_extensions = ['docx', 'doc', 'pdf', 'md', 'txt', 'markdown']
        filename = doc_file.filename or ""
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        
        if file_ext not in allowed_doc_extensions:
            raise HTTPException(status_code=400, detail=f"不支持文档类型：{file_ext}")
        
        try:
            file_content = await doc_file.read()
            
            if file_ext in ['md', 'txt', 'markdown']:
                supplement_parts.append(file_content.decode('utf-8'))
            else:
                doc_content = await _process_document_file(file_content, file_ext, filename)
                supplement_parts.append(doc_content)
        except Exception as e:
            logger.error(f"读取文档文件失败：{str(e)}")
            raise HTTPException(status_code=400, detail=f"文档读取失败：{str(e)}")
    
    if images:
        allowed_image_extensions = ['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp']
        
        for idx, img_file in enumerate(images):
            if img_file:
                filename = img_file.filename or f"image_{idx}"
                file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                
                if file_ext not in allowed_image_extensions:
                    logger.warning(f"跳过不支持的图片类型：{file_ext} ({filename})")
                    continue
                
                try:
                    img_content = await img_file.read()
                    ocr_text = await _process_image_with_ocr(img_content, filename)
                    if ocr_text.strip():
                        supplement_parts.append(ocr_text)
                except Exception as e:
                    logger.warning(f"图片OCR处理失败：{filename} - {str(e)}")
    
    if content:
        supplement_parts.append(content)
    
    if not supplement_parts:
        raise HTTPException(status_code=400, detail="请上传文档文件、图片文件或提供文本内容")
    
    supplement_content = "\n\n---\n\n".join(supplement_parts)
    
    original_doc = version.requirement_doc or ""
    
    if not original_doc:
        raise HTTPException(status_code=400, detail="该版本没有原需求文档")
    
    analyzer = RequirementChangeAnalyzer(db)
    
    try:
        result = await analyzer.analyze_change(
            version_id=version_id,
            original_doc=original_doc,
            supplement_doc=supplement_content,
            user_id=current_user["user"].id
        )
        
        return {
            "success": True,
            "message": "补充需求上传成功，变更分析已完成",
            "data": result,
            "ocr_processed": len(images) if images else 0
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"分析补充需求变更失败：{str(e)}")
        logger.error(f"完整堆栈：\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"分析失败：{str(e)}")


async def _process_image_with_ocr(image_data: bytes, filename: str) -> str:
    """
    使用OCR处理图片，提取文字内容
    
    Args:
        image_data: 图片二进制数据
        filename: 文件名
        
    Returns:
        OCR识别的文本内容
    """
    try:
        from app.core.services.ocr_service import OCRService
        
        ocr_service = OCRService(engine='tesseract')
        result = ocr_service.recognize_text(image_data, language='chi_sim+eng')
        
        if result.get('success') and result.get('text'):
            ocr_text = result['text'].strip()
            logger.info(f"图片OCR成功：{filename}，提取文字长度：{len(ocr_text)}")
            return f"\n\n### 图片内容 ({filename})\n\n{ocr_text}\n"
        else:
            error_msg = result.get('error', '未知错误')
            logger.warning(f"图片OCR未识别到文字：{filename} - {error_msg}")
            return f"\n\n### 图片 ({filename})\n\n[图片OCR未能提取文字内容]\n"
            
    except ImportError:
        logger.warning("OCR服务不可用，请确保已安装pytesseract和tesseract")
        return f"\n\n### 图片 ({filename})\n\n[OCR服务未安装，无法提取图片文字]\n"
    except Exception as e:
        logger.error(f"图片OCR处理失败：{filename} - {str(e)}")
        return f"\n\n### 图片 ({filename})\n\n[OCR处理失败：{str(e)}]\n"


async def _process_document_file(file_content: bytes, file_ext: str, filename: str) -> str:
    """
    处理文档文件（Word/PDF），提取文本内容
    
    Args:
        file_content: 文件二进制数据
        file_ext: 文件扩展名
        filename: 文件名
        
    Returns:
        提取的文本内容
    """
    try:
        from app.core.services.document_parser import document_parser
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=f'.{file_ext}', delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = tmp_file.name
        
        try:
            result = document_parser.parse_file(tmp_path, filename)
            content = result.get('content', '')
            
            image_texts = result.get('images', [])
            if image_texts:
                merged_content = document_parser.merge_content(content, image_texts)
                logger.info(f"文档解析成功：{filename}，内容长度：{len(merged_content)}，图片OCR：{len(image_texts)}张")
                return merged_content
            else:
                logger.info(f"文档解析成功：{filename}，内容长度：{len(content)}")
                return content
        finally:
            os.unlink(tmp_path)
            
    except ImportError as e:
        logger.warning(f"文档解析服务不可用：{str(e)}")
        return f"[已上传文档：{filename}，文档解析服务未安装，请手动输入内容]"
    except Exception as e:
        logger.error(f"文档解析失败：{filename} - {str(e)}")
        return f"[已上传文档：{filename}，解析失败：{str(e)}]"


@router.get("/records", response_model=RequirementChangeRecordListResponse)
def list_change_records(
    version_id: Optional[int] = Query(None, description="版本ID"),
    status: Optional[str] = Query(None, description="状态筛选"),
    change_type: Optional[str] = Query(None, description="变更类型筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_READ)
):
    """
    获取变更记录列表
    
    需要权限：requirement_change:read
    """
    query = db.query(RequirementChangeRecord)
    
    if version_id:
        query = query.filter(RequirementChangeRecord.version_id == version_id)
    
    if status:
        query = query.filter(RequirementChangeRecord.status == status)
    
    if change_type:
        query = query.filter(RequirementChangeRecord.change_type == change_type)
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    records = query.order_by(
        RequirementChangeRecord.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    return RequirementChangeRecordListResponse(
        items=[RequirementChangeRecordResponse.model_validate({
            "id": r.id,
            "version_id": r.version_id,
            "change_type": r.change_type,
            "module_name": r.module_name,
            "old_description": r.old_description,
            "new_description": r.new_description,
            "impact_level": r.impact_level,
            "affected_test_cases": r.affected_test_cases or [],
            "affected_test_cases_count": r.affected_test_cases_count or 0,
            "suggested_action": r.suggested_action,
            "suggested_reason": r.suggested_reason,
            "status": r.status,
            "action_taken": r.action_taken,
            "keep_old_cases": r.keep_old_cases or False,
            "new_test_cases": r.new_test_cases or [],
            "new_test_cases_count": r.new_test_cases_count or 0,
            "created_by": r.created_by,
            "created_at": r.created_at,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at,
            "review_comment": r.review_comment,
            "processed_by": r.processed_by,
            "processed_at": r.processed_at,
            "error_message": r.error_message
        }) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/records/{record_id}", response_model=RequirementChangeRecordResponse)
def get_change_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_READ)
):
    """
    获取变更记录详情
    
    需要权限：requirement_change:read
    """
    record = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail=f"变更记录ID {record_id} 不存在")
    
    return RequirementChangeRecordResponse.model_validate(record)


@router.post("/records/{record_id}/approve")
async def approve_change_record(
    record_id: int,
    request: ApproveChangeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_APPROVE)
):
    """
    批准变更记录并执行处理
    
    需要权限：requirement_change:approve
    """
    analyzer = RequirementChangeAnalyzer(db)
    
    try:
        result = await analyzer.process_approved_change(
            change_record_id=record_id,
            action=request.action,
            keep_old_cases=request.keep_old_cases,
            reviewer_id=current_user["user"].id,
            review_comment=request.review_comment
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "处理失败"))
        
        return {
            "success": True,
            "message": "变更处理完成",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批准变更记录失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")


@router.post("/records/{record_id}/reject")
def reject_change_record(
    record_id: int,
    reason: str = Query(..., description="拒绝原因"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_APPROVE)
):
    """
    拒绝变更记录
    
    需要权限：requirement_change:approve
    """
    record = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail=f"变更记录ID {record_id} 不存在")
    
    if record.status != ChangeRecordStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"变更记录状态为{record.status}，无法拒绝")
    
    record.status = ChangeRecordStatus.REJECTED.value
    record.reviewed_by = current_user["user"].id
    record.reviewed_at = datetime.utcnow()
    record.review_comment = reason
    
    db.commit()
    
    logger.info(f"拒绝变更记录{record_id}，原因：{reason}")
    
    return {
        "success": True,
        "message": "变更记录已拒绝",
        "record_id": record_id
    }


@router.post("/batch-approve")
async def batch_approve_changes(
    request: BatchApproveRequest,
    version_id: int = Query(..., description="版本ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_APPROVE)
):
    """
    批量批准变更
    
    支持一键批准所有变更，或逐个指定处理动作
    
    需要权限：requirement_change:approve
    """
    analyzer = RequirementChangeAnalyzer(db)
    
    try:
        result = await analyzer.batch_approve_changes(
            version_id=version_id,
            approve_all=request.approve_all,
            actions=request.actions,
            reviewer_id=current_user["user"].id
        )
        
        return {
            "success": True,
            "message": f"批量处理完成：共{result['total']}条，处理{result['processed']}条，失败{result['failed']}条",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"批量批准变更失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"批量处理失败：{str(e)}")


@router.get("/batches", response_model=RequirementChangeBatchListResponse)
def list_change_batches(
    version_id: Optional[int] = Query(None, description="版本ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_READ)
):
    """
    获取变更批次列表
    
    需要权限：requirement_change:read
    """
    query = db.query(RequirementChangeBatch)
    
    if version_id:
        query = query.filter(RequirementChangeBatch.version_id == version_id)
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    batches = query.order_by(
        RequirementChangeBatch.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    return RequirementChangeBatchListResponse(
        items=[RequirementChangeBatchResponse.model_validate(b) for b in batches],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/batches/{batch_id}", response_model=RequirementChangeBatchResponse)
def get_change_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_READ)
):
    """
    获取变更批次详情
    
    需要权限：requirement_change:read
    """
    batch = db.query(RequirementChangeBatch).filter(
        RequirementChangeBatch.id == batch_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail=f"变更批次ID {batch_id} 不存在")
    
    return RequirementChangeBatchResponse.model_validate(batch)


@router.get("/batches/{batch_id}/records", response_model=RequirementChangeRecordListResponse)
def get_batch_records(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_READ)
):
    """
    获取变更批次下的所有变更记录
    
    需要权限：requirement_change:read
    """
    batch = db.query(RequirementChangeBatch).filter(
        RequirementChangeBatch.id == batch_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail=f"变更批次ID {batch_id} 不存在")
    
    records = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.version_id == batch.version_id,
        RequirementChangeRecord.created_at >= batch.created_at
    ).order_by(RequirementChangeRecord.created_at.desc()).all()
    
    total = len(records)
    
    return RequirementChangeRecordListResponse(
        items=[RequirementChangeRecordResponse.model_validate({
            "id": r.id,
            "version_id": r.version_id,
            "change_type": r.change_type,
            "module_name": r.module_name,
            "old_description": r.old_description,
            "new_description": r.new_description,
            "impact_level": r.impact_level,
            "affected_test_cases": r.affected_test_cases or [],
            "affected_test_cases_count": r.affected_test_cases_count or 0,
            "suggested_action": r.suggested_action,
            "suggested_reason": r.suggested_reason,
            "status": r.status,
            "action_taken": r.action_taken,
            "keep_old_cases": r.keep_old_cases or False,
            "new_test_cases": r.new_test_cases or [],
            "new_test_cases_count": r.new_test_cases_count or 0,
            "created_by": r.created_by,
            "created_at": r.created_at,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at,
            "review_comment": r.review_comment,
            "processed_by": r.processed_by,
            "processed_at": r.processed_at,
            "error_message": r.error_message
        }) for r in records],
        total=total,
        page=1,
        page_size=total,
        total_pages=1
    )


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_change_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_DELETE)
):
    """
    删除变更记录
    
    仅可删除待审核状态的记录
    
    需要权限：requirement_change:delete
    """
    record = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail=f"变更记录ID {record_id} 不存在")
    
    if record.status != ChangeRecordStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"仅可删除待审核状态的记录，当前状态：{record.status}")
    
    db.delete(record)
    db.commit()
    
    logger.info(f"删除变更记录{record_id}")
    
    return None


@router.get("/test-cases/affected")
def get_affected_test_cases(
    record_id: int = Query(..., description="变更记录ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_READ)
):
    """
    获取受影响的测试用例详情
    
    需要权限：test:read
    """
    record = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail=f"变更记录ID {record_id} 不存在")
    
    affected_ids = record.affected_test_cases or []
    
    if not affected_ids:
        return {"test_cases": [], "total": 0}
    
    test_cases = db.query(TestCase).filter(
        TestCase.id.in_(affected_ids)
    ).all()
    
    return {
        "test_cases": [
            {
                "id": tc.id,
                "name": tc.name,
                "module": tc.module,
                "status": tc.status,
                "priority": tc.priority,
                "created_at": tc.created_at.isoformat() if tc.created_at else None
            }
            for tc in test_cases
        ],
        "total": len(test_cases),
        "change_type": record.change_type,
        "module_name": record.module_name
    }


@router.post("/test-cases/batch-update-status")
def batch_update_test_case_status(
    test_case_ids: List[int],
    new_status: str = Query(..., description="新状态"),
    reason: Optional[str] = Query(None, description="状态变更原因"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.TEST_UPDATE)
):
    """
    批量更新测试用例状态
    
    需要权限：test:update
    """
    valid_statuses = [
        "draft", "pending_review", "approved", "rejected",
        "deprecated", "archived"
    ]
    
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的状态：{new_status}")
    
    if not test_case_ids:
        raise HTTPException(status_code=400, detail="请提供测试用例ID列表")
    
    updated = db.query(TestCase).filter(
        TestCase.id.in_(test_case_ids)
    ).update({
        TestCase.status: new_status
    }, synchronize_session=False)
    
    db.commit()
    
    logger.info(f"批量更新{updated}个测试用例状态为{new_status}")
    
    return {
        "success": True,
        "message": f"已更新{updated}个测试用例状态为{new_status}",
        "updated_count": updated
    }


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_change_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_DELETE)
):
    """
    删除变更批次及其所有变更记录
    
    仅可删除待审核状态的批次记录
    
    需要权限：requirement_change:delete
    """
    batch = db.query(RequirementChangeBatch).filter(
        RequirementChangeBatch.id == batch_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail=f"变更批次ID {batch_id} 不存在")
    
    # 删除该批次下的所有待审核变更记录
    records = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.batch_id == batch_id,
        RequirementChangeRecord.status == ChangeRecordStatus.PENDING.value
    ).all()
    
    deleted_count = len(records)
    for record in records:
        db.delete(record)
    
    # 删除批次记录
    db.delete(batch)
    db.commit()
    
    logger.info(f"删除变更批次{batch_id}及其{deleted_count}条待审核记录")
    
    return None


@router.delete("/batches/version/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_pending_batches_by_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_DELETE)
):
    """
    删除指定版本的所有待审核变更批次
    
    需要权限：requirement_change:delete
    """
    # 查询该版本的所有待审核批次
    batches = db.query(RequirementChangeBatch).filter(
        RequirementChangeBatch.version_id == version_id
    ).all()
    
    deleted_batch_count = 0
    deleted_record_count = 0
    
    for batch in batches:
        # 删除该批次下的所有待审核变更记录
        records = db.query(RequirementChangeRecord).filter(
            RequirementChangeRecord.batch_id == batch.id,
            RequirementChangeRecord.status == ChangeRecordStatus.PENDING.value
        ).all()
        
        for record in records:
            db.delete(record)
            deleted_record_count += 1
        
        db.delete(batch)
        deleted_batch_count += 1
    
    db.commit()
    
    logger.info(f"删除版本{version_id}的{deleted_batch_count}个批次，{deleted_record_count}条待审核记录")
    
    return None


@router.post("/records/batch-delete")
def batch_delete_change_records(
    record_ids: List[int],
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.REQUIREMENT_CHANGE_DELETE)
):
    """
    批量删除变更记录
    
    仅可删除待审核状态的记录
    
    需要权限：requirement_change:delete
    """
    if not record_ids:
        raise HTTPException(status_code=400, detail="请提供变更记录ID列表")
    
    records = db.query(RequirementChangeRecord).filter(
        RequirementChangeRecord.id.in_(record_ids)
    ).all()
    
    deleted_count = 0
    skipped_count = 0
    
    for record in records:
        if record.status == ChangeRecordStatus.PENDING.value:
            db.delete(record)
            deleted_count += 1
        else:
            skipped_count += 1
    
    db.commit()
    
    logger.info(f"批量删除{deleted_count}条待审核变更记录，跳过{skipped_count}条非待审核记录")
    
    return {
        "success": True,
        "message": f"已删除{deleted_count}条记录，跳过{skipped_count}条非待审核记录",
        "deleted_count": deleted_count,
        "skipped_count": skipped_count
    }