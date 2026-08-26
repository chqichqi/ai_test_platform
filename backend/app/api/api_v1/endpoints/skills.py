"""
SKILL管理API端点
对应需求文档 3.16 SKILL管理模块
"""

import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

from app.core.database import get_db
from app.core.models.test_skill import TestSkill, SkillExample, SkillUsageLog, SkillType, SkillStatus
from app.core.schemas.skill import (
    SkillCreate, SkillUpdate, SkillResponse, SkillDetailResponse, SkillListResponse,
    SkillExampleCreate, SkillExampleResponse, SkillQueryParams,
    SkillTestRequest, SkillTestResponse,
    ProjectSkillCreate, ProjectSkillResponse,
    SkillExportResponse, SkillImportRequest,
    SkillContentSchema, SkillRoleSchema, SkillInputSchema, SkillOutputSchema,
    SkillMethodSchema, SkillDomainRuleSchema
)
from app.core.logger import logger
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


# ==================== 默认SKILL内容模板 ====================

def get_default_skill_content(skill_type: str) -> dict:
    """获取默认SKILL内容"""
    return {
        "role": {
            "name": "测试专家",
            "description": f"你是一位资深的{skill_type}测试专家，擅长根据需求文档生成高质量的测试用例。",
            "expertise": [
                "深入理解业务需求",
                "识别功能点和测试要点",
                "生成覆盖全面、可执行的测试用例"
            ],
            "behavior_rules": [
                "遵循输出规范格式",
                "使用专业测试术语",
                "考虑用户实际使用场景"
            ]
        },
        "input": {
            "required_fields": ["project_context", "requirement_text"],
            "optional_fields": ["requirement_images_ocr", "existing_test_cases", "special_requirements"]
        },
        "output": {
            "format": "json",
            "schema": {
                "test_cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "用例标题"},
                            "module": {"type": "string", "description": "所属模块"},
                            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                            "preconditions": {"type": "array", "items": {"type": "string"}},
                            "test_steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "step": {"type": "integer"},
                                        "action": {"type": "string"},
                                        "expected": {"type": "string"}
                                    }
                                }
                            },
                            "test_data": {"type": "object"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "automation_level": {"type": "string", "enum": ["high", "medium", "low"]}
                        }
                    }
                },
                "analysis_summary": {
                    "type": "object",
                    "properties": {
                        "total_count": {"type": "integer"},
                        "p0_count": {"type": "integer"},
                        "coverage_analysis": {"type": "string"},
                        "risk_points": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        },
        "methods": [
            {
                "name": "等价类划分",
                "description": "将输入数据划分为若干等价类，从每个类中选取代表值测试",
                "applicable_scenarios": ["输入字段测试", "下拉框选项测试"]
            },
            {
                "name": "边界值分析",
                "description": "重点测试边界值及其附近值",
                "applicable_scenarios": ["范围类输入", "数量限制"]
            },
            {
                "name": "场景法",
                "description": "基于业务流程场景设计测试用例",
                "applicable_scenarios": ["业务流程测试", "用户故事测试"]
            },
            {
                "name": "错误推测",
                "description": "基于经验推测可能存在的缺陷",
                "applicable_scenarios": ["异常场景测试", "安全性测试"]
            }
        ],
        "domain_rules": [],
        "quality_checks": [
            "每个功能点至少覆盖正常、异常、边界三种场景",
            "关键路径必须包含P0级用例",
            "预期结果必须明确可验证",
            "测试数据必须具体有效",
            "标题简洁明了，不超过100字",
            "步骤描述清晰，无歧义"
        ],
        "prompt_template": """【角色】
{{role.name}} - {{role.description}}

专业知识：
{{#role.expertise}}
- {{.}}
{{/role.expertise}}

【任务】
根据以下需求文档生成测试用例：

【项目上下文】
项目名称：{{input.project_context.project_name}}
项目类型：{{input.project_context.project_type}}
业务领域：{{input.project_context.business_domain}}

【需求内容】
{{input.requirement_text}}

{{#input.requirement_images_ocr}}
【需求图片内容】
{{.}}
{{/input.requirement_images_ocr}}

【生成要求】
1. 使用以下测试方法：
{{#methods}}
- {{name}}：{{description}}
{{/methods}}

2. 必须覆盖的场景：
- 正常场景（基本流）
- 异常场景（错误处理）
- 边界场景（边界值分析）

3. 质量检查：
{{#quality_checks}}
- {{.}}
{{/quality_checks}}

4. 输出格式要求：
- 严格按照JSON Schema格式输出
- 每个用例必须包含完整的字段
- 优先级合理分配（P0:核心功能, P1:重要功能, P2:一般功能, P3:次要功能）

【输出格式】
请以JSON格式输出，包含test_cases数组和analysis_summary对象。"""
    }


# ==================== SKILL CRUD API ====================

@router.get("/", response_model=SkillListResponse)
def list_skills(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    skill_type: Optional[str] = Query(None, description="类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    project_id: Optional[int] = Query(None, description="项目筛选"),
    is_global: Optional[bool] = Query(None, description="是否全局"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_READ),
):
    """
    获取SKILL列表
    
    权限: skill:read
    """
    try:
        query = db.query(TestSkill)
        
        # 筛选条件
        if skill_type:
            query = query.filter(TestSkill.skill_type == skill_type)
        if status:
            query = query.filter(TestSkill.status == status)
        if project_id:
            query = query.filter(TestSkill.project_id == project_id)
        if is_global is not None:
            query = query.filter(TestSkill.is_global == is_global)
        
        # 搜索
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    TestSkill.name.ilike(search_pattern),
                    TestSkill.code.ilike(search_pattern),
                    TestSkill.description.ilike(search_pattern)
                )
            )
        
        # 默认只显示active状态的SKILL
        if status is None:
            query = query.filter(TestSkill.status == SkillStatus.ACTIVE.value)
        
        # 排序：默认优先显示默认SKILL和最新创建的
        query = query.order_by(
            TestSkill.is_default.desc(),
            TestSkill.created_at.desc()
        )
        
        # 分页
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return {
            "items": [SkillResponse.model_validate(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    except Exception as e:
        logger.error(f"获取SKILL列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取SKILL列表失败: {str(e)}"
        )


@router.post("/", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(
    skill_in: SkillCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_CREATE),
):
    """
    创建SKILL
    
    权限: skill:create
    """
    try:
        # 检查编码是否已存在
        existing = db.query(TestSkill).filter(TestSkill.code == skill_in.code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKILL编码 '{skill_in.code}' 已存在"
            )
        
        # 如果没有提供content，使用默认模板
        content = skill_in.content
        if not content or not content.role:
            default_content = get_default_skill_content(skill_in.skill_type)
            content = SkillContentSchema(**default_content)
        
        # 创建SKILL
        skill = TestSkill(
            name=skill_in.name,
            code=skill_in.code,
            description=skill_in.description,
            skill_type=skill_in.skill_type,
            tags=skill_in.tags or [],
            is_global=skill_in.is_global,
            is_default=skill_in.is_default,
            project_id=skill_in.project_id,
            content=content.model_dump(),
            status=SkillStatus.ACTIVE.value,
            created_by=current_user["user"].id,
            version="1.0.0",
            is_latest=True
        )
        
        db.add(skill)
        db.commit()
        db.refresh(skill)
        
        logger.info(f"创建SKILL成功: {skill.code} - {skill.name}")
        return SkillResponse.model_validate(skill)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建SKILL失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建SKILL失败: {str(e)}"
        )


@router.get("/{skill_id}", response_model=SkillDetailResponse)
def get_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_READ),
):
    """
    获取SKILL详情
    
    权限: skill:read
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 获取示例
        examples = [
            {
                "id": ex.id,
                "name": ex.name,
                "description": ex.description,
                "input_example": ex.input_example,
                "output_example": ex.output_example,
                "is_active": ex.is_active,
                "sort_order": ex.sort_order
            }
            for ex in skill.examples.filter(SkillExample.is_active == True).order_by(SkillExample.sort_order).all()
        ]
        
        return {
            **SkillResponse.model_validate(skill).model_dump(),
            "content": skill.content,
            "examples": examples
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取SKILL详情失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取SKILL详情失败: {str(e)}"
        )


@router.put("/{skill_id}", response_model=SkillResponse)
def update_skill(
    skill_id: int,
    skill_update: SkillUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_UPDATE),
):
    """
    更新SKILL
    
    权限: skill:update
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 更新字段
        update_data = skill_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(skill, field, value)
        
        db.commit()
        db.refresh(skill)
        
        logger.info(f"更新SKILL成功: {skill.code}")
        return SkillResponse.model_validate(skill)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新SKILL失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新SKILL失败: {str(e)}"
        )


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_DELETE),
):
    """
    删除SKILL（物理删除）
    
    权限: skill:delete
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 物理删除 - 直接从数据库删除记录
        db.delete(skill)
        db.commit()
        
        logger.info(f"删除SKILL成功: {skill.code}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除SKILL失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除SKILL失败: {str(e)}"
        )


@router.post("/{skill_id}/copy", response_model=SkillResponse)
def copy_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_CREATE),
):
    """
    复制SKILL
    
    权限: skill:create
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 生成新的编码
        new_code = f"{skill.code}_copy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 创建副本
        new_skill = TestSkill(
            name=f"{skill.name} (副本)",
            code=new_code,
            description=skill.description,
            skill_type=skill.skill_type,
            tags=skill.tags,
            is_global=skill.is_global,
            is_default=False,
            project_id=skill.project_id,
            content=skill.content,
            status=SkillStatus.DRAFT.value,
            created_by=current_user["user"].id,
            version="1.0.0",
            is_latest=True,
            parent_skill_id=skill.id
        )
        
        db.add(new_skill)
        db.commit()
        db.refresh(new_skill)
        
        # 复制示例
        for example in skill.examples.all():
            new_example = SkillExample(
                skill_id=new_skill.id,
                name=example.name,
                description=example.description,
                input_example=example.input_example,
                output_example=example.output_example,
                sort_order=example.sort_order,
                created_by=current_user["user"].id
            )
            db.add(new_example)
        
        db.commit()
        
        logger.info(f"复制SKILL成功: {new_skill.code}")
        return SkillResponse.model_validate(new_skill)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"复制SKILL失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"复制SKILL失败: {str(e)}"
        )


# ==================== SKILL示例管理 ====================

@router.get("/{skill_id}/examples", response_model=List[SkillExampleResponse])
def list_skill_examples(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_READ),
):
    """
    获取SKILL示例列表
    
    权限: skill:read
    """
    try:
        examples = db.query(SkillExample).filter(
            SkillExample.skill_id == skill_id,
            SkillExample.is_active == True
        ).order_by(SkillExample.sort_order).all()
        
        return [SkillExampleResponse.model_validate(ex) for ex in examples]
        
    except Exception as e:
        logger.error(f"获取SKILL示例失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取SKILL示例失败: {str(e)}"
        )


@router.post("/{skill_id}/examples", response_model=SkillExampleResponse)
def create_skill_example(
    skill_id: int,
    example_in: SkillExampleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_UPDATE),
):
    """
    创建SKILL示例
    
    权限: skill:update
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        example = SkillExample(
            skill_id=skill_id,
            name=example_in.name,
            description=example_in.description,
            input_example=example_in.input_example,
            output_example=example_in.output_example,
            sort_order=example_in.sort_order,
            created_by=current_user["user"].id
        )
        
        db.add(example)
        db.commit()
        db.refresh(example)
        
        return SkillExampleResponse.model_validate(example)
        
    except Exception as e:
        logger.error(f"创建SKILL示例失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建SKILL示例失败: {str(e)}"
        )


# ==================== SKILL统计 ====================

@router.get("/{skill_id}/stats")
def get_skill_stats(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_READ),
):
    """
    获取SKILL使用统计
    
    权限: skill:read
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 获取使用记录统计
        usage_stats = db.query(SkillUsageLog).filter(
            SkillUsageLog.skill_id == skill_id
        )
        
        total_usage = usage_stats.count()
        avg_quality = usage_stats.with_entities(
            db.func.avg(SkillUsageLog.quality_score)
        ).scalar() or 0
        
        return {
            "skill_id": skill_id,
            "usage_count": skill.usage_count,
            "generation_count": skill.generation_count,
            "avg_quality_score": float(avg_quality) if avg_quality else None,
            "total_usage_records": total_usage,
            "last_used_at": skill.updated_at.isoformat() if skill.updated_at else None
        }
        
    except Exception as e:
        logger.error(f"获取SKILL统计失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取SKILL统计失败: {str(e)}"
        )


# ==================== SKILL导入导出 ====================

@router.get("/{skill_id}/export")
def export_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_READ),
):
    """
    导出SKILL
    
    权限: skill:read
    """
    try:
        skill = db.query(TestSkill).filter(TestSkill.id == skill_id).first()
        if not skill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SKILL不存在"
            )
        
        # 获取示例
        examples = [
            {
                "name": ex.name,
                "description": ex.description,
                "input_example": ex.input_example,
                "output_example": ex.output_example
            }
            for ex in skill.examples.all()
        ]
        
        return {
            "name": skill.name,
            "code": skill.code,
            "version": skill.version,
            "skill_type": skill.skill_type.value if skill.skill_type else "",
            "description": skill.description,
            "content": skill.content,
            "examples": examples,
            "export_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"导出SKILL失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出SKILL失败: {str(e)}"
        )


@router.post("/import", response_model=SkillResponse)
def import_skill(
    import_data: SkillImportRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.SKILL_CREATE),
):
    """
    导入SKILL
    
    权限: skill:create
    """
    try:
        data = import_data.skill_data
        
        # 生成新的编码（避免冲突），限制在50字符内
        import hashlib
        import time
        original_code = data.get("code", "")
        # 使用原始code的前30字符 + 时间戳哈希的短码
        code_prefix = original_code[:30] if len(original_code) > 30 else original_code
        short_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        new_code = f"{code_prefix}_{short_hash}"
        
        # 确保不超过50字符
        if len(new_code) > 50:
            new_code = new_code[:50]
        
        # 创建SKILL
        skill = TestSkill(
            name=f"{data.get('name', 'Imported Skill')} (导入)",
            code=new_code,
            description=data.get("description"),
            skill_type=data.get("skill_type", "functional"),
            tags=data.get("tags", []),
            is_global=import_data.project_id is None,
            is_default=False,
            project_id=import_data.project_id,
            content=data.get("content", {}),
            status=SkillStatus.ACTIVE.value,
            created_by=current_user["user"].id,
            version="1.0.0",
            is_latest=True
        )
        
        db.add(skill)
        db.commit()
        db.refresh(skill)
        
        # 导入示例
        for example_data in data.get("examples", []):
            example = SkillExample(
                skill_id=skill.id,
                name=example_data.get("name"),
                description=example_data.get("description"),
                input_example=example_data.get("input_example", ""),
                output_example=example_data.get("output_example", {}),
                created_by=current_user["user"].id
            )
            db.add(example)
        
        db.commit()
        
        logger.info(f"导入SKILL成功: {skill.code}")
        return SkillResponse.model_validate(skill)
        
    except Exception as e:
        logger.error(f"导入SKILL失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入SKILL失败: {str(e)}"
        )
