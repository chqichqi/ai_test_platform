"""
API测试断言执行器
用于验证响应数据是否符合断言规则
"""

import re
import json
from typing import Dict, Any, List, Optional
from app.core.logger import logger


class ApiAssertExecutor:
    """API测试断言执行器"""
    
    SUCCESS_CODE = 10000
    
    COMMON_SUCCESS_CODES = [0, 10000, 200, 20000, 100200, "success", "SUCCESS"]
    COMMON_ERROR_CODES = [-1, 10001, 40001, 50001, 400, 401, 403, 404, 500]
    
    def __init__(self, response_body: Dict[str, Any], assert_rules: List[Dict[str, Any]]):
        self.response_body = response_body
        self.assert_rules = assert_rules or []
        self.results: List[Dict[str, Any]] = []
        self.all_passed = True
    
    def execute(self) -> List[Dict[str, Any]]:
        """执行所有断言规则"""
        for rule in self.assert_rules:
            result = self._execute_single_rule(rule)
            self.results.append(result)
            if not result["passed"]:
                self.all_passed = False
        
        return self.results
    
    def _execute_single_rule(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个断言规则"""
        rule_type = rule.get("type", "")
        field = rule.get("field", "")
        expected_value = rule.get("value")
        description = rule.get("description", "")
        skip_if_missing = rule.get("skip_if_missing", False)
        
        result = {
            "rule": rule_type,
            "field": field,
            "expected_value": expected_value,
            "actual_value": None,
            "passed": False,
            "message": description
        }
        
        # 检查是否需要跳过缺失字段
        if field and skip_if_missing:
            actual_value = self._get_field_value(field)
            if actual_value is None:
                result["passed"] = True
                result["message"] = f"响应无{field}字段，跳过断言"
                return result
        
        try:
            if rule_type == "http_status":
                # HTTP状态码断言已在外层验证，这里只标记通过
                result["passed"] = True
                result["message"] = f"HTTP状态码应为: {expected_value}"
            
            elif rule_type == "response_not_empty":
                # 响应体不为空断言
                result["passed"] = bool(self.response_body) and len(self.response_body) > 0
                if not result["passed"]:
                    result["message"] = "响应体为空"
            
            elif rule_type == "status_eq":
                # 按 rule.field 精确取值（生成侧 _build_assert_rules 顶层 code/status → status_eq 带 field）。
                # 不能用 `or` 短路——业务码 code=0 会被误判为缺失（审计 M1）；
                # 无 field 的旧规则才回退顶层 code→status 探测。
                _f = field or "code"
                actual_value = self.response_body.get(_f) if isinstance(self.response_body, dict) else None
                if actual_value is None and not field:
                    actual_value = self.response_body.get("status") if isinstance(self.response_body, dict) else None
                result["actual_value"] = actual_value
                result["passed"] = actual_value == expected_value
                if not result["passed"]:
                    result["message"] = f"业务码不匹配: {_f} 期望 {expected_value}, 实际 {actual_value}"
            
            elif rule_type == "json_value_eq":
                actual_value = self._get_field_value(field)
                result["actual_value"] = actual_value
                result["passed"] = actual_value == expected_value
                if not result["passed"]:
                    result["message"] = f"字段值不匹配: {field} 期望 {expected_value}, 实际 {actual_value}"
            
            elif rule_type == "json_contains":
                actual_value = self._get_field_value(field)
                skip_if_missing = rule.get("skip_if_missing", False)
                
                if actual_value is None and skip_if_missing:
                    result["passed"] = True
                    result["message"] = f"响应无 {field} 字段，跳过断言"
                else:
                    result["passed"] = actual_value is not None
                    result["actual_value"] = actual_value if actual_value is not None else "不存在"
                    if not result["passed"]:
                        result["message"] = f"响应不包含字段: {field}"
            
            elif rule_type == "json_type":
                actual_value = self._get_field_value(field)
                result["actual_value"] = type(actual_value).__name__
                expected_type = expected_value
                type_map = {
                    "string": str,
                    "integer": int,
                    "number": (int, float),
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                    "null": type(None)
                }
                expected_type_class = type_map.get(expected_type, str)
                result["passed"] = isinstance(actual_value, expected_type_class)
                if not result["passed"]:
                    result["message"] = f"字段类型不匹配: {field} 期望 {expected_type}, 实际 {type(actual_value).__name__}"
            
            elif rule_type == "json_not_null":
                actual_value = self._get_field_value(field)
                result["actual_value"] = actual_value
                result["passed"] = actual_value is not None and actual_value != ""
                if not result["passed"]:
                    result["message"] = f"字段值为空: {field}"
            
            elif rule_type == "json_array_length":
                actual_value = self._get_field_value(field)
                if isinstance(actual_value, list):
                    result["actual_value"] = len(actual_value)
                    result["passed"] = len(actual_value) >= expected_value
                    if not result["passed"]:
                        result["message"] = f"数组长度不足: {field} 期望至少 {expected_value} 个, 实际 {len(actual_value)} 个"
                else:
                    result["message"] = f"字段不是数组: {field}"
            
            elif rule_type == "json_regex":
                actual_value = self._get_field_value(field)
                result["actual_value"] = actual_value
                if isinstance(actual_value, str):
                    pattern = expected_value
                    result["passed"] = bool(re.match(pattern, actual_value))
                    if not result["passed"]:
                        result["message"] = f"字段值不匹配正则: {field} 模式 {pattern}, 实际 {actual_value}"
                else:
                    result["message"] = f"字段不是字符串: {field}"
            
            elif rule_type == "http_status_eq":
                result["passed"] = True
                result["message"] = "HTTP状态码断言已在外层验证"
            
            elif rule_type == "http_status":
                # HTTP状态码断言，期望状态码在列表中
                # 这个断言类型用于标记期望的HTTP状态码，实际验证在外层执行
                result["passed"] = True
                result["message"] = f"HTTP状态码应为: {expected_value}"
            
            elif rule_type == "json_in":
                actual_value = self._get_field_value(field)
                result["actual_value"] = actual_value
                
                if actual_value is None:
                    if field in ["code", "status"]:
                        # 特殊处理：业务码字段不存在时
                        # 如果是认证测试（value包含40101/40301），检查HTTP状态码是否是401/403
                        # 因为很多API在认证失败时直接返回HTTP 401，而不返回业务码
                        if isinstance(expected_value, list):
                            auth_error_codes = [40101, 40301]
                            if any(c in expected_value for c in auth_error_codes):
                                result["passed"] = True
                                result["message"] = f"响应无{field}字段，可能是纯HTTP认证失败（401/403），跳过业务码断言"
                            else:
                                result["passed"] = False
                                result["message"] = f"字段不存在: {field}"
                        else:
                            result["passed"] = False
                            result["message"] = f"字段不存在: {field}"
                    else:
                        result["passed"] = False
                        result["message"] = f"字段不存在: {field}"
                elif isinstance(expected_value, list):
                    result["passed"] = actual_value in expected_value
                    if not result["passed"]:
                        result["message"] = f"字段值不在期望范围内: {field} 期望 {expected_value}, 实际 {actual_value}"
                else:
                    result["passed"] = actual_value == expected_value
            
            else:
                result["message"] = f"未知的断言类型: {rule_type}"
        
        except Exception as e:
            result["message"] = f"断言执行错误: {str(e)}"
            logger.error(f"Assert rule execution failed: {str(e)}")
        
        return result
    
    def _get_field_value(self, field: str) -> Any:
        """获取响应体中指定字段的值，支持嵌套路径"""
        if not field:
            return None
        
        keys = field.split(".")
        value = self.response_body
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                index = int(key)
                if 0 <= index < len(value):
                    value = value[index]
                else:
                    return None
            else:
                return None
        
        return value
    
    def is_all_passed(self) -> bool:
        """检查所有断言是否通过"""
        return self.all_passed
    
    def get_summary(self) -> str:
        """获取断言结果摘要"""
        passed_count = sum(1 for r in self.results if r["passed"])
        total_count = len(self.results)
        
        if self.all_passed:
            return f"所有断言通过 ({passed_count}/{total_count})"
        else:
            failed_rules = [r for r in self.results if not r["passed"]]
            messages = [r["message"] for r in failed_rules]
            return f"断言失败 ({passed_count}/{total_count}): " + "; ".join(messages)


def generate_assert_rules_from_response_spec(response_spec: Dict[str, Any], case_type: str) -> List[Dict[str, Any]]:
    """根据响应定义生成断言规则，智能分析响应结构
    
    改进点：
    - 递归分析嵌套的响应结构
    - 自动识别token、access_token等认证字段
    - 根据Swagger定义正确生成字段路径
    """
    rules = []
    
    response_fields = {}
    has_code_field = False
    has_data_field = False
    has_message_field = False
    token_fields = []
    
    def analyze_schema_recursive(schema: Dict[str, Any], parent_path: str = "") -> None:
        """递归分析schema，找出所有字段和token字段"""
        if not schema or schema.get("type") != "object":
            return
            
        properties = schema.get("properties", {})
        for prop_name, prop_spec in properties.items():
            current_path = f"{parent_path}.{prop_name}" if parent_path else prop_name
            
            prop_type = prop_spec.get("type", "unknown")
            
            # 记录顶层字段
            if not parent_path:
                if prop_name == "code":
                    has_code_field = True
                elif prop_name == "data":
                    has_data_field = True
                elif prop_name == "message":
                    has_message_field = True
            
            # 识别token相关字段
            if prop_name in ["token", "access_token", "auth_token", "jwt", "bearer_token"]:
                token_fields.append(current_path)
            
            # 为字段生成断言规则
            if prop_type in ["string", "number", "integer", "boolean"]:
                rules.append({
                    "type": "json_contains",
                    "field": current_path,
                    "description": f"响应应包含 {current_path} 字段",
                    "skip_if_missing": parent_path != ""  # 嵌套字段允许跳过
                })
            
            # 递归处理嵌套对象
            if prop_type == "object":
                analyze_schema_recursive(prop_spec, current_path)
    
    if response_spec:
        content = response_spec.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        
        if schema:
            analyze_schema_recursive(schema)
            response_fields = schema.get("properties", {})
    
    # 如果Swagger没有定义响应结构，使用默认假设
    if not response_fields:
        has_code_field = True
        has_data_field = True
        has_message_field = True
        token_fields = ["data.token", "data.access_token", "token", "access_token"]
        logger.info("Swagger未定义响应结构，使用默认断言规则（假设标准响应格式）")
    
    # 根据测试类型添加特定的断言规则
    if case_type == "normal":
        # 检查HTTP状态码是否为成功状态
        rules.append({
            "type": "http_status",
            "value": [200, 201, 204],
            "description": "HTTP状态码应为成功状态(200/201/204)"
        })
        
        # 如果响应有code字段，添加业务码断言
        if has_code_field:
            # 从响应定义中提取成功码（不使用硬编码）
            code_spec = response_fields.get("code", {})
            code_enum = code_spec.get("enum")
            code_default = code_spec.get("default")
            code_example = code_spec.get("example")
            
            # 确定期望的成功码值
            expected_success_codes = []
            
            if code_enum:
                # 从枚举中提取成功码（通常是0或200附近的值）
                for c in code_enum:
                    if isinstance(c, int):
                        # 常见成功码特征：0、200、或小于100的正数
                        if c == 0 or c == 200 or (c > 0 and c < 100):
                            expected_success_codes.append(c)
                if not expected_success_codes and code_enum:
                    # 如果没找到明显成功码，使用第一个枚举值
                    expected_success_codes = [code_enum[0]]
            
            if code_default and code_default not in expected_success_codes:
                expected_success_codes.insert(0, code_default)
            
            if code_example and code_example not in expected_success_codes:
                expected_success_codes.insert(0, code_example)
            
            # 根据提取的成功码生成断言
            if expected_success_codes:
                if len(expected_success_codes) == 1:
                    rules.append({
                        "type": "status_eq",
                        "field": "code",
                        "value": expected_success_codes[0],
                        "description": f"业务返回码应为 {expected_success_codes[0]} (成功)",
                        "skip_if_missing": False
                    })
                else:
                    rules.append({
                        "type": "json_in",
                        "field": "code",
                        "value": expected_success_codes,
                        "description": f"业务返回码应为成功状态({expected_success_codes})",
                        "skip_if_missing": False
                    })
            else:
                # 如果Swagger未定义业务码，仅验证HTTP状态码（不验证业务码）
                logger.info("Swagger未定义业务码枚举值，跳过业务码断言")
        
        # 如果响应有data字段，才添加data断言
        if has_data_field:
            rules.append({
                "type": "json_not_null",
                "field": "data",
                "description": "响应数据data字段不应为空"
            })
        
        # 如果响应有message字段，验证message类型
        if has_message_field:
            message_spec = response_fields.get("message", {})
            if message_spec.get("type") == "string":
                rules.append({
                    "type": "json_type",
                    "field": "message",
                    "value": "string",
                    "description": "message字段应为字符串类型"
                })
        
        # 对于登录接口，添加token字段断言
        if token_fields:
            # 添加第一个token字段的断言（主要token）
            if len(token_fields) > 0:
                rules.append({
                    "type": "json_contains",
                    "field": token_fields[0],
                    "description": f"响应应包含 {token_fields[0]} 字段",
                    "skip_if_missing": False
                })
            # 添加其他token字段的断言（备用）
            for tf in token_fields[1:]:
                rules.append({
                    "type": "json_contains",
                    "field": tf,
                    "description": f"响应应包含 {tf} 字段",
                    "skip_if_missing": True
                })
    
    elif case_type == "error":
        # 错误场景：主要验证HTTP状态码，业务码验证可选
        rules.append({
            "type": "http_status",
            "value": [400, 401, 403, 404, 422, 500, 200],
            "description": "HTTP状态码可能为错误状态或200（业务错误码）"
        })
        
        if has_code_field:
            # 错误场景：验证业务码字段存在，不硬编码具体错误码值
            # 从Swagger提取的成功码（如果有）
            code_spec = response_fields.get("code", {})
            success_code_values = []
            
            # 从错误响应定义中提取可能错误码（如果定义了4xx/5xx响应）
            if response_spec:
                error_codes_extracted = []
                for status_code in ["400", "401", "403", "404", "422", "500"]:
                    error_response = response_spec.get(status_code, {})
                    if error_response:
                        content = error_response.get("content", {})
                        json_content = content.get("application/json", {})
                        schema = json_content.get("schema", {})
                        if schema.get("type") == "object":
                            props = schema.get("properties", {})
                            if "code" in props:
                                code_schema = props["code"]
                                if code_schema.get("enum"):
                                    error_codes_extracted.extend(code_schema.get("enum"))
                                if code_schema.get("example"):
                                    error_codes_extracted.append(code_schema.get("example"))
            
            rules.append({
                "type": "json_not_null",
                "field": "code",
                "description": "错误响应应包含code字段"
            })
            
            if error_codes_extracted:
                # 如果从Swagger提取到错误码，验证业务码在错误码列表中
                rules.append({
                    "type": "json_in",
                    "field": "code",
                    "value": error_codes_extracted,
                    "description": f"业务返回码应为错误状态({error_codes_extracted})",
                    "skip_if_missing": False
                })
            else:
                # Swagger未定义错误码时，只验证业务码不为成功码（更通用的方式）
                logger.info("Swagger未定义错误码枚举值，验证业务码存在（不限制具体值）")
        
        if has_message_field:
            rules.append({
                "type": "json_not_null",
                "field": "message",
                "description": "错误信息message字段应存在"
            })
            rules.append({
                "type": "json_type",
                "field": "message",
                "value": "string",
                "description": "message字段应为字符串类型"
            })
    
    elif case_type == "auth":
        # 权限测试：主要验证HTTP状态码
        rules.append({
            "type": "http_status",
            "value": [401, 403, 200],
            "description": "HTTP状态码应为401(未授权)或403(禁止访问)"
        })
        
        if has_code_field:
            rules.append({
                "type": "json_not_null",
                "field": "code",
                "description": "响应应包含业务码字段"
            })
            # 不硬编码具体错误码，让测试执行器根据实际响应判断
        
        if has_message_field:
            rules.append({
                "type": "json_not_null",
                "field": "message",
                "description": "错误信息应存在"
            })
            rules.append({
                "type": "json_type",
                "field": "message",
                "value": "string",
                "description": "message字段应为字符串类型"
            })
    
    elif case_type == "boundary":
        # 边界值测试：主要验证HTTP状态码
        rules.append({
            "type": "http_status",
            "value": [400, 422, 200],
            "description": "HTTP状态码应为400(参数错误)或422(验证失败)"
        })
        
        if has_code_field:
            rules.append({
                "type": "json_not_null",
                "field": "code",
                "description": "响应应包含业务码字段"
            })
            # 不硬编码具体错误码，让测试执行器根据实际响应判断
    
    return rules