"""
项目设置API
对应需求文档 3.1.3 项目设置
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.project import Project
from app.core.models.project_ext import ProjectSetting
from app.core.schemas.project_ext import (
    ProjectSettingUpdate,
    ProjectSettingResponse,
)
from app.api.api_v1.endpoints.auth import get_current_user

router = APIRouter()


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并两个 dict — override 中的嵌套 dict 与 base 递归合并，而非整键替换"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@router.get("/{project_id}/settings", response_model=ProjectSettingResponse)
def get_project_settings(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取项目设置
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取或创建设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if not settings:
        # 自动创建默认设置
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={
                "execution_completed": True,
                "execution_failed": True,
                "issue_created": True,
                "channels": ["email"]
            },
            execution_defaults={
                "parallel": 4,
                "retry": 1,
                "timeout": 3600
            },
            test_defaults={
                "browser": "chromium",
                "viewport": {"width": 1920, "height": 1080},
                "headless": True
            },
            exploration_config={
                "web": {
                    "base_url": "",
                    "username": "",
                    "password": "",
                    "login_rules": {},
                },
                "app": {
                    "appium_url": "",
                    "username": "",
                    "password": "",
                    "auto_launch": True,
                },
            },
            custom_settings={},
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return settings


@router.put("/{project_id}/settings", response_model=ProjectSettingResponse)
def update_project_settings(
    project_id: int,
    settings_data: ProjectSettingUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    更新项目设置
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取或创建设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if not settings:
        # 创建默认设置
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={},
            execution_defaults={},
            test_defaults={},
            exploration_config={},
            custom_settings={},
        )
        db.add(settings)
    
    # 更新通知配置
    if settings_data.notification_config is not None:
        current_config = settings.notification_config or {}
        new_config = settings_data.notification_config.model_dump()
        current_config.update(new_config)
        settings.notification_config = current_config
    
    # 更新执行默认配置
    if settings_data.execution_defaults is not None:
        current_defaults = settings.execution_defaults or {}
        new_defaults = settings_data.execution_defaults.model_dump()
        current_defaults.update(new_defaults)
        settings.execution_defaults = current_defaults
    
    # 更新测试默认配置
    if settings_data.test_defaults is not None:
        current_defaults = settings.test_defaults or {}
        new_defaults = settings_data.test_defaults.model_dump()
        current_defaults.update(new_defaults)
        settings.test_defaults = current_defaults
    
    # 更新自定义设置
    if settings_data.custom_settings is not None:
        current_custom = settings.custom_settings or {}
        current_custom.update(settings_data.custom_settings)
        settings.custom_settings = current_custom

    # 更新探索配置（含登录规则）— 深合并避免嵌套 key 被整体替换
    if settings_data.exploration_config is not None:
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        current = dict(settings.exploration_config or {})
        new_config = settings_data.exploration_config.model_dump(exclude_none=True)
        settings.exploration_config = copy.deepcopy(_deep_merge(current, new_config))
        flag_modified(settings, "exploration_config")

    db.commit()
    db.refresh(settings)

    return settings


@router.patch("/{project_id}/settings/notification", response_model=ProjectSettingResponse)
def update_notification_settings(
    project_id: int,
    notification_config: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    更新通知设置（部分更新）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取或创建设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if not settings:
        settings = ProjectSetting(
            project_id=project_id,
            notification_config=notification_config,
            execution_defaults={},
            test_defaults={},
            custom_settings={},
            exploration_config={},
        )
        db.add(settings)
    else:
        current_config = settings.notification_config or {}
        current_config.update(notification_config)
        settings.notification_config = current_config
    
    db.commit()
    db.refresh(settings)
    
    return settings


@router.patch("/{project_id}/settings/execution-defaults", response_model=ProjectSettingResponse)
def update_execution_defaults(
    project_id: int,
    execution_defaults: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    更新执行默认配置（部分更新）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取或创建设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if not settings:
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={},
            execution_defaults=execution_defaults,
            test_defaults={},
            custom_settings={},
        )
        db.add(settings)
    else:
        current_defaults = settings.execution_defaults or {}
        current_defaults.update(execution_defaults)
        settings.execution_defaults = current_defaults
    
    db.commit()
    db.refresh(settings)
    
    return settings


@router.patch("/{project_id}/settings/test-defaults", response_model=ProjectSettingResponse)
def update_test_defaults(
    project_id: int,
    test_defaults: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    更新测试默认配置（部分更新）
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取或创建设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if not settings:
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={},
            execution_defaults={},
            test_defaults=test_defaults,
            custom_settings={},
        )
        db.add(settings)
    else:
        current_defaults = settings.test_defaults or {}
        current_defaults.update(test_defaults)
        settings.test_defaults = current_defaults
    
    db.commit()
    db.refresh(settings)
    
    return settings


@router.delete("/{project_id}/settings/custom/{key}")
def delete_custom_setting(
    project_id: int,
    key: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    删除自定义设置项
    """
    # 检查项目是否存在
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 获取设置
    settings = db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()
    
    if settings and settings.custom_settings:
        custom_settings = dict(settings.custom_settings)
        if key in custom_settings:
            del custom_settings[key]
            settings.custom_settings = custom_settings
            db.commit()
            return {"message": f"自定义设置 '{key}' 已删除"}
    
    raise HTTPException(status_code=404, detail="自定义设置项不存在")


@router.patch("/{project_id}/settings/exploration")
def update_exploration_config(
    project_id: int,
    config: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新探索配置（WEB: base_url/username/password；APP: appium_url/username/password）"""
    from app.core.logger import logger
    logger.info(f"[探索配置] PATCH project_id={project_id}, config={config}")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    settings = db.query(ProjectSetting).filter(ProjectSetting.project_id == project_id).first()
    if not settings:
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={}, execution_defaults={}, test_defaults={}, custom_settings={},
            exploration_config={},
        )
        db.add(settings)
    import copy
    current = dict(settings.exploration_config or {})
    settings.exploration_config = copy.deepcopy(_deep_merge(current, config))
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(settings, "exploration_config")
    db.commit()
    logger.info(f"[探索配置] 已保存: {settings.exploration_config}")
    return {"project_id": project_id, "exploration_config": current}


# ==================== API 鉴权配置 ====================

@router.get("/{project_id}/settings/api-auth")
def get_api_auth_config(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取 API 鉴权配置"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    settings = db.query(ProjectSetting).filter(ProjectSetting.project_id == project_id).first()
    ec = (settings.exploration_config or {}) if settings else {}
    auth = ec.get("api_auth") or {}
    # 同时返回 base_url（用于构造完整登录 URL）
    web = ec.get("web", {})
    base_url = web.get("base_url", "") or ""
    if not base_url:
        envs = web.get("environments") or []
        active = web.get("active_environment") or ""
        matched = [e for e in envs if isinstance(e, dict) and e.get("name") == active]
        if matched:
            base_url = matched[0].get("url", "") or ""
    # 返回凭证状态（WEB 端配置的 username/password，API 也复用）
    credential_ready = bool(base_url and web.get("username") and web.get("password"))
    return {
        "project_id": project_id,
        "api_auth": auth,
        "base_url": base_url,
        "credential_ready": credential_ready,
        "username": web.get("username", "") or "",
        "password": web.get("password", "") or "",
    }


@router.post("/{project_id}/settings/api-auth")
def save_api_auth_config(
    project_id: int,
    config: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """保存 API 鉴权配置（写入 exploration_config.api_auth）"""
    from app.core.logger import logger
    logger.info(f"[API鉴权] 保存 project_id={project_id}, config={config}")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    settings = db.query(ProjectSetting).filter(ProjectSetting.project_id == project_id).first()
    if not settings:
        settings = ProjectSetting(
            project_id=project_id,
            notification_config={}, execution_defaults={}, test_defaults={}, custom_settings={},
            exploration_config={},
        )
        db.add(settings)
    import copy
    current_ec = dict(settings.exploration_config or {})
    # 清除 verified 状态（配置变更后需重新验证）
    config["verified"] = False
    config["verified_at"] = None
    # ── 高级参数自动补齐：普通用户只填登录接口 URL 即可，其余自动推断 ──
    if not config.get("token_source"):
        config["token_source"] = "body"
    if not config.get("token_inject_location"):
        config["token_inject_location"] = "header"
    if not config.get("token_inject_name"):
        config["token_inject_name"] = "Authorization"
    if not config.get("token_inject_template"):
        config["token_inject_template"] = "Bearer {token}"
    if not config.get("request_body") or not isinstance(config["request_body"], dict):
        config["request_body"] = {"username": "{username}", "password": "{password}"}
    if not config.get("token_path"):
        # 从 Swagger 候选推断 Token 提取路径（响应 schema 递归扫描结果）
        _inferred_path = ""
        try:
            _cands = _scan_login_candidates(db, project_id)
            _url = (str(config.get("login_url") or "")).strip().rstrip("/")
            for _c in _cands:
                if str(_c["path"] or "").strip().rstrip("/") == _url:
                    _tps = _c.get("token_path_candidates") or []
                    if _tps:
                        _inferred_path = _tps[0]
                        break
        except Exception:
            pass
        config["token_path"] = _inferred_path or "data.token"
    current_ec["api_auth"] = copy.deepcopy(config)
    settings.exploration_config = current_ec
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(settings, "exploration_config")
    db.commit()
    logger.info(f"[API鉴权] 已保存: {current_ec.get('api_auth')}")
    return {"project_id": project_id, "api_auth": current_ec.get("api_auth")}


@router.post("/{project_id}/settings/api-auth/test")
def test_api_auth_config(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """测试 API 鉴权配置：用配置的登录接口 + 凭证发起请求，提取 Token 并验证"""
    import requests as req
    import json as _json
    from app.core.logger import logger

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    settings = db.query(ProjectSetting).filter(ProjectSetting.project_id == project_id).first()
    ec = (settings.exploration_config or {}) if settings else {}
    web = ec.get("web", {})
    auth = ec.get("api_auth") or {}

    # 1. 解析 base_url
    base_url = web.get("base_url", "") or ""
    if not base_url:
        envs = web.get("environments") or []
        active = web.get("active_environment") or ""
        matched = [e for e in envs if isinstance(e, dict) and e.get("name") == active]
        if matched:
            base_url = matched[0].get("url", "") or ""
    if not base_url:
        raise HTTPException(status_code=400, detail="项目未配置目标系统 URL（base_url），请先在项目设置中配置")

    # 2. 校验鉴权配置完整性
    login_url = auth.get("login_url", "") or ""
    login_method = auth.get("login_method", "POST") or "POST"
    if not login_url:
        raise HTTPException(status_code=400, detail="未配置登录接口 URL")

    token_path = auth.get("token_path", "") or ""
    if not token_path:
        raise HTTPException(status_code=400, detail="未配置 Token 提取路径")

    # 3. 获取凭证
    username = web.get("username", "") or ""
    password = web.get("password", "") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="项目未配置登录用户名/密码，请先在项目设置中配置")

    # 4. 构造登录请求
    full_url = login_url if login_url.startswith("http") else base_url.rstrip("/") + "/" + login_url.lstrip("/")
    logger.info(f"[API鉴权测试] 登录 URL: {full_url}, method={login_method}")

    body_template = auth.get("request_body") or {}
    body = {}
    for k, v in body_template.items():
        if isinstance(v, str):
            body[k] = v.replace("{username}", username).replace("{password}", password)
        else:
            body[k] = v

    # 5. 发起登录请求
    try:
        if login_method.upper() == "GET":
            resp = req.get(full_url, params=body, timeout=15, verify=False)
        else:
            resp = req.request(login_method.upper(), full_url, json=body, timeout=15, verify=False)
        logger.info(f"[API鉴权测试] 响应状态: {resp.status_code}")
    except Exception as e:
        logger.error(f"[API鉴权测试] 请求失败: {e}")
        raise HTTPException(status_code=400, detail=f"登录请求失败: {str(e)}")

    if resp.status_code >= 500:
        raise HTTPException(status_code=400, detail=f"登录接口返回服务器错误 {resp.status_code}")

    # 6. 提取 Token
    token_source = auth.get("token_source", "body")
    token_value = None

    try:
        if token_source == "header":
            token_value = resp.headers.get(token_path, "")
        else:
            data = resp.json() if resp.text else {}
            parts = token_path.split(".")
            for part in parts:
                if isinstance(data, dict):
                    data = data.get(part)
                elif isinstance(data, list) and part.isdigit():
                    data = data[int(part)] if int(part) < len(data) else None
                else:
                    data = None
                    break
            token_value = data
    except Exception as e:
        logger.error(f"[API鉴权测试] Token 提取失败: {e}")
        raise HTTPException(status_code=400, detail=f"Token 提取失败（路径 '{token_path}'）：{str(e)}")

    if not token_value:
        raise HTTPException(
            status_code=400,
            detail=f"未能从响应中提取到 Token（路径 '{token_path}'）。响应前500字符: {str(resp.text)[:500]}"
        )

    logger.info(f"[API鉴权测试] Token 提取成功: {str(token_value)[:50]}...")

    # 7. 验证通过 → 标记 verified
    try:
        current_ec = dict(settings.exploration_config or {})
        auth["verified"] = True
        from datetime import datetime
        auth["verified_at"] = datetime.utcnow().isoformat()
        current_ec["api_auth"] = auth
        settings.exploration_config = current_ec
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(settings, "exploration_config")
        db.commit()
        logger.info(f"[API鉴权测试] ✅ 鉴权验证通过")
    except Exception as e:
        logger.warning(f"[API鉴权测试] 标记 verified 失败（不影响测试结果）: {e}")

    return {
        "success": True,
        "token_preview": str(token_value)[:30] + "..." if len(str(token_value)) > 30 else str(token_value),
        "status_code": resp.status_code,
    }


def _scan_login_candidates(db: Session, project_id: int) -> list:
    """从项目所有版本的 Swagger 文档检测候选登录接口（端点与登录模块导入服务共用的纯函数）"""
    from app.core.models.requirement import RequirementDocument
    from app.core.models.project import Version
    import json as _json

    # 查找项目下所有版本的 swagger 文档
    versions = db.query(Version).filter(Version.project_id == project_id).all()
    version_ids = [v.id for v in versions]
    docs = db.query(RequirementDocument).filter(
        RequirementDocument.version_id.in_(version_ids),
        RequirementDocument.type == 'swagger',
        RequirementDocument.content != '',
    ).order_by(RequirementDocument.created_at.desc()).all()

    candidates = []
    # 登录接口识别关键词（零硬编码：来自 WebExplorationConfig，与登录模块导入/网络捕获共用同一配置；
    # 项目可在 exploration_config.explore 段覆盖定制）
    from app.core.services.exploration_config import build_web_exploration_config
    from app.core.models.project_ext import ProjectSetting as _PSExt
    _ps_row = db.query(_PSExt).filter(_PSExt.project_id == project_id).first()
    _cfg = build_web_exploration_config(_ps_row.exploration_config if _ps_row else None)
    auth_keywords = [k.strip() for k in (_cfg.login_api_keywords + ',' + _cfg.login_token_keywords).split(',') if k.strip()]

    for doc in docs:
        try:
            spec = _json.loads(doc.content or '{}')
        except Exception:
            continue

        paths = spec.get('paths') or {}
        for path_url, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            path_lower = path_url.lower()
            for method, detail in methods.items():
                if method.lower() not in ('get', 'post', 'put', 'patch', 'delete'):
                    continue
                if not isinstance(detail, dict):
                    continue
                summary = (detail.get('summary') or '').lower()
                operation_id = (detail.get('operationId') or '').lower()
                tags = [t.lower() for t in (detail.get('tags') or [])]
                combined = f"{path_lower} {summary} {operation_id} {' '.join(tags)}"

                score = 0
                for kw in auth_keywords:
                    if kw in combined:
                        score += 1

                if score > 0:
                    # 解析请求体参数
                    request_body_params = {}
                    req_body = detail.get('requestBody') or {}
                    content = req_body.get('content', {})
                    json_schema = content.get('application/json', {}).get('schema', {}) or content.get('*/*', {}).get('schema', {})
                    if not json_schema:
                        json_schema = {}
                    props = json_schema.get('properties') or {}
                    for pname, pdef in (props if isinstance(props, dict) else {}).items():
                        request_body_params[pname] = pdef.get('type', 'string') if isinstance(pdef, dict) else 'string'

                    # 从响应 schema 递归推断 Token 字段的完整 JSON 路径（数据驱动），无响应定义时用常见路径兜底
                    def _collect_token_paths(schema, prefix=''):
                        _paths = []
                        _props = (schema or {}).get('properties') or {}
                        if not isinstance(_props, dict):
                            return _paths
                        for _pname, _pdef in _props.items():
                            if not isinstance(_pdef, dict):
                                continue
                            _cur = f"{prefix}.{_pname}" if prefix else str(_pname)
                            if isinstance(_pdef.get('properties'), dict):
                                _paths.extend(_collect_token_paths(_pdef, _cur))
                                continue
                            _pl = str(_pname).lower()
                            if any(_k in _pl for _k in _cfg.login_token_keywords.split(',')):
                                _paths.append(_cur)
                        return _paths

                    token_paths = []
                    responses = detail.get('responses') or {}
                    for _rcode, _rbody in (responses.items() if isinstance(responses, dict) else []):
                        if not isinstance(_rbody, dict):
                            continue
                        _rcontent = _rbody.get('content') or {}
                        _rschema = _rcontent.get('application/json', {}).get('schema', {}) or _rcontent.get('*/*', {}).get('schema', {})
                        token_paths.extend(_collect_token_paths(_rschema))
                    if not token_paths:
                        token_paths = ['access_token', 'token', 'data.access_token', 'data.token']

                    candidates.append({
                        "path": path_url,
                        "method": method.upper(),
                        "summary": detail.get('summary', ''),
                        "operationId": detail.get('operationId', ''),
                        "tags": detail.get('tags', []),
                        "score": score,
                        "request_body_params": request_body_params,
                        "token_path_candidates": token_paths,
                    })

    # 按得分降序排列
    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates


@router.get("/{project_id}/settings/api-auth/candidates")
def get_login_candidates(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """从已导入的 Swagger 文档中自动检测候选登录接口"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    candidates = _scan_login_candidates(db, project_id)
    return {"project_id": project_id, "candidates": candidates}
