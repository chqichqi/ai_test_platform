"""
元素定位器 — 文本/角色多层回退策略

核心思路：用"搜索特定元素"替代"发现所有元素"。
对 React/Ant Design/Element UI 均有效，不依赖 CSS class。

五层回退:
  1. page.get_by_text(target, exact=True) — 精确文本
  2. page.get_by_role(role, name=target) — ARIA 角色 + 可访问名称
  3. page.get_by_label(target) — 表单标签关联
  4. page.get_by_placeholder(target) — placeholder 属性
  5. JS TreeWalker 全页文本扫描 — 最后兜底
"""

import logging
from typing import Any, Dict, Optional, List

from app.core.services.text_normalize import normalize_ws

logger = logging.getLogger(__name__)

# Playwright 角色 → get_by_role 支持的 role 映射
_ROLE_MAP = {
    'button': 'button',
    'link': 'link',
    'textbox': 'textbox',
    'searchbox': 'searchbox',
    'combobox': 'combobox',
    'listbox': 'listbox',
    'tab': 'tab',
    'menuitem': 'menuitem',
    'checkbox': 'checkbox',
    'radio': 'radio',
    'option': 'option',
    'switch': 'switch',
    'row': 'row',
    'table_row': 'row',
    'heading': 'heading',
    'img': 'img',
}


def _normalize_role(role: str) -> str:
    """标准化角色名称到 Playwright 支持的 role。"""
    role_lower = role.lower().strip()
    return _ROLE_MAP.get(role_lower, role_lower)


class LocateResult:
    """定位结果"""
    __slots__ = ('found', 'locator', 'strategy', 'element_info')

    def __init__(self, found: bool, locator=None, strategy: str = '',
                 element_info: Optional[Dict] = None):
        self.found = found
        self.locator = locator
        self.strategy = strategy
        self.element_info = element_info or {}

    def __bool__(self):
        return self.found


class ElementLocator:
    """同步 Playwright 文本/角色定位器。

    用于在已知页面上按描述搜索特定元素，
    而非遍历所有元素做盲发现。
    """

    def __init__(self, page, config=None):
        """
        Args:
            page: Playwright sync Page 对象
            config: WebExplorationConfig（可选，用于 JS 回退的选择器配置）
        """
        self.page = page
        self.config = config

    def _build_args_from_locator(self, locate_result, target: str) -> dict:
        """从 LocateResult 构建 UI 步骤 args dict（用于生成 __login__ 步骤）。

        优先使用语义化的定位方式（role/text/placeholder），回退 CSS selector。
        """
        args = {}
        info = locate_result.element_info or {}
        strategy = locate_result.strategy or ''

        # 角色定位
        role = info.get('role', '')
        if role and role in ('button', 'link', 'textbox', 'combobox', 'tab', 'menuitem', 'searchbox'):
            args['role'] = role
            args['locator'] = target
            return args

        # 文本定位
        if 'text' in strategy:
            args['locator'] = target
            return args

        # CSS class 定位（取第一个有意义 class）
        cls = info.get('cls', '')
        if 'select' in cls.lower() or 'picker' in cls.lower():
            args['locator'] = target
            return args

        # 兜底：只用 target 文本
        args['locator'] = target
        return args

    # ═══════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════

    def locate(self,
               target: str,
               role: str = '',
               context_hint: str = '',
               ui_pattern: str = '',
               scope_element=None) -> LocateResult:
        """按动作语义定位真实可交互元素。

        重要原则：如果调用方给了 role，role 是约束而不是提示。
        例如“患者姓名”+textbox 不能先命中页面上的 label/div；
        click 也不能因为容器包含目标文本就把容器当成按钮。
        """
        if not target or not str(target).strip():
            return LocateResult(False, strategy='empty_target')
        target = str(target).strip()
        normalized_role = _normalize_role(role) if role else ''
        search_root = self._resolve_scope(context_hint, scope_element)

        # 1. 明确 role 时先 role；这是最高可信路径。
        if normalized_role:
            result = self._try_get_by_role(target, normalized_role, search_root)
            if result.found and result.locator:
                return result

        # 2. 表单控件：label/placeholder 是真实控件语义，不应先走 text。
        if normalized_role in ('textbox', 'searchbox', 'combobox'):
            for fn, name in (
                (self._try_get_by_label, 'label'),
                (self._try_get_by_placeholder, 'placeholder'),
            ):
                result = fn(target, search_root)
                if result.found and result.locator:
                    return result

        # 3. 精确文本，只接受可见且可操作元素；容器文本不直接作为成功。
        result = self._try_get_by_text(target, search_root, require_actionable=bool(normalized_role or ui_pattern in ('button','link','card','icon','tab','menu','menuitem','row','table_row')))
        if result.found and result.locator:
            return result

        # 4. 表单控件再允许通用 role fallback。
        if normalized_role in ('textbox', 'searchbox'):
            for r in ('textbox', 'searchbox'):
                result = self._try_get_by_role(target, r, search_root)
                if result.found and result.locator:
                    return result

        # 5. JS TreeWalker 只作为证据发现；必须能够重新构造可操作 locator 才算 found。
        result = self._try_js_treewalker(target, normalized_role, scope_element)
        if result.found and result.locator:
            return result

        # 6. 评分兜底必须存在文本/ARIA/同义词关联，禁止纯 UI class 假阳性。
        result = self._try_scoring_match(target, normalized_role, ui_pattern, scope_element)
        if result.found and result.locator:
            return result

        logger.warning(f"[ElementLocator] 未找到可执行元素: target={target!r}, role={role!r}, context={context_hint!r}")
        return LocateResult(False, strategy='not_found')

    # ═══════════════════════════════════════════════════════════
    # 各层策略
    # ═══════════════════════════════════════════════════════════

    def _try_get_by_text(self, target: str, scope=None, require_actionable: bool = False) -> LocateResult:
        """文本定位：优先最小可见节点，并在需要时提升到可交互祖先。"""
        try:
            root = scope or self.page
            exact = root.get_by_text(target, exact=True)
            count = exact.count()
            candidates = []
            for i in range(min(count, 20)):
                try:
                    loc = exact.nth(i)
                    if not loc.is_visible():
                        continue
                    candidate = self._actionable_ancestor(loc) if require_actionable else loc
                    if candidate is not None and candidate.is_visible():
                        candidates.append(candidate)
                except Exception:
                    continue
            if candidates:
                # 去重 locator 不可靠，按 DOM 面积选择最小者。
                best = self._pick_best(candidates, len(candidates))
                if best:
                    return LocateResult(True, best, 'text_exact', self._describe(best))

            partial = root.get_by_text(target, exact=False)
            count = partial.count()
            for i in range(min(count, 20)):
                try:
                    loc = partial.nth(i)
                    if not loc.is_visible():
                        continue
                    candidate = self._actionable_ancestor(loc) if require_actionable else loc
                    if candidate is not None and candidate.is_visible():
                        return LocateResult(True, candidate, 'text_contains', self._describe(candidate))
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[ElementLocator] get_by_text failed: {e}")
        return LocateResult(False, strategy='text')

    def _actionable_ancestor(self, locator):
        """把 span/div 文本提升到最近真实交互祖先。"""
        try:
            return locator.locator(
                'xpath=ancestor-or-self::*['
                'self::button or self::a or self::input or self::textarea or self::select or '
                '@role="button" or @role="link" or @role="tab" or @role="checkbox" or '
                '@role="radio" or @role="switch" or @role="combobox" or @onclick or @tabindex="0"'
                '][1]'
            ).first
        except Exception:
            return locator

    def _try_get_by_role(self, target: str, role: str, scope=None) -> LocateResult:
        """第 2 层: get_by_role(name=target)"""
        try:
            scope_locator = scope or self.page

            # 精确名称
            loc = scope_locator.get_by_role(role, name=target, exact=True).first
            try:
                if loc.is_visible():
                    return LocateResult(True, loc, 'role_exact',
                                        self._describe(loc))
            except Exception:
                pass

            # 包含名称
            candidates = scope_locator.get_by_role(role, name=target, exact=False)
            count = candidates.count()
            if count > 0:
                best = self._pick_best(candidates, count)
                if best:
                    return LocateResult(True, best, 'role_contains',
                                        self._describe(best))
        except Exception as e:
            logger.debug(f"[ElementLocator] get_by_role failed: {e}")

        return LocateResult(False, strategy='role')

    def _try_get_by_label(self, target: str, scope=None) -> LocateResult:
        """第 3 层: get_by_label（通过 &lt;label for="..."&gt; 关联）"""
        try:
            scope_locator = scope or self.page

            # 精确匹配
            loc = scope_locator.get_by_label(target, exact=True).first
            try:
                if loc.is_visible():
                    return LocateResult(True, loc, 'label_exact',
                                        self._describe(loc))
            except Exception:
                pass

            # 部分匹配
            candidates = scope_locator.get_by_label(target, exact=False)
            count = candidates.count()
            if count > 0:
                return LocateResult(True, candidates.first, 'label_contains', self._describe(candidates.first))
        except Exception as e:
            logger.debug(f"[ElementLocator] get_by_label failed: {e}")

        return LocateResult(False, strategy='label')

    def _try_get_by_placeholder(self, target: str, scope=None) -> LocateResult:
        """第 4 层: get_by_placeholder"""
        try:
            scope_locator = scope or self.page

            loc = scope_locator.get_by_placeholder(target).first
            try:
                if loc.is_visible():
                    return LocateResult(True, loc, 'placeholder',
                                        self._describe(loc))
            except Exception:
                pass

            # 部分匹配
            candidates = scope_locator.get_by_placeholder(target)
            count = candidates.count()
            if count > 0:
                return LocateResult(True, candidates.first, 'placeholder_partial', self._describe(candidates.first))
        except Exception as e:
            logger.debug(f"[ElementLocator] get_by_placeholder failed: {e}")

        return LocateResult(False, strategy='placeholder')

    def _try_js_treewalker(self, target: str, role: str, scope=None) -> LocateResult:
        """第 5 层: JS TreeWalker 全页扫描 + 文本精确匹配。

        复用探索引擎中已验证的 TreeWalker 模式：
        - 遍历所有可见叶子节点
        - 精确文本匹配
        - 取最近的 button/a/[role]/[onclick]/li 祖先
        """
        try:
            # 构建选择器（从 config 或默认值）
            click_sel = 'button, a[href], [role="button"], [role="link"], [onclick], [tabindex="0"], li'
            if self.config and hasattr(self.config, 'click_selectors'):
                click_sel = self.config.click_selectors

            result = self.page.evaluate("""
                (params) => {
                    const target = params.target;
                    // 归一化目标文本（去空白/全角空格）——应用侧可能渲染为「重 置」
                    const normTarget = target.replace(/[\\s\\u3000]+/g, '');
                    const clickSel = params.clickSel;
                    const scopeEl = params.scopeEl;

                    const walker = document.createTreeWalker(
                        scopeEl || document.body,
                        NodeFilter.SHOW_ELEMENT,
                        null,
                        false
                    );

                    let bestEl = null;
                    let bestLen = Infinity;

                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        if (el.offsetParent === null) continue;

                        const text = (el.textContent || '').trim();
                        if (!text) continue;

                        // 归一化后精确文本匹配（「重 置」可命中「重置」）
                        if (text.replace(/[\\s\\u3000]+/g, '') === normTarget && text.length < bestLen) {
                            bestEl = el;
                            bestLen = text.length;
                        }
                    }

                    if (!bestEl) return null;

                    // 找最近的可交互祖先
                    let clickTarget = bestEl.closest(clickSel) || bestEl;

                    // 滚动到可见
                    clickTarget.scrollIntoView({block: 'center', behavior: 'instant'});

                    // 返回元素信息
                    const rect = clickTarget.getBoundingClientRect();
                    const tag = clickTarget.tagName.toLowerCase();
                    const cls = (clickTarget.className || '').toString().substring(0, 80);
                    // 优先取匹配节点自身文本（真实 DOM 文本），避免祖先容器 textContent 污染
                    const selfText = (bestEl.textContent || '').trim();
                    const elemText = (selfText || clickTarget.textContent || '').trim().substring(0, 80);

                    return {
                        tag: tag,
                        role: clickTarget.getAttribute('role') || '',
                        cls: cls,
                        text: elemText,
                        href: clickTarget.getAttribute('href') || '',
                        onclick: !!clickTarget.getAttribute('onclick'),
                        hasTabIndex: clickTarget.hasAttribute('tabindex'),
                        selector: tag + (cls ? '.' + cls.split(' ')[0] : ''),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                    };
                }
            """, {
                'target': target,
                'clickSel': click_sel,
                'scopeEl': scope,
            })

            if result:
                # TreeWalker 找到了元素，用返回的信息构建 locator
                info = result
                logger.info(f"[ElementLocator] TreeWalker found: tag={info['tag']}, "
                           f"text='{info['text'][:40]}', role='{info['role']}'")

                # 尝试用找到的信息构建可靠的 Playwright locator
                loc = None
                try:
                    if info.get('role'):
                        try:
                            loc = self.page.get_by_role(info['role'],
                                                        name=info['text'][:40]).first
                            if loc and loc.is_visible():
                                return LocateResult(True, loc, 'treewalker_role',
                                                    element_info=info)
                        except Exception:
                            pass
                    # 回退：直接用文本重新定位
                    if info.get('text'):
                        try:
                            loc = self.page.get_by_text(info['text'][:40], exact=False).first
                            if loc and loc.is_visible():
                                return LocateResult(True, loc, 'treewalker_text',
                                                    element_info=info)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 最终回退：返回无 locator 但有 element_info 的结果
                # 调用方可以用 page.evaluate 直接操作
                return LocateResult(True, None, 'treewalker_info',
                                    element_info=info)

        except Exception as e:
            logger.warning(f"[ElementLocator] TreeWalker failed: {e}")

        return LocateResult(False, strategy='treewalker')

    def _try_keyword_fallback(self, target: str, role: str) -> LocateResult:
        """第 6 层：长描述文本关键词拆解。

        AI 生成的步骤可能是描述性长句，用多种策略拆解关键词逐个尝试。
        """
        import re
        # 策略 A：按所有非中文非字母数字字符拆分（含引号、括号、运算符等）
        parts = re.split(r'[^a-zA-Z0-9一-鿿]+', target)
        # 策略 B：滑窗提取 2-6 字中文片段
        chinese_only = re.sub(r'[^一-鿿]', '', target)
        candidates = []
        # A: 按分隔符拆出的片段
        for p in parts:
            p = p.strip()
            if 2 <= len(p) <= 8:
                candidates.append(p)
        # B: 中文滑窗
        for seg_len in (4, 3, 2):
            for i in range(len(chinese_only) - seg_len + 1):
                seg = chinese_only[i:i + seg_len]
                if seg:
                    candidates.append(seg)

        seen = set()
        attempted = []
        for kw in candidates[:15]:
            if kw in seen:
                continue
            seen.add(kw)
            attempted.append(kw)
            try:
                loc = self.page.get_by_text(kw, exact=False).first
                if loc and loc.is_visible():
                    logger.info(f"[ElementLocator] Keyword fallback found: '{kw}'")
                    return LocateResult(True, loc, 'keyword_fallback', self._describe(loc))
            except Exception:
                continue

        logger.info(f"[ElementLocator] Keyword fallback failed, tried: {attempted}")
        return LocateResult(False, strategy='keyword_fallback')

    def _try_synonym_fallback(self, target: str, role: str) -> LocateResult:
        """第 7 层：同义词映射回退。

        当需求/用例中的描述与页面实际文本存在差异时（如"新增"vs"添加"），
        通过项目级配置的同义词映射进行回退匹配。

        同义词表来自 exploration_config.element_synonyms：
            {"新增": ["添加", "新建", "创建", "+ New"], ...}
        """
        synonyms = getattr(self.config, 'element_synonyms', None)
        if not synonyms or not isinstance(synonyms, dict):
            return LocateResult(False, strategy='synonym_no_config')

        # 查找 target 的同义词列表
        candidates = synonyms.get(target)
        if not candidates:
            # 也尝试不加描述后缀的短形式
            for key in synonyms:
                if key in target or target in key:
                    candidates = synonyms[key]
                    break
        if not candidates:
            return LocateResult(False, strategy='synonym_not_found')

        attempted = []
        for synonym in candidates[:8]:  # 最多尝试 8 个同义词
            attempted.append(synonym)
            try:
                # 精确匹配
                loc = self.page.get_by_text(synonym, exact=True).first
                try:
                    if loc.is_visible():
                        logger.info(f"[ElementLocator] Synonym exact match: '{target}' → '{synonym}'")
                        return LocateResult(True, loc, 'synonym_exact',
                                           self._describe(loc))
                except Exception:
                    pass

                # 包含匹配
                loc = self.page.get_by_text(synonym, exact=False).first
                try:
                    if loc.is_visible():
                        logger.info(f"[ElementLocator] Synonym contains match: '{target}' → '{synonym}'")
                        return LocateResult(True, loc, 'synonym_contains',
                                           self._describe(loc))
                except Exception:
                    pass

                # 如果有 role hint，也尝试 role + synonym
                if role:
                    normalized_role = _normalize_role(role)
                    try:
                        loc = self.page.get_by_role(normalized_role, name=synonym).first
                        if loc.is_visible():
                            logger.info(f"[ElementLocator] Synonym role match: '{target}' → '{synonym}' as {role}")
                            return LocateResult(True, loc, 'synonym_role',
                                               self._describe(loc))
                    except Exception:
                        pass
            except Exception:
                continue

        logger.info(f"[ElementLocator] Synonym fallback failed, tried: {attempted}")
        return LocateResult(False, strategy='synonym_failed')

    # ═══════════════════════════════════════════════════════════
    # 第 6 层: 全量扫描 + 评分排序
    # ═══════════════════════════════════════════════════════════

    def _try_scoring_match(self, target: str, role: str, ui_pattern: str = '', scope=None) -> LocateResult:
        """全量扫描页面可见元素，对每个候选评分，取最高分。

        比 L6 关键词拆解 + L7 同义词回退更鲁棒：
        - 不需要预先知道同义词
        - 综合考虑文本/角色/类名/结构
        - 分数驱动，不依赖命中/未命中的二值判断
        """
        try:
            # 构建同义词候选（从 config.element_synonyms 读取）
            synonyms = getattr(self.config, 'element_synonyms', {}) or {}
            synonym_candidates = []
            for key, vals in synonyms.items():
                if target in key or key in target:
                    synonym_candidates.extend(vals)
                for v in vals:
                    if target in v or v in target:
                        synonym_candidates.append(key)
                        synonym_candidates.extend(vals)
                        break

            # 构建 UI 模式提示词（用于 class 匹配加分）
            ui_hints = []
            if ui_pattern:
                ui_hints.append(ui_pattern)
            # 补充 UI 模式关键词（从 config 读取，回退默认值）
            _pattern_keywords = getattr(self.config, 'ui_pattern_keywords', None) or {
                'card': ['card', 'panel', 'tile', 'widget'],
                'button': ['btn', 'button'],
                'input': ['input', 'field', 'textbox'],
                'dropdown': ['select', 'dropdown', 'picker', 'combobox'],
                'link': ['link', 'anchor'],
                'icon': ['icon', 'svg'],
                'tab': ['tab', 'nav-item'],
                'menu': ['menu', 'menuitem'],
                'row': ['row', 'tr', 'item'],
            }
            if ui_pattern in _pattern_keywords:
                ui_hints.extend(_pattern_keywords[ui_pattern])
            # 也加入 role 作为 hint
            if role:
                ui_hints.append(role)

            # JS 扫描
            scan_result = self.page.evaluate("""
                (params) => {
                    const target = params.target;
                    const scopeEl = params.scopeEl;
                    const walker = document.createTreeWalker(
                        scopeEl || document.body,
                        NodeFilter.SHOW_ELEMENT,
                        {
                            acceptNode: (el) => {
                                if (!el.offsetParent) return NodeFilter.FILTER_SKIP;
                                // 只取叶子或近似叶子节点（children ≤ 3）
                                if (el.children.length > 3) return NodeFilter.FILTER_SKIP;
                                const text = (el.textContent || '').trim();
                                if (!text || text.length > 80) return NodeFilter.FILTER_SKIP;
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        },
                        false
                    );

                    const candidates = [];
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        const text = (el.textContent || '').trim();
                        const tag = el.tagName.toLowerCase();
                        const cls = (el.className || '').toString().substring(0, 100);
                        const roleAttr = el.getAttribute('role') || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const title = el.getAttribute('title') || '';
                        const href = el.getAttribute('href') || '';
                        const onclick = !!el.getAttribute('onclick');
                        const hasTabIndex = el.hasAttribute('tabindex');
                        const rect = el.getBoundingClientRect();

                        // 找最近的可交互祖先
                        const clickSel = 'button, a[href], [role="button"], [role="link"], [onclick], [tabindex="0"], li, [class*="card"], [class*="panel"], [class*="item"]';
                        let clickTarget = el.closest(clickSel) || el;
                        const ctRect = clickTarget.getBoundingClientRect();

                        // 附近文本（前一个兄弟元素）
                        let nearText = '';
                        const prev = el.previousElementSibling;
                        if (prev) nearText = (prev.textContent || '').trim().substring(0, 40);

                        candidates.push({
                            text: text,
                            tag: tag,
                            cls: cls,
                            role: roleAttr,
                            ariaLabel: ariaLabel,
                            title: title,
                            href: href,
                            nearText: nearText,
                            clickable: !!(onclick || hasTabIndex ||
                                tag === 'button' || tag === 'a' ||
                                roleAttr === 'button' || roleAttr === 'link'),
                            ctTag: clickTarget.tagName.toLowerCase(),
                            ctCls: (clickTarget.className || '').toString().substring(0, 100),
                            ctRole: clickTarget.getAttribute('role') || '',
                            x: Math.round(ctRect.x),
                            y: Math.round(ctRect.y),
                        });
                    }
                    return candidates;
                }
            """, {'target': target, 'scopeEl': scope})

            if not scan_result or not isinstance(scan_result, list):
                return LocateResult(False, strategy='scoring_no_candidates')

            # ── 评分 ──
            scored = []
            for c in scan_result:
                score = 0
                text = c.get('text', '')
                ctCls = (c.get('ctCls', '') + ' ' + c.get('cls', '')).lower()
                aria = c.get('ariaLabel', '').lower()
                title = c.get('title', '').lower()
                near = c.get('nearText', '').lower()
                ctRole = c.get('ctRole', '').lower()
                roleAttr = c.get('role', '').lower()

                # 文本精确匹配（归一化后比较——应用侧可能带空格：「重 置」vs「重置」，
                # 归一化后真实按钮可精确命中，容器「target 子串」不再靠未归一化的空格击败它）
                norm_text = normalize_ws(text)
                norm_target = normalize_ws(target)
                if norm_text == norm_target:
                    score += 50
                elif norm_target in norm_text:
                    score += 40
                elif norm_text in norm_target:
                    score += 30
                else:
                    # 部分匹配（任意 2+ 字重叠）
                    common = sum(1 for ch in norm_target if ch in norm_text)
                    if common >= 2 and len(norm_target) >= 2:
                        score += common * 5

                # 同义词匹配
                for syn in synonym_candidates:
                    if normalize_ws(syn) in norm_text or norm_text in normalize_ws(syn):
                        score += 35
                        break

                # ARIA / title 匹配（同样归一化，避免带空格属性）
                norm_aria = normalize_ws(aria)
                norm_title = normalize_ws(title)
                norm_near = normalize_ws(near)
                if norm_target in norm_aria:
                    score += 30
                if norm_target in norm_title:
                    score += 25
                if norm_target in norm_near:
                    score += 15

                # UI 模式匹配（class 含 card/btn/input 等 hints）
                for hint in ui_hints:
                    if hint in ctCls:
                        score += 10
                        break

                # role 匹配
                if role and (role in (ctRole or roleAttr)):
                    score += 5

                # 可点击加分
                if c.get('clickable'):
                    score += 3

                # 排除整句描述（>20 字的 text 大概率不是 UI 元素）
                if len(text) > 20:
                    score -= 20

                scored.append((score, c))

            if not scored:
                return LocateResult(False, strategy='scoring_empty')

            # 取最高分
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best = scored[0]

            logger.info(f"[ElementLocator] Scoring: {len(scored)} candidates, "
                       f"best='{best['text'][:30]}' score={best_score} "
                       f"ctTag={best['ctTag']} ctCls={best['ctCls'][:40]}")

            if best_score < 10:
                return LocateResult(False, strategy=f'scoring_low({best_score})')

            # 文本关联门槛：纯 UI hint/clickable 支撑的低分命中不算成功——
            # 真机实证（2026-08-23）「重置」命中「取 消」（score=13 全来自
            # btn 提示 + 可点击，文本零关联）是假阳性，会污染探索诊断与校正数据源。
            # 要求 best 候选与 target 至少存在一种文本/ARIA/同义词关联。
            b_text = best.get('text', '')
            n_best = normalize_ws(b_text)
            b_common = sum(1 for ch in norm_target if ch in n_best)
            _text_related = (n_best == norm_target or norm_target in n_best
                             or n_best in norm_target or b_common >= 2)
            b_aria = normalize_ws((best.get('ariaLabel') or '').lower())
            b_title = normalize_ws((best.get('title') or '').lower())
            _attr_related = bool(norm_target in b_aria or norm_target in b_title)
            _syn_related = any(
                normalize_ws(s) in n_best or n_best in normalize_ws(s)
                for s in synonym_candidates)
            if not (_text_related or _attr_related or _syn_related):
                return LocateResult(False,
                                    strategy=f'scoring_unrelated({best_score})')

            # 用最佳候选信息构建 locator
            info = {
                'tag': best['ctTag'],
                'role': best['ctRole'] or best['role'],
                'cls': best['ctCls'],
                'text': best['text'][:80],
                'href': best['href'],
                'onclick': best['clickable'],
                'hasTabIndex': best['clickable'],
                'x': best['x'],
                'y': best['y'],
            }

            # 尝试用 best match 信息构建 Playwright locator
            loc = None
            try:
                if best['ctRole']:
                    loc = self.page.get_by_role(best['ctRole'], name=best['text'][:40]).first
                    if loc and loc.is_visible():
                        return LocateResult(True, loc, f'scored({best_score})', element_info=info)
            except Exception:
                pass
            try:
                if best['text']:
                    loc = self.page.get_by_text(best['text'][:40], exact=False).first
                    if loc and loc.is_visible():
                        return LocateResult(True, loc, f'scored_text({best_score})', element_info=info)
            except Exception:
                pass

            # 返回无 locator 但有 element_info 的结果
            return LocateResult(True, None, f'scored_info({best_score})', element_info=info)

        except Exception as e:
            logger.warning(f"[ElementLocator] Scoring match failed: {e}")
            return LocateResult(False, strategy='scoring_error')

    # ═══════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════

    def _resolve_scope(self, context_hint: str, scope_element=None):
        """解析搜索范围（返回 Playwright Locator 或 None）。

        注意: 绝不返回 ElementHandle——ElementHandle 没有 get_by_text/get_by_role
        等定位方法。默认使用 Page 级别搜索（返回 None）。
        """
        if context_hint == 'modal':
            # 在弹窗内搜索
            try:
                dialog = self.page.locator(
                    '[role="dialog"]:not([style*="display: none"]), '
                    'dialog[open], '
                    '[class*="modal"]:not([style*="display: none"])'
                ).first
                if dialog.count() > 0:
                    return dialog
            except Exception:
                pass
        elif context_hint == 'table_row':
            # 在表格内搜索
            try:
                table = self.page.locator('table, [role="table"], [role="grid"]').first
                if table.count() > 0:
                    return table
            except Exception:
                pass

        # 默认：无 scope 限定（Page 级别搜索）
        # 不返回 ElementHandle——它不支持 get_by_text/get_by_role
        # scope_element 仅用于第5层 TreeWalker 回退
        return None

    def _pick_best(self, candidates, count: int):
        """从 Locator 集合或 Python list 中选择可见面积最小的候选。"""
        best = None
        best_area = float('inf')
        limit = min(count, 10)
        for i in range(limit):
            try:
                loc = candidates[i] if isinstance(candidates, (list, tuple)) else candidates.nth(i)
                if not loc.is_visible():
                    continue
                box = loc.bounding_box()
                if box:
                    area = box.get('width', 0) * box.get('height', 0)
                    if area > 0 and area < best_area:
                        best_area, best = area, loc
            except Exception:
                continue
        if best is None and limit > 0:
            try:
                best = candidates[0] if isinstance(candidates, (list, tuple)) else candidates.first
            except Exception:
                pass
        return best

    def _describe(self, locator) -> Dict[str, Any]:
        """提取可用于 Evidence/脚本生成的真实元素信息。"""
        def attr(name):
            try: return locator.get_attribute(name) or ''
            except Exception: return ''
        try: tag = locator.evaluate("el => el.tagName.toLowerCase()")
        except Exception: tag = ''
        try: text = (locator.inner_text() or '').strip()
        except Exception: text = ''
        role = attr('role')
        aria = attr('aria-label')
        title = attr('title')
        elem_id = attr('id')
        name = attr('name')
        placeholder = attr('placeholder')
        href = attr('href')
        selector = ''
        if elem_id:
            selector = f'#{elem_id}'
        elif name:
            selector = f'[name="{name.replace(chr(34), chr(92)+chr(34))}"]'
        elif aria:
            selector = f'[aria-label="{aria.replace(chr(34), chr(92)+chr(34))}"]'
        return {
            'tag': tag, 'role': role, 'text': text[:120], 'aria_label': aria,
            'title': title, 'id': elem_id, 'name': name, 'placeholder': placeholder,
            'href': href, 'selector': selector,
        }
