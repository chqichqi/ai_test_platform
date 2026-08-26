"""
自愈机制和变更感知API端点
对应需求文档 3.4.2 自愈机制 和 3.4.3 变更感知
"""

from typing import Optional, List
from datetime import datetime
import hashlib
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.models.web_ui_test import (
    ElementLocator, AutoHealRecord, PageChangeRecord, PageSnapshot
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


class LocatorCreate(BaseModel):
    project_id: str = Field(..., description="项目ID")
    page_name: Optional[str] = None
    page_url: Optional[str] = None
    element_name: str = Field(..., description="元素名称")
    element_description: Optional[str] = None
    primary_locator: str = Field(..., description="主定位器")
    primary_locator_type: str = Field(..., description="定位器类型")
    fallback_locators: Optional[List[dict]] = None


class LocatorResponse(BaseModel):
    id: str
    project_id: str
    page_name: Optional[str]
    page_url: Optional[str]
    element_name: str
    element_description: Optional[str]
    primary_locator: Optional[str]
    primary_locator_type: Optional[str]
    fallback_locators: Optional[List[dict]]
    confidence_score: float
    auto_healed: bool
    heal_count: int
    last_validated_at: Optional[datetime]
    last_success: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AutoHealRequest(BaseModel):
    locator_id: str = Field(..., description="定位器ID")
    page_html: str = Field(..., description="页面HTML")
    element_description: Optional[str] = Field(None, description="元素描述")
    screenshot_base64: Optional[str] = Field(None, description="页面截图Base64")


class AutoHealResponse(BaseModel):
    success: bool
    old_locator: Optional[str]
    new_locator: Optional[str]
    confidence: float
    match_type: str
    message: str


class PageMonitorRequest(BaseModel):
    project_id: str
    page_url: str
    page_name: Optional[str] = None
    html_content: str
    screenshot_base64: Optional[str] = None


class ChangeAnalysisResponse(BaseModel):
    has_changes: bool
    change_severity: str
    affected_locators: List[dict]
    affected_cases: List[dict]
    change_details: List[dict]


@router.post("/locators", response_model=LocatorResponse, status_code=status.HTTP_201_CREATED)
def create_locator(
    locator_in: LocatorCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建元素定位器"""
    locator = ElementLocator(
        project_id=locator_in.project_id,
        page_name=locator_in.page_name,
        page_url=locator_in.page_url,
        element_name=locator_in.element_name,
        element_description=locator_in.element_description,
        primary_locator=locator_in.primary_locator,
        primary_locator_type=locator_in.primary_locator_type,
        fallback_locators=locator_in.fallback_locators,
        last_validated_at=datetime.utcnow()
    )
    
    db.add(locator)
    db.commit()
    db.refresh(locator)
    
    logger.info(f"创建元素定位器: {locator.element_name}")
    
    return LocatorResponse.model_validate(locator)


@router.get("/locators", response_model=List[LocatorResponse])
def list_locators(
    project_id: str = Query(...),
    page_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取元素定位器列表"""
    query = db.query(ElementLocator).filter(ElementLocator.project_id == project_id)
    
    if page_name:
        query = query.filter(ElementLocator.page_name == page_name)
    
    locators = query.order_by(ElementLocator.created_at.desc()).limit(100).all()
    
    return [LocatorResponse.model_validate(l) for l in locators]


@router.post("/heal", response_model=AutoHealResponse)
def auto_heal(
    request: AutoHealRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """
    自动修复元素定位器
    
    当元素定位失败时，AI分析页面并查找相似元素
    """
    locator = db.query(ElementLocator).filter(ElementLocator.id == request.locator_id).first()
    if not locator:
        raise HTTPException(status_code=404, detail=f"定位器ID {request.locator_id} 不存在")
    
    old_locator = locator.primary_locator
    old_type = locator.primary_locator_type
    
    result = _find_similar_element(
        request.page_html,
        old_locator,
        old_type,
        request.element_description or locator.element_description
    )
    
    if result['success']:
        heal_record = AutoHealRecord(
            locator_id=locator.id,
            old_locator=old_locator,
            new_locator=result['new_locator'],
            old_locator_type=old_type,
            new_locator_type=result['new_type'],
            confidence_score=result['confidence'],
            match_type=result['match_type'],
            match_details=result.get('details'),
            page_html=request.page_html[:50000]
        )
        
        if result['confidence'] >= 0.9:
            locator.primary_locator = result['new_locator']
            locator.primary_locator_type = result['new_type']
            locator.confidence_score = result['confidence']
            locator.auto_healed = True
            locator.heal_count += 1
            heal_record.status = 'auto_approved'
        else:
            heal_record.status = 'pending'
        
        db.add(heal_record)
        db.commit()
        
        logger.info(f"自动修复定位器: {locator.element_name}, 置信度: {result['confidence']}")
    
    return AutoHealResponse(
        success=result['success'],
        old_locator=old_locator,
        new_locator=result.get('new_locator'),
        confidence=result['confidence'],
        match_type=result['match_type'],
        message=result['message']
    )


def _find_similar_element(html: str, old_locator: str, locator_type: str, description: str) -> dict:
    """
    AI查找相似元素
    
    匹配策略：
    1. 文本匹配 - 根据元素描述查找包含相同文本的元素
    2. 属性匹配 - 查找具有相似属性的元素
    3. 位置匹配 - 查找页面相似位置的元素
    """
    result = {
        'success': False,
        'confidence': 0.0,
        'match_type': 'none',
        'message': '未找到匹配元素',
        'new_locator': None,
        'new_type': None
    }
    
    text_content = _extract_text_from_description(description)
    
    if text_content:
        text_pattern = re.compile(re.escape(text_content), re.IGNORECASE)
        if text_pattern.search(html):
            new_locator = f'text={text_content}'
            result.update({
                'success': True,
                'confidence': 0.85,
                'match_type': 'text',
                'message': f'通过文本匹配找到元素: "{text_content}"',
                'new_locator': new_locator,
                'new_type': 'text'
            })
            return result
    
    if locator_type in ['css', 'xpath']:
        pattern_match = _find_pattern_variant(html, old_locator, locator_type)
        if pattern_match:
            result.update({
                'success': True,
                'confidence': pattern_match['confidence'],
                'match_type': 'pattern',
                'message': '通过模式变体匹配找到元素',
                'new_locator': pattern_match['locator'],
                'new_type': pattern_match['type']
            })
            return result
    
    keywords = re.findall(r'\w+', description.lower())
    if keywords:
        for keyword in keywords[:3]:
            if len(keyword) > 2:
                attr_patterns = [
                    f'[data-testid*="{keyword}"]',
                    f'[aria-label*="{keyword}"]',
                    f'[title*="{keyword}"]',
                    f'[name*="{keyword}"]',
                    f'[id*="{keyword}"]',
                ]
                
                for pattern in attr_patterns:
                    attr_name = pattern.split('[')[1].split('*')[0]
                    if attr_name.lower() in html.lower():
                        result.update({
                            'success': True,
                            'confidence': 0.75,
                            'match_type': 'attribute',
                            'message': f'通过属性匹配找到元素: {attr_name}',
                            'new_locator': pattern,
                            'new_type': 'css'
                        })
                        return result
    
    return result


def _extract_text_from_description(description: str) -> str:
    """从描述中提取可能的文本内容"""
    patterns = [
        r'"([^"]+)"',
        r"'([^']+)'",
        r'【(.+?)】',
        r'「(.+?)」',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)
    
    words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', description)
    if words:
        return words[0]
    
    return ''


def _find_pattern_variant(html: str, locator: str, locator_type: str) -> Optional[dict]:
    """查找定位器的变体"""
    if locator_type == 'css':
        if locator.startswith('#'):
            new_id = locator[1:]
            if f'id="{new_id}"' not in html and f"id='{new_id}'" not in html:
                parts = new_id.split('-')
                if len(parts) > 1:
                    for i in range(len(parts)):
                        variant = '-'.join(parts[:i+1])
                        if f'id="{variant}"' in html or f"id='{variant}'" in html:
                            return {
                                'locator': f'#{variant}',
                                'type': 'css',
                                'confidence': 0.7
                            }
    
    return None


@router.post("/monitor", response_model=ChangeAnalysisResponse)
def monitor_page(
    request: PageMonitorRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    监控页面变更
    
    对比当前页面与历史快照，检测变更
    """
    current_hash = hashlib.sha256(request.html_content.encode()).hexdigest()
    
    last_snapshot = db.query(PageSnapshot).filter(
        PageSnapshot.project_id == request.project_id,
        PageSnapshot.page_url == request.page_url
    ).order_by(PageSnapshot.created_at.desc()).first()
    
    if not last_snapshot:
        snapshot = PageSnapshot(
            project_id=request.project_id,
            page_url=request.page_url,
            html_content=request.html_content[:500000],
            hash=current_hash,
            elements=_extract_elements(request.html_content)
        )
        db.add(snapshot)
        db.commit()
        
        return ChangeAnalysisResponse(
            has_changes=False,
            change_severity='none',
            affected_locators=[],
            affected_cases=[],
            change_details=[]
        )
    
    if last_snapshot.hash == current_hash:
        return ChangeAnalysisResponse(
            has_changes=False,
            change_severity='none',
            affected_locators=[],
            affected_cases=[],
            change_details=[]
        )
    
    changes = _detect_changes(last_snapshot.html_content, request.html_content)
    
    affected_locators = _find_affected_locators(db, request.project_id, changes)
    
    change_record = PageChangeRecord(
        project_id=request.project_id,
        page_url=request.page_url,
        page_name=request.page_name,
        change_type='content_change',
        change_severity='high' if len(affected_locators) > 3 else 'medium' if affected_locators else 'low',
        affected_locators=[{'id': l.id, 'name': l.element_name} for l in affected_locators],
        old_snapshot_id=last_snapshot.id,
        details=changes[:20]
    )
    
    new_snapshot = PageSnapshot(
        project_id=request.project_id,
        page_url=request.page_url,
        html_content=request.html_content[:500000],
        hash=current_hash,
        elements=_extract_elements(request.html_content)
    )
    
    db.add(change_record)
    db.add(new_snapshot)
    db.commit()
    
    logger.info(f"检测到页面变更: {request.page_url}, 受影响定位器: {len(affected_locators)}")
    
    return ChangeAnalysisResponse(
        has_changes=True,
        change_severity=change_record.change_severity,
        affected_locators=[{'id': l.id, 'name': l.element_name, 'locator': l.primary_locator} for l in affected_locators],
        affected_cases=[],
        change_details=changes[:10]
    )


def _extract_elements(html: str) -> List[dict]:
    """提取页面元素"""
    elements = []
    
    patterns = [
        (r'data-testid="([^"]+)"', 'data-testid'),
        (r'id="([^"]+)"', 'id'),
        (r'class="([^"]+)"', 'class'),
        (r'name="([^"]+)"', 'name'),
    ]
    
    for pattern, attr_type in patterns:
        matches = re.findall(pattern, html)
        for match in matches:
            elements.append({
                'type': attr_type,
                'value': match,
                'count': matches.count(match)
            })
    
    return elements[:100]


def _detect_changes(old_html: str, new_html: str) -> List[dict]:
    """检测页面变更"""
    changes = []
    
    old_ids = set(re.findall(r'id="([^"]+)"', old_html))
    new_ids = set(re.findall(r'id="([^"]+)"', new_html))
    
    removed = old_ids - new_ids
    added = new_ids - old_ids
    
    for id_val in removed:
        changes.append({
            'type': 'element_removed',
            'detail': f'元素移除: #{id_val}',
            'element': id_val
        })
    
    for id_val in added:
        changes.append({
            'type': 'element_added',
            'detail': f'元素新增: #{id_val}',
            'element': id_val
        })
    
    return changes


def _find_affected_locators(db: Session, project_id: str, changes: List[dict]) -> List[ElementLocator]:
    """查找受影响的定位器"""
    affected = []
    
    for change in changes:
        element = change.get('element')
        if element:
            locators = db.query(ElementLocator).filter(
                ElementLocator.project_id == project_id,
                ElementLocator.primary_locator.contains(element)
            ).all()
            affected.extend(locators)
    
    return list({l.id: l for l in affected}.values())


@router.get("/heal-records")
def list_heal_records(
    project_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取自动修复记录列表"""
    query = db.query(AutoHealRecord).join(
        ElementLocator, AutoHealRecord.locator_id == ElementLocator.id
    ).filter(ElementLocator.project_id == project_id)
    
    if status:
        query = query.filter(AutoHealRecord.status == status)
    
    records = query.order_by(AutoHealRecord.created_at.desc()).limit(50).all()
    
    return {
        'items': [r.to_dict() for r in records],
        'total': len(records)
    }


@router.post("/heal-records/{record_id}/approve")
def approve_heal(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """审批自动修复"""
    record = db.query(AutoHealRecord).filter(AutoHealRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"修复记录ID {record_id} 不存在")
    
    locator = db.query(ElementLocator).filter(ElementLocator.id == record.locator_id).first()
    if locator:
        locator.primary_locator = record.new_locator
        locator.primary_locator_type = record.new_locator_type
        locator.confidence_score = record.confidence_score
        locator.auto_healed = True
    
    record.status = 'approved'
    record.approved_by = str(current_user["user"].id)
    record.approved_at = datetime.utcnow()
    
    db.commit()
    
    logger.info(f"审批自动修复: {record_id}")
    
    return {'message': '审批成功'}


@router.post("/heal-records/{record_id}/reject")
def reject_heal(
    record_id: int,
    comment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """拒绝自动修复"""
    record = db.query(AutoHealRecord).filter(AutoHealRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"修复记录ID {record_id} 不存在")
    
    record.status = 'rejected'
    record.approved_by = str(current_user["user"].id)
    record.approved_at = datetime.utcnow()
    record.review_comment = comment
    
    db.commit()
    
    return {'message': '已拒绝'}


@router.get("/change-records")
def list_change_records(
    project_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取变更记录列表"""
    query = db.query(PageChangeRecord).filter(
        PageChangeRecord.project_id == project_id
    )
    
    if status:
        query = query.filter(PageChangeRecord.status == status)
    
    records = query.order_by(PageChangeRecord.created_at.desc()).limit(50).all()
    
    return {
        'items': [r.to_dict() for r in records],
        'total': len(records)
    }


@router.post("/change-records/{record_id}/review")
def review_change(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """审核变更记录"""
    record = db.query(PageChangeRecord).filter(PageChangeRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"变更记录ID {record_id} 不存在")
    
    record.status = 'reviewed'
    record.reviewed_by = str(current_user["user"].id)
    record.reviewed_at = datetime.utcnow()
    
    db.commit()
    
    return {'message': '审核成功'}