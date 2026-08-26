"""
通知与告警API端点
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.models.notification import (
    NotificationChannel, AlertRule, MessageTemplate, NotificationHistory
)
from app.core.services.notification_service import (
    NotificationManager, CHANNEL_TYPE_OPTIONS, CONDITION_TYPE_OPTIONS
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


class ChannelCreate(BaseModel):
    project_id: Optional[int] = None
    name: str
    type: str
    webhook_url: Optional[str] = None
    secret: Optional[str] = None
    email_config: Optional[dict] = None
    enabled: bool = True


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    webhook_url: Optional[str] = None
    secret: Optional[str] = None
    email_config: Optional[dict] = None
    enabled: Optional[bool] = None


class AlertRuleCreate(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    condition_type: str
    condition_config: Optional[dict] = None
    channel_ids: List[int] = []
    receivers: Optional[List[str]] = None
    custom_template: Optional[str] = None
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    condition_type: Optional[str] = None
    condition_config: Optional[dict] = None
    channel_ids: Optional[List[int]] = None
    receivers: Optional[List[str]] = None
    custom_template: Optional[str] = None
    enabled: Optional[bool] = None


class SendNotificationRequest(BaseModel):
    channel_id: int
    title: str
    content: str
    recipients: Optional[List[str]] = None


@router.post("/channels", status_code=status.HTTP_201_CREATED)
def create_channel(
    channel_in: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建通知渠道"""
    channel = NotificationChannel(
        project_id=channel_in.project_id,
        name=channel_in.name,
        type=channel_in.type,
        webhook_url=channel_in.webhook_url,
        secret=channel_in.secret,
        email_config=channel_in.email_config,
        enabled=channel_in.enabled,
        created_by=current_user["user"].id
    )
    
    db.add(channel)
    db.commit()
    db.refresh(channel)
    
    logger.info(f"创建通知渠道: {channel.name}, type={channel.type}")
    
    return {"id": channel.id, "message": "创建成功"}


@router.get("/channels")
def list_channels(
    project_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取通知渠道列表"""
    query = db.query(NotificationChannel)
    
    if project_id:
        query = query.filter(NotificationChannel.project_id == project_id)
    
    total = query.count()
    channels = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": c.id,
                "project_id": c.project_id,
                "name": c.name,
                "type": c.type,
                "enabled": c.enabled,
                "test_status": c.test_status,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in channels
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/channels/{channel_id}")
def get_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取通知渠道详情"""
    channel = db.query(NotificationChannel).filter(
        NotificationChannel.id == channel_id
    ).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")
    
    return {
        "id": channel.id,
        "project_id": channel.project_id,
        "name": channel.name,
        "type": channel.type,
        "webhook_url": channel.webhook_url,
        "secret": "***" if channel.secret else None,
        "email_config": {
            k: ("***" if k == "password" else v)
            for k, v in (channel.email_config or {}).items()
        },
        "enabled": channel.enabled,
        "test_status": channel.test_status,
        "test_message": channel.test_message,
        "last_test_at": channel.last_test_at.isoformat() if channel.last_test_at else None,
        "created_at": channel.created_at.isoformat() if channel.created_at else None
    }


@router.put("/channels/{channel_id}")
def update_channel(
    channel_id: int,
    channel_in: ChannelUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新通知渠道"""
    channel = db.query(NotificationChannel).filter(
        NotificationChannel.id == channel_id
    ).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")
    
    update_data = channel_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(channel, key, value)
    
    db.commit()
    db.refresh(channel)
    
    logger.info(f"更新通知渠道: {channel.name}")
    
    return {"message": "更新成功"}


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除通知渠道"""
    channel = db.query(NotificationChannel).filter(
        NotificationChannel.id == channel_id
    ).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="渠道不存在")
    
    db.delete(channel)
    db.commit()
    
    logger.info(f"删除通知渠道: {channel.name}")
    
    return {"message": "删除成功"}


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """测试通知渠道"""
    manager = NotificationManager(db)
    result = await manager.test_channel(channel_id)
    
    return result


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    rule_in: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """创建告警规则"""
    rule = AlertRule(
        project_id=rule_in.project_id,
        name=rule_in.name,
        description=rule_in.description,
        condition_type=rule_in.condition_type,
        condition_config=rule_in.condition_config,
        channel_ids=rule_in.channel_ids,
        receivers=rule_in.receivers,
        custom_template=rule_in.custom_template,
        enabled=rule_in.enabled,
        created_by=current_user["user"].id
    )
    
    db.add(rule)
    db.commit()
    db.refresh(rule)
    
    logger.info(f"创建告警规则: {rule.name}")
    
    return {"id": rule.id, "message": "创建成功"}


@router.get("/rules")
def list_rules(
    project_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取告警规则列表"""
    query = db.query(AlertRule).filter(AlertRule.project_id == project_id)
    
    total = query.count()
    rules = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "condition_type": r.condition_type,
                "enabled": r.enabled,
                "trigger_count": r.trigger_count,
                "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None
            }
            for r in rules
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.put("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    rule_in: AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """更新告警规则"""
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    update_data = rule_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    
    db.commit()
    
    return {"message": "更新成功"}


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_DELETE)
):
    """删除告警规则"""
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    db.delete(rule)
    db.commit()
    
    return {"message": "删除成功"}


@router.post("/send")
async def send_notification(
    request: SendNotificationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_UPDATE)
):
    """发送通知"""
    manager = NotificationManager(db)
    result = await manager.send_notification(
        channel_id=request.channel_id,
        title=request.title,
        content=request.content,
        recipients=request.recipients
    )
    
    return result


@router.get("/history")
def list_history(
    project_id: int = Query(...),
    channel_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """获取通知历史"""
    query = db.query(NotificationHistory).filter(
        NotificationHistory.project_id == project_id
    )
    
    if channel_id:
        query = query.filter(NotificationHistory.channel_id == channel_id)
    if status:
        query = query.filter(NotificationHistory.status == status)
    
    total = query.count()
    history = query.order_by(NotificationHistory.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    
    return {
        "items": [
            {
                "id": h.id,
                "channel_id": h.channel_id,
                "recipient": h.recipient,
                "subject": h.subject,
                "status": h.status,
                "error_message": h.error_message,
                "sent_at": h.sent_at.isoformat() if h.sent_at else None,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in history
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/options")
def get_options():
    """获取选项配置"""
    return {
        "channel_types": CHANNEL_TYPE_OPTIONS,
        "condition_types": CONDITION_TYPE_OPTIONS
    }