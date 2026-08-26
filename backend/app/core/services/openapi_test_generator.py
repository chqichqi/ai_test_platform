"""
OpenAPI 测试用例生成器 - 基于 openapi-testgen 最佳实践

参考: https://github.com/galushkoart/openapi-testgen-monorepo

核心理念:
1. Provider-Rule 架构: Providers 协调测试生成，Rules 编码 OpenAPI 约束
2. 根据 Schema 定义生成具体的违规参数（而非通用空值）
3. 测试用例命名清晰描述违反的约束
4. 正确处理 Swagger 2.0 和 OpenAPI 3.0 格式
5. 正确解析 $ref 引用，从 components/schemas 获取完整字段定义
"""

import json
import re
import logging
import random
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class OpenApiSchemaParser:
    """OpenAPI Schema 解析器 - 正确处理 Swagger 2.0 和 OpenAPI 3.0"""
    
    def __init__(self, swagger_doc: Optional[Dict[str, Any]] = None):
        """初始化解析器，保存完整的Swagger文档以便解析$ref"""
        self.swagger_doc = swagger_doc or {}
    
    def set_swagger_doc(self, swagger_doc: Optional[Dict[str, Any]] = None):
        """设置Swagger文档"""
        self.swagger_doc = swagger_doc
    
    def _resolve_ref(self, ref_path: str) -> Dict[str, Any]:
        """真正解析$ref引用，从components/schemas获取schema定义"""
        if not ref_path or not ref_path.startswith("#/"):
            return {}
        
        # 解析路径: #/components/schemas/UserRegister
        parts = ref_path.split("/")
        if len(parts) < 4:
            return {}
        
        # 导航到目标schema
        current = self.swagger_doc
        for part in parts[1:]:  # 跳过开头的#
            if part in current:
                current = current[part]
            else:
                logger.warning(f"$ref path not found: {ref_path}, missing: {part}")
                return {}
        
        return current if isinstance(current, dict) else {}
    
    def parse_request_body(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """解析请求体定义，返回字段 Schema"""
        body_schema = {}
        
        # Swagger 2.0 格式: parameters 中有 in="body" 的参数
        parameters = endpoint.get("parameters", [])
        for param in parameters:
            if isinstance(param, dict) and param.get("in") == "body":
                schema = param.get("schema", {})
                
                if schema.get("type") == "object":
                    properties = schema.get("properties", {})
                    required_list = schema.get("required", [])
                    for prop_name, prop_spec in properties.items():
                        # 智能判断字段是否必填
                        is_required = prop_name in required_list or not self._is_optional_type(prop_spec)
                        body_schema[prop_name] = self._parse_property_schema(prop_name, prop_spec, is_required)
                
                # 处理Swagger 2.0的$ref引用 - 先尝试真正解析，再fallback推断
                elif schema.get("$ref"):
                    ref_path = schema.get("$ref", "")
                    resolved_schema = self._resolve_ref(ref_path)
                    if resolved_schema:
                        # 真正从Swagger文档解析schema
                        properties = resolved_schema.get("properties", {})
                        required_list = resolved_schema.get("required", [])
                        for prop_name, prop_spec in properties.items():
                            # 智能判断字段是否必填
                            is_required = prop_name in required_list or not self._is_optional_type(prop_spec)
                            body_schema[prop_name] = self._parse_property_schema(prop_name, prop_spec, is_required)
                        logger.info(f"从$ref解析请求体: {ref_path}, 字段数={len(body_schema)}, 必填字段: {[k for k,v in body_schema.items() if v.get('required')]}")
                    else:
                        # fallback: 根据路径推断
                        body_schema = self._infer_schema_from_ref(ref_path, endpoint.get("path", ""), endpoint.get("method", ""))
                
                break
        
        # OpenAPI 3.0 格式: requestBody.content.application/json.schema
        request_body_spec = endpoint.get("requestBody")
        if request_body_spec and len(body_schema) == 0:  # 修复：空字典 {} 是 True，需要检查长度
            content = request_body_spec.get("content", {})
            
            # 尝试多种content类型
            for content_type in ["application/json", "application/x-www-form-urlencoded", "multipart/form-data"]:
                content_data = content.get(content_type, {})
                schema = content_data.get("schema", {})
                
                if schema.get("type") == "object":
                    properties = schema.get("properties", {})
                    required_list = schema.get("required", [])
                    for prop_name, prop_spec in properties.items():
                        # 智能判断字段是否必填
                        is_required = prop_name in required_list or not self._is_optional_type(prop_spec)
                        body_schema[prop_name] = self._parse_property_schema(prop_name, prop_spec, is_required)
                    break
                
                # 处理 $ref 引用 - 真正解析
                if schema.get("$ref"):
                    ref_path = schema.get("$ref", "")
                    resolved_schema = self._resolve_ref(ref_path)
                    if resolved_schema:
                        properties = resolved_schema.get("properties", {})
                        required_list = resolved_schema.get("required", [])
                        for prop_name, prop_spec in properties.items():
                            # 智能判断字段是否必填：
                            # 1. 在schema.required列表中 → 必填
                            # 2. 字段类型允许null（anyOf含null或有default） → 可选
                            # 3. 其他情况 → 必填
                            is_required = prop_name in required_list or not self._is_optional_type(prop_spec)
                            body_schema[prop_name] = self._parse_property_schema(prop_name, prop_spec, is_required)
                        logger.info(f"从$ref解析请求体: {ref_path}, 字段数={len(body_schema)}, 必填字段: {[k for k,v in body_schema.items() if v.get('required')]}")
                        break
                    else:
                        # fallback: 根据路径推断
                        body_schema = self._infer_schema_from_ref(ref_path, endpoint.get("path", ""), endpoint.get("method", ""))
                        if len(body_schema) > 0:
                            break
        
        # 如果还是没有解析出body_schema，尝试从接口路径推断
        if len(body_schema) == 0:  # 修复：空字典 {} 是 True，需要检查长度
            path_lower = endpoint.get("path", "").lower()
            method = endpoint.get("method", "").upper()
            
            if "register" in path_lower or "signup" in path_lower:
                body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
                body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
                body_schema["email"] = {"type": "string", "format": "email", "required": True, "description": "邮箱"}
                logger.info(f"从路径推断注册接口参数: {path_lower}")
            
            elif "login" in path_lower:
                body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
                body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
                logger.info(f"从路径推断登录接口参数: {path_lower}")
        
        return body_schema
    
    def parse_query_params(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """解析查询参数定义"""
        query_schema = {}
        parameters = endpoint.get("parameters", [])
        for param in parameters:
            if isinstance(param, dict) and param.get("in") == "query":
                param_name = param.get("name", "")
                param_required = param.get("required", False)
                param_spec = param.get("schema", {})
                if not param_spec:
                    param_spec = {
                        "type": param.get("type", "string"),
                        "format": param.get("format"),
                        "enum": param.get("enum"),
                        "minLength": param.get("minLength"),
                        "maxLength": param.get("maxLength"),
                        "minimum": param.get("minimum"),
                        "maximum": param.get("maximum"),
                        "pattern": param.get("pattern"),
                        "default": param.get("default"),
                        "example": param.get("example")
                    }
                query_schema[param_name] = self._parse_property_schema(param_name, param_spec, param_required)
        return query_schema
    
    def parse_path_params(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """解析路径参数定义"""
        path_schema = {}
        parameters = endpoint.get("parameters", [])
        for param in parameters:
            if isinstance(param, dict) and param.get("in") == "path":
                param_name = param.get("name", "")
                param_required = True  # 路径参数总是必填
                param_spec = param.get("schema", {})
                if not param_spec:
                    param_spec = {
                        "type": param.get("type", "string"),
                        "format": param.get("format"),
                        "pattern": param.get("pattern"),
                        "default": param.get("default"),
                        "example": param.get("example")
                    }
                path_schema[param_name] = self._parse_property_schema(param_name, param_spec, param_required)
        return path_schema
    
    def _infer_schema_from_ref(self, ref_path: str, endpoint_path: str, endpoint_method: str) -> Dict[str, Any]:
        """从$ref引用路径推断请求体Schema"""
        body_schema = {}
        
        ref_lower = ref_path.lower()
        path_lower = endpoint_path.lower()
        
        if "login" in ref_lower or "auth" in ref_lower and "login" in path_lower:
            body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
            body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
        
        elif "register" in ref_lower or "register" in path_lower or "signup" in ref_lower or "signup" in path_lower:
            body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
            body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
            body_schema["email"] = {"type": "string", "format": "email", "required": True, "description": "邮箱"}
        
        elif "user" in ref_lower and "create" not in ref_lower:
            body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
            body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
            body_schema["email"] = {"type": "string", "format": "email", "required": False, "description": "邮箱"}
        
        elif "project" in ref_lower:
            body_schema["name"] = {"type": "string", "required": True, "description": "项目名称"}
            body_schema["code"] = {"type": "string", "required": True, "description": "项目编码"}
            body_schema["description"] = {"type": "string", "required": False, "description": "项目描述"}
        
        elif "version" in ref_lower:
            body_schema["version_number"] = {"type": "string", "required": True, "description": "版本号"}
            body_schema["version_name"] = {"type": "string", "required": True, "description": "版本名称"}
            body_schema["description"] = {"type": "string", "required": False, "description": "版本描述"}
        
        elif "requirement" in ref_lower or "doc" in ref_lower:
            body_schema["title"] = {"type": "string", "required": True, "description": "文档标题"}
            body_schema["content"] = {"type": "string", "required": True, "description": "文档内容"}
        
        elif endpoint_method.upper() == "POST":
            if path_lower.endswith("/users") or "/users" in path_lower:
                body_schema["username"] = {"type": "string", "required": True, "description": "用户名"}
                body_schema["password"] = {"type": "string", "required": True, "description": "密码"}
                body_schema["email"] = {"type": "string", "format": "email", "required": False, "description": "邮箱"}
            elif path_lower.endswith("/projects") or "/projects" in path_lower:
                body_schema["name"] = {"type": "string", "required": True, "description": "名称"}
                body_schema["description"] = {"type": "string", "required": False, "description": "描述"}
            else:
                body_schema["name"] = {"type": "string", "required": True, "description": "名称"}
        
        elif endpoint_method.upper() in ["PUT", "PATCH"]:
            body_schema["id"] = {"type": "integer", "required": True, "description": "ID"}
            body_schema["name"] = {"type": "string", "required": False, "description": "名称"}
        
        logger.info(f"从$ref引用推断Schema: {ref_path} -> {body_schema}")
        return body_schema
    
    def _is_optional_type(self, prop_spec: Dict[str, Any]) -> bool:
        """判断字段类型是否可选（是否允许null）"""
        # 检查 anyOf/oneOf 是否包含 null 类型
        any_of = prop_spec.get("anyOf") or prop_spec.get("oneOf")
        if any_of:
            for type_spec in any_of:
                if type_spec.get("type") == "null":
                    return True  # 允许null，是可选字段
        
        # 检查是否有 default 值（有默认值的字段通常可选）
        if prop_spec.get("default") is not None:
            return True
        
        return False  # 不允许null，是必填字段
    
    def _parse_property_schema(self, name: str, spec: Dict[str, Any], required: bool) -> Dict[str, Any]:
        """解析单个属性的 Schema"""
        return {
            "name": name,
            "type": spec.get("type", "string"),
            "format": spec.get("format"),
            "required": required,
            "description": spec.get("description", ""),
            "enum": spec.get("enum"),
            "minLength": spec.get("minLength"),
            "maxLength": spec.get("maxLength"),
            "minimum": spec.get("minimum"),
            "maximum": spec.get("maximum"),
            "pattern": spec.get("pattern"),
            "default": spec.get("default"),
            "example": spec.get("example")
        }


class ExampleValueGenerator:
    """示例值生成器 - 根据 Schema 定义生成有效示例值"""
    
    def generate_valid_value(self, schema: Dict[str, Any]) -> Any:
        """根据 Schema 定义生成有效的示例值"""
        prop_type = schema.get("type", "string")
        prop_name = schema.get("name", "")
        prop_format = schema.get("format")
        prop_enum = schema.get("enum")
        prop_default = schema.get("default")
        prop_example = schema.get("example")
        
        # 优先使用默认值或示例值
        if prop_example is not None:
            return prop_example
        if prop_default is not None:
            return prop_default
        
        # 使用枚举的第一个值
        if prop_enum:
            return prop_enum[0]
        
        # 根据名称推断
        name_lower = prop_name.lower()
        if "username" in name_lower or "user" in name_lower:
            return "testuser"
        if "password" in name_lower or "pwd" in name_lower:
            return "Test@123456"
        if "email" in name_lower or "mail" in name_lower:
            return "test@example.com"
        if "phone" in name_lower or "mobile" in name_lower:
            return "13800138000"
        if "name" in name_lower:
            return "测试名称"
        if "id" in name_lower:
            if prop_type == "integer":
                return 1
            return "test_id_001"
        if "title" in name_lower:
            return "测试标题"
        if "content" in name_lower or "description" in name_lower:
            return "测试内容描述"
        if "token" in name_lower:
            return "test_token_abc123"
        if "url" in name_lower or "link" in name_lower:
            return "https://example.com"
        if "date" in name_lower:
            return "2026-01-01"
        if "time" in name_lower:
            return "2026-01-01T12:00:00Z"
        if "page" in name_lower:
            return 1
        if "size" in name_lower or "limit" in name_lower:
            return 10
        
        # 根据 format 推断
        if prop_format == "email":
            return "test@example.com"
        if prop_format == "uri" or prop_format == "url":
            return "https://example.com"
        if prop_format == "date":
            return "2026-01-01"
        if prop_format == "date-time":
            return "2026-01-01T12:00:00Z"
        if prop_format == "password":
            return "Test@123456"
        if prop_format == "uuid":
            return "00000000-0000-0000-0000-000000000001"
        
        # 根据 type 推断
        if prop_type == "string":
            return "test_value"
        if prop_type == "integer":
            return 1
        if prop_type == "number":
            return 1.0
        if prop_type == "boolean":
            return True
        if prop_type == "array":
            return ["item1"]
        if prop_type == "object":
            return {"key": "value"}
        
        return "test_value"


class InvalidValueGenerator:
    """无效值生成器 - 根据 Schema 约束生成违反约束的值
    
    基于 openapi-testgen 的规则:
    - MissingRequired: 缺少必填参数
    - InvalidType: 类型错误
    - InvalidPattern: 正则不匹配
    - InvalidEnum: 不在枚举范围
    - InvalidRange: 超出 min/max
    - InvalidLength: 超出 minLength/maxLength
    """
    
    def generate_invalid_values(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """根据 Schema 约束生成多个无效值，每个违反不同的约束"""
        invalid_cases = []
        
        prop_name = schema.get("name", "")
        prop_type = schema.get("type", "string")
        prop_required = schema.get("required", False)
        prop_enum = schema.get("enum")
        prop_pattern = schema.get("pattern")
        prop_min_length = schema.get("minLength")
        prop_max_length = schema.get("maxLength")
        prop_minimum = schema.get("minimum")
        prop_maximum = schema.get("maximum")
        prop_format = schema.get("format")
        
        # 1. Missing Required - 如果是必填参数，生成空值
        if prop_required:
            invalid_cases.append({
                "rule": "MissingRequired",
                "value": None,
                "description": f"缺少必填参数: {prop_name}",
                "name_suffix": "缺少必填参数"
            })
            # 也生成空字符串的情况
            if prop_type == "string":
                invalid_cases.append({
                    "rule": "EmptyRequired",
                    "value": "",
                    "description": f"必填参数为空字符串: {prop_name}",
                    "name_suffix": "空字符串"
                })
        
        # 2. Invalid Type - 类型错误
        if prop_type == "string":
            invalid_cases.append({
                "rule": "InvalidType",
                "value": 12345,
                "description": f"字符串参数传整数: {prop_name}",
                "name_suffix": "类型错误(整数)"
            })
        elif prop_type == "integer":
            invalid_cases.append({
                "rule": "InvalidType",
                "value": "not_a_number",
                "description": f"整数参数传字符串: {prop_name}",
                "name_suffix": "类型错误(字符串)"
            })
        elif prop_type == "boolean":
            invalid_cases.append({
                "rule": "InvalidType",
                "value": "not_a_boolean",
                "description": f"布尔参数传字符串: {prop_name}",
                "name_suffix": "类型错误(字符串)"
            })
        
        # 3. Invalid Pattern - 正则不匹配
        if prop_pattern:
            invalid_cases.append({
                "rule": "InvalidPattern",
                "value": "!!!invalid!!!",
                "description": f"参数值不符合正则约束 {prop_pattern}: {prop_name}",
                "name_suffix": "正则不匹配"
            })
        
        # 4. Invalid Enum - 不在枚举范围
        if prop_enum and len(prop_enum) > 0:
            invalid_cases.append({
                "rule": "InvalidEnum",
                "value": "invalid_enum_value_xyz",
                "description": f"参数值不在枚举范围 {prop_enum}: {prop_name}",
                "name_suffix": "无效枚举值"
            })
        
        # 5. Invalid Length - 超出长度限制
        if prop_min_length and prop_min_length > 0:
            # 字符串太短
            short_value = "x" * (prop_min_length - 1) if prop_min_length > 1 else ""
            invalid_cases.append({
                "rule": "TooShort",
                "value": short_value,
                "description": f"字符串长度不足最小值 {prop_min_length}: {prop_name}",
                "name_suffix": f"长度不足(min={prop_min_length})"
            })
        
        if prop_max_length:
            # 字符串太长
            long_value = "x" * (prop_max_length + 10)
            invalid_cases.append({
                "rule": "TooLong",
                "value": long_value,
                "description": f"字符串长度超过最大值 {prop_max_length}: {prop_name}",
                "name_suffix": f"长度超出(max={prop_max_length})"
            })
        
        # 6. Invalid Range - 超出数值范围
        if prop_minimum is not None:
            invalid_cases.append({
                "rule": "BelowMinimum",
                "value": prop_minimum - 100,
                "description": f"数值低于最小值 {prop_minimum}: {prop_name}",
                "name_suffix": f"低于最小值(min={prop_minimum})"
            })
        
        if prop_maximum is not None:
            invalid_cases.append({
                "rule": "AboveMaximum",
                "value": prop_maximum + 100,
                "description": f"数值超过最大值 {prop_maximum}: {prop_name}",
                "name_suffix": f"超过最大值(max={prop_maximum})"
            })
        
        # 7. Invalid Format - 格式错误
        if prop_format == "email":
            invalid_cases.append({
                "rule": "InvalidFormat",
                "value": "invalid-email-format",
                "description": f"邮箱格式错误: {prop_name}",
                "name_suffix": "邮箱格式错误"
            })
        elif prop_format == "uri" or prop_format == "url":
            invalid_cases.append({
                "rule": "InvalidFormat",
                "value": "invalid-url-format",
                "description": f"URL格式错误: {prop_name}",
                "name_suffix": "URL格式错误"
            })
        elif prop_format == "date":
            invalid_cases.append({
                "rule": "InvalidFormat",
                "value": "invalid-date-format",
                "description": f"日期格式错误: {prop_name}",
                "name_suffix": "日期格式错误"
            })
        
        # 如果没有生成任何无效值，生成一个默认的空值
        if not invalid_cases:
            invalid_cases.append({
                "rule": "EmptyValue",
                "value": "",
                "description": f"参数值为空: {prop_name}",
                "name_suffix": "空值"
            })
        
        return invalid_cases


class OpenApiTestGenerator:
    """OpenAPI 测试用例生成器 - 基于 Provider-Rule 架构"""
    
    SUCCESS_CODE = 10000
    
    def __init__(self):
        self.schema_parser = OpenApiSchemaParser()
        self.example_generator = ExampleValueGenerator()
        self.invalid_generator = InvalidValueGenerator()
    
    def generate_test_cases(self, endpoint: Dict[str, Any]) -> List[Dict[str, Any]]:
        """为单个接口生成测试用例"""
        cases = []
        
        method = endpoint.get("method", "GET")
        path = endpoint.get("path", "/")
        summary = endpoint.get("summary", "") or endpoint.get("description", "")
        responses = endpoint.get("responses", {})
        
        # 解析参数定义
        swagger_status = '有' if self.schema_parser.swagger_doc else '空'
        logger.info(f"解析 {method} {path}: swagger_doc={swagger_status}, components数={len(self.schema_parser.swagger_doc.get('components', {}).get('schemas', {})) if self.schema_parser.swagger_doc else 0}")
        body_schema = self.schema_parser.parse_request_body(endpoint)
        logger.info(f"解析结果: body_schema={body_schema}")
        
        query_schema = self.schema_parser.parse_query_params(endpoint)
        path_schema = self.schema_parser.parse_path_params(endpoint)
        
        # 检查是否有参数
        has_params = bool(body_schema) or bool(query_schema) or bool(path_schema)
        
        # 检查是否是登录接口
        is_login = self._is_login_endpoint(path, method)
        
        # 检查是否是无参数的简单GET接口
        is_simple_get = method == "GET" and not has_params and self._is_simple_get_path(path)
        
        logger.info(f"解析接口 {method} {path}: body={body_schema}, query={query_schema}, has_params={has_params}, is_login={is_login}, is_simple_get={is_simple_get}")
        
        # 1. 正常场景用例
        normal_case = self._generate_normal_case(endpoint, body_schema, query_schema, path_schema)
        cases.append(normal_case)
        
        # 2. 参数校验异常用例（仅对有参数的接口）
        if has_params and not is_simple_get:
            error_cases = self._generate_error_cases(endpoint, body_schema, query_schema, path_schema)
            cases.extend(error_cases)
        
        # 3. 认证用例
        if not is_login and endpoint.get("requires_auth"):
            auth_case = self._generate_auth_case(endpoint)
            cases.append(auth_case)
        
        # 简单GET接口只生成认证用例
        if is_simple_get and endpoint.get("requires_auth"):
            auth_case = self._generate_auth_case(endpoint)
            cases.append(auth_case)
        
        return cases
    
    def _is_login_endpoint(self, path: str, method: str) -> bool:
        """判断是否是登录接口"""
        path_lower = path.lower()
        login_paths = ["login", "auth/login", "signin", "sign-in", "token", "auth/token"]
        for lp in login_paths:
            if lp in path_lower or path_lower.endswith(lp):
                return method.upper() == "POST"
        return False
    
    def _is_simple_get_path(self, path: str) -> bool:
        """判断是否是无参数的简单GET路径"""
        path_lower = path.lower()
        simple_paths = [
            "/auth/me", "/users/me", "/user/me", "/profile", "/me",
            "/config", "/settings", "/current-user", "/current_user"
        ]
        for sp in simple_paths:
            if path_lower == sp or path_lower.endswith(sp):
                return True
        
        keywords = ["me", "current", "profile", "self"]
        for kw in keywords:
            if kw in path_lower:
                return True
        
        return False
    
    def _generate_normal_case(
        self, 
        endpoint: Dict[str, Any],
        body_schema: Dict[str, Any],
        query_schema: Dict[str, Any],
        path_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成正常场景用例"""
        method = endpoint.get("method", "GET")
        path = endpoint.get("path", "/")
        summary = endpoint.get("summary", "")
        responses = endpoint.get("responses", {})
        
        # 生成有效的参数值
        request_body = {}
        logger.info(f"_generate_normal_case: body_schema={body_schema}")
        for prop_name, prop_schema in body_schema.items():
            request_body[prop_name] = self.example_generator.generate_valid_value(prop_schema)
        
        query_params = {}
        for param_name, param_schema in query_schema.items():
            query_params[param_name] = self.example_generator.generate_valid_value(param_schema)
        
        path_params = {}
        for param_name, param_schema in path_schema.items():
            path_params[param_name] = self.example_generator.generate_valid_value(param_schema)
        
        # 特殊处理：登录接口强制使用测试账号
        if self._is_login_endpoint(path, method):
            logger.info(f"检测到登录接口: {path}, 强制使用测试账号")
            request_body["username"] = "admin"
            request_body["password"] = "admin123"
            logger.info(f"登录接口request_body已设置为: {request_body}")
        
        # 特殊处理：注册接口生成随机唯一用户名，避免冲突
        is_register_endpoint = "register" in path.lower() or "signup" in path.lower()
        if is_register_endpoint:
            timestamp = int(time.time() * 1000) % 100000  # 使用时间戳确保唯一性
            random_suffix = random.randint(1000, 9999)  # 添加随机数
            if "username" in request_body:
                request_body["username"] = f"testuser_{timestamp}_{random_suffix}"
                logger.info(f"注册接口生成随机用户名: {request_body['username']}")
            if "email" in request_body:
                request_body["email"] = f"test_{timestamp}_{random_suffix}@example.com"
                logger.info(f"注册接口生成随机邮箱: {request_body['email']}")
        
        # 特殊处理：注册接口强制添加confirm_password
        if is_register_endpoint:
            if "password" in request_body and "confirm_password" not in request_body:
                request_body["confirm_password"] = request_body["password"]
                logger.info(f"注册接口添加confirm_password: {request_body['confirm_password']}")
        
        logger.info(f"最终request_body: {request_body}")
        
        # 分析响应定义，推断业务码
        business_code_info = self._analyze_response_business_code(responses)
        
        # 判断是否是业务接口（有业务逻辑）
        is_business_api = self._is_business_api(endpoint)
        
        # 根据响应定义智能生成断言规则
        assert_rules = self._generate_smart_assert_rules(responses, "normal")
        
        # 动态生成验证预期
        if is_business_api and business_code_info["has_business_code"]:
            success_codes = business_code_info["success_codes"]
            success_code_str = str(success_codes[0]) if success_codes else "10000"
            if len(success_codes) > 1:
                success_code_str = "/".join(str(c) for c in success_codes[:3])
            test_step_expected = f"业务返回码{success_code_str}(成功)，响应数据结构正确"
            expected_result = f"业务返回码{success_code_str}，响应数据正确"
        elif is_business_api:
            test_step_expected = "业务返回码表示成功，响应数据结构正确"
            expected_result = "业务返回成功，响应数据正确"
        else:
            test_step_expected = "HTTP状态码200，响应正常"
            expected_result = "HTTP状态码200，响应正常"
        
        # 根据Swagger的responses定义动态提取expected_status
        # 成功状态码：200系列（200, 201, 204等）
        # 客户端错误：400系列（400, 401, 403, 404, 422等）
        success_status_codes = []
        client_error_status_codes = []
        
        for status_code in responses.keys():
            try:
                code_int = int(status_code)
                if 200 <= code_int < 300:
                    success_status_codes.append(code_int)
                elif 400 <= code_int < 500:
                    client_error_status_codes.append(code_int)
            except ValueError:
                # 忽略非数字状态码（如"default"）
                pass
        
        # 正常用例期望所有成功状态码
        if success_status_codes:
            expected_status_value = success_status_codes[0]  # 使用第一个成功状态码
        else:
            expected_status_value = 200  # Fallback
        
        logger.info(f"从Swagger responses提取状态码: 成功={success_status_codes}, 错误={client_error_status_codes}")
        
        return {
            "name": f"{method} {path} - 正常功能验证",
            "case_type": "normal",
            "priority": "P1",
            "description": f"正常场景测试: {summary}",
            "preconditions": "API服务正常运行，已获取有效认证token",
            "test_steps": [
                {"step": 1, "action": f"发送{method}请求到{path}", "expected": test_step_expected}
            ],
            "expected_status": expected_status_value,
            "expected_result": expected_result,
            "assert_rules": assert_rules,
            "query_params": query_params,
            "path_params": path_params,
            "request_body": request_body,
            "headers": {}
        }
    
    def _is_business_api(self, endpoint: Dict[str, Any]) -> bool:
        """判断是否是业务接口（有业务逻辑，需要验证业务返回码）"""
        path = endpoint.get("path", "").lower()
        method = endpoint.get("method", "").upper()
        summary = endpoint.get("summary", "").lower()
        
        # 业务接口关键词
        business_keywords = [
            "login", "register", "signup", "auth", "signin",
            "create", "add", "update", "modify", "delete", "remove",
            "submit", "save", "process", "execute", "approve", "reject",
            "user", "project", "version", "requirement", "test", "case",
            "upload", "download", "import", "export", "generate",
            "login请求", "登录", "注册", "创建", "添加", "更新", "删除"
        ]
        
        # 非业务接口关键词（健康检查、静态资源等）
        non_business_keywords = [
            "health", "ping", "status", "info", "version", "metrics",
            "config", "setting", "option", "list", "query", "search", "get",
            "healthcheck", "heartbeat", "alive", "ready"
        ]
        
        # 检查是否是非业务接口
        for kw in non_business_keywords:
            if kw in path or kw in summary:
                if method == "GET":
                    return False
        
        # 检查是否是业务接口
        for kw in business_keywords:
            if kw in path or kw in summary:
                return True
        
        # POST/PUT/DELETE/PATCH 默认认为是业务接口
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            return True
        
        # 有请求体的接口认为是业务接口
        request_body = endpoint.get("requestBody") or endpoint.get("request_body")
        if request_body:
            return True
        
        return False
    
    def _analyze_response_business_code(self, responses: Dict[str, Any]) -> Dict[str, Any]:
        """分析响应定义，推断业务成功码
        
        返回：
        {
            "has_business_code": bool,  # 是否有业务返回码
            "success_codes": list,      # 成功的业务码列表（从Swagger提取）
            "code_field": str,          # 业务码字段名（通常是code或status）
            "error_codes": list         # 错误的业务码列表（从错误响应提取）
        }
        """
        result = {
            "has_business_code": False,
            "success_codes": [],       # 空列表，将从Swagger响应定义填充
            "code_field": "code",
            "error_codes": []          # 空列表，将从错误响应填充
        }
        
        # 分析200/201响应提取成功码
        response_200 = responses.get("200") or responses.get("201") or {}
        content = response_200.get("content", {})
        
        # 尝试多种content类型
        for content_type in ["application/json", "*/*", "text/plain"]:
            content_data = content.get(content_type, {})
            if not content_data:
                continue
            
            schema = content_data.get("schema", {})
            examples = content_data.get("examples", {})
            
            # 1. 从examples中提取业务码
            if examples:
                for example_name, example_data in examples.items():
                    example_value = example_data.get("value", {})
                    if isinstance(example_value, dict):
                        # 查找业务码字段
                        for code_field in ["code", "status", "errcode", "errno", "resultCode", "result_code"]:
                            if code_field in example_value:
                                code_value = example_value[code_field]
                                result["has_business_code"] = True
                                result["code_field"] = code_field
                                if isinstance(code_value, (int, str)):
                                    # 成功响应中的码，加入成功码列表
                                    if code_value not in result["success_codes"]:
                                        result["success_codes"].append(code_value)
                                break
            
            # 2. 从schema中分析
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                
                # 检查是否有业务码字段
                for code_field in ["code", "status", "errcode", "errno", "resultCode", "result_code"]:
                    if code_field in properties:
                        code_schema = properties[code_field]
                        result["has_business_code"] = True
                        result["code_field"] = code_field
                        
                        # 从enum中提取
                        if code_schema.get("enum"):
                            enum_values = code_schema.get("enum", [])
                            # 通常第一个enum值是成功码
                            if enum_values:
                                result["success_codes"] = enum_values[:3] if len(enum_values) > 3 else enum_values
                        
                        # 从default/example中提取
                        if code_schema.get("default"):
                            default_value = code_schema.get("default")
                            if default_value not in result["success_codes"]:
                                result["success_codes"].insert(0, default_value)
                        
                        if code_schema.get("example"):
                            example_value = code_schema.get("example")
                            if example_value not in result["success_codes"]:
                                result["success_codes"].insert(0, example_value)
                        
                        break
                
                # 检查是否有data/result字段（有这些字段说明是业务包装）
                if "data" in properties or "result" in properties or "resultData" in properties:
                    result["has_business_code"] = True
        
        # 3. 分析错误响应（400, 401等）
        for status_code in ["400", "401", "403", "404", "422", "500"]:
            error_response = responses.get(status_code, {})
            error_content = error_response.get("content", {})
            for content_type in ["application/json", "*/*"]:
                error_data = error_content.get(content_type, {})
                if not error_data:
                    continue
                
                error_examples = error_data.get("examples", {})
                if error_examples:
                    for example_name, example_data in error_examples.items():
                        example_value = example_data.get("value", {})
                        if isinstance(example_value, dict):
                            code_field = result["code_field"]
                            if code_field in example_value:
                                code_value = example_value[code_field]
                                if isinstance(code_value, (int, str)) and code_value not in result["error_codes"]:
                                    result["error_codes"].append(code_value)
        
        logger.info(f"业务码分析结果: {result}")
        return result
        
        # 检查是否是业务接口
        for kw in business_keywords:
            if kw in path or kw in summary:
                return True
        
        # POST/PUT/DELETE/PATCH 默认认为是业务接口
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            return True
        
        # 有请求体的接口认为是业务接口
        request_body = endpoint.get("requestBody") or endpoint.get("request_body")
        if request_body:
            return True
        
        return False
    
    def _generate_smart_assert_rules(self, responses: Dict[str, Any], case_type: str) -> List[Dict[str, Any]]:
        """根据响应定义智能生成断言规则"""
        rules = []
        
        # 从Swagger responses提取所有状态码
        success_status_codes = []
        client_error_status_codes = []
        
        for status_code in responses.keys():
            try:
                code_int = int(status_code)
                if 200 <= code_int < 300:
                    success_status_codes.append(code_int)
                elif 400 <= code_int < 500:
                    client_error_status_codes.append(code_int)
            except ValueError:
                pass
        
        # 基础HTTP状态码断言 - 使用Swagger定义的状态码
        if case_type == "normal":
            # 正常用例：期望成功状态码（200系列）
            http_status_values = success_status_codes if success_status_codes else [200, 201, 204]
            rules.append({
                "type": "http_status",
                "value": http_status_values,
                "description": f"HTTP状态码应为成功状态({'/'.join(map(str, http_status_values))})"
            })
        elif case_type == "error":
            # 异常用例：期望错误状态码（400系列），但也接受成功（某些验证错误可能通过）
            http_status_values = client_error_status_codes if client_error_status_codes else [400, 401, 403, 404, 422, 500]
            # 异常场景也可能返回成功（如验证通过但业务失败）
            if success_status_codes and 200 not in http_status_values:
                http_status_values.append(200)
            rules.append({
                "type": "http_status",
                "value": http_status_values,
                "description": f"HTTP状态码可能为错误状态({'/'.join(map(str, http_status_values[:5]))})"
            })
        elif case_type == "auth":
            # 认证用例：期望401/403
            rules.append({
                "type": "http_status",
                "value": [401, 403],
                "description": "HTTP状态码应为401(未授权)或403(禁止访问)"
            })
        
        # 分析响应结构
        response_200 = responses.get("200") or responses.get("201") or {}
        content = response_200.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        
        # 检测响应类型
        response_type = self._detect_response_type(schema)
        
        # 检查是否有code和message字段
        has_code_field = False
        has_message_field = False
        if schema and schema.get("type") == "object":
            properties = schema.get("properties", {})
            has_code_field = "code" in properties
            has_message_field = "message" in properties
        
        if case_type == "normal":
            if response_type == "standard":
                # 标准响应格式 {code, data, message}
                rules.append({
                    "type": "json_in",
                    "field": "code",
                    "value": [0, 200, 10000, 20000],
                    "description": "业务返回码应为成功状态",
                    "skip_if_missing": True
                })
                rules.append({
                    "type": "json_not_null",
                    "field": "data",
                    "description": "响应数据data字段不应为空",
                    "skip_if_missing": True
                })
            elif response_type == "paged":
                # 分页响应格式 {page, items, total, page_size}
                rules.append({
                    "type": "json_contains",
                    "field": "items",
                    "description": "响应应包含items列表",
                    "skip_if_missing": True
                })
                rules.append({
                    "type": "json_not_null",
                    "field": "total",
                    "description": "响应应包含total字段",
                    "skip_if_missing": True
                })
            elif response_type == "direct":
                # 直接返回数据（无包装）
                pass  # 只检查HTTP状态码
            elif response_type == "empty":
                # 空响应（DELETE等）
                pass  # 只检查HTTP状态码
            
            # 通用断言：检查响应不为空（除非是空响应）
            if response_type not in ["empty"]:
                rules.append({
                    "type": "response_not_empty",
                    "description": "响应体不应为空"
                })
        
        elif case_type == "error":
            rules.append({
                "type": "json_in",
                "field": "code",
                "value": [10001, 40001, 40002, 40003, 50001, -1, 400, 401, 403, 404, 422, 500],
                "description": "业务返回码应为错误状态",
                "skip_if_missing": True
            })
        
        elif case_type == "auth":
            # 认证测试：主要验证HTTP状态码401/403
            # 不期望200状态码，因为认证失败应该返回401/403
            rules.append({
                "type": "http_status",
                "value": [401, 403],
                "description": "HTTP状态码应为401(未授权)或403(禁止访问)"
            })
            
            if has_code_field:
                # 如果有业务码字段，验证认证相关的错误码
                rules.append({
                    "type": "json_in",
                    "field": "code",
                    "value": [40101, 40301, 10001, 40001],
                    "description": "业务返回码应为认证错误(40101/40301)",
                    "skip_if_missing": True
                })
            
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
        
        return rules
    
    def _detect_response_type(self, schema: Dict[str, Any]) -> str:
        """检测响应类型"""
        if not schema:
            return "unknown"
        
        schema_type = schema.get("type", "")
        
        if schema_type == "object":
            properties = schema.get("properties", {})
            
            # 检测标准响应格式 {code, data, message}
            if "code" in properties and "data" in properties:
                return "standard"
            
            # 检测分页响应格式 {page, items, total}
            if "items" in properties and "total" in properties:
                return "paged"
            if "page" in properties and "items" in properties:
                return "paged"
            if "data" in properties and "data" in schema.get("properties", {}):
                data_schema = properties.get("data", {})
                if data_schema.get("type") == "array":
                    return "paged"
            
            # 其他对象格式
            return "direct"
        
        elif schema_type == "array":
            return "direct"
        
        elif schema_type == "string" or schema_type == "integer" or schema_type == "number":
            return "direct"
        
        # 空响应
        if schema.get("description") and "no content" in schema.get("description", "").lower():
            return "empty"
        
        return "unknown"
    
    def _generate_error_cases(
        self,
        endpoint: Dict[str, Any],
        body_schema: Dict[str, Any],
        query_schema: Dict[str, Any],
        path_schema: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """生成参数校验异常用例 - 每个参数生成多个异常场景"""
        cases = []
        
        method = endpoint.get("method", "GET")
        path = endpoint.get("path", "/")
        
        # 为每个 body 参数生成异常用例
        for prop_name, prop_schema in body_schema.items():
            invalid_values = self.invalid_generator.generate_invalid_values(prop_schema)
            
            # 只取前2个最典型的异常场景（避免用例过多）
            for invalid_case in invalid_values[:2]:
                # 构建请求体：只修改当前参数，其他参数使用有效值
                error_body = {}
                for other_name, other_schema in body_schema.items():
                    if other_name == prop_name:
                        if invalid_case["value"] is None:
                            continue  # 缺少参数时不包含该字段
                        error_body[other_name] = invalid_case["value"]
                    else:
                        error_body[other_name] = self.example_generator.generate_valid_value(other_schema)
                
                error_case = {
                    "name": f"{method} {path} - {prop_name}{invalid_case['name_suffix']}",
                    "case_type": "error",
                    "priority": "P2",
                    "description": f"异常场景测试: {invalid_case['description']}",
                    "preconditions": "API服务正常运行",
                    "test_steps": [
                        {"step": 1, "action": f"发送{method}请求到{path}，请求体: {json.dumps(error_body, ensure_ascii=False)}", "expected": "HTTP状态码400/422，业务返回错误码"}
                    ],
                    "expected_status": 400,
                    "expected_result": "业务返回错误码，错误信息明确",
                    "assert_rules": [
                        {"type": "http_status", "value": [400, 401, 403, 404, 422, 500, 200], "description": "HTTP状态码可能为错误状态"},
                        {"type": "json_in", "field": "code", "value": [10001, 40001, 40002, 40003, 50001, -1, 400, 401, 403, 404, 422, 500], "description": "业务返回码应为错误状态", "skip_if_missing": True}
                    ],
                    "query_params": {},
                    "request_body": error_body,
                    "headers": {},
                    "rule": invalid_case["rule"]
                }
                cases.append(error_case)
        
        # 为每个 query 参数生成异常用例
        for param_name, param_schema in query_schema.items():
            invalid_values = self.invalid_generator.generate_invalid_values(param_schema)
            
            for invalid_case in invalid_values[:2]:
                error_query = {}
                for other_name, other_schema in query_schema.items():
                    if other_name == param_name:
                        if invalid_case["value"] is None:
                            continue
                        error_query[other_name] = invalid_case["value"]
                    else:
                        error_query[other_name] = self.example_generator.generate_valid_value(other_schema)
                
                error_case = {
                    "name": f"{method} {path} - {param_name}{invalid_case['name_suffix']}",
                    "case_type": "error",
                    "priority": "P2",
                    "description": f"异常场景测试: {invalid_case['description']}",
                    "preconditions": "API服务正常运行",
                    "test_steps": [
                        {"step": 1, "action": f"发送{method}请求到{path}，查询参数: {json.dumps(error_query, ensure_ascii=False)}", "expected": "HTTP状态码400/422，业务返回错误码"}
                    ],
                    "expected_status": 400,
                    "expected_result": "业务返回错误码",
                    "assert_rules": [
                        {"type": "http_status", "value": [400, 401, 403, 404, 422, 500, 200]},
                        {"type": "json_in", "field": "code", "value": [10001, 40001, 40002, 40003, 50001, -1, 400, 401, 403, 404, 422, 500], "skip_if_missing": True}
                    ],
                    "query_params": error_query,
                    "request_body": {},
                    "headers": {},
                    "rule": invalid_case["rule"]
                }
                cases.append(error_case)
        
        # 限制异常用例数量，避免过多
        return cases[:6]  # 每个接口最多6个异常用例
    
    def _generate_auth_case(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """生成认证错误用例
        
        改进：智能处理认证失败响应
        - 接受HTTP 401/403状态码（认证失败）
        - 如果响应有业务码，验证认证相关的错误码（40101等）
        - 如果响应无业务码（只有HTTP状态码），接受401/403
        """
        method = endpoint.get("method", "GET")
        path = endpoint.get("path", "/")
        
        return {
            "name": f"{method} {path} - 认证错误验证",
            "case_type": "auth",
            "priority": "P1",
            "description": "认证测试: 验证未携带认证信息时返回401/403或认证错误码",
            "preconditions": "API服务需要认证",
            "test_steps": [
                {"step": 1, "action": f"发送{method}请求，不携带认证token", "expected": "HTTP状态码401/403，或业务返回认证错误码"}
            ],
            "expected_status": 401,
            "expected_result": "HTTP 401/403或业务认证错误码",
            "assert_rules": [
                {"type": "http_status", "value": [401, 403], "description": "HTTP状态码应为401(未授权)或403(禁止访问)"},
                {"type": "json_in", "field": "code", "value": [40101, 40301, 10001, 40001], "description": "如果有业务码字段，应为认证错误码", "skip_if_missing": True}
            ],
            "query_params": {},
            "request_body": {},
            "headers": {}
        }