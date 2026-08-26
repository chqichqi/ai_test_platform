"""
LLM 驱动探索器 — 使用 Playwright 无障碍树（MCP browser_snapshot 协议风格），
LLM 通过 ref 精确点击，不再靠 text_content 子串匹配。
"""

import asyncio, json
from typing import Dict, Any, List, Optional
from app.core.logger import logger
from app.core.services.llm_service import LLMService


# ── MCP 风格工具定义 ──
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "获取当前页面的无障碍树快照。返回每个可交互元素的 ref、role、name，LLM 据此决定操作",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "点击由 browser_snapshot 返回的 ref 指定的元素",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "browser_snapshot 返回的元素 ref 编号"},
                    "description": {"type": "string", "description": "点击的元素描述（用于日志）"},
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate_back",
            "description": "返回上一页",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "滚到底部再回顶部，加载全部懒加载内容",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_finish",
            "description": "探索完成",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "探索结果摘要"},
                },
                "required": ["summary"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是浏览器自动化专家。用 browser_snapshot 看页面 → browser_click 点卡片 → browser_navigate_back 返回。

## 流程
1. browser_scroll 加载全页
2. browser_snapshot 获取元素列表（每个有 ref/role/name）
3. 对有 name 的 link/button 逐个 browser_click(ref)
4. 点击后立刻 browser_navigate_back 返回
5. 全部点完 browser_finish

## 规则
- 只点 role=link 或 button 的元素（card 通常渲染为 link/button）
- name 为空或危险词（退出/注销/删除）的跳过
- 子页面只记录 URL 立刻返回，不点子页面元素
- 必须点完 snapshot 里每个有效的才 finish
"""


class LLMExplorer:
    """LLM 驱动的浏览器探索器（无障碍树 + ref 精确点击）"""

    def __init__(self, page, llm_service: LLMService):
        self.page = page
        self.llm = llm_service
        self._ref_map: Dict[str, Any] = {}  # ref → locator
        self.explored: list = []
        self.pages_visited: list = []
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.max_steps = 60

    async def explore(self, base_url: str, module_name: str = "当前模块") -> Dict[str, Any]:
        self.pages_visited.append(self.page.url)
        self.messages.append({
            "role": "user",
            "content": f"开始探索：{module_name}。当前页面 {self.page.url}",
        })

        for _ in range(self.max_steps):
            response = await self._call_llm()
            if not response:
                break

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                if "finish" in (response.get("content") or "").lower():
                    break
                continue

            self.messages.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = json.loads(func.get("arguments", "{}"))
                result = await self._execute(name, args)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                })
                if name == "browser_finish":
                    return {
                        "pages_visited": self.pages_visited,
                        "explored": self.explored,
                        "summary": args.get("summary", ""),
                        "llm_driven": True,
                    }

        return {
            "pages_visited": self.pages_visited,
            "explored": self.explored,
            "summary": f"探索了 {len(self.explored)} 个元素, {len(self.pages_visited)} 个页面",
            "llm_driven": True,
        }

    # ── 工具实现 ──

    async def _execute(self, name: str, args: dict) -> dict:
        try:
            if name == "browser_snapshot":
                return await self._snapshot()

            elif name == "browser_click":
                ref = args.get("ref", "")
                desc = args.get("description", ref)
                if not ref or ref not in self._ref_map:
                    return {"error": f"ref '{ref}' 无效，请先调 browser_snapshot"}
                loc = self._ref_map[ref]

                url_before = self.page.url
                try:
                    await loc.click(timeout=3000)
                except Exception as e:
                    return {"error": f"点击失败: {e}"}

                try:
                    await self.page.wait_for_url(lambda u: u != url_before, timeout=5000)
                except Exception:
                    pass

                new_url = self.page.url
                navigated = new_url != url_before
                if navigated:
                    self.pages_visited.append(new_url)
                dup = any(e["url"] == new_url and navigated for e in self.explored)
                self.explored.append({"text": desc, "navigated": navigated, "url": new_url})
                return {"clicked": desc, "navigated": navigated, "url": new_url,
                        "duplicate": dup}

            elif name == "browser_navigate_back":
                try:
                    await self.page.go_back()
                    await self.page.wait_for_load_state("networkidle", timeout=8000)
                    return {"back_to": self.page.url}
                except Exception as e:
                    return {"error": str(e)}

            elif name == "browser_scroll":
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.8)
                await self.page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(0.4)
                return {"scrolled": True}

            elif name == "browser_finish":
                return {"done": True}

            return {"error": f"Unknown: {name}"}
        except Exception as e:
            return {"error": str(e)}

    async def _snapshot(self) -> dict:
        """获取无障碍树快照——只返回可交互的 link/button，带唯一 ref"""
        self._ref_map.clear()
        elements = []

        # 使用 Playwright 的 role locator 获取所有可交互元素
        for role in ["link", "button"]:
            locs = self.page.get_by_role(role)
            count = await locs.count()
            for i in range(min(count, 100)):
                try:
                    loc = locs.nth(i)
                    if not await loc.is_visible():
                        continue
                    name = (await loc.text_content() or "").strip()[:60]
                    if not name:
                        continue
                    if any(d in name for d in ["退出", "注销", "删除"]):
                        continue
                    ref = f"{role[0]}{len(elements)}"
                    self._ref_map[ref] = loc
                    elements.append({"ref": ref, "role": role, "name": name})
                except Exception:
                    pass

        return {"url": self.page.url, "elements": elements}

    # ── LLM 调用 ──

    async def _call_llm(self) -> Optional[dict]:
        try:
            import requests
            from sqlalchemy import text as sql_text

            row = self.llm.db.execute(sql_text(
                "SELECT base_url, api_key, model FROM llm_configs WHERE is_active = 1 LIMIT 1"
            )).fetchone()
            if not row:
                return None

            api_url = row[0].rstrip('/')
            if not api_url.endswith('/chat/completions'):
                api_url = f"{api_url}/v1/chat/completions" if '/v1' not in api_url else f"{api_url}/chat/completions"

            payload = {
                "model": row[2],
                "messages": self.messages[-30:],  # 保留最近 30 条
                "tools": TOOLS,
                "temperature": 0,
                "max_tokens": 4000,
            }
            resp = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {row[1]}", "Content-Type": "application/json"},
                json=payload, timeout=120,
            )
            if resp.status_code != 200:
                logger.error(f"[LLMExplorer] API {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()["choices"][0]["message"]
        except Exception as e:
            logger.error(f"[LLMExplorer] LLM: {e}")
            return None
