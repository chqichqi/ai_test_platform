"""登录模块内容项目级存储。

登录模块是项目级资产：同一个项目使用同一套登录逻辑，跨版本共享。
业务流内容存 `ProjectSetting.exploration_config.login_module_content`（项目级配置，
与 api_auth 同源管理），不再按版本存 RequirementDocument。

存量兼容：改造前登录模块内容按版本存于 RequirementDocument（type=business_flow,
name='登录模块'）；`get_login_module_content` 在项目级为空时回退查旧版本文档（纯读，
不写）。一次性迁移脚本 scripts/migrate_login_module_to_project.py 负责把每项目
首个版本的内容搬运到项目级，旧记录保留不删。
"""

from typing import Optional

_LOGIN_MODULE_KEY = "login_module_content"


def _get_setting(db, project_id: int):
    from app.core.models.project_ext import ProjectSetting
    if project_id is None:
        return None
    return db.query(ProjectSetting).filter(
        ProjectSetting.project_id == project_id
    ).first()


def get_login_module_content(db, project_id: Optional[int]) -> str:
    """读取项目级登录模块业务流内容；项目级为空时回退旧版本文档（纯读兼容）。"""
    content = ""
    psetting = _get_setting(db, project_id)
    if psetting:
        ec = psetting.exploration_config or {}
        content = str(ec.get(_LOGIN_MODULE_KEY) or "").strip()
    if content or project_id is None:
        return content
    return _legacy_document_content(db, project_id)


def has_login_module_configured(db, project_id: Optional[int]) -> bool:
    """项目级登录模块是否已配置（创建版本门控/业务流校验/前端状态查询共用同一判定）。

    判定与 import_login_module 成功路径三件套同源：
    - 存在未软删的 __login__ UI 用例（test_script 非空且非占位、test_data 非空）
    - 有 project_id 时，项目级业务流内容非空（空时回退旧版本文档，存量兼容）
    project_id 为空时仅做全局 __login__ 存在性判定（旧调用兼容）。
    """
    from app.core.models.web_ui_test import WebUITestCase
    q = db.query(WebUITestCase).filter(
        WebUITestCase.test_case_id == '__login__',
        WebUITestCase.deleted_at.is_(None),
    )
    if project_id:
        q = q.filter(WebUITestCase.project_id == str(project_id))
    login = q.first()
    if not login:
        return False
    ts = (login.test_script or '').strip()
    if not ts or ts.startswith('#'):
        return False
    # test_data 是 JSON 列：新数据为 dict（spec），存量可能为 str——非空即视为有数据
    td = login.test_data
    if td is None:
        return False
    if isinstance(td, str):
        if not td.strip():
            return False
    elif not isinstance(td, dict) or not td:
        return False
    if project_id:
        if not get_login_module_content(db, project_id):
            return False
    return True


def has_project_web_configured(db, project_id: Optional[int]) -> bool:
    """项目配置（Web）是否完备：目标系统 URL 已配置。

    判定依据：`ProjectSetting.exploration_config.web.base_url` 非空（环境管理
    保存时同步到 base_url）。与登录模块一起构成「创建版本前两个前置配置」
    （2026-09-01 用户定性：创建项目后未完成项目配置与登录配置前不能创建版本）。
    project_id 为空时返回 False（无法判定即视为未配置）。
    """
    if project_id is None:
        return False
    psetting = _get_setting(db, project_id)
    if not psetting:
        return False
    web = (psetting.exploration_config or {}).get("web") or {}
    return bool(str((web.get("base_url") or "")).strip())


def save_login_module_content(db, project_id: int, content: str) -> bool:
    """写入项目级登录模块业务流内容；无项目配置时返回 False（由调用方决定处理）。"""
    if project_id is None:
        return False
    from sqlalchemy.orm.attributes import flag_modified
    psetting = _get_setting(db, project_id)
    if not psetting:
        return False
    ec = dict(psetting.exploration_config or {})
    ec[_LOGIN_MODULE_KEY] = (content or "").strip()
    psetting.exploration_config = ec
    flag_modified(psetting, "exploration_config")
    db.commit()
    return True


def _legacy_document_content(db, project_id: int) -> str:
    """回退：该项目任一版本下已保存的登录模块文档内容（存量兼容，纯读）。"""
    from app.core.models.project import Version
    from app.core.models.requirement import RequirementDocument
    doc = db.query(RequirementDocument).join(
        Version, RequirementDocument.version_id == Version.id
    ).filter(
        Version.project_id == project_id,
        RequirementDocument.type == "business_flow",
        RequirementDocument.name == "登录模块",
        RequirementDocument.content != "",
    ).order_by(RequirementDocument.updated_at.asc()).first()
    return (doc.content or "").strip() if doc else ""
