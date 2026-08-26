"""
场景编排模型
UI/API/性能测试用例编排为场景，支持拖拽排序、临时跳过、选择版本执行
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Text, Integer, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class SceneType(str, enum.Enum):
    UI = "ui"
    API = "api"
    PERFORMANCE = "performance"


class SceneStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"


class Scene(Base):
    """场景编排 — 有序的用例集合"""
    __tablename__ = "scenes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="场景名称")
    description = Column(Text, comment="场景描述")
    scene_type = Column(
        SAEnum(SceneType), nullable=False, default=SceneType.UI,
        comment="场景类型: ui/api/performance"
    )
    project_id = Column(BigInteger, ForeignKey("projects.id"), nullable=False, comment="项目ID")
    version_id = Column(BigInteger, ForeignKey("versions.id"), nullable=True, comment="默认版本ID")
    status = Column(
        SAEnum(SceneStatus), default=SceneStatus.DRAFT, comment="状态"
    )
    # 执行配置（JSON）
    config = Column(JSON, default=dict, comment="执行配置（并发数、持续时间等）")

    created_by = Column(BigInteger, comment="创建人ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    items = relationship("SceneItem", back_populates="scene", cascade="all, delete-orphan",
                         order_by="SceneItem.sort_order")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scene_type": self.scene_type.value if self.scene_type else None,
            "project_id": self.project_id,
            "version_id": self.version_id,
            "status": self.status.value if self.status else None,
            "config": self.config,
            "item_count": len(self.items) if self.items else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SceneItem(Base):
    """场景中的单个用例条目"""
    __tablename__ = "scene_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scene_id = Column(BigInteger, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    # 用例来源表：web_ui_test_case 或 api_test_cases
    case_id = Column(BigInteger, nullable=False, comment="用例ID（ui 条目=功能用例逻辑 id）")
    # ── 方案B：ui 条目绑定具体 WUI 实例 id（执行时按此重解析，软删后自动找最新版）──
    wui_id = Column(String(36), comment="绑定的 WUI 实例ID（执行时重解析目标）")
    case_type = Column(String(20), nullable=False, default="ui", comment="用例类型: ui/api")
    sort_order = Column(Integer, default=0, comment="执行顺序（可拖拽调整）")
    enabled = Column(Boolean, default=True, comment="是否启用（false=临时跳过）")
    custom_params = Column(JSON, default=dict, comment="覆盖参数")

    created_at = Column(DateTime, server_default=func.now())

    scene = relationship("Scene", back_populates="items")

    def to_dict(self):
        return {
            "id": self.id,
            "scene_id": self.scene_id,
            "case_id": self.case_id,
            "case_type": self.case_type,
            "sort_order": self.sort_order,
            "enabled": self.enabled,
            "custom_params": self.custom_params,
        }
