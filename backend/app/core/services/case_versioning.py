"""
方案B 用例版本化 — 生效行解析（纯 Python 分组，MySQL 5.7 兼容，不用窗口函数）

语义（用户确认）：
- 项目版本 ≠ 用例 revision。只有受影响的用例「变更即派生」：
  派生时旧行 status=archived（冻结），新行 status=draft、revision_no+1、derived_from_id=旧行id。
- 某逻辑用例（logical_case_id）在版本 V 的生效行 =
  version_id<=V 且 status 非 deprecated/archived 中 (version_id, revision_no) 最大的一行。
- 迁移回填 logical_case_id=id（现有数据逻辑=物理），所以 (row.logical_case_id or row.id) 恒有值。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.models.requirement import TestCase

# 非生效（冻结/废弃）状态
_FROZEN_STATUSES = ("deprecated", "archived")


def _logical_id(row: TestCase) -> int:
    return row.logical_case_id or row.id


def _sort_key(row: TestCase) -> Tuple[int, int]:
    """版本时间线主维度：version_id 优先，同版本内 revision_no 递增"""
    return (row.version_id or 0, row.revision_no or 1)


def resolve_effective_cases(
    db: Session,
    project_id: int,
    version_id: Optional[int] = None,
) -> List[TestCase]:
    """项目内全部逻辑用例的生效行列表。

    version_id 给定 → 该版本视角（version_id<=V 的非冻结行）；
    缺省 → 全局最新（所有非冻结行）。
    """
    query = db.query(TestCase).filter(
        TestCase.project_id == project_id,
        or_(TestCase.status.is_(None), ~TestCase.status.in_(_FROZEN_STATUSES)),
    )
    if version_id is not None:
        query = query.filter(TestCase.version_id <= version_id)
    rows = query.all()

    # 同逻辑 id 分组，取 (version_id, revision_no) 最大行
    best: Dict[int, TestCase] = {}
    for row in rows:
        lid = _logical_id(row)
        cur = best.get(lid)
        if cur is None or _sort_key(row) > _sort_key(cur):
            best[lid] = row
    return list(best.values())


def resolve_case_by_logical_id(
    db: Session,
    project_id: int,
    logical_case_id: int,
    version_id: Optional[int] = None,
) -> Optional[TestCase]:
    """某逻辑用例在指定版本（或缺省=最新）的生效行；无则 None"""
    for row in resolve_effective_cases(db, project_id, version_id):
        if _logical_id(row) == logical_case_id:
            return row
    return None


def next_revision_no(db: Session, logical_case_id: int) -> int:
    """该逻辑用例的下一修订号（全部行含冻结）"""
    rows = db.query(TestCase).filter(TestCase.logical_case_id == logical_case_id).all()
    if not rows:
        return 1
    return max(_sort_key(r)[1] for r in rows) + 1


# ═══════════════════════════════════════════════════════════
# 转化链路共享 helper（v2/v1/规则引擎/探索兜底四路统一）
# ═══════════════════════════════════════════════════════════

def _query_test_case_safe(db: Session, tc_id_int):
    """查询 test_cases 行；表不存在/查询失败 → None（无版本化概念的场景原样处理）"""
    try:
        return db.query(TestCase).filter(TestCase.id == tc_id_int).first()
    except Exception:
        return None


def load_effective_case(db: Session, test_case_id) -> Optional[TestCase]:
    """按物理 id 或逻辑 id 解析功能用例的【生效行】（转化/执行内容查询统一入口）。

    兼容三类输入：
    - 物理 id（前端列表直传）：查行 → 按逻辑 id resolve 生效行
    - 逻辑 id（方案B 绑定后）：id 恰是首个物理行 id → 同样 resolve 生效行
      （首个物理行可能是已派生冻结的旧行，不能直接返回）
    - 非数字 id：返回 None（SimpleTestCase str id 由调用方自行处理）
    冻结行且无后继（REMOVE 场景）→ resolve 返回 None → 回退该行本身（状态校验由调用方把关）。
    """
    try:
        tc_id_int = int(test_case_id)
    except (ValueError, TypeError):
        return None
    row = _query_test_case_safe(db, tc_id_int)
    if row is None:
        return None
    eff = resolve_case_by_logical_id(db, row.project_id, row.logical_case_id or row.id)
    if eff is not None:
        return eff
    return row


def wui_binding_id(db: Session, test_case_id) -> str:
    """WUI 绑定功能用例的【逻辑 id】（方案B：WebUITestCase.test_case_id 存逻辑 id）。

    幂等：传逻辑 id 原样返回；传物理 id 映射到逻辑 id；
    SimpleTestCase（str id）/查不到 → 原样返回（无版本化概念）。
    """
    try:
        tc_id_int = int(test_case_id)
    except (ValueError, TypeError):
        return str(test_case_id)
    row = _query_test_case_safe(db, tc_id_int)
    if row is None:
        return str(test_case_id)
    return str(row.logical_case_id or row.id)


def find_existing_wui(db: Session, project_id, test_case_id):
    """按逻辑 id（兼容历史物理 id 绑定）查找已绑定 WUI，命中返回 (existing, logical_id)。

    - 历史数据：WUI.test_case_id 绑定物理 id → 用该逻辑用例全部物理行 id 匹配
    - 新数据：绑定逻辑 id → 直接匹配
    - SimpleTestCase（str id）：原样匹配
    返回 (WebUITestCase | None, logical_id_str)。
    """
    from app.core.models.web_ui_test import WebUITestCase
    try:
        tc_id_int = int(test_case_id)
    except (ValueError, TypeError):
        candidates = [str(test_case_id)]
    else:
        row = _query_test_case_safe(db, tc_id_int)
        if row is None:
            candidates = [str(test_case_id)]
        else:
            logical_id = str(row.logical_case_id or row.id)
            try:
                phys_ids = [
                    str(r.id) for r in db.query(TestCase).filter(
                        TestCase.logical_case_id == (row.logical_case_id or row.id)
                    ).all()
                ]
            except Exception:
                phys_ids = []
            candidates = list(dict.fromkeys([logical_id] + phys_ids))
    _q = db.query(WebUITestCase).filter(WebUITestCase.test_case_id.in_(candidates))
    if project_id:
        _q = _q.filter(WebUITestCase.project_id == str(project_id))
    existing = _q.order_by(WebUITestCase.created_at.desc()).first()
    return existing, candidates[0]


# ═══════════════════════════════════════════════════════════
# 跨版本复用用例（用户确认：创建新版本时从任意历史版本复用用例，两种模式：
# ① 全模块复用：module 指定 → 源版本视角该模块全部生效用例一起复制；
# ② 勾选复用：case_ids 指定 → 只复制勾选的用例（模块只是 UI 筛选维度））
# ═══════════════════════════════════════════════════════════

def reuse_cases(
    db: Session,
    project_id: int,
    target_version_id: int,
    source_version_id: int,
    case_ids: Optional[List[int]] = None,
    module: Optional[str] = None,
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """把源版本视角的用例复制到目标版本（同一项目）。

    两种模式（用户确认，都要支持）：
    - 勾选模式 case_ids 非空：每个 id → 按逻辑 id 解析源视角生效行，
      被派生冻结/废弃的旧行在源视角不可见 → 跳过（与全局生效口径一致）
    - 全模块模式 case_ids 为空且 module 非空：源版本视角该模块全部生效用例一起复制
    - 两者同时给 → case_ids 优先（前端两个按钮不会同时传）
    - 两者都不给 → 空操作（endpoint 层 400 拦截，此处兜底）

    复制语义：
    - 新行 logical_case_id 保留（延续逻辑用例时间线）、revision_no=next_revision_no、
      derived_from_id=源行 id、version_id=目标版本、status=源行 status（源视角非冻结 → 原样保留）、
      generated_by="version_reuse"、内容=源行 JSON-safe 副本（同变更派生的拷贝模式）
    - 幂等：目标版本已有该逻辑用例的显式行（version_id==target）→ 跳过，重复提交不产生重复行
    """
    # 目标版本显式行（version_id == target）的逻辑 id 集合 → 已存在则跳过
    explicit = db.query(TestCase).filter(
        TestCase.project_id == project_id,
        TestCase.version_id == target_version_id,
    ).all()
    existing_lids = {_logical_id(r) for r in explicit}

    # 解析要复制的源行（源版本视角生效行）；无效/不可见/已存在的在此计入 skipped
    skipped_count = 0
    src_targets: List[TestCase] = []
    if case_ids:
        for raw_id in case_ids:
            try:
                cid = int(raw_id)
            except (ValueError, TypeError):
                skipped_count += 1
                continue
            src = _query_test_case_safe(db, cid)
            if src is None:
                skipped_count += 1
                continue
            eff = resolve_case_by_logical_id(db, project_id, _logical_id(src), source_version_id)
            if eff is None:  # 源视角不可见（冻结/废弃）→ 跳过
                skipped_count += 1
                continue
            src_targets.append(eff)
    elif module:
        src_targets = [
            r for r in resolve_effective_cases(db, project_id, source_version_id)
            if (r.module or "") == module
        ]

    def _as_list(_v):
        if isinstance(_v, list):
            return _v
        if isinstance(_v, str):
            try:
                return json.loads(_v)
            except Exception:
                return None
        return None

    def _as_dict(_v):
        if isinstance(_v, dict):
            return _v
        if isinstance(_v, str):
            try:
                return json.loads(_v)
            except Exception:
                return None
        return None

    reused_count = 0
    reused_ids: List[int] = []
    seen_lids: set = set()  # 同批次重复逻辑用例只复制一次
    for eff in src_targets:
        lid = _logical_id(eff)
        if lid in seen_lids:
            skipped_count += 1
            continue
        seen_lids.add(lid)
        if lid in existing_lids:
            skipped_count += 1
            continue
        new_row = TestCase(
            project_id=project_id,
            version_id=target_version_id,
            module=eff.module,
            name=eff.name,
            description=eff.description,
            preconditions=eff.preconditions,
            test_steps=_as_list(eff.test_steps),
            expected_result=eff.expected_result,
            test_data=_as_dict(eff.test_data),
            priority=eff.priority,
            case_type=eff.case_type,
            execution_type=eff.execution_type,
            tags=_as_list(eff.tags),
            generated_by="version_reuse",
            status=eff.status,  # 源视角生效行非冻结 → 状态原样保留（approved/published/draft）
            logical_case_id=lid,
            revision_no=next_revision_no(db, lid),
            derived_from_id=eff.id,
            created_by=created_by,
        )
        if new_row.id is None and db.bind and db.bind.dialect.name == "sqlite":
            # dev sqlite：BigInteger 主键不自增（生产 MySQL 走原生自增）
            new_row.id = (db.query(func.max(TestCase.id)).scalar() or 0) + 1
        db.add(new_row)
        db.flush()
        existing_lids.add(lid)  # 已复制 → 本批次后续跳过
        reused_count += 1
        reused_ids.append(new_row.id)
    db.commit()
    return {
        "reused_count": reused_count,
        "skipped_count": skipped_count,
        "reused_ids": reused_ids,
    }
