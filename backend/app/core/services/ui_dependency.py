"""
WebUI 用例依赖调度（执行层 · 通用，2026-09-03）

用户语义：
1. 用例 B 声明 depends_on 前置(共享准备/setup)用例 S → 执行时必须先跑 S、再跑 B；
2. 同一批内多条用例依赖同一个 S → S 只执行一次（第一条跑过即算，后续依赖直接复用其结果，
   不再重复执行）——S 在调度序里只出现一次即天然满足该去重。

id 一律按"不透明字符串"处理（WebUITestCase 的 id/test_case_id 是 UUID varchar(36)，
不是整数）——不依赖任何具体主键类型，换任何模型/项目均通用。

只做纯调度，不碰浏览器/数据库：
- resolve_execution_order(selected, loader): 展开传递依赖 → 判环 → 返回
  (ordered_objs, dep_map)。ordered 满足前置在前、每条用例只出现一次(共享去重)。
- dependency_skip_reason(...): 判断某用例是否因前置未通过而应跳过。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def _dep_ids(obj: Any) -> List[str]:
    """读取对象的 depends_on（JSON 列，可能返回 list / 字符串 / None），归一为 str 列表。"""
    d = getattr(obj, "depends_on", None) or []
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            return []
    if isinstance(d, list):
        out = []
        for x in d:
            s = str(x).strip()
            if s and s.lower() != "none" and s.lower() != "null":
                out.append(s)
        return out
    return []


def _key(obj: Any) -> Optional[str]:
    """对象 → 不透明字符串 id。"""
    i = getattr(obj, "id", None)
    return str(i) if i is not None else None


def resolve_execution_order(
    selected: List[Any],
    loader: Optional[Callable[[str], Optional[Any]]] = None,
) -> Tuple[List[Any], Dict[str, List[str]]]:
    """把选中的用例展开成"含前置用例、前置在前、每条一次"的执行顺序。"""
    if not selected:
        return [], {}

    id2obj: Dict[str, Any] = {}
    for o in selected:
        k = _key(o)
        if k is not None:
            id2obj.setdefault(k, o)

    # 展开传递依赖（loader 补加载不在选中集里的前置）
    needed: Set[str] = set(id2obj.keys())
    pending = list(needed)
    while pending:
        cur = pending.pop()
        obj = id2obj.get(cur)
        if obj is None:
            continue
        for d in _dep_ids(obj):
            if d in needed:
                continue
            if d not in id2obj and loader is not None:
                dobj = loader(d)
                dk = _key(dobj)
                if dobj is not None and dk is not None:
                    id2obj.setdefault(dk, dobj)
            if d in id2obj:
                needed.add(d)
                pending.append(d)
            else:
                logger.warning(
                    f"[UIDep] 用例 {cur} 依赖的前置 {d} 不存在/无法加载，跳过该依赖"
                )

    # 依赖图（只保留执行集内存在的依赖）
    dep_map: Dict[str, List[str]] = {}
    for cid in needed:
        obj = id2obj.get(cid)
        dep_map[cid] = [d for d in _dep_ids(obj) if d in needed]

    # DFS 后序拓扑（前置在前、每条一次、稳定）+ 判环安全打破
    resolved: List[Any] = []
    seen: Set[str] = set()
    in_stack: Set[str] = set()

    def _visit(cid: str) -> None:
        if cid in seen:
            return
        if cid in in_stack:
            logger.warning(f"[UIDep] 检测到循环依赖，已安全打破: {cid}")
            return
        in_stack.add(cid)
        for d in dep_map.get(cid, []):
            _visit(d)
        in_stack.discard(cid)
        if cid in seen:
            return
        obj = id2obj.get(cid)
        if obj is not None:
            resolved.append(obj)
            seen.add(cid)

    for sel in selected:
        k = _key(sel)
        if k is not None:
            _visit(k)

    return resolved, dep_map


def dependency_skip_reason(
    case_id: Any,
    dep_map: Dict[str, List[str]],
    outcomes: Dict[str, str],
) -> Optional[str]:
    """判断某用例是否因前置未通过而应跳过。

    outcomes: {case_id_str: 'passed'|'failed'|'skipped'|'error'}
    返回跳过原因字符串；无需跳过返回 None。case_id 可为任意类型，内部转 str 比较。
    """
    cid = str(case_id)
    for d in dep_map.get(cid, []):
        st = outcomes.get(d)
        if st is not None and st != "passed":
            return f"前置用例({d})状态={st}，依赖用例跳过"
    return None
