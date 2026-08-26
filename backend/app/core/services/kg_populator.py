"""
KnowledgeGraph 填充器

将探索结果写入 KnowledgeGraph 的 JSON 列 + ExplorationPageSnapshot 行。
这是对当前系统最关键的修复 —— 在此之前，KG 的 10 个 JSON 列从未被任何代码实际写入。

写入列:
  - kg.pages: 访问过的页面列表
  - kg.menus: 导航菜单结构
  - kg.elements: 所有交互元素（含多策略定位器）
  - kg.forms: 表单信息
  - kg.tables: 表格信息
  - kg.flows: 操作流程（从步骤链推导）
  - kg.dropdowns: 下拉选项（从 deep_dive）
  - kg.modals: 弹窗信息（从 deep_dive）
  - kg.dependencies: 依赖关系（节点→节点边，D3 可视化用）
  - kg.api_calls: API 调用记录

同时写入:
  - ExplorationPageSnapshot 行（每访问页面一条）
  - 计数器更新
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.models.knowledge_graph import KnowledgeGraph, ExplorationPageSnapshot
from app.core.logger import logger

# stale-running 死任务判定阈值：探索进程崩溃后行会永远停在 running，
# 超过该时长仍未完成视为死任务（2h 为探索系统级的启发式超时，非业务值）
RUNNING_STALE_SECONDS = 2 * 3600

# 步骤诊断 flow 名前缀（平台内部约定名，按模块分 flow：__step_diagnostics__:{module}）。
# 写入侧（populate）与读取侧（functional_to_ui_service._query_existing_kg）同源，
# 防键名漂移（雷区表第一条）；旧格式无后缀 __step_diagnostics__ 仅存量库读取回退
STEP_DIAG_FLOW_PREFIX = "__step_diagnostics__:"


class KGPopulator:
    """将探索结果 + 测试步骤 写入 KnowledgeGraph 数据库行。"""

    def __init__(self, db: Session):
        self.db = db

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    def populate(self,
                 project_id: int,
                 version_id: int,
                 module_name: str,
                 exploration_result: Dict[str, Any],
                 guided_steps: Optional[List] = None,
                 test_cases: Optional[List] = None,
                 base_url: str = '',
                 username: str = '',
                 auth_data: Optional[Dict] = None,
                 platform_type: str = 'web',
                 replace_mode: str = 'auto',  # 'auto' | 'full' | 'merge'
                 explored_modules: Optional[List[str]] = None,
                 ) -> KnowledgeGraph:
        """填充知识图谱。

        Args:
            replace_mode:
                - 'full': 全量替换（force_explore 时使用）
                - 'merge': 合并模式——新数据合并入旧 KG，未探索模块的数据保留
                - 'auto': 自动判断——有旧 KG 且非首次探索则 merge，否则 full
            explored_modules: merge 模式下本次探索的模块名列表（用于判断哪些旧快照需要保留）
        """
        # 1. 查找或创建 KnowledgeGraph（项目唯一行）
        kg, _created = self._find_or_create_graph(project_id, version_id, base_url, username)
        # 新建行由本管线持有 running，最终置 completed；既有行状态保留
        prev_status = None if _created else kg.exploration_status

        # 判断合并模式（项目唯一行：行已存在即可合并，
        # 不再因旧行非 completed 而退化为 full——running 状态由全站 BFS 管线持有）
        if replace_mode == 'auto':
            replace_mode = 'merge' if (kg.id is not None and explored_modules) else 'full'
        do_merge = (replace_mode == 'merge' and kg.id is not None)

        # 2. 提取新数据
        new_pages = self._extract_pages(exploration_result, module_name)
        new_menus = self._extract_menus(exploration_result)
        new_elements = self._extract_elements(exploration_result, guided_steps)
        new_forms = self._extract_forms(exploration_result, guided_steps)
        new_tables = self._extract_tables(exploration_result)
        new_flows = self._extract_flows(exploration_result, guided_steps, test_cases)
        new_dropdowns = exploration_result.get('deep_dive', {}).get('dropdowns', {})
        new_modals = exploration_result.get('deep_dive', {}).get('modals', [])
        new_api_calls = exploration_result.get('deep_dive', {}).get('api_endpoints', [])

        # 持久化步骤诊断（按模块分 flow：__step_diagnostics__:{module}，F1 修复 2026-08-25）
        # 历史缺陷：单一 __step_diagnostics__ flow 同名覆盖——主探索（全模块）populate 后，
        # 补充探索（仅缺失模块）再次 populate 用该模块诊断整体替换 → 其他模块诊断丢失 →
        # 下次转化误判「探索未覆盖此步骤」→ 再触发补充探索 → 跨批次震荡。
        # 分组键用合并层标记的 _module（_merge_exploration_results 逐条附加），
        # 无标记时回退本次 populate 的 module_name（逗号串仅兜底，不参与分组冲突）。
        step_diag = exploration_result.get('step_diagnostics', [])
        _diag_groups: Dict[str, list] = {}
        for _d in step_diag:
            if not isinstance(_d, dict):
                continue
            _mod = (_d.get('_module') or module_name or '通用').strip() or '通用'
            _diag_groups.setdefault(_mod, []).append(_d)
        for _mod, _diags in _diag_groups.items():
            new_flows.append({
                "flow_name": f"{STEP_DIAG_FLOW_PREFIX}{_mod}",
                "flow_type": "meta",
                "steps": _diags,
            })

        if do_merge:
            # ── 合并模式：旧数据 + 新数据 ──
            # pages: 按 URL 去重，新数据优先（提取器产出 page_url 键，兼容 url 键）
            def _page_url(p):
                return ((p.get('page_url') or p.get('url') or '') if isinstance(p, dict) else '')
            # 拷贝一份再修改：原地 mutate 原列表不会触发 SQLAlchemy 变更检测（old is new → UPDATE 省略该列）
            _old_pages = list(kg.pages or [])
            _old_urls = {_page_url(p) for p in _old_pages}
            for p in new_pages:
                if isinstance(p, dict) and _page_url(p) not in _old_urls:
                    _old_pages.append(p)
                elif isinstance(p, dict):
                    # 替换同 URL 的旧条目
                    for i, op in enumerate(_old_pages):
                        if _page_url(op) == _page_url(p):
                            _old_pages[i] = p
                            break
            kg.pages = _old_pages

            # elements: 按 text+tag 去重
            _old_els = list(kg.elements or [])
            _old_keys = {(e.get('text', ''), e.get('tag', '')) for e in _old_els if isinstance(e, dict)}
            for e in new_elements:
                key = (e.get('text', ''), e.get('tag', ''))
                if isinstance(e, dict) and key not in _old_keys:
                    _old_els.append(e)
            kg.elements = _old_els

            # menus: site_map 是每次探索全量扫描的导航结构（当前导航真相）——
            # 非空时全量替换，避免历史按 name 叠加把旧数据残留（2026-08-23：
            # 修复前被误判为模块的内容卡片永远不消失，重探索也看不到修复结果，
            # 用户要求「重新打开就要更新」）。
            # site_map 为空（无导航识别/旧探索产物）时不覆盖，保留旧 menus。
            if new_menus:
                kg.menus = new_menus

            # forms: 按 name 去重合并
            _old_forms = list(kg.forms or [])
            _old_fnames = {f.get('name', '') for f in _old_forms if isinstance(f, dict)}
            for f in new_forms:
                if isinstance(f, dict) and f.get('name', '') not in _old_fnames:
                    _old_forms.append(f)
            kg.forms = _old_forms

            # tables: 追加
            _old_tables = list(kg.tables or [])
            _old_tnames = {t.get('name', '') for t in _old_tables if isinstance(t, dict)}
            for t in new_tables:
                if isinstance(t, dict) and t.get('name', '') not in _old_tnames:
                    _old_tables.append(t)
            kg.tables = _old_tables

            # flows: 按 flow_name 去重，新数据覆盖同名的旧数据
            _old_flows = list(kg.flows or [])
            # 旧格式迁移（F1 2026-08-25）：无后缀 __step_diagnostics__ 单 flow 按模块分 flow
            # 后废弃——合并时从旧数据剔除（读取侧对存量库回退兼容，新格式出现即无并存）
            _old_flows = [f for f in _old_flows if not (
                isinstance(f, dict) and f.get('flow_name') == '__step_diagnostics__'
            )]
            _old_fnames = {f.get('flow_name', '') for f in _old_flows if isinstance(f, dict)}
            for f in new_flows:
                fname = f.get('flow_name', '') if isinstance(f, dict) else ''
                if fname and fname in _old_fnames:
                    # 步骤诊断 flow（__step_diagnostics__:{module}）：按 (target, action)
                    # key 级合并而非整体替换——补充探索只重探缺失步骤，整体替换会清空
                    # 主探索已成功诊断 → 下次转化误判缺失 → 跨批次互斥震荡（E1 复查修复
                    # 2026-08-25；此前 F1 只修了跨模块分组，模块内同 flow 仍整体替换）。
                    # 新诊断覆盖同 key（重探结果为准），新批次未出现的旧 key 保留
                    # （主探索全量步骤时语义等同整体替换——所有 key 都有新诊断）。
                    if (fname.startswith(STEP_DIAG_FLOW_PREFIX)
                            and isinstance(f.get('steps'), list)):
                        _old_idx = None
                        for i, of in enumerate(_old_flows):
                            if isinstance(of, dict) and of.get('flow_name', '') == fname:
                                _old_idx = i
                                break
                        if _old_idx is not None:
                            _old_steps = list((_old_flows[_old_idx].get('steps') or []))
                            _new_steps = list(f.get('steps') or [])
                            _new_keys = {(d.get('target', ''), d.get('action', ''))
                                         for d in _new_steps if isinstance(d, dict)}
                            _merged = _new_steps + [
                                d for d in _old_steps
                                if isinstance(d, dict)
                                and (d.get('target', ''), d.get('action', '')) not in _new_keys
                            ]
                            _new_f = dict(f)
                            _new_f['steps'] = _merged
                            _old_flows[_old_idx] = _new_f
                            continue
                    for i, of in enumerate(_old_flows):
                        if isinstance(of, dict) and of.get('flow_name', '') == fname:
                            _old_flows[i] = f
                            break
                elif isinstance(f, dict):
                    _old_flows.append(f)
            kg.flows = _old_flows

            # dropdowns: dict 浅合并，新 key 覆盖旧 key
            _old_dd = dict(kg.dropdowns or {})
            _old_dd.update(new_dropdowns)
            kg.dropdowns = _old_dd

            # modals / api_calls: 去重追加
            _old_modals = list(kg.modals or [])
            _old_mnames = {m.get('title', m.get('name', '')) for m in _old_modals if isinstance(m, dict)}
            for m in new_modals:
                if isinstance(m, dict) and m.get('title', m.get('name', '')) not in _old_mnames:
                    _old_modals.append(m)
            kg.modals = _old_modals

            _old_apis = list(kg.api_calls or [])
            _old_urls_api = {a.get('url', '') for a in _old_apis if isinstance(a, dict)}
            for a in new_api_calls:
                if isinstance(a, dict) and a.get('url', '') not in _old_urls_api:
                    _old_apis.append(a)
            kg.api_calls = _old_apis

            logger.info(f"[KGPopulator] 合并模式: pages {len(kg.pages)}(+{len(new_pages)}新), "
                       f"elements {len(kg.elements)}(+{len(new_elements)}新), "
                       f"dropdowns {len(kg.dropdowns)}(+{len(new_dropdowns)}新)")
        else:
            # ── 全量替换模式 ──
            kg.pages = new_pages
            kg.menus = new_menus
            kg.elements = new_elements
            kg.forms = new_forms
            kg.tables = new_tables
            kg.flows = new_flows
            kg.dropdowns = new_dropdowns
            kg.modals = new_modals
            kg.api_calls = new_api_calls
            logger.info(f"[KGPopulator] 全量替换模式: {len(kg.pages)} pages, {len(kg.elements)} elements")

        kg.dependencies = self._infer_dependencies(kg, module_name, guided_steps)

        # 3. 更新计数器
        kg.page_count = len(kg.pages)
        kg.menu_count = len(kg.menus)
        kg.element_count = len(kg.elements)
        kg.flow_count = len(kg.flows)
        kg.api_count = len(kg.api_calls)

        # 4. 状态和时间（并发仲裁：running 状态由全站 BFS 管线持有，
        #    merge 写入只叠加数据不改状态；stale-running（>2h）视为死任务兜底置 completed）
        if prev_status != 'running':
            kg.exploration_status = 'completed'
        else:
            _stale = (kg.started_at and
                      (datetime.utcnow() - kg.started_at).total_seconds() > RUNNING_STALE_SECONDS)
            if _stale:
                kg.exploration_status = 'completed'
                logger.warning("[KGPopulator] 检测到 stale-running（>2h）死任务，置为 completed")
        kg.completed_at = datetime.utcnow()

        # 5. 鉴权数据
        if auth_data:
            kg.auth_data = auth_data

        # 探索中断感知（F2 2026-08-25）：探索循环静默中断历史事故（99 步只执行 35 步）
        # 中断原因经 _merge_exploration_results 逐模块透传到 stats.interrupted，
        # 落库时日志告警，数据不完整可观测
        _interrupted = (exploration_result.get('stats') or {}).get('interrupted')
        if _interrupted:
            logger.warning(f"[KGPopulator] 探索被中断（stats.interrupted: {_interrupted}）——"
                           f"KG 数据可能不完整")

        # 6. 质量评估
        located_count = sum(1 for e in kg.elements if isinstance(e, dict) and e.get('located', False))
        if kg.element_count > 0:
            kg.locator_validation_rate = located_count / kg.element_count
            kg.confidence_score = min(0.95, 0.5 + 0.45 * kg.locator_validation_rate)

        self.db.commit()

        # 7. 清理快照
        if do_merge and explored_modules:
            # 合并模式：只删本次探索涉及的页面的旧快照，保留其他模块的快照
            # 注意：提取器产出 page_url 键（兼容 url 键），键名不一致会删不到任何快照
            _new_urls = {_page_url(p) for p in new_pages}
            if _new_urls:
                try:
                    deleted = self.db.query(ExplorationPageSnapshot).filter(
                        ExplorationPageSnapshot.graph_id == kg.id,
                        ExplorationPageSnapshot.page_url.in_(_new_urls),
                    ).delete(synchronize_session=False)
                    if deleted:
                        logger.info(f"[KGPopulator] 合并模式清理 {deleted} 条相关旧快照（保留其他模块）")
                except Exception as e:
                    logger.warning(f"[KGPopulator] 合并模式清理快照失败: {e}")
        else:
            # 全量替换：清空全部旧快照
            try:
                old_snapshots = self.db.query(ExplorationPageSnapshot).filter(
                    ExplorationPageSnapshot.graph_id == kg.id
                ).delete()
                if old_snapshots:
                    logger.info(f"[KGPopulator] 全量替换清理 {old_snapshots} 条旧快照")
            except Exception as e:
                logger.warning(f"[KGPopulator] 清理旧快照失败: {e}")

        # 8. 写入新快照
        self._write_page_snapshots(kg.id, exploration_result, module_name)

        logger.info(
            f"[KGPopulator] Graph #{kg.id} populated: "
            f"{kg.page_count} pages, {kg.menu_count} menus, "
            f"{kg.element_count} elements, {kg.flow_count} flows, "
            f"{kg.api_count} API calls, confidence={kg.confidence_score:.2f}"
        )
        return kg

    # ═══════════════════════════════════════════════════════════
    # 提取器
    # ═══════════════════════════════════════════════════════════

    def _find_or_create_graph(self, project_id, version_id, base_url, username) -> tuple:
        """查找项目唯一 KG 行或创建新行（知识图谱是项目级资产，UNIQUE(project_id)）。

        Returns:
            (kg, was_created): was_created=True 表示本次新建（状态由本管线持有）
        """
        kg = self.db.query(KnowledgeGraph).filter(
            KnowledgeGraph.project_id == project_id,
        ).first()

        if not kg:
            kg = KnowledgeGraph(
                project_id=project_id,
                version_id=version_id,
                graph_name=f'Exploration-P{project_id}',
                base_url=base_url,
                exploration_strategy='normal',
                login_username=username,
                exploration_status='running',
                started_at=datetime.utcnow(),
            )
            self.db.add(kg)
            self.db.flush()  # 获取 id
            return kg, True

        # 复用已有行：version_id 记录最近更新来源版本（版本删除后为 None）
        if version_id is not None and kg.version_id != version_id:
            kg.version_id = version_id
        if base_url and kg.base_url != base_url:
            kg.base_url = base_url
        if username and kg.login_username != username:
            kg.login_username = username

        return kg, False

    def _extract_pages(self, result: Dict, module_name: str) -> List[Dict]:
        """提取访问过的页面列表。"""
        pages = []
        seen_urls = set()

        # 从 pages_visited 提取（str URL 才是合法输入，dict 防御性跳过）
        for url in result.get('pages_visited', []):
            if isinstance(url, str) and url and url not in seen_urls:
                seen_urls.add(url)
                pages.append({
                    'page_url': url,
                    'page_name': self._url_to_page_name(url, module_name),
                    'page_title': '',
                    'module': module_name,
                })

        # 从 state_graph 补充
        for sn in result.get('state_graph', []):
            if not isinstance(sn, dict):
                continue
            url = sn.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                pages.append({
                    'page_url': url,
                    'page_name': self._url_to_page_name(url, module_name),
                    'page_title': sn.get('title', ''),
                    'module': module_name,
                })

        # 从 element_jumps 补充跳转目标
        jumps = result.get('element_jumps', {})
        if isinstance(jumps, dict):
            for mod_name, mod_data in jumps.items():
                if isinstance(mod_data, dict):
                    for el in mod_data.get('elements', []):
                        if not isinstance(el, dict):
                            continue
                        jump_url = el.get('jump_url', '')
                        if jump_url and jump_url not in seen_urls:
                            seen_urls.add(jump_url)
                            pages.append({
                                'page_url': jump_url,
                                'page_name': self._url_to_page_name(jump_url, mod_name),
                                'page_title': '',
                                'module': mod_name,
                            })

        return pages

    def _extract_menus(self, result: Dict) -> List[Dict]:
        """提取导航菜单结构。"""
        menus = []
        seen_names = set()

        site_map = result.get('site_map', {})
        for m in site_map.get('modules', []):
            if not isinstance(m, dict):
                continue
            name = m.get('name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                menus.append({
                    'name': name,
                    'href': m.get('href', ''),
                    'level': 1,
                    'parent': '',
                    'source': m.get('source', ''),
                })

        # 从 element_jumps 提取子菜单（二级）
        jumps = result.get('element_jumps', {})
        if isinstance(jumps, dict):
            for mod_data in jumps.values():
                if isinstance(mod_data, dict):
                    for el in mod_data.get('elements', []):
                        if not isinstance(el, dict):
                            continue
                        name = el.get('name', '')
                        if name and el.get('navigated') and name not in seen_names:
                            seen_names.add(name)
                            menus.append({
                                'name': name,
                                'href': el.get('jump_url', ''),
                                'level': 2,
                                'parent': el.get('parent_module', ''),
                                'source': 'exploration',
                            })

        return menus

    def _extract_elements(self, result: Dict, guided_steps=None) -> List[Dict]:
        """提取所有交互元素（含定位器信息）。

        关键：当评分引擎找到相似（非精确）匹配时，
        locator_text 使用探索到的实际页面文本，而非步骤解析器的 target_text。
        例如：target="室早" 但页面实际是 "室性早搏" → locator_text="室性早搏"
        这样下游生成的 Playwright 脚本才能正确定位真实元素。
        """
        elements = []
        seen = set()

        # 构建 actual_text 查找表（target → 实际页面文本）
        actual_text_map = {}
        # 来源1: step_diagnostics
        for diag in result.get('step_diagnostics', []):
            target = diag.get('target', '') or diag.get('name', '')
            actual = diag.get('actual_text', '')
            if target and actual and actual != target:
                actual_text_map[target] = actual
        # 来源2: element_jumps
        jumps = result.get('element_jumps', {})
        if isinstance(jumps, dict):
            for mod_data in jumps.values():
                if isinstance(mod_data, dict):
                    for el in mod_data.get('elements', []):
                        if not isinstance(el, dict):
                            continue
                        name = el.get('name', '')
                        actual = el.get('actual_text', '')
                        if name and actual and actual != name:
                            actual_text_map[name] = actual
        # 来源3: click_log（兼容直接传 click_log 的场景）
        for entry in result.get('click_log', []):
            if isinstance(entry, dict):
                name = entry.get('name', '')
                actual = entry.get('actual_text', '')
                if name and actual and actual != name:
                    actual_text_map[name] = actual

        # 从 guided_steps 提取（最精确的来源）
        if guided_steps:
            for gs in guided_steps:
                if hasattr(gs, 'target_text'):
                    key = (gs.target_text, gs.role_hint)
                elif isinstance(gs, dict):
                    key = (gs.get('target_text', ''), gs.get('role_hint', ''))
                else:
                    continue
                if key[0] and key not in seen:
                    seen.add(key)
                    _loc_text = actual_text_map.get(key[0], key[0])
                    elements.append({
                        'element_name': key[0],
                        'name': key[0],
                        'type': key[1] or 'button',
                        'role': key[1] or 'button',
                        'text': key[0],
                        'locator_text': _loc_text,
                        'locator_role': key[1] or 'button',
                        'source': 'guided_step',
                        'located': True,
                    })

        # 从 element_jumps 补充跳转过的元素
        jumps = result.get('element_jumps', {})
        if isinstance(jumps, dict):
            for mod_data in jumps.values():
                if isinstance(mod_data, dict):
                    for el in mod_data.get('elements', []):
                        if not isinstance(el, dict):
                            continue
                        name = el.get('name', '')
                        role = el.get('role', 'button')
                        key = (name, role)
                        if name and key not in seen:
                            seen.add(key)
                            _loc_text = el.get('actual_text', '') or actual_text_map.get(name, name)
                            elements.append({
                                'element_name': name,
                                'name': name,
                                'type': role,
                                'role': role,
                                'text': name,
                                'locator_text': _loc_text,
                                'locator_role': role,
                                'href': el.get('jump_url', ''),
                                'navigated': el.get('navigated', False),
                                'source': 'element_jump',
                                'located': True,
                            })

        # 从 deep_dive tables 提取表格数据
        dd = result.get('deep_dive', {})
        for table_info in dd.get('tables', []):
            if not isinstance(table_info, dict):
                continue
            tname = table_info.get('name', '')
            if tname:
                elements.append({
                    'element_name': tname,
                    'name': tname,
                    'type': 'table',
                    'role': 'table',
                    'text': tname,
                    'source': 'deep_dive',
                    'located': False,
                })

        return elements

    def _extract_forms(self, result: Dict, guided_steps=None) -> List[Dict]:
        """提取表单信息。"""
        forms = []

        # 从 deep_dive.forms
        dd = result.get('deep_dive', {})
        for form_info in dd.get('forms', []):
            if not isinstance(form_info, dict):
                continue
            forms.append({
                'name': form_info.get('name', ''),
                'fields': form_info.get('fields', []),
                'submit_button': form_info.get('submit', ''),
                'source': 'deep_dive',
            })

        # 从 guided_steps 的 FILL/SELECT 步骤提取字段
        if guided_steps:
            current_form_fields = []
            for gs in guided_steps:
                if hasattr(gs, 'action_type'):
                    at = gs.action_type
                    tn = gs.target_text
                elif isinstance(gs, dict):
                    at = gs.get('action_type', '')
                    tn = gs.get('target_text', '')
                else:
                    continue

                if at in ('fill', 'select') and tn:
                    current_form_fields.append({
                        'name': tn,
                        'type': 'textbox' if at == 'fill' else 'combobox',
                        'value': (gs.fill_value if hasattr(gs, 'fill_value')
                                  else gs.get('fill_value', '')),
                    })

            if current_form_fields:
                forms.append({
                    'name': '表单',
                    'fields': current_form_fields,
                    'source': 'guided_steps',
                })

        return forms

    def _extract_tables(self, result: Dict) -> List[Dict]:
        """提取表格信息。"""
        dd = result.get('deep_dive', {})
        tables = dd.get('tables', [])
        # 确保是可序列化的列表
        if isinstance(tables, list):
            return tables
        return []

    def _extract_flows(self, result: Dict, guided_steps=None,
                       test_cases=None) -> List[Dict]:
        """提取操作流程。"""
        flows = []

        if guided_steps and test_cases:
            for tc in test_cases:
                tc_name = (getattr(tc, 'name', None) or
                          getattr(tc, 'title', '未命名'))
                tc_module = getattr(tc, 'module', '') or '通用'

                steps = []
                for gs in guided_steps:
                    if hasattr(gs, 'seq'):
                        step_dict = {
                            'seq': gs.seq,
                            'action': gs.action_type,
                            'target': gs.target_text,
                            'locator_role': gs.role_hint,
                            'locator_text': gs.target_text,
                        }
                    elif isinstance(gs, dict):
                        step_dict = {
                            'seq': gs.get('seq', 0),
                            'action': gs.get('action_type', ''),
                            'target': gs.get('target_text', ''),
                            'locator_role': gs.get('role_hint', ''),
                            'locator_text': gs.get('target_text', ''),
                        }
                    else:
                        continue
                    steps.append(step_dict)

                if steps:
                    flows.append({
                        'flow_name': tc_name,
                        'flow_type': self._infer_flow_type(tc_name, steps),
                        'module': tc_module,
                        'start_page': '',
                        'end_page': '',
                        'steps': steps,
                    })

        return flows

    def _infer_dependencies(self, kg: KnowledgeGraph, module_name: str,
                            guided_steps=None) -> List[Dict]:
        """推断节点间依赖关系（D3 可视化的边）。"""
        deps = []

        # 模块 → 首页面
        if kg.pages:
            deps.append({
                'from': module_name,
                'to': kg.pages[0].get('page_name', ''),
                'type': '导航',
            })

        # 页面 → 页面（导航跳转）
        for i, page in enumerate(kg.pages):
            if i > 0:
                deps.append({
                    'from': kg.pages[i - 1].get('page_name', ''),
                    'to': page.get('page_name', ''),
                    'type': '跳转',
                })

        # 菜单 → 页面
        for menu in kg.menus:
            if menu.get('href'):
                for page in kg.pages:
                    if menu['href'] in page.get('page_url', ''):
                        deps.append({
                            'from': menu['name'],
                            'to': page.get('page_name', ''),
                            'type': '菜单入口',
                        })
                        break

        # 步骤间流程依赖
        if guided_steps:
            for i, gs in enumerate(guided_steps):
                if i > 0:
                    prev_target = (gs.target_text if hasattr(gs, 'target_text')
                                   else gs.get('target_text', ''))
                    curr_target = ''
                    if hasattr(guided_steps[i - 1], 'target_text'):
                        curr_target = guided_steps[i - 1].target_text
                    elif isinstance(guided_steps[i - 1], dict):
                        curr_target = guided_steps[i - 1].get('target_text', '')

                    if curr_target and prev_target:
                        deps.append({
                            'from': curr_target,
                            'to': prev_target,
                            'type': '步骤流转',
                        })

        return deps

    # ═══════════════════════════════════════════════════════════
    # 页面快照
    # ═══════════════════════════════════════════════════════════

    def _write_page_snapshots(self, graph_id: int, result: Dict, module_name: str):
        """为每个访问过的页面写入 ExplorationPageSnapshot。"""
        pages_visited = result.get('pages_visited', [])
        state_graph = result.get('state_graph', [])
        element_jumps = result.get('element_jumps', {})

        # 去重 URL
        seen_urls = set()
        order = 0

        for url in pages_visited:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            order += 1
            self._save_snapshot(graph_id, url, module_name, order, result)

        # 从 state_graph 补充（使用各模块的实际名称）
        for sn in state_graph:
            if not isinstance(sn, dict):
                continue
            url = sn.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                order += 1
                sn_module = sn.get('_module', module_name)
                self._save_snapshot(graph_id, url, sn_module, order, result, sn)

        self.db.commit()

    def _save_snapshot(self, graph_id: int, url: str, module_name: str,
                       order: int, result: Dict, state_node=None):
        """保存单页快照。使用正确的模型字段（修复已存在的 bug）。"""
        try:
            snapshot = ExplorationPageSnapshot(
                graph_id=graph_id,
                page_url=url,
                page_title='',
                page_name=module_name,
                menu_level=1,
                parent_menu='',
                elements=self._get_page_elements(url, result),
                forms=[],
                tables=[],
                buttons=[],
                links=[],
                operations=[],
                dom_snapshot=json.dumps(
                    self._get_page_state(url, result),
                    ensure_ascii=False,
                ) if result else '',
                visited_at=datetime.utcnow(),
                visit_order=order,
            )
            self.db.add(snapshot)
        except Exception as e:
            logger.warning(f"[KGPopulator] 保存页面快照失败 ({url[:60]}): {e}")
            self.db.rollback()

    def _get_page_elements(self, url: str, result: Dict) -> List[Dict]:
        """获取指定页面的元素列表。"""
        elements = []
        jumps = result.get('element_jumps', {})
        if isinstance(jumps, dict):
            for mod_data in jumps.values():
                if isinstance(mod_data, dict) and mod_data.get('url', '') == url:
                    for el in mod_data.get('elements', []):
                        if not isinstance(el, dict):
                            continue
                        elements.append({
                            'name': el.get('name', ''),
                            'role': el.get('role', ''),
                            'navigated': el.get('navigated', False),
                        })
        return elements

    def _get_page_state(self, url: str, result: Dict) -> Optional[Dict]:
        """获取指定页面的状态快照数据。"""
        for sn in result.get('state_graph', []):
            if sn.get('url', '') == url:
                return sn
        return None

    # ═══════════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _url_to_page_name(url: str, module: str) -> str:
        """从 URL 提取页面名称。"""
        if not url:
            return module
        # hash 路由: #/device/list → device-list
        if '#' in url:
            fragment = url.split('#')[-1].split('?')[0]
            parts = [p for p in fragment.split('/') if p]
            return '-'.join(parts) if parts else module
        # 普通 URL
        from urllib.parse import urlparse
        path = urlparse(url).path.strip('/')
        parts = [p for p in path.split('/') if p]
        return '-'.join(parts[-2:]) if parts else module

    @staticmethod
    def _infer_flow_type(name: str, steps: List[Dict]) -> str:
        """从名称和步骤推断流程类型。"""
        name_lower = name.lower()
        if any(kw in name_lower for kw in ('新增', '创建', '添加', 'create', 'add')):
            return 'create'
        if any(kw in name_lower for kw in ('修改', '编辑', '更新', 'edit', 'update')):
            return 'update'
        if any(kw in name_lower for kw in ('删除', '移除', 'delete', 'remove')):
            return 'delete'
        if any(kw in name_lower for kw in ('查看', '详情', 'view', 'detail')):
            return 'view'
        if any(kw in name_lower for kw in ('登录', 'login')):
            return 'login'
        return 'custom'
