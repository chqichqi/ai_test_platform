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
# 非 JSON body 原文保留截断上限（字符数；防巨表单撑爆库，非业务值）
_RAW_BODY_MAX_CHARS = 10000


def _sanitize(value: Any) -> Any:
    """递归脱敏：key 命中敏感词（password/token 等）的值一律替换为占位符。

    仅对 dict 的 key 名判断（不猜值），保留业务数据结构供用例直接运行。
    """
    if isinstance(value, dict):
        return {
            k: ("${%s}" % k if _SENSITIVE_KEY_RE.search(k) else _sanitize(v))
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


def _build_api_data_plan(rec: Dict[str, Any], variant: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from app.core.services.test_data_plan import build_api_test_data_plan
    variant = variant or {}
    return build_api_test_data_plan(
        query_params=variant.get("query", rec.get("query_params") or {}),
        path_params=variant.get("path_params", rec.get("path_params") or {}),
        request_body=variant.get("body", rec.get("request_body") if isinstance(rec.get("request_body"), dict) else {}),
        headers=variant.get("headers", rec.get("headers") or {}),
        mutation_key=variant.get("mutation_key", ""),
        mutation=variant.get("mutation", ""),
        observed=True,
        metadata={"source": "exploration", "observed_request": True, "mutation": variant.get("mutation") or None},
    )


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
        self._module_name = "通用模块"
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
                for k, v in parse_qs(parsed.query, keep_blank_values=True).items()
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

                # 去重改为“用例类型/变体级”去重：同一接口已有 normal 用例时，仍允许
                # 探索补充 wrong_type/missing/no_auth 等异常用例。
                from sqlalchemy import or_
                existing_cases = db.query(ApiTestCase).filter(
                    ApiTestCase.project_id == project_id,
                    ApiTestCase.method == rec["method"],
                    or_(
                        ApiTestCase.path == rec.get("path", ""),
                        ApiTestCase.path == _normalize_path(rec.get("path", "")),
                    ),
                ).all()

                # 未处于具体模块探索阶段的网络请求（例如首屏公共用户/组织接口）
                # 不再伪装成“探索”；使用稳定的通用模块名称，且后续模块请求会被
                # capture.set_module() 正确归属。
                module = rec.get("module") or "通用模块"
                # 每个捕获请求使用自己的 origin，避免跨域 API 被错误拼到前端域名。
                rec_base = rec.get("origin") or default_base
                candidates = []
                if not any(c.case_type == "normal" for c in existing_cases):
                    candidates.append(self._build_normal_case(rec, project_id, rec_base, module, version_id))
                candidates.extend(self._build_error_cases(rec, project_id, rec_base, module, version_id))

                for c in candidates:
                    c_tags = set(c.tags or [])
                    duplicate = False
                    for old_case in existing_cases:
                        old_tags = set(old_case.tags or [])
                        if c.case_type == "normal":
                            duplicate = old_case.case_type == "normal"
                        else:
                            # 探索异常变体用唯一 tag 区分；允许同一接口同时存在多个异常场景。
                            variant_tags = c_tags.intersection({"no_auth", "missing_param", "wrong_type", "not_found"})
                            duplicate = bool(variant_tags.intersection(old_tags)) and "exploration" in old_tags
                        if duplicate:
                            break
                    if duplicate:
                        stats["skipped"] += 1
                        continue
                    db.add(c)
                    db.flush()
                    existing_cases.append(c)
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
        """探索正常用例：委托统一 OpenApiTestGenerator，避免探索与 Swagger 两套规则。"""
        from app.core.services.openapi_test_generator import OpenApiTestGenerator
        from app.core.models.api_test import ApiTestCase

        generator = OpenApiTestGenerator()
        data = generator.generate_observed_cases(
            rec, module=module, include_normal=True, include_error=False, include_boundary=False, include_auth=False, max_cases=1
        )
        if not data:
            return None
        case_data = data[0]
        return ApiTestCase(
            project_id=project_id, version_id=version_id, endpoint_id=None,
            name=case_data["name"], description=case_data["description"],
            method=rec["method"], path=rec["path"], base_url=base_url,
            headers=case_data.get("headers") or None, query_params=case_data.get("query_params") or None,
            path_params=case_data.get("path_params") or None, request_body=case_data.get("request_body") or None,
            test_data=_build_api_data_plan(rec), expected_status=case_data.get("expected_status"),
            expected_body=rec.get("response_body"), preconditions=case_data.get("preconditions", ""),
            assert_rules=case_data.get("assert_rules", []), test_steps=case_data.get("test_steps", []),
            expected_result=case_data.get("expected_result", ""), case_type="normal", priority="P2",
            status="draft", tags=["exploration", f"module:{module}"], generated_by="ai"
        )

    def _build_error_cases(self, rec: Dict[str, Any], project_id: int,
                           base_url: str, module: str,
                           version_id: Optional[int] = None):
        """探索异常用例：与 Swagger 共用 OpenApiTestGenerator 的变体策略。"""
        from app.core.services.openapi_test_generator import OpenApiTestGenerator
        from app.core.models.api_test import ApiTestCase

        generator = OpenApiTestGenerator()
        generated = generator.generate_observed_cases(
            rec, module=module, include_normal=False, include_error=True, include_boundary=False, include_auth=True, max_cases=5
        )
        cases = []
        for data in generated:
            tag = "no_auth" if "无鉴权" in data.get("name", "") else "api_error"
            mutation = data.get("mutation", "")
            mutation_key = data.get("mutation_key", "")
            variant = {
                "query": data.get("query_params") or {},
                "path_params": data.get("path_params") or {},
                "body": data.get("request_body") or {},
                "headers": data.get("headers") or {},
                "mutation_key": mutation_key, "mutation": mutation,
            }
            cases.append(ApiTestCase(
                project_id=project_id, version_id=version_id, endpoint_id=None,
                name=data["name"], description=data["description"], method=rec["method"], path=rec["path"], base_url=base_url,
                headers=data.get("headers") or None, query_params=data.get("query_params") or None,
                path_params=data.get("path_params") or None, request_body=data.get("request_body") or None,
                test_data=_build_api_data_plan(rec, variant), expected_status=None,
                preconditions=data.get("preconditions", ""), assert_rules=data.get("assert_rules", []),
                test_steps=data.get("test_steps", []), expected_result=data.get("expected_result", ""),
                case_type="error", priority="P3", status="draft",
                tags=["exploration", f"module:{module}", tag], generated_by="ai"
            ))
        return cases
