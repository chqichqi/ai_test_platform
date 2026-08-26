# -*- coding: utf-8 -*-
"""
探索期 API 接口捕获与用例生成（ApiFlowCapture）。

在探索浏览器 context 上监听 XHR/fetch 请求，把探索过程中真实调用的 API 接口
捕获下来，生成 API 用例保存到 api_test_cases，供后续直接执行测试。

设计要点：
- 捕获：仅 xhr/fetch；排除登录接口（api_auth.login_url）与静态资源
- 安全：Authorization/Cookie 原文与 password/secret/token 类字段一律不落库——
  只记录「鉴权形态」（Bearer 注入头/前缀），执行时由项目级 api_auth 实时取 token
  替换占位符 {{auth_token}}（见 api_tests._execute_single_case_with_cache）
- 生成（与 Swagger 导入生成并存，共用 api_test_cases 表）：
  - 成功接口（2xx）→ normal 用例（expected_status=实际码 + 响应体字段断言）
  - 主动构造异常变体（缺参数/类型错误/不存在资源/无鉴权）→ error 用例
    （4xx 区间断言——执行器 http_status 规则 value 支持列表）
  - 探索期真实发生的 4xx/5xx 失败**不固化**（一过性失败无复现价值）
- 去重：按 (project_id, method, path) 查库，已存在（含 Swagger 生成）则跳过
- 来源区分：endpoint_id 为空 + tags 含 "exploration" + 名称前缀 [探索]
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from app.core.services.api_assert_executor import ApiAssertExecutor

logger = logging.getLogger(__name__)

# 敏感 key（headers/请求体里这些字段的值不落库——明文凭证红线）
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)password|passwd|secret|token|apikey|api_key|authorization|cookie"
)
# 数字路径段（去重键用：/orders/123 → /orders/{id}）
_PATH_SEG_RE = re.compile(r"/\d+")
# 「不存在资源」变体用的必不存在 ID（数字参数替换目标，生成后执行 4xx）
_NOT_FOUND_ID = 999999999
# 非 JSON body 原文保留截断上限（字符数；防巨表单撑爆库，非业务值）
_RAW_BODY_MAX_CHARS = 10000


def _sanitize(value: Any) -> Any:
    """递归脱敏：key 命中敏感词（password/token 等）的值一律替换为占位符。

    仅对 dict 的 key 名判断（不猜值），保留业务数据结构供用例直接运行。
    """
    if isinstance(value, dict):
        return {
            k: ("***" if _SENSITIVE_KEY_RE.search(k) else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _normalize_path(path: str) -> str:
    """数字路径段 → {id}（去重键用；存储仍保留实际路径便于直接运行）。"""
    return _PATH_SEG_RE.sub("/{id}", path or "")


def _is_biz_failure(response_body: Any) -> bool:
    """HTTP 2xx 但业务码非成功的响应判定（A2 修复 2026-08-25）。

    捕获的 HTTP 200 + 业务失败码（如 code=50001）若固化为 normal 用例，
    _build_assert_rules 会把失败码写进 status_eq/json_value_eq 断言 → 执行时
    成功响应（code=0）断言必然失败（用户反馈「探索生成的 API 用例不对」的根因之一）。
    判定源：
      - success 布尔字段：False/失败词 → 业务失败
      - 顶层 code 字段：值不在通用成功码集合（api_assert_executor.COMMON_SUCCESS_CODES
        同源）→ 业务失败（code 语义就是业务码，非成功值必失败）
      - 顶层 status 字段：int 成功码集合判定；字符串只认明确失败词
        （error/fail/failed/false——"active" 等实体状态不是业务码，不判定，防误杀）
    仅判定顶层（失败码约定在顶层；嵌套业务对象字段不参与，防误杀）。
    """
    if not isinstance(response_body, dict):
        return False
    success_vals = set(ApiAssertExecutor.COMMON_SUCCESS_CODES)
    success_vals |= {"0", "200", "true", "True"}
    # success 布尔语义优先（bool 是明确成功/失败信号；不参与码集合比较）
    sv = response_body.get("success")
    if isinstance(sv, bool):
        return not sv
    if isinstance(sv, str) and sv.lower() in ("false", "0", "error", "fail", "failed"):
        return True
    # HTTP 成功语义 status 集合（F26 修复 2026-08-25）：int status 此前只豁免 200，
    # 201/202/204（created/accepted/no content）等明确成功码被误判业务失败 →
    # 捕获响应被跳过，正常接口不生成用例
    _HTTP_OK_CODES = {200, 201, 202, 204}
    for f in ("code", "status"):
        v = response_body.get(f)
        if v is None or isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            iv = int(v)
            if f == "status" and (iv in _HTTP_OK_CODES or iv in success_vals):
                continue  # HTTP 语义 status（2xx 成功或业务码 0），非业务失败
            if iv not in success_vals:
                return True
        elif isinstance(v, str):
            low = v.lower()
            if low in ("error", "fail", "failed", "false"):
                return True
            if f == "code" and v not in success_vals and low not in (
                    "ok", "success", "successful", "0", "200"):
                return True
    return False


def _truncate_json(value: Any, max_bytes: int, depth: int = 0) -> Any:
    """响应体截断：超长字符串截断、超大列表截断、超大 dict 截断、超深递归截断
    （防巨响应撑爆库；max_bytes 用于调用方总字节兜底）。"""
    if depth > 6:
        return None
    if isinstance(value, dict):
        items = list(value.items())
        if len(items) > 30:
            items = items[:30] + [("...", None)]
        return {k: _truncate_json(v, max_bytes, depth + 1) for k, v in items}
    if isinstance(value, list):
        if len(value) > 20:
            value = value[:20] + ["..."]
        return [_truncate_json(v, max_bytes, depth + 1) for v in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "..."
    return value


def _collect_field_paths(body: Any, depth: int = 2, max_fields: int = 8) -> List[Dict[str, Any]]:
    """从实际响应体收集字段路径（a.b.c）及实际值，用于生成断言。

    业务码/消息类字段（code/status/message/msg/success）收集实际值 → 值断言；
    其余关键字段（data 及常规业务字段）只收集路径 → 存在性断言。
    """
    collected: List[Dict[str, Any]] = []

    def walk(node: Any, prefix: str, d: int) -> None:
        if not isinstance(node, dict) or d > depth or len(collected) >= max_fields:
            return
        for k, v in node.items():
            cur = f"{prefix}.{k}" if prefix else str(k)
            last = cur.rsplit(".", 1)[-1]  # 末段字段名：顶层与嵌套（data.code）同规则
            if last in ("code", "status", "message", "msg", "success"):
                # 业务码值断言（用户诉求：不只断 HTTP 状态，断实际返回的 code）
                if v is not None and isinstance(v, (int, float, str)):
                    collected.append({"field": cur, "value": v, "is_biz_code": True})
                else:
                    collected.append({"field": cur, "value": None, "is_biz_code": False})
            elif cur == "data" or last in ("total", "count", "id", "list", "rows", "records"):
                collected.append({"field": cur, "value": None, "is_biz_code": False})
            walk(v, cur, d + 1)
            if len(collected) >= max_fields:
                break

    walk(body, "", 0)
    return collected[:max_fields]


def _build_assert_rules(body: Any, expected_status: int) -> List[Dict[str, Any]]:
    """从捕获的实际响应体构建断言规则：HTTP 状态码 + 非空 + 业务码值断言 + 关键字段存在。

    - 顶层 code/status（常见 result.code）：status_eq 值断言（执行器取 body.code/status 比较）
    - 嵌套业务码（如 data.code）：json_value_eq 值断言（jsonpath 取值比较）
    - 其余关键字段：json_contains 存在性断言（skip_if_missing 兜底）
    """
    rules: List[Dict[str, Any]] = [
        {"type": "http_status", "value": [expected_status], "description": "HTTP状态码"}
    ]
    if body:
        rules.append({"type": "response_not_empty", "value": None, "description": "响应体非空"})
        for item in _collect_field_paths(body):
            field = item["field"]
            val = item["value"]
            if not item["is_biz_code"]:
                rules.append({
                    "type": "json_contains", "field": field, "value": None,
                    "skip_if_missing": True,
                    "description": f"响应包含字段 {field}",
                })
            elif field in ("code", "status") and val is not None:
                # 顶层业务码：值断言（= 探索期捕获的真实成功值，稳定可固化）
                rules.append({
                    "type": "status_eq", "field": field, "value": val,
                    "description": f"业务码 {field} == {val}",
                })
            elif val is not None and field.rsplit(".", 1)[-1] in ("code", "status"):
                # 嵌套业务码（data.code 等）：jsonpath 值断言——仅 code/status 可固化
                # （F27 修复 2026-08-25：message/msg 文本是动态内容，带时间戳/随机数/
                # 环境信息，固化值断言执行必败；success 标志同理只做存在性断言）
                rules.append({
                    "type": "json_value_eq", "field": field, "value": val,
                    "description": f"业务码 {field} == {val}",
                })
            else:
                # message/msg（动态文本）与 success 标志：仅存在性断言，不固化值
                rules.append({
                    "type": "json_contains", "field": field, "value": None,
                    "skip_if_missing": True,
                    "description": f"响应包含字段 {field}",
                })
    return rules


def _build_test_steps(method: str, path: str, assert_rules: List[Dict[str, Any]],
                      variant_desc: str = "") -> List[Dict[str, Any]]:
    """构造 API 用例的测试步骤（请求 + 断言映射）——详情页「测试步骤及预期结果」。

    F28 修复（2026-08-25）：此前 test_steps 从未填充 → 详情页「测试步骤及预期结果」
    恒空白（用户反馈）。步骤语义与执行器（api_tests.py _execute_* 实际断言）一一对应，
    避免「写一套做一套」：http_status → 状态码断言，status_eq/json_value_eq → 字段值
    断言，json_contains → 字段存在性断言。
    """
    steps: List[Dict[str, Any]] = []
    if variant_desc:
        steps.append({
            "step": 1,
            "action": f"发送 {method} 请求 {path}（{variant_desc}）",
            "expected": "响应为 4xx 错误",
        })
    else:
        steps.append({
            "step": 1,
            "action": f"发送 {method} 请求 {path}",
            "expected": "请求成功，获取响应",
        })
    for i, rule in enumerate(assert_rules or [], start=2):
        rtype = rule.get("type")
        field = rule.get("field")
        value = rule.get("value")
        if rtype == "http_status":
            statuses = value if isinstance(value, list) else [value]
            status_text = " / ".join(str(s) for s in statuses)
            steps.append({"step": i, "action": f"断言 HTTP 状态码为 {status_text}",
                          "expected": f"响应状态码在预期区间 [{status_text}]"})
        elif rtype in ("status_eq", "json_value_eq"):
            steps.append({"step": i, "action": f"断言响应字段 {field} 等于 {value}",
                          "expected": f"字段 {field} == {value}"})
        elif rtype == "json_contains":
            steps.append({"step": i, "action": f"断言响应包含字段 {field}",
                          "expected": f"响应体包含字段 {field}"})
        elif rtype == "response_not_empty":
            steps.append({"step": i, "action": "断言响应体非空",
                          "expected": "响应体有内容"})
        else:
            text = rule.get("description") or f"断言 {rtype}"
            steps.append({"step": i, "action": text, "expected": text})
    return steps


class ApiFlowCapture:
    """探索浏览器 context 上的 API 接口捕获器。

    用法（探索链路挂点）：
        capture = ApiFlowCapture(ctx_sync, config, project_id, base_url, db)
        ...
        for module_name, steps in module_steps.items():
            capture.set_module(module_name)
            ... 探索该模块 ...
        stats = capture.flush_to_db(db, project_id, base_url)
    """

    def __init__(self, ctx, config, project_id: int, base_url: str = "", db=None):
        self._enabled = bool(getattr(config, "api_capture_enabled", True))
        self._per_module = int(getattr(config, "api_capture_per_module", 20))
        # 全局硬上限（A1 修复 2026-08-25）：per_module 是模块级配额，跨模块用全局计数
        # 会让第一个模块独占额度、其余模块捕获归零——全局上限只防单次会话病态海量
        self._max_total = int(getattr(config, "api_capture_max_total", 500))
        self._max_body = int(getattr(config, "api_capture_max_body_bytes", 50000))
        self._base_url = base_url or ""
        self._login_url = self._load_login_url(db, project_id)
        self._module_name = ""
        self._captured: List[Dict[str, Any]] = []
        self._by_key: Dict[tuple, int] = {}
        self._module_counts: Dict[str, int] = {}  # 每模块已捕获条数（配额按模块独立生效）
        # ctx 上的全局监听（探索全程所有页面）
        try:
            ctx.on("request", self._on_request)
            ctx.on("response", self._on_response)
            logger.info(
                f"[ApiFlowCapture] 已挂载网络监听 enabled={self._enabled} "
                f"per_module={self._per_module} login_url={self._login_url or '未配置'}"
            )
        except Exception as e:  # 监听挂载失败不阻断探索
            logger.warning(f"[ApiFlowCapture] 监听挂载失败: {e}")

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    @staticmethod
    def _load_login_url(db, project_id: int) -> str:
        """读取项目级 api_auth.login_url（登录接口排除用——登录请求体含密码不落库）。"""
        if not db or not project_id:
            return ""
        try:
            from app.core.models.project_ext import ProjectSetting
            ps = db.query(ProjectSetting).filter(
                ProjectSetting.project_id == project_id
            ).first()
            if not ps:
                return ""
            return ((ps.exploration_config or {}).get("api_auth") or {}).get("login_url", "") or ""
        except Exception:
            return ""

    def set_module(self, module_name: str) -> None:
        """标记当前探索模块（用于用例名称/描述/来源标签）。"""
        self._module_name = module_name or ""
        # 模块级配额计数：未出现过的新模块从 0 计（A1 修复——此前全局计数截断）
        self._module_counts.setdefault(self._module_name, 0)

    # ------------------------------------------------------------------
    # 捕获
    # ------------------------------------------------------------------

    def _on_request(self, request) -> None:
        """request 事件：记录接口信息（值必须在此回调内同步读取——事件后对象失效）。"""
        if not self._enabled:
            return
        try:
            if request.resource_type not in ("xhr", "fetch"):
                return
            url = request.url or ""
            if not url.startswith(("http://", "https://")):
                return
            if self._login_url and self._login_url in url:
                return  # 登录接口排除（其请求体含密码，也不应生成用例）

            parsed = urlparse(url)
            path = parsed.path or "/"
            key = (request.method, _normalize_path(path))
            if key in self._by_key:
                return  # 会话内已捕获（合并逻辑：保留首次）
            # 配额双闸（A1 修复 2026-08-25）：per_module 按当前模块独立计数——
            # 修复前用全局 len(self._captured) 比较，第一个模块满额后其余模块
            # 捕获归零（用户反馈「多模块探索只有首个模块有 API 用例」的根因）；
            # 全局 max_total 仅防单次会话病态海量
            if self._module_counts.get(self._module_name, 0) >= self._per_module:
                return
            if len(self._captured) >= self._max_total:
                logger.warning(f"[ApiFlowCapture] 会话捕获达全局上限 {self._max_total}，停止捕获")
                return

            # headers：剔除鉴权头原文（Authorization/Cookie 只记形态）
            raw_headers = dict(request.headers or {})
            auth_shape: Optional[Dict[str, str]] = None
            headers: Dict[str, str] = {}
            for k, v in raw_headers.items():
                kl = k.lower()
                if kl == "authorization":
                    auth_shape = {
                        "type": "bearer",
                        "header_name": "Authorization",
                        "prefix": v.split(" ")[0] + " " if " " in v else "",
                    }
                    continue
                if kl == "cookie":
                    if not auth_shape:
                        names = [c.split("=")[0] for c in v.split(";") if "=" in c]
                        auth_shape = {"type": "cookie", "names": names}
                    continue
                if _SENSITIVE_KEY_RE.search(kl):
                    continue
                headers[k] = v

            # query / body（脱敏：password/token 类字段不落明文）
            query_params = {
                k: v[0] if len(v) == 1 else v
                for k, v in parse_qs(parsed.query).items()
            } or None
            request_body = None
            if request.post_data:
                try:
                    request_body = _sanitize(json.loads(request.post_data))
                except Exception:
                    # 非 JSON body（x-www-form-urlencoded/纯文本/畸形 JSON）：保留原文
                    # 截断（A3 修复 2026-08-25——此前丢弃后生成的用例缺失 body，执行必失败），
                    # 执行侧按 Content-Type 走 data= 原样发送
                    _raw = request.post_data if isinstance(request.post_data, str) else None
                    request_body = _sanitize(_raw)[:_RAW_BODY_MAX_CHARS] if _raw else None

            rec = {
                "method": request.method,
                "path": path,
                "full_path": path + (f"?{parsed.query}" if parsed.query else ""),
                # API 基址真源：捕获请求的协议+域名（web.base_url 可能是 SPA 登录页地址，
                # 含 #/ hash 不能作 API 基址——2026-08-24 用户反馈用例执行必失败的根因）
                "origin": f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else "",
                "query_params": query_params,
                "request_body": request_body,
                "headers": headers,
                "auth_shape": auth_shape,
                "status": None,
                "response_body": None,
                "module": self._module_name,
            }
            self._by_key[key] = len(self._captured)
            self._captured.append(rec)
            self._module_counts[self._module_name] = (
                self._module_counts.get(self._module_name, 0) + 1
            )
        except Exception as e:
            logger.debug(f"[ApiFlowCapture] 捕获请求异常: {e}")

    def _on_response(self, response) -> None:
        """response 事件：补记实际状态码与响应体（供 expected_status 与断言）。"""
        if not self._enabled:
            return
        try:
            # A4 修复 2026-08-25：用原始请求 URL 匹配 key（response.url 是重定向后的
            # 最终地址，与 _on_request 记录的请求 key 不一致 → 重定向接口 status 永不落，
            # 全被判「未收到响应」跳过）
            parsed = urlparse(response.request.url or response.url or "")
            key = (response.request.method, _normalize_path(parsed.path or "/"))
            idx = self._by_key.get(key)
            if idx is None:
                return
            rec = self._captured[idx]
            rec["status"] = response.status
            try:
                body = response.json()
                if body is not None:
                    body = _truncate_json(body, self._max_body)
                    # 总字节兜底：递归截断后仍超限（病态宽响应）→ 不落响应体原文，
                    # 仅保留 status 断言（response_body 为 None 时 _build_assert_rules 自动降级）
                    try:
                        _size = len(json.dumps(body, ensure_ascii=False, default=str))
                    except Exception:
                        _size = self._max_body + 1
                    rec["response_body"] = body if _size <= self._max_body else None
            except Exception:
                pass  # 非 JSON 响应体不记录
        except Exception as e:
            logger.debug(f"[ApiFlowCapture] 捕获响应异常: {e}")

    # ------------------------------------------------------------------
    # 用例生成（落库）
    # ------------------------------------------------------------------

    def flush_to_db(self, db, project_id: int, base_url: str = "",
                    version_id: Optional[int] = None) -> Dict[str, int]:
        """把捕获的接口生成 API 用例落库（normal + error 变体）。

        version_id: 探索上下文版本（最近来源版本，与 KG 同语义）。前端 API 用例
                    列表按版本查询（/cases/version/{id}），不落 version_id 则
                    version_id=NULL 的探索用例在列表不可见（2026-08-23 用户反馈
                    「提示生成 40 条但列表看不到」的根因）。

        Returns: {"generated": n, "skipped": n, "errors": n}
        """
        if not self._enabled or not self._captured:
            return {"generated": 0, "skipped": 0, "errors": 0}
        # API 基址优先级：捕获请求的真实 origin（如 https://hospitalweb.xinjikang.cn）
        # > 调用方传入 base_url > 构造函数 base_url。web.base_url 可能含 #/（SPA 登录页），
        # hash 后路径不发到服务器，作 API 基址会拼接出必失败 URL（2026-08-24 定性）。
        captured_origins = [r.get("origin") or "" for r in self._captured if r.get("origin")]
        default_base = (captured_origins[0] if captured_origins else None) or base_url or self._base_url

        from app.core.models.api_test import ApiTestCase

        stats = {"generated": 0, "skipped": 0, "errors": 0}
        try:
            for rec in self._captured:
                status = rec.get("status") or 0
                if not (200 <= status < 300):
                    # 探索期真实发生的 4xx/5xx：一过性失败无复现价值，不固化
                    logger.info(
                        f"[ApiFlowCapture] 跳过非 2xx 接口 {rec['method']} {rec['path']} "
                        f"(status={status})——探索期失败不固化"
                    )
                    continue
                if _is_biz_failure(rec.get("response_body")):
                    # HTTP 2xx 但业务码非成功（如 code=50001）：固化会把失败码写进断言，
                    # 执行时必失败（A2 修复 2026-08-25）——与 4xx 同策略跳过
                    logger.info(
                        f"[ApiFlowCapture] 跳过业务失败响应 {rec['method']} {rec['path']} "
                        f"(HTTP {status} 但业务码非成功)——失败不固化为 normal 断言"
                    )
                    continue

                # 去重：与库内已有用例（含 Swagger 生成）按 (method, path) 查重
                # ——/orders/123 与库中 /orders/{id}（Swagger 模板形）或探索期另一 id
                # 视为同一接口，跳过（存储仍保留实际 path 便于直接运行）
                # 审计 L4：两侧不同形（库内原始 path vs 归一化 rec path）永远匹配不上，
                # 需双形态比较——原始精确命中（重复探索）+ 归一化命中（Swagger 模板形）
                from sqlalchemy import or_
                exists = db.query(ApiTestCase).filter(
                    ApiTestCase.project_id == project_id,
                    ApiTestCase.method == rec["method"],
                    or_(
                        ApiTestCase.path == rec.get("path", ""),
                        ApiTestCase.path == _normalize_path(rec.get("path", "")),
                    ),
                ).first()
                if exists:
                    stats["skipped"] += 1
                    continue

                module = rec.get("module") or "探索"
                # A5 修复 2026-08-25：逐用例 base_url——跨域项目（前端域名与 API 域名
                # 不同）每个捕获请求的 origin 才是该用例的真实基址；全局只取第一个
                # origin 会让其他域接口全部打到错误基址（单域场景 rec.origin == 全局第一个）
                rec_base = rec.get("origin") or default_base
                cases = [self._build_normal_case(rec, project_id, rec_base, module, version_id)]
                cases.extend(self._build_error_cases(rec, project_id, rec_base, module, version_id))
                for c in cases:
                    db.add(c)
                    stats["generated"] += 1
            db.commit()
            logger.info(
                f"[ApiFlowCapture] 探索生成 API 用例: 生成 {stats['generated']} 条, "
                f"去重跳过 {stats['skipped']} 条"
            )
        except Exception as e:
            import traceback as _tb
            logger.error(f"[ApiFlowCapture] 生成用例失败: {e}\n{_tb.format_exc()}")
            stats["errors"] += 1
        return stats

    def _build_normal_case(self, rec: Dict[str, Any], project_id: int,
                           base_url: str, module: str,
                           version_id: Optional[int] = None):
        """成功接口 → normal 用例（鉴权头写占位符，执行时由 api_auth 实时 token 替换）。"""
        from app.core.models.api_test import ApiTestCase

        headers = dict(rec.get("headers") or {})
        shape = rec.get("auth_shape") or {}
        if shape.get("type") == "bearer":
            # 占位符 {{auth_token}}：执行器 env_auth_vars 有 token 时替换为实时值。
            # 裸占位符不带前缀——前缀统一由执行侧 token_injection.prefix（默认 "Bearer "）
            # 注入，生成侧写前缀会造成「Bearer Bearer」双前缀（审计 H1）。
            headers[shape.get("header_name") or "Authorization"] = "{{auth_token}}"

        # F28：断言规则先算（test_steps 按规则逐条映射，保证详情页步骤与执行断言同源）
        assert_rules = _build_assert_rules(rec.get("response_body"), rec.get("status") or 200)
        return ApiTestCase(
            project_id=project_id,
            version_id=version_id,
            endpoint_id=None,
            name=f"[探索] {module} - {rec['method']} {rec['path']}",
            description=f"探索自动生成（模块：{module}）：{rec['method']} {rec['full_path']}",
            method=rec["method"],
            path=rec["path"],
            base_url=base_url,
            headers=headers or None,
            query_params=rec.get("query_params"),
            path_params=None,
            request_body=rec.get("request_body"),
            expected_status=rec.get("status") or 200,
            # 预期响应体：探索期捕获的真实响应快照（截断后），详情页可见、执行可对照
            expected_body=rec.get("response_body"),
            preconditions=("需有效登录：执行时按项目 api_auth 配置自动调登录接口注入实时 Token"
                           "（请求头 {{auth_token}} 占位符自动替换，不落明文）"),
            assert_rules=assert_rules,
            test_steps=_build_test_steps(rec["method"], rec.get("path", ""), assert_rules),
            case_type="normal",
            priority="P2",
            status="draft",
            tags=["exploration", f"module:{module}"],
            generated_by="ai",
        )

    def _build_error_cases(self, rec: Dict[str, Any], project_id: int,
                           base_url: str, module: str,
                           version_id: Optional[int] = None):
        """做法 B：以捕获的成功接口为模板，主动构造异常请求变体（真构造，非空壳）。

        变体（最多 4 种，no_auth 优先保证不被截断）：
          1. 无鉴权     —— tags 标记 no_auth，执行器跳过鉴权注入 → 期望 4xx(401/403)
          2. 缺参数     —— 删 query/body 第一个非敏感参数 → 期望 4xx
          3. 类型错误   —— 第一个标量值改类型（数字→字符串）→ 期望 4xx
          4. 不存在资源 —— path/query/body 数字值 → 999999999 → 期望 4xx

        头部策略：业务头（rec.headers 已脱敏，无鉴权原文）全部保留——缺参数/类型错误/
        不存在资源变体本意是「带鉴权但参数错」，保留 Content-Type 等才能稳定复现 4xx；
        no_auth 变体只用无鉴权业务头。正常用例的鉴权占位符由执行器实时替换注入。

        expected_status 不设精确码：断言规则用 4xx 区间列表
        （执行器 http_status value 支持列表，api_tests.py L1455 in 判断）。
        """
        from app.core.models.api_test import ApiTestCase

        query = dict(rec.get("query_params") or {})
        body = dict(rec.get("request_body") or {}) if isinstance(rec.get("request_body"), dict) else {}
        # 业务头（已脱敏）；with_auth=False 的 no_auth 变体不加鉴权占位符
        plain_headers = dict(rec.get("headers") or {})
        shape = rec.get("auth_shape") or {}
        auth_headers = dict(plain_headers)
        if shape.get("type") == "bearer":
            # 裸占位符（前缀归执行侧 token_injection.prefix 注入，防双前缀，见 _build_normal_case）
            auth_headers[shape.get("header_name") or "Authorization"] = "{{auth_token}}"
        cases = []
        variants: List[Dict[str, Any]] = []

        # 1. 无鉴权：执行器对 no_auth 标签用例跳过鉴权注入（用户核心诉求，排最前防截断）
        if rec.get("auth_shape"):
            variants.append({
                "desc": "无鉴权访问",
                "tag": "no_auth",
                "query": dict(query), "body": dict(body),
                "headers": plain_headers,
            })

        # 2. 缺参数：删第一个非敏感 key（body 优先，其次 query）
        built = False  # 本次变体是否构造成功——不能用 variants 判定（no_auth 前置已非空，污染 break）
        for src_name, src in (("body", body), ("query", query)):
            for k in list(src.keys()):
                if _SENSITIVE_KEY_RE.search(k):
                    continue
                variants.append({
                    "desc": "缺参数",
                    "tag": "missing_param",
                    "query": dict(query), "body": dict(body),
                    "headers": auth_headers,
                })
                variants[-1][src_name].pop(k, None)
                built = True
                break
            if built:
                break

        # 3. 类型错误：第一个标量值改类型（数字→字符串 / 字符串→数组）
        built = False  # 同缺参数：用本次构造标志判定，防 no_auth 前置污染
        for src_name, src in (("body", body), ("query", query)):
            for k, v in src.items():
                if not isinstance(v, (int, float, str)) or _SENSITIVE_KEY_RE.search(k):
                    continue
                variants.append({
                    "desc": "参数类型错误",
                    "tag": "wrong_type",
                    "query": dict(query), "body": dict(body),
                    "headers": auth_headers,
                })
                if isinstance(v, bool):
                    variants[-1][src_name][k] = "not_bool"
                elif isinstance(v, (int, float)):
                    variants[-1][src_name][k] = str(v) + "not_number"
                else:
                    variants[-1][src_name][k] = [v, "extra"]
                built = True
                break
            if built:
                break

        # 4. 不存在资源：数字值参数 → 999999999（覆盖 path 与 query/body 数字）
        for src_name, src in (("path", None), ("body", body), ("query", query)):
            if src_name == "path":
                path_v = rec.get("path", "")
                if re.search(r"/\d+", path_v):
                    variants.append({
                        "desc": "资源不存在",
                        "tag": "not_found",
                        "query": dict(query), "body": dict(body),
                        "path": re.sub(r"/\d+", f"/{_NOT_FOUND_ID}", path_v, count=1),
                        "headers": auth_headers,
                    })
                continue
            for k, v in src.items():
                if isinstance(v, int) and not _SENSITIVE_KEY_RE.search(k):
                    variants.append({
                        "desc": "资源不存在",
                        "tag": "not_found",
                        "query": dict(query), "body": dict(body),
                        "headers": auth_headers,
                    })
                    variants[-1][src_name][k] = _NOT_FOUND_ID
                    break
            # 已有任一 not_found 变体（path 或 body）即不再构造 query 重复变体
            if any(v["tag"] == "not_found" for v in variants):
                break

        # F28：error 变体断言规则（4xx 区间）——test_steps 按此映射，与执行器一致
        error_rules = [
            {"type": "http_status", "value": [400, 401, 403, 404, 422],
             "description": "HTTP状态码为 4xx"},
        ]
        for v in variants[:4]:
            cases.append(ApiTestCase(
                project_id=project_id,
                version_id=version_id,
                endpoint_id=None,
                name=f"[探索-异常] {module} - {rec['method']} {rec['path']} - {v['desc']}",
                description=f"探索自动生成异常变体（{v['desc']}）：{rec['method']} "
                            f"{v.get('path') or rec['path']}",
                method=rec["method"],
                path=v.get("path") or rec.get("path", ""),
                base_url=base_url,
                headers=v.get("headers") or None,  # no_auth 变体仅业务头，其余含鉴权占位符
                query_params=v.get("query") or None,
                path_params=None,
                request_body=v.get("body") or None,
                expected_status=None,  # 4xx 区间由 assert_rules 表达
                preconditions=("无需鉴权：验证未授权访问被拦截（4xx）"
                               if v["tag"] == "no_auth"
                               else "需有效登录：执行时自动注入鉴权 Token（{{auth_token}} 占位符替换）"),
                assert_rules=error_rules,
                test_steps=_build_test_steps(
                    rec["method"], v.get("path") or rec.get("path", ""),
                    error_rules, variant_desc=v["desc"]),
                case_type="error",
                priority="P3",
                status="draft",
                tags=["exploration", f"module:{module}", v["tag"]],
                generated_by="ai",
            ))
        return cases
