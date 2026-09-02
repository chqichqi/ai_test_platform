"""
POM (Page Object Model) 代码生成器

从知识图谱 / 探索结果数据中生成 Playwright sync Page Object 类。
可被以下模块复用：
- mcp_exploration_agent.py (探索阶段 Phase 4)
- web_ui_conversion_agent.py (功能用例转化)
- web_ui_test_service.py (规则引擎转化)
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── POM 生成系统 Prompt ──
POM_GENERATION_SYSTEM_PROMPT = """你是Playwright Python专家。根据探索数据生成Page Object代码。

## 硬约束
- 使用 `from playwright.sync_api import Page` (同步模式)
- 选择器只来自探索数据，禁止编造
- 每个页面一个类，类名 = 页面名称（英文 PascalCase）
- `__init__(self, page: Page)` 中声明所有元素定位器
- 每个可操作元素至少一个方法
- 导航方法用 `page.wait_for_url()` 等待跳转完成
- 导航到其他页面的方法返回目标页面对象（链式导航）
- 方法参数使用有意义的名称（如 `name: str`, `value: str`）
- 每个方法添加 docstring（中文）
- 只输出 Python 代码，不要 markdown 代码块标记
"""

POM_GENERATION_USER_PROMPT = """## 探索数据
```json
{exploration_data}
```

## 页面信息
- 起始URL: {base_url}
- 发现的页面: {pages_summary}
- 导航菜单: {menus_summary}

请生成所有页面的 Page Object 类代码。"""


def generate_pom_classes(
    exploration_data: Dict[str, Any],
    base_url: str = "http://localhost:3000",
    llm_service: Optional[Any] = None,
    cancel_check=None,   # callable → bool
) -> Dict[str, str]:
    """
    从探索数据生成 POM 类代码。

    Args:
        exploration_data: 探索结果数据，包含 pages/elements/flows/dropdowns/tables/modals
        base_url: 目标系统基础 URL
        llm_service: LLM 服务实例 (LLMService)，为 None 时使用规则引擎回退

    Returns:
        {"PageName": "class PageName:\\n    def __init__(...)...", ...}
    """
    if llm_service:
        return _generate_with_llm(exploration_data, base_url, llm_service, cancel_check)
    else:
        return _generate_with_rules(exploration_data, base_url)


def _generate_with_llm(
    data: Dict[str, Any],
    base_url: str,
    llm_service: Any,
    cancel_check=None,
) -> Dict[str, str]:
    """LLM 驱动的 POM 生成"""
    pages = _extract_pages(data)
    menus = data.get("menus", data.get("nav_items", []))

    pages_summary = ", ".join(
        f"{p.get('title', p.get('url', '?'))}" for p in pages[:20]
    )
    menus_summary = ", ".join(
        f"{m.get('name', m.get('label', '?'))}" for m in (menus or [])[:10]
    )

    ctx = json.dumps(data, ensure_ascii=False, indent=2)[:12000]
    user_prompt = POM_GENERATION_USER_PROMPT.format(
        exploration_data=ctx,
        base_url=base_url,
        pages_summary=pages_summary or "无",
        menus_summary=menus_summary or "无",
    )

    try:
        code = llm_service.call_llm(
            prompt=user_prompt,
            system_prompt=POM_GENERATION_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=llm_service.get_scaled_max_tokens(),
            cancel_check=cancel_check,
        )
        if code:
            code = code.strip()
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:]) if lines[1:] else code
            if code.endswith("```"):
                code = code[:-3].strip()
    except Exception as e:
        logger.warning(f"LLM POM 生成失败，回退到规则引擎: {e}")
        code = None

    if not code:
        return _generate_with_rules(data, base_url)

    # 解析 LLM 输出：按 class 定义拆分
    return _parse_pom_classes(code)


def _generate_with_rules(
    data: Dict[str, Any],
    base_url: str,
) -> Dict[str, str]:
    """规则引擎回退：从元素数据机械生成 POM"""
    pages = _extract_pages(data)
    elements_by_page = _group_elements_by_page(data)

    result = {}
    for page in pages:
        page_url = page.get("url", "/")
        page_title = page.get("title", _url_to_class_name(page_url))
        class_name = _url_to_class_name(page_title or page_url)
        page_elements = elements_by_page.get(page_url, []) or elements_by_page.get(page_title, [])

        result[class_name] = _build_pom_class(class_name, page_title, page_url, page_elements, base_url)

    # 如果没有页面数据，至少生成一个入口页面
    if not result:
        elements = data.get("elements", [])
        all_elements = []
        for e in (elements if isinstance(elements, list) else []):
            if isinstance(e, dict):
                all_elements.append(e)
        result["MainPage"] = _build_pom_class(
            "MainPage", "主页", "/", all_elements, base_url
        )

    return result


def _extract_pages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从探索数据中提取页面列表（统一转为 [{"url":..., "title":...}] 格式）"""
    pages = data.get("pages", [])
    if pages:
        if isinstance(pages, list):
            # 兼容纯字符串 URL 列表（缓存 KG 可能存成这种格式）
            normalized = []
            for p in pages:
                if isinstance(p, str):
                    normalized.append({"url": p, "title": p.rsplit("/", 1)[-1]})
                elif isinstance(p, dict):
                    url = p.get("page_url", p.get("url", ""))
                    title = p.get("page_title", p.get("title", url))
                    normalized.append({"url": url, "title": title})
            return normalized
        return list(pages)

    # 从 elements 中收集页面
    elements = data.get("elements", [])
    seen = set()
    result = []
    for elem in (elements if isinstance(elements, list) else []):
        if isinstance(elem, dict):
            url = elem.get("page_url", "")
            if url and url not in seen:
                seen.add(url)
                result.append({"url": url, "title": elem.get("page_title", url)})
    return result


def _group_elements_by_page(data: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """按页面分组元素"""
    groups: Dict[str, List[Dict]] = {}
    elements = data.get("elements", [])
    for elem in (elements if isinstance(elements, list) else []):
        if isinstance(elem, dict):
            page = elem.get("page_url", elem.get("page", "/"))
            if page not in groups:
                groups[page] = []
            groups[page].append(elem)

    # 加上 pages[].elements
    for page in data.get("pages", []):
        if isinstance(page, dict):
            url = page.get("url", "")
            if url and url not in groups:
                groups[url] = []
            for elem in page.get("elements", []):
                if isinstance(elem, dict):
                    groups.setdefault(url, []).append(elem)

    return groups


def _build_pom_class(
    class_name: str,
    page_title: str,
    page_url: str,
    elements: List[Dict],
    base_url: str,
) -> str:
    """机械生成一个 POM 类"""

    lines = [
        "from playwright.sync_api import Page",
        "",
        "",
        f"class {class_name}:",
        f'    """{page_title or class_name} 页面 ({page_url})"""',
        "",
        "    def __init__(self, page: Page):",
        "        self.page = page",
    ]

    # 声明元素定位器
    locator_names = set()
    for elem in elements:
        name = elem.get("name", elem.get("element_name", ""))
        selector = (
            elem.get("selector")
            or elem.get("primary_locator")
            or elem.get("css_selector")
            or ""
        )
        elem_type = elem.get("type", elem.get("element_type", "unknown"))
        # clickable 语义：探索如实记录不可点击元素（heading/static/table 等）——
        # 不为其生成 click 方法（POM 生成侧防线，与执行守卫/转化改写同源）
        if elem.get("clickable") is False or elem.get("role") in ("heading", "static", "paragraph", "table"):
            continue

        if not name or not selector:
            continue

        var_name = _to_snake_case(name)
        if var_name in locator_names:
            continue
        locator_names.add(var_name)

        # 清理选择器中的引号
        safe_selector = selector.replace('"', '\\"')
        lines.append(f'        self.{var_name} = page.locator("{safe_selector}")')

    lines.append("")
    lines.append("    def navigate(self, url: str = None) -> None:")
    # 历史缺陷：base_url.rstrip('/') + page_url 对 hash 路由项目拼出错误地址
    # （base_url=https://host/#/login + /workpanel → #/login/workpanel）→ 与生成/执行侧同源规范化
    from app.core.services.step_runner import _normalize_page_url
    full_url = _normalize_page_url(page_url, base_url) or base_url
    lines.append(f'        """导航到 {page_title or class_name} 页面"""')
    lines.append(f'        target = url or "{full_url}"')
    # F32 修复（2026-08-25）：networkidle 对带 WebSocket/长轮询的 SPA 永不满足
    # （默认 30s 超时）→ goto 卡死拖垮整条用例；domcontentloaded 与执行侧
    # step_runner._do_goto 的 else 分支同源（探索阶段也是 domcontentloaded）
    lines.append('        self.page.goto(target, wait_until="domcontentloaded", timeout=15000)')
    lines.append("")

    # 为每个元素生成 click/fill 方法
    for elem in elements:
        name = elem.get("name", elem.get("element_name", ""))
        selector = (
            elem.get("selector")
            or elem.get("primary_locator")
            or elem.get("css_selector")
            or ""
        )
        elem_type = elem.get("type", elem.get("element_type", "unknown"))
        # clickable 语义：探索如实记录不可点击元素（heading/static/table 等）——
        # 不为其生成 click 方法（POM 生成侧防线，与执行守卫/转化改写同源）
        if elem.get("clickable") is False or elem.get("role") in ("heading", "static", "paragraph", "table"):
            continue
        var_name = _to_snake_case(name)

        if not name or var_name not in locator_names:
            continue

        if elem_type in ("button", "link", "clickable"):
            lines.append(f"    def click_{var_name}(self) -> None:")
            lines.append(f'        """点击 {name}"""')
            lines.append(f"        self.{var_name}.click()")
            lines.append("")
        elif elem_type in ("input", "textbox", "textarea"):
            lines.append(f"    def fill_{var_name}(self, value: str) -> None:")
            lines.append(f'        """在 {name} 中输入内容"""')
            lines.append(f"        self.{var_name}.fill(value)")
            lines.append("")
        elif elem_type in ("dropdown", "select"):
            lines.append(f"    def select_{var_name}(self, option: str) -> None:")
            lines.append(f'        """在 {name} 中选择选项"""')
            lines.append(f"        self.{var_name}.click()")
            lines.append(
                '        self.page.locator(".ant-select-dropdown:visible '
                f'.ant-select-item").filter(has_text=option).click()'
            )
            lines.append("")

    return "\n".join(lines)


def _parse_pom_classes(code: str) -> Dict[str, str]:
    """解析 LLM 输出的多类 POM 代码，按类名拆分"""
    # 匹配 class XxxPage: 或 class Xxx:
    pattern = re.compile(r"^class\s+(\w+)\s*(?:\([^)]*\))?\s*:", re.MULTILINE)
    matches = list(pattern.finditer(code))

    if not matches:
        return {"GeneratedPage": code}

    result = {}
    for i, match in enumerate(matches):
        class_name = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(code)
        result[class_name] = code[start:end].strip()

    return result


def _url_to_class_name(url_or_title: str) -> str:
    """将 URL 或页面标题转为 PascalCase 类名"""
    # 去掉协议和域名
    name = re.sub(r"https?://[^/]*", "", url_or_title)
    # 去掉查询参数
    name = name.split("?")[0]
    # 去掉首尾斜杠
    name = name.strip("/#")
    # 分割路径
    parts = re.split(r"[/\-_#\s]", name)
    # 转为 PascalCase
    words = []
    for part in parts:
        if part:
            words.append(part[0].upper() + part[1:].lower() if len(part) > 1 else part.upper())
    if not words:
        words = ["MainPage"]
    result = "".join(words)
    # 确保以 Page 结尾
    if not result.endswith("Page"):
        result += "Page"
    return result


def _to_snake_case(name: str) -> str:
    """将中文/英文名称转为 snake_case 变量名"""
    # 尝试提取英文部分
    english = re.sub(r"[^\w\s\-_]", "", name)
    if not english.strip():
        # 纯中文：用拼音简化
        import hashlib
        return "el_" + hashlib.md5(name.encode()).hexdigest()[:6]

    # 转为 snake_case
    result = re.sub(r"([A-Z])", r"_\1", english).lower()
    result = re.sub(r"[\s\-]+", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or "element"
