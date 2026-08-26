"""
测试步骤 → GuidedAction 解析器

纯函数，无 Playwright 依赖，可直接单元测试。
将中文/英文操作语句映射为 (ActionType, target_text, role_hint, value)。

解析策略（优先级从高到低）:
  0. 「」标记优先提取 — 功能用例已按约定标记 UI 元素（最高优先级，零猜测）
  1. 动词匹配 → ActionType
  2. 目标提取 → target_text + role_hint
  3. 值提取 → fill_value / select_option
  4. LLM 回退（当规则无法匹配时）
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 延迟导入 ActionType 以避免循环依赖（运行时从 exploration agent 导入）
_ACTION_TYPE_ENUM = None


def _get_action_type_enum():
    """延迟导入 ActionType，避免模块级循环依赖"""
    global _ACTION_TYPE_ENUM
    if _ACTION_TYPE_ENUM is None:
        from app.core.services.mcp_exploration_agent import ActionType
        _ACTION_TYPE_ENUM = ActionType
    return _ACTION_TYPE_ENUM


@dataclass
class GuidedStep:
    """解析后的引导探索步骤"""
    seq: int
    action_type: str           # ActionType value: "click"/"fill"/"select"/...
    target_text: str           # 目标元素文本，如 "新增" / "患者姓名"
    role_hint: str = ""        # ARIA 角色提示: "button"/"textbox"/"combobox"/"link"/"tab"
    fill_value: str = ""       # FILL 动作的填充值
    select_option: str = ""    # SELECT 动作的选项值
    expected_result: str = ""  # 预期结果描述
    context_hint: str = ""     # 上下文提示: "在弹窗中" / "在表格第一行"
    ui_pattern: str = ""       # UI 呈现形式: "card"/"button"/"input"/"dropdown"/"link"/"icon"/"menu"
    raw_action: str = ""       # 原始步骤描述（用于日志/回退）
    source: str = "regex"      # 解析来源: "regex" / "field" / "llm"


# ═══════════════════════════════════════════════════════════════
# 动词→ActionType 映射（优先级排序，长匹配在前）
# ═══════════════════════════════════════════════════════════════
_VERB_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex_pattern, action_type, default_role)
    # click 类
    (r'^(点击|单击|点选|点)', 'click', 'button'),
    (r'^(按下|按)', 'click', 'button'),
    # fill 类
    (r'^(填写|输入|填入|录入|键入|设置|写)', 'fill', 'textbox'),
    # select 类
    (r'^(选择|下拉选择|选中|切换选项|改为|选取)', 'select', 'combobox'),
    # hover
    (r'^(悬停|悬浮|鼠标悬停)', 'hover', 'button'),
    # right_click
    (r'^(右键|右击)', 'right_click', 'button'),
    # tab_switch
    (r'^(切换|点Tab|切换到.*(?:页|标签|Tab))', 'tab_switch', 'tab'),
    # navigate
    (r'^(进入|打开|跳转|访问|导航|点击进入|点击打开)', 'navigate', 'link'),
    # go_back / 返回
    (r'^(返回|回到|go_back|page\.go_back)', 'go_back', ''),
    # wait
    (r'^(等待|延时|暂停)', 'wait_for', ''),
    # validate
    (r'^(验证|断言|检查|确认|应该显示|期望|预期)', 'validate', ''),
]

# ── 指代词检测（2026-08-25 用户反馈「强制探索只探索了部分功能或用例」）──
# 「点击该条预警」「记录第一条预警的患者姓名」——target 是纯指代/计数词，页面上
# 不存在该文本 → 正则路径定位必败 not_found → 该对象从未被探索 → 转化时 LLM 无
# 定位依据自由发挥（造出 assert_visible(locator=患者姓名) 烂步骤）。
# 命中此模式 → 移入 _unparsed_raw 交给 LLM（LLM 有全量步骤上下文，能从前序步骤的
# 「」标记对象推断出具体 UI 元素名）。
_DEICTIC_RE = re.compile(
    r'^(该条|该|此条|此|当前|这条|那条|这行|那行|这一行|上一行|'
    r'下一个|下一条|上一条|第一个|第一条|最后一条|最新一条|最新|所选|选中|当前选中)'
)

# 目标末尾的角色提示词（从 target_text 末尾剥离）
_ROLE_SUFFIX_PATTERNS: List[Tuple[str, str]] = [
    (r'按钮$', 'button'),
    (r'(链接|连接)$', 'link'),
    (r'(输入框|文本框|搜索框|搜索栏)$', 'textbox'),
    (r'(下拉框|下拉列表|下拉菜单|下拉|选择框)$', 'combobox'),
    (r'(选项卡|Tab|标签页|标签)$', 'tab'),
    (r'(菜单|菜单项)$', 'menuitem'),
    (r'(图标|Icon)$', 'button'),
    (r'(行|记录)$', 'table_row'),
]

# FILL 值提取模式
_FILL_VALUE_PATTERNS = [
    r'为[""「](.+?)[""」]',     # 填写姓名为"张三"
    r'[:：]\s*(.+?)$',          # 姓名: 张三
    r'为(.+)$',                 # 填写姓名为张三
    r'=\s*(.+?)$',              # 姓名=张三
]

# SELECT 选项提取模式
_SELECT_OPTION_PATTERNS = [
    r'为[""「](.+?)[""」]',     # 选择科室为"内科"
    r'[:：]\s*(.+?)$',          # 科室: 内科
    r'为(.+)$',                 # 选择科室为内科
]

# 上下文模式
_CONTEXT_PATTERNS = [
    (r'在弹窗中|在对话框中|在模态框中|弹出.*中', 'modal'),
    (r'在表格(第?\d*)行', 'table_row'),
    (r'在表单中', 'form'),
    (r'在侧边栏|在导航栏|在菜单中', 'sidebar'),
]


# ═══════════════════════════════════════════════════════════════
# 第 0 层：「」标记优先提取（最高优先级，零猜测）
# ═══════════════════════════════════════════════════════════════

# 「元素名」提取
_BRACKET_TARGET_RE = re.compile(r'「([^」]+)」')
# "值" 提取
_QUOTE_VALUE_RE = re.compile(r'"([^"]+)"')
# 验证：前缀
_VALIDATE_PREFIX_RE = re.compile(r'^验证[：:]\s*')

# 标记内值/选项的上下文判断词
_VALUE_FILL_VERBS = {'填写', '输入', '填入', '录入', '键入', '设置', '写', '填', 'fill', 'type', 'input'}
_VALUE_SELECT_VERBS = {'选择', '下拉', '选中', '切换选项', '改为', '选取', '切换', 'select', 'choose', 'pick'}
# 默认 UI 模式映射（config.ui_pattern_mapping 可覆盖）
_DEFAULT_UI_PATTERN_MAP = {
    '卡片': 'card', 'card': 'card',
    '按钮': 'button', 'button': 'button',
    '输入框': 'input', '文本框': 'input', '搜索框': 'input', '搜索栏': 'input',
    '下拉框': 'dropdown', '下拉列表': 'dropdown', '下拉菜单': 'dropdown', '选择框': 'dropdown',
    '链接': 'link', '连接': 'link',
    '图标': 'icon', 'Icon': 'icon',
    '选项卡': 'tab', 'Tab': 'tab', '标签页': 'tab', '标签': 'tab',
    '菜单': 'menu', '菜单项': 'menu',
    '行': 'row', '记录': 'row',
}

_DESCRIPTIVE_SUFFIXES_RE = re.compile(
    r'(卡片|按钮|链接|图标|输入框|文本框|搜索框|搜索栏|'
    r'下拉框|下拉列表|下拉菜单|选择框|'
    r'选项卡|Tab|标签页|标签|菜单|菜单项|行|记录|弹窗|对话框|页面)$'
)


def _get_ui_pattern_map(config=None):
    """获取 UI 模式映射（优先从 config 读，回退默认值）。"""
    if config and hasattr(config, 'ui_pattern_mapping') and config.ui_pattern_mapping:
        return config.ui_pattern_mapping
    return _DEFAULT_UI_PATTERN_MAP


def _extract_markers(raw_action: str) -> Optional[dict]:
    """从「」标记和"验证："前缀中直接提取元素名和值。

    当功能用例已按约定用「」标记 UI 元素时，这是零猜测的精确提取。
    不需要正则模式匹配动词——标记本身就给出了 target。

    Returns:
        None — 没有标记，走常规正则解析流程
        dict — {
            'target_text': str,       # 从「」提取的元素名（必有）
            'fill_value': str,        # 从 "" 提取的填充值
            'select_option': str,     # 从 "" 提取的选项值
            'is_validate': bool,      # 是否验证步骤
            'has_markers': True,
        }
    """
    target_text = ""
    value_text = ""
    has_element_marker = False
    has_value_marker = False
    is_validate = False

    # 1. 提取「元素名」——取第一个「」的内容作为主目标
    bracket_matches = _BRACKET_TARGET_RE.findall(raw_action)
    if bracket_matches:
        target_text = bracket_matches[0].strip()
        if target_text:
            has_element_marker = True

    # 2. 提取 "值" ——取第一个 "" 的内容
    quote_matches = _QUOTE_VALUE_RE.findall(raw_action)
    if quote_matches:
        value_text = quote_matches[0].strip()
        if value_text:
            has_value_marker = True

    # 3. 检测 验证：前缀
    if _VALIDATE_PREFIX_RE.match(raw_action):
        is_validate = True

    # —— 没有任何标记 → 走常规流程 ——
    if not has_element_marker and not is_validate:
        return None

    # —— 区分 fill_value vs select_option ——
    fill_value = ""
    select_option = ""
    if has_value_marker and value_text:
        # 从原始文本中找动词来判断值的用途
        action_lower = raw_action.lower()
        # 先检查 select 动词
        has_select_verb = any(v in action_lower for v in _VALUE_SELECT_VERBS)
        # 再检查 fill 动词
        has_fill_verb = any(v in action_lower for v in _VALUE_FILL_VERBS)

        if has_select_verb:
            select_option = value_text
        elif has_fill_verb:
            fill_value = value_text
        else:
            # 无法确定时：如果动作中含"填写/输入"类词 → fill
            # 否则如果含"选择/切换"类词 → select
            # 否则默认 fill
            fill_value = value_text

    return {
        'target_text': target_text,
        'fill_value': fill_value,
        'select_option': select_option,
        'is_validate': is_validate,
        'has_markers': True,
    }


def _extract_target(raw_action: str, verb_match: re.Match,
                    role_suffixes=None, context_patterns=None) -> Tuple[str, str, str]:
    """从原始动作描述中提取 target_text 和 role_hint。

    Returns: (target_text, role_hint, context_hint)
    """
    if role_suffixes is None:
        role_suffixes = _ROLE_SUFFIX_PATTERNS
    if context_patterns is None:
        context_patterns = _CONTEXT_PATTERNS

    # 1. 提取上下文提示
    context_hint = ""
    for entry in context_patterns:
        pat = entry["pattern"] if isinstance(entry, dict) else entry[0]
        ctx = entry["context"] if isinstance(entry, dict) else entry[1]
        if re.search(pat, raw_action):
            context_hint = ctx
            raw_action = re.sub(pat, '', raw_action).strip()
            break

    # 2. 去掉动词前缀，得到目标文本
    target = raw_action[verb_match.end():].strip()

    # 去掉开头的介词/助词
    target = re.sub(r'^(了|的是|这个|那个|一下|一次)', '', target).strip()
    # 去掉动词后的冒号（"点击：登录按钮" → "登录按钮"）
    target = re.sub(r'^[：:]\s*', '', target).strip()

    if not target:
        return "", "", context_hint

    # 3. 从末尾剥离角色提示词
    role_hint = ""
    for entry in role_suffixes:
        pat = entry["pattern"] if isinstance(entry, dict) else entry[0]
        role = entry["role"] if isinstance(entry, dict) else entry[1]
        m = re.search(pat, target)
        if m:
            role_hint = role
            target = target[:m.start()].strip()
            break

    return target, role_hint, context_hint


def _extract_value(target: str, action_type: str) -> Tuple[str, str, str]:
    """从目标文本中分离值和纯目标名。

    Returns: (clean_target, value, option)
    """
    if action_type == 'fill':
        for pattern in _FILL_VALUE_PATTERNS:
            m = re.search(pattern, target)
            if m:
                value = m.group(1).strip()
                clean_target = target[:m.start()].strip()
                # 去掉末尾的 "为" / ":"
                clean_target = re.sub(r'[为:：]\s*$', '', clean_target).strip()
                return clean_target, value, ""

    if action_type == 'select':
        for pattern in _SELECT_OPTION_PATTERNS:
            m = re.search(pattern, target)
            if m:
                option = m.group(1).strip()
                clean_target = target[:m.start()].strip()
                clean_target = re.sub(r'[为:：]\s*$', '', clean_target).strip()
                return clean_target, "", option

    return target, "", ""


def parse_single_step(step: dict, seq: int = 1, config=None) -> GuidedStep:
    """解析单个测试步骤为 GuidedStep。

    Args:
        step: 步骤 dict，支持以下格式:
              - {seq, action: "点击新增按钮", expected: "..."}
              - {seq, action: "click", target: "新增按钮", value: "..."}
              - {seq, description: "点击新增按钮"}
              - 纯字符串
        seq: 步骤序号（当 step 不含 seq 时使用）
        config: 可选的 ExplorationConfig（覆盖默认动词/角色/上下文模式）

    Returns:
        GuidedStep 对象
    """
    # 从 config 获取模式（回退到模块级默认值）
    verb_patterns = getattr(config, 'step_verb_patterns', None) or _VERB_PATTERNS
    role_suffixes = getattr(config, 'step_role_suffixes', None) or _ROLE_SUFFIX_PATTERNS
    context_patterns = getattr(config, 'step_context_patterns', None) or _CONTEXT_PATTERNS
    # ── 预处理：提取原始动作描述 ──
    raw_action = ""
    expected = ""

    if isinstance(step, str):
        raw_action = step
    elif isinstance(step, dict):
        # 优先取 action 字段（最常见）
        raw_action = str(step.get('action', '') or
                        step.get('step', '') or
                        step.get('desc', '') or
                        step.get('description', '') or '')
        expected = str(step.get('expected', '') or
                      step.get('expected_result', '') or '')
        seq = step.get('seq', seq)

    raw_action = raw_action.strip()

    # ── 剥离序号前缀（用户常粘贴带编号的步骤列表）──
    # 支持: "1、", "1.", "1)", "1 ", "步骤1:", "Step 1:", "- ", "* " 等
    _raw_before = raw_action
    raw_action = re.sub(
        r'^(?:(?:步骤|Step)\s*\d+\s*[：:.\-—–]\s*'
        r'|\d+\s*[、.，,)\-—–：:]\s*'
        r'|[-*•▪▸►◄■□○●◆◇]\s*'
        r')+',
        '', raw_action
    ).strip()
    # ── 剥离前置副词/连词（"同时输入" → "输入"）──
    raw_action = re.sub(
        r'^(同时|然后|接着|再|并|并且|随后|之后|最后|再然后|若|如果|则|请|如|当)\s*',
        '', raw_action
    ).strip()
    if raw_action != _raw_before:
        logger.debug(f"[StepParser] 剥离前缀: '{_raw_before[:60]}' → '{raw_action[:60]}'")

    # ── 从步骤描述推断 ui_pattern / context_hint ──
    _infer_ui = ''
    _infer_ctx = ''
    if raw_action:
        _rl = raw_action
        if not _infer_ui:
            if any(kw in _rl for kw in ('下拉', '选择框', '选项', 'dropdown')):
                _infer_ui = 'dropdown'
            elif any(kw in _rl for kw in ('弹窗', '对话框', '模态框', 'modal', 'dialog')):
                _infer_ui = 'modal'
            elif any(kw in _rl for kw in ('表格', '列表', '行', '记录')):
                _infer_ui = 'table_row'
        if not _infer_ctx:
            if any(kw in _rl for kw in ('弹窗中', '对话框中')):
                _infer_ctx = 'modal'
            elif any(kw in _rl for kw in ('下拉', '下拉框')):
                _infer_ctx = 'dropdown'

    if not raw_action:
        return GuidedStep(
            seq=seq, action_type='', target_text='', raw_action='',
            expected_result=expected, source='regex'
        )

    # ── 结构字段直接解析（用例已经是结构化的）──
    if isinstance(step, dict):
        struct_action = str(step.get('action', '')).lower().strip()
        struct_target = str(step.get('target', '') or step.get('element', '') or '')
        struct_value = str(step.get('value', '') or step.get('data', '') or '')

        _base = dict(expected_result=expected, raw_action=raw_action, source='field',
                     ui_pattern=_infer_ui, context_hint=_infer_ctx)

        if struct_action in ('click', '点击', '单击'):
            return GuidedStep(seq=seq, action_type='click', target_text=struct_target or raw_action,
                            role_hint='button', fill_value='', **_base)
        if struct_action in ('fill', 'input', '填写', '输入', 'type'):
            return GuidedStep(seq=seq, action_type='fill', target_text=struct_target,
                            role_hint='textbox', fill_value=struct_value, **_base)
        if struct_action in ('select', '选择', 'choose', 'pick'):
            return GuidedStep(seq=seq, action_type='select', target_text=struct_target,
                            role_hint='combobox', select_option=struct_value, **_base)
        if struct_action in ('navigate', 'goto', '导航', '跳转', '打开'):
            return GuidedStep(seq=seq, action_type='navigate',
                            target_text=struct_target or raw_action, role_hint='link', **_base)
        if struct_action in ('validate', 'assert', '验证', '断言', '检查'):
            return GuidedStep(seq=seq, action_type='validate',
                            target_text=struct_target or raw_action, **_base)
        if struct_action in ('wait', '等待'):
            return GuidedStep(seq=seq, action_type='wait_for',
                            target_text=struct_target or raw_action, **_base)
        if struct_action in ('go_back', '返回', '回到'):
            return GuidedStep(seq=seq, action_type='go_back',
                            target_text='', **_base)

    # ── 第 0 层：「」标记优先提取（最高优先级，零猜测）──
    marker = _extract_markers(raw_action)
    if marker:
        target = marker['target_text']
        is_validate = marker['is_validate']

        # 纯验证步骤（以"验证："开头）→ 直接返回，不需要元素定位
        if is_validate:
            # 从「」中提取的元素名作为 context（验证的对象）
            expected_text = raw_action
            # 去掉"验证："前缀得到纯净的预期结果
            expected_text = _VALIDATE_PREFIX_RE.sub('', expected_text).strip()
            if not expected_text:
                expected_text = raw_action
            return GuidedStep(
                seq=seq,
                action_type='validate',
                target_text=target,  # 「」中的元素可作为验证参照
                role_hint='',
                fill_value='',
                select_option='',
                expected_result=expected_text,
                context_hint='',
                raw_action=raw_action,
                source='marker',
            )

        # 非验证步骤但有「」标记 → 从标记提取 target/value，从剩余文本提取 action_type
        # 先尝试用动词匹配确定 action_type
        action_type = ''
        role_hint = ''
        for entry in verb_patterns:
            pattern = entry["pattern"] if isinstance(entry, dict) else entry[0]
            at = entry["action"] if isinstance(entry, dict) else entry[1]
            dr = entry["role"] if isinstance(entry, dict) else entry[2]
            m = re.match(pattern, raw_action)
            if m:
                action_type = at
                role_hint = dr
                break

        if not action_type:
            # 二次尝试：动词不在句首时（常见于"在「...」中填写..."格式）
            # 去掉 ^ 锚点，用 re.search 在整句中搜索动词
            for entry in verb_patterns:
                pattern = entry["pattern"] if isinstance(entry, dict) else entry[0]
                at = entry["action"] if isinstance(entry, dict) else entry[1]
                dr = entry["role"] if isinstance(entry, dict) else entry[2]
                # 去掉开头锚点
                search_pattern = pattern.lstrip('^')
                if re.search(search_pattern, raw_action):
                    action_type = at
                    role_hint = dr
                    break

        if not action_type:
            # 无动词匹配 → 从 marker 的 value 推断
            # 有 fill_value → fill；有 select_option → select；否则默认 click
            if marker['fill_value']:
                action_type = 'fill'
                role_hint = 'textbox'
            elif marker['select_option']:
                action_type = 'select'
                role_hint = 'combobox'
            else:
                action_type = 'click'
                role_hint = 'button'

        # 从「」后面的文本提取角色提示 + UI 呈现形式
        _ui_pattern = ""
        if not role_hint or role_hint == 'button':
            last_bracket_end = raw_action.rfind('」')
            if last_bracket_end >= 0:
                suffix_text = raw_action[last_bracket_end + 1:].strip()
                for entry in role_suffixes:
                    pat = entry["pattern"] if isinstance(entry, dict) else entry[0]
                    rl = entry["role"] if isinstance(entry, dict) else entry[1]
                    m = re.search(pat, suffix_text)
                    if m:
                        role_hint = rl
                        # 同时提取 UI 呈现形式
                        matched_word = m.group(1) if m.lastindex else m.group(0)
                        _ui_pattern = _get_ui_pattern_map(config).get(matched_word, '')
                        break

        # 提取上下文提示
        context_hint = ""
        for entry in context_patterns:
            pat = entry["pattern"] if isinstance(entry, dict) else entry[0]
            ctx = entry["context"] if isinstance(entry, dict) else entry[1]
            if re.search(pat, raw_action):
                context_hint = ctx
                break

        return GuidedStep(
            seq=seq,
            action_type=action_type,
            target_text=target,
            role_hint=role_hint,
            fill_value=marker['fill_value'],
            select_option=marker['select_option'],
            expected_result=expected,
            context_hint=_infer_ctx or context_hint,
            ui_pattern=_infer_ui or _ui_pattern,
            raw_action=raw_action,
            source='marker',
        )

    # ── 正则规则解析（中文动作描述）──
    for entry in verb_patterns:
        pattern = entry["pattern"] if isinstance(entry, dict) else entry[0]
        action_type = entry["action"] if isinstance(entry, dict) else entry[1]
        default_role = entry["role"] if isinstance(entry, dict) else entry[2]
        m = re.match(pattern, raw_action)
        if m:
            target, role_hint, context_hint = _extract_target(raw_action, m, role_suffixes, context_patterns)
            role_hint = role_hint or default_role

            # 提取值
            clean_target, fill_value, select_option = _extract_value(target, action_type)

            return GuidedStep(
                seq=seq,
                action_type=action_type,
                target_text=clean_target,
                role_hint=role_hint,
                fill_value=fill_value,
                select_option=select_option,
                expected_result=expected,
                context_hint=_infer_ctx or context_hint,
                ui_pattern=_infer_ui or '',
                raw_action=raw_action,
                source='regex',
            )

    # ── 二次尝试：动词不在句首时用 re.search 在整句中搜索（取最后一个匹配，因自然语言中动作通常在句末）──
    _last_match = None
    _last_entry = None
    for entry in verb_patterns:
        pattern = entry["pattern"] if isinstance(entry, dict) else entry[0]
        # 去掉 ^ 锚点，在整句中搜索动词
        search_pattern = pattern.lstrip('^')
        for m in re.finditer(search_pattern, raw_action):
            _last_match = m
            _last_entry = entry
    if _last_match and _last_entry:
        m = _last_match
        entry = _last_entry
        action_type = entry["action"] if isinstance(entry, dict) else entry[1]
        default_role = entry["role"] if isinstance(entry, dict) else entry[2]
        # 从动词结束位置截取目标文本
        _after_verb = raw_action[m.end():].strip()
        # 去掉前置介词/助词
        _after_verb = re.sub(r'^(了|的是|这个|那个|一下|一次)', '', _after_verb).strip()
        # 去掉动词后的冒号（"点击：登录按钮" → "登录按钮"）
        _after_verb = re.sub(r'^[：:]\s*', '', _after_verb).strip()
        target = _after_verb
        role_hint = default_role
        context_hint = ""

        # 从末尾剥离角色提示词
        for entry_r in role_suffixes:
            pat = entry_r["pattern"] if isinstance(entry_r, dict) else entry_r[0]
            role = entry_r["role"] if isinstance(entry_r, dict) else entry_r[1]
            rm = re.search(pat, target)
            if rm:
                role_hint = role
                target = target[:rm.start()].strip()
                break

        clean_target, fill_value, select_option = _extract_value(target, action_type)

        # 质量检查：target 过长（>10字）或含分隔符 → 说明提取不干净，扔给 LLM
        if clean_target and (len(clean_target) > 10 or any(c in clean_target for c in '，。；：、?？!！')):
            logger.debug(f"[StepParser] re.search 回退目标不干净(target={clean_target})，交由 LLM")
            # 不返回，让该步骤落入 _unparsed_raw → LLM 处理
        else:
            logger.debug(f"[StepParser] re.search 回退匹配(末位): '{raw_action[:60]}' → action={action_type}, target={clean_target}")
            return GuidedStep(
                seq=seq,
                action_type=action_type,
                target_text=clean_target,
                role_hint=role_hint,
                fill_value=fill_value,
                select_option=select_option,
                expected_result=expected,
                context_hint=_infer_ctx or context_hint,
                ui_pattern=_infer_ui or '',
                raw_action=raw_action,
                source='regex_fallback',
            )

    # ── 最终回退：无「」标记 + 无动词匹配 → 不可解析，跳过 ──
    _final_ui_pattern = ''
    _final_context = ''
    # 尝试读出已设的值（两条路径用了不同变量名）
    for _vn in ('ui_pattern', '_ui_pattern'):
        _v = locals().get(_vn, '')
        if _v:
            _final_ui_pattern = _v
            break
    for _vn in ('context_hint',):
        _v = locals().get(_vn, '')
        if _v:
            _final_context = _v
            break
    # 推断
    _rl = raw_action
    if not _final_ui_pattern:
        if any(kw in _rl for kw in ('下拉', '选择框', '选项', 'dropdown')):
            _final_ui_pattern = 'dropdown'
        elif any(kw in _rl for kw in ('弹窗', '对话框', '模态框', 'modal', 'dialog')):
            _final_ui_pattern = 'modal'
        elif any(kw in _rl for kw in ('表格', '列表', '行', '记录')):
            _final_ui_pattern = 'table_row'
    if not _final_context:
        if any(kw in _rl for kw in ('弹窗中', '对话框中', '模态框中')):
            _final_context = 'modal'
        elif any(kw in _rl for kw in ('下拉', '下拉框')):
            _final_context = 'dropdown'

    # ── 回退：无「」标记 + 无动词匹配 → 不可解析，跳过 ──
    # 不再将整句描述当成 CLICK 目标（"使用page.go_back()返回工作台" 不是 UI 元素）
    logger.warning(f"[StepParser] 步骤无法解析（无「」标记且无动词匹配）: {raw_action[:80]}")
    return GuidedStep(
        seq=seq,
        action_type='',           # 空 action_type → 探索时跳过
        target_text='',
        role_hint='',
        expected_result=expected,
        raw_action=raw_action,
        source='regex',
    )


def parse_steps(test_steps, llm_service=None, config=None) -> List[GuidedStep]:
    """解析测试步骤列表。

    Args:
        test_steps: JSON 数组、JSON 字符串、或 dict 列表
        llm_service: 可选的 LLM 服务（用于无法解析的步骤回退）
        config: 可选的 ExplorationConfig（用于自定义动词/角色/上下文模式）

    Returns:
        GuidedStep 列表
    """
    import json

    # 字符串 → JSON
    if isinstance(test_steps, str):
        try:
            test_steps = json.loads(test_steps)
        except (json.JSONDecodeError, TypeError):
            # 单条纯文本步骤
            return [parse_single_step({'action': test_steps}, 1)]

    if not isinstance(test_steps, list):
        return []

    if not test_steps:
        return []

    # 逐条解析
    guided_steps = []
    _unparsed_raw = []  # 收集正则解析失败的步骤
    for i, step in enumerate(test_steps):
        gs = parse_single_step(step, i + 1, config=config)

        # 跳过空步骤（但记录下来，用于 LLM 回退）
        if not gs.target_text and not gs.action_type:
            _raw = step.get('action', '') if isinstance(step, dict) else str(step)
            if _raw.strip():
                _unparsed_raw.append({"seq": i + 1, "raw": _raw.strip()})
            continue

        # ── 指代词目标 → 交 LLM 上下文推断（2026-08-25）──
        # 正则命中但 target 是纯指代/计数词（「该条预警」「第一条记录」）——页面无此
        # 文本，探索必 not_found；LLM 有全量步骤上下文，可从「」标记对象推断具体元素名。
        if gs.source in ('regex', 'regex_fallback') and gs.target_text:
            if _DEICTIC_RE.match(gs.target_text.strip()):
                _raw = step.get('action', '') if isinstance(step, dict) else str(step)
                if _raw.strip():
                    _unparsed_raw.append({"seq": i + 1, "raw": _raw.strip()})
                    logger.debug(f"[StepParser] 指代目标 '{gs.target_text}' → 交 LLM 推断: {_raw[:60]}")
                    continue

        guided_steps.append(gs)

    # LLM 回退：正则解析不了的步骤，用 LLM 理解自然语言描述
    if llm_service and _unparsed_raw:
        logger.info(f"[StepParser] 正则解析后 {len(_unparsed_raw)} 条未匹配，启用 LLM 回退")
        _llm_parsed = _llm_parse_natural_language(_unparsed_raw, llm_service)
        for _gs in _llm_parsed:
            if _gs.action_type and _gs.target_text:
                # 按 seq 归位插入（2026-08-25 复查修复：此前统一 append 末尾，指代/
                # 回退步骤在探索执行时被排到序列最后——步骤驱动探索顺序执行、页面状态
                # 相关，「返回工作台」先于「点击该条预警」执行会在错误页面状态下探索）
                _ins_at = len(guided_steps)
                _seq = getattr(_gs, 'seq', None)
                if _seq is not None:
                    for _i, _g in enumerate(guided_steps):
                        if getattr(_g, 'seq', 0) >= _seq:
                            _ins_at = _i
                            break
                guided_steps.insert(_ins_at, _gs)
                logger.info(f"[StepParser] LLM 解析: '{_gs.raw_action[:50]}' → {_gs.action_type}/{_gs.target_text}")

    return guided_steps


def _llm_parse_natural_language(steps_raw: List[dict], llm_service) -> List[GuidedStep]:
    """用 LLM 解析自然语言描述的测试步骤。

    Args:
        steps_raw: [{"seq": 1, "raw": "打开系统并进入到登录页面"}, ...]
        llm_service: LLMService 实例

    Returns:
        GuidedStep 列表（LLM 解析出来的）
    """
    steps_text = "\n".join(f"{s['seq']}. {s['raw']}" for s in steps_raw)
    prompt = f"""你是 UI 自动化测试专家。请分析以下用自然语言描述的测试步骤，逐条提取其中的可交互动作。

对于每条步骤，输出：action（动作类型）、target（操作目标元素名）、value（要填入/选择的值）、role（元素角色）。

动作类型（action）只能是：
- click: 点击按钮/链接/图标
- fill: 在输入框中填写内容
- select: 在下拉框中选择选项
- navigate: 跳转/打开页面
- validate: 验证/断言/检查（非交互步骤，不需要 target）

规则：
1. target 只取页面上真实可见的 UI 元素文本（≤6字），不含描述词（如"按钮""输入框""卡片"）
2. 如果有多个动作在一句中，只提取第一个可执行的动作
3. 条件描述（"若...则..."）提取"则"后面的动作，target 要具体
4. 纯描述/条件判断无具体动作的，返回 action=""（跳过）
5. value 在 fill 时填输入值（如手机号/密码），在 select 时填选项（如"第一个"）
6. 前面的序号去掉
7. 指代词推断（2026-08-25）：步骤中的"该条/该/此/当前/这条/第一条/最后一条/所选"等
   指代词指代前序步骤中操作的对象（通常是「」标记的元素或前文已出现的元素名）。
   target 必须输出**被指代对象的具体 UI 元素名**，不能输出指代词本身！
   例：前面步骤是「查看「佩戴预警 (0)」卡片」，本步骤「点击该条预警」→
   target="佩戴预警"（去计数括号、去"卡片"描述词）。
   例：前面出现「新增」按钮，本步骤「点击该按钮」→ target="新增"。
8. "记录/获取/捕获/读取 XX 的 YY"（如"记录第一条预警的患者姓名"）→ YY 是页面展示的
   数据字段（如"患者姓名"），target=YY；若 YY 明显是变量语义而非页面文本，
   或无法推断出真实元素，返回 action=""（跳过，不编造 target）
9. 无法从上下文推断出页面真实元素的，返回 action=""（跳过），绝不输出指代词或描述句

待解析步骤：
{steps_text}

输出严格 JSON 数组（不含 markdown 代码块标记），每条对应一个步骤：
[{{"seq":序号,"action":"click|fill|select|navigate|validate|","target":"元素名","value":"值或空","role":"button|textbox|combobox|link|tab|"}}]"""

    try:
        import json as _json
        response = llm_service.call_llm(
            prompt=prompt,
            system_prompt="你是UI自动化测试专家。分析自然语言测试步骤，提取UI元素名和操作类型。只输出JSON数组。",
            max_tokens=llm_service.get_scaled_max_tokens(),
        )
        # 提取 JSON 数组（贪婪匹配：非贪婪 `\[.*?\]` 在 JSON 字符串内含 `]` 时提前截断，
        # json.loads 失败 → 整批步骤丢失；2026-08-25 复查修复）
        json_match = re.search(r'\[.*\]', response or '', re.DOTALL)
        if not json_match:
            logger.warning(f"[StepParser] LLM 响应未找到 JSON 数组: {(response or '')[:200]}")
            return []
        parsed = _json.loads(json_match.group(0))
    except Exception as e:
        logger.error(f"[StepParser] LLM 解析失败: {e}")
        return []

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        action = (item.get('action') or '').strip().lower()
        target = (item.get('target') or '').strip()
        value = (item.get('value') or '').strip()
        role = (item.get('role') or '').strip()
        try:
            # 容错：LLM 可能输出 "1.0"/"1.0 " 等非整数形态，int() 抛错会整批回退丢失
            seq = int(float(str(item.get('seq', 0)).strip()))
        except (ValueError, TypeError):
            seq = 0

        # 标准化 action 类型
        _action_map = {
            'click': 'click', '单击': 'click', '点击': 'click', 'tap': 'click',
            'fill': 'fill', '输入': 'fill', '填写': 'fill', '填入': 'fill', 'type': 'fill', 'input': 'fill',
            'select': 'select', '选择': 'select', '下拉': 'select', 'choose': 'select',
            'navigate': 'navigate', '打开': 'navigate', '进入': 'navigate', '跳转': 'navigate', '访问': 'navigate', 'goto': 'navigate',
            'validate': 'validate', '验证': 'validate', '断言': 'validate', '检查': 'validate', '确认': 'validate',
        }
        action_type = _action_map.get(action, '')

        # 跳过空动作（纯描述/条件判断）
        if not action_type:
            continue

        results.append(GuidedStep(
            seq=seq or len(results) + 1,
            action_type=action_type,
            target_text=target,
            role_hint=role,
            fill_value=value if action_type == 'fill' else '',
            select_option=value if action_type == 'select' else '',
            raw_action=steps_raw[seq - 1]['raw'] if 0 < seq <= len(steps_raw) else '',
            source='llm',
        ))

    return results


def _llm_refine_steps(unclear: List[GuidedStep], all_steps: List[GuidedStep],
                      llm_service) -> List[GuidedStep]:
    """用 LLM 修正角色提示不明确或目标文本过长的步骤。

    让 LLM 理解自然语言用例步骤，分离「操作对象」和「操作值」。
    """
    prompt_parts = [
        "你是 UI 自动化测试专家。请分析以下测试步骤，提取其中可交互的 UI 元素。",
        "",
        "核心规则：target 和 value 必须分离！",
        "- target = 页面上真实可见的 UI 元素文本（不含描述词！），如\"筛选\"\"搜索\"\"保存\"\"室早\"",
        "- value  = 要填入或选中的值，如\"≥30\"\"张三\"\"内科\"",
        "- 描述词（不要包含在 target 中）：卡片、按钮、输入框、下拉框、链接、图标、菜单、弹窗、页面",
        "",
        "关键约定——用「」包裹真正的 UI 元素名，用\"\"包裹操作值：",
        "- 举例：\"筛选≥30\" → target=\"筛选\", value=\"≥30\"（\"筛选\"是元素，\"≥30\"是值）",
        "- 举例：\"室早卡片跳转\" → target=\"室早\"（\"卡片\"是描述词，不取！）",
        "- 举例：\"选择科室为内科\" → target=\"科室\", value=\"内科\"",
        "- 举例：\"填写患者姓名为张三\" → target=\"患者姓名\", value=\"张三\"",
        "- 举例：\"点击新增按钮\" → target=\"新增\"（\"按钮\"是描述词）",
        "- 举例：\"筛选'未发送'\" → target=\"筛选\", value=\"未发送\"",
        "",
        "步骤类型判断：",
        "- 点击某元素 → action=click, target=元素名(≤6字)",
        "- 填写/输入 → action=fill, target=输入框名, value=填充值",
        "- 选择/筛选 → action=select, target=下拉框名, value=选项值",
        "- 纯验证/断言（描述的是\"检查/确认\"而非\"操作\"）→ action=validate, target可为空",
        "",
        "待解析步骤:",
    ]
    for gs in unclear:
        prompt_parts.append(f"  - {gs.raw_action}")
    prompt_parts.append("")
    prompt_parts.append('输出严格 JSON（不含 markdown 代码块）:')
    prompt_parts.append('[{"target":"元素名(纯UI文本,≤6字,不含描述词)","value":"值或空","role":"button|textbox|combobox|link|tab","action":"click|fill|select|validate"}]')

    prompt = '\n'.join(prompt_parts)
    response = llm_service.call_llm(
        prompt=prompt,
        system_prompt="你是UI自动化测试专家。分析测试步骤，提取UI元素名和操作类型。只输出JSON。",
        max_tokens=llm_service.get_scaled_max_tokens(0.1, 8000),
    )

    import json
    try:
        # 提取 JSON
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if json_match:
            refined = json.loads(json_match.group(0))
            for i, gs in enumerate(unclear):
                if i < len(refined):
                    r = refined[i]
                    gs.target_text = r.get('target', gs.target_text)
                    gs.role_hint = r.get('role', gs.role_hint)
                    gs.action_type = r.get('action', gs.action_type)
                    # LLM 返回的 value → 根据 action 类型填入对应字段
                    val = r.get('value', '')
                    if val:
                        if gs.action_type == 'fill':
                            gs.fill_value = val
                        elif gs.action_type == 'select':
                            gs.select_option = val
                    gs.source = 'llm'
    except Exception:
        pass

    return all_steps


def steps_are_parseable(test_steps) -> bool:
    """快速检查步骤是否可解析（至少 1 条有效步骤）。"""
    guided = parse_steps(test_steps)
    return len(guided) > 0 and any(
        gs.target_text and gs.action_type for gs in guided
    )
