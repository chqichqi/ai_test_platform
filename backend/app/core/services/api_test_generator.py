"""
API测试用例自动生成服务
通过AI分析Swagger文档，自动生成可执行的测试用例
"""

import json
import re
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.core.logger import logger
from app.core.models.api_test import ApiDefinition, ApiEndpoint, ApiTestCase
from app.core.models.project import Version
from app.core.services.llm_service import LLMService


class ApiTestGeneratorService:
    """API测试用例生成服务"""
    
    SYSTEM_PROMPT = """你是一个专业的API测试工程师，需要根据Swagger文档中的接口信息生成详细的测试用例。

生成的测试用例必须：
1. 包含完整的前置条件（如：需要登录、需要先创建资源等）
2. 包含详细的测试步骤（每个步骤包含action和expected）
3. 包含可执行的请求参数（headers、query_params、request_body）
4. 包含断言规则（用于验证响应）
5. 测试用例必须可以直接运行执行

请严格按照JSON格式返回测试用例数组。"""

    CASE_GENERATION_PROMPT = """请根据以下接口信息生成测试用例。

## 接口信息
- 路径: {path}
- 方法: {method}
- 描述: {summary}
- 标签: {tag}
- 参数: {parameters}
- 请求体定义: {request_body}
- 响应定义: {responses}
- 认证要求: {security}

## 生成要求
生成以下类型的测试用例（根据接口特点选择合适的类型）：

1. **正常场景用例**（{include_normal}）：
   - 使用合理的参数值
   - 预期返回成功状态码（200/201等）
   - 验证响应数据的正确性

2. **异常场景用例**（{include_error}）：
   - 参数缺失或格式错误
   - 预期返回400/422等错误状态码
   - 验证错误消息

3. **边界值用例**（{include_boundary}）：
   - 参数边界值测试（空值、最大值、最小值）
   - 特殊字符测试

4. **认证/权限用例**（{include_auth}）：
   - 未认证访问测试
   - 权限不足测试

## 输出格式
请返回JSON数组，每个用例包含以下字段：

```json
[
  {{
    "name": "用例名称（包含接口路径和测试类型）",
    "case_type": "normal/error/boundary/auth",
    "priority": "P0/P1/P2/P3",
    "description": "用例描述",
    "preconditions": "前置条件（如：用户已登录、数据已准备等）",
    "test_steps": [
      {{\"step\": 1, \"action\": \"发送请求\", \"expected\": \"返回状态码200\"}}
    ],
    "headers": {{\"Content-Type\": \"application/json\"}},
    "query_params": {{}},
    "request_body": {{}},
    "expected_status": 200,
    "expected_result": "预期结果描述",
    "assert_rules": [
      {{\"type\": \"status_eq\", \"value\": 200, \"description\": \"状态码正确\"}}
    ]
  }}
]
```

## 参数值建议
- 字符串参数：使用test、example等测试值
- 数字参数：使用1、100等边界值
- ID参数：使用占位符RESOURCE_ID
- 认证token：使用占位符AUTH_TOKEN

## 断言规则类型说明
- status_eq: 状态码等于指定值
- json_contains: 响应包含指定字段
- json_type: 字段类型检查
- json_value_eq: 字段值等于

最多生成 {max_cases} 个测试用例。只返回JSON数组，不要其他解释文字。"""

    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
        self.swagger_doc = None
    
    async def fetch_swagger(self, swagger_url: str) -> Optional[Dict[str, Any]]:
        """获取Swagger文档内容，支持多种格式"""
        
        swagger_url = swagger_url.strip()
        
        # 转换中文冒号为英文冒号
        swagger_url = swagger_url.replace('：', ':')
        
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(swagger_url)
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "").lower()
                content = response.text
                
                if "json" in content_type or content.strip().startswith("{") or content.strip().startswith("["):
                    try:
                        return response.json()
                    except:
                        pass
                
                if "yaml" in content_type or "yml" in swagger_url.lower():
                    try:
                        import yaml
                        return yaml.safe_load(content)
                    except:
                        pass
                
                if swagger_url.endswith("/docs") or swagger_url.endswith("/docs/") or "/docs" in swagger_url:
                    json_url = swagger_url.replace("/docs", "/openapi.json").replace("/docs/", "/openapi.json")
                    if json_url.endswith("/"):
                        json_url = json_url.rstrip("/") + ".json"
                    logger.info(f"Detected Swagger UI page, trying JSON URL: {json_url}")
                    
                    try:
                        json_response = await client.get(json_url)
                        json_response.raise_for_status()
                        return json_response.json()
                    except Exception as e:
                        logger.warning(f"Failed to fetch JSON from {json_url}: {e}, trying to parse HTML")
                
                if "html" in content_type or content.strip().startswith("<") or "<!doctype" in content.lower():
                    logger.info("Detected HTML page, parsing DOM to extract API info")
                    return self._parse_swagger_html(content, swagger_url)
                
                try:
                    return response.json()
                except:
                    try:
                        import yaml
                        return yaml.safe_load(content)
                    except:
                        pass
                
                logger.warning(f"Content from {swagger_url} is neither JSON nor YAML, trying AI extraction")
                return await self._extract_api_from_content(content, swagger_url)
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {swagger_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch swagger from {swagger_url}: {str(e)}")
            return None
    
    def _parse_swagger_html(self, html_content: str, base_url: str) -> Optional[Dict[str, Any]]:
        """解析Swagger UI HTML页面，提取API信息"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            swagger_data = {
                "openapi": "3.0.0",
                "info": {
                    "title": "API文档",
                    "version": "1.0.0"
                },
                "paths": {}
            }
            
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    content = script.string
                    if 'spec' in content or 'swagger' in content.lower():
                        json_match = re.search(r'"spec"\s*:\s*(\{[\s\S]*?\})', content)
                        if json_match:
                            try:
                                spec_json = json.loads(json_match.group(1))
                                if "paths" in spec_json:
                                    return spec_json
                            except:
                                pass
                        
                        json_match = re.search(r'(\{[\s\S]*"paths"[\s\S]*\})', content)
                        if json_match:
                            try:
                                return json.loads(json_match.group(1))
                            except:
                                pass
            
            path_sections = soup.find_all(['div', 'section'], class_=re.compile(r'(path|endpoint|operation)', re.I))
            
            for section in path_sections:
                path_elem = section.find(['span', 'div', 'a'], class_=re.compile(r'(path|route)', re.I))
                method_elem = section.find(['span', 'div'], class_=re.compile(r'(method|verb|get|post|put|delete|patch)', re.I))
                
                if path_elem and method_elem:
                    path_text = path_elem.get_text(strip=True)
                    method_text = method_elem.get_text(strip=True).upper()
                    
                    if method_text in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        summary_elem = section.find(['span', 'div', 'p'], class_=re.compile(r'(summary|description)', re.I))
                        summary = summary_elem.get_text(strip=True) if summary_elem else ""
                        
                        if path_text not in swagger_data["paths"]:
                            swagger_data["paths"][path_text] = {}
                        
                        swagger_data["paths"][path_text][method_text.lower()] = {
                            "summary": summary,
                            "responses": {"200": {"description": "成功"}}
                        }
            
            title_elem = soup.find(['title', 'h1', 'h2'])
            if title_elem:
                swagger_data["info"]["title"] = title_elem.get_text(strip=True)
            
            if swagger_data["paths"]:
                logger.info(f"Parsed {len(swagger_data['paths'])} paths from HTML")
                return swagger_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to parse Swagger HTML: {str(e)}")
            return None
    
    async def _extract_api_from_content(self, content: str, url: str) -> Optional[Dict[str, Any]]:
        """使用AI从任意内容中提取API信息"""
        try:
            example_json = '''
{
  "openapi": "3.0.0",
  "info": {"title": "API文档", "version": "1.0.0"},
  "paths": {
    "/api/users": {
      "get": {"summary": "获取用户列表", "responses": {"200": {"description": "成功"}}},
      "post": {"summary": "创建用户", "responses": {"201": {"description": "创建成功"}}}
    }
  }
}
'''
            
            prompt = "请从以下网页内容中提取所有API接口信息，返回OpenAPI格式的JSON。\n\n"
            prompt += f"URL: {url}\n\n"
            prompt += f"内容片段:\n{content[:10000]}\n\n"
            prompt += "请返回标准OpenAPI JSON格式，包含paths对象，每个路径下包含对应的HTTP方法和基本信息。\n"
            prompt += "示例格式:\n```json\n" + example_json + "\n```\n\n"
            prompt += "只返回JSON，不要其他解释。"

            response = self.llm_service.call_llm(prompt, temperature=0.3,
                                                 max_tokens=self.llm_service.get_scaled_max_tokens(0.1, 8000))
            
            if response:
                json_match = re.search(r'\{[\s\S]*"paths"[\s\S]*\}', response)
                if json_match:
                    try:
                        return json.loads(json_match.group(0))
                    except:
                        pass
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract API from content: {str(e)}")
            return None
    
    def parse_endpoints(self, swagger: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析Swagger文档中的接口，识别认证需求"""
        endpoints = []
        paths = swagger.get("paths", {})
        
        # 解析认证定义
        security_definitions = self._parse_security_definitions(swagger)
        
        # 获取全局认证配置（用于没有显式security的接口）
        global_security = swagger.get("security", [])
        has_global_security = len(global_security) > 0 and len(security_definitions) > 0
        
        # 识别登录接口（通常是 /login, /auth/login, /token 等）
        login_endpoint = self._identify_login_endpoint(paths)
        
        logger.info(f"Swagger解析: 全局认证配置={has_global_security}, 认证定义数={len(security_definitions)}")
        
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue
                
                tags = spec.get("tags", [])
                tag = tags[0] if tags else None
                
                # 检查接口是否需要认证（改进的判断逻辑）
                endpoint_security = spec.get("security")
                
                # 判断逻辑：
                # 1. 如果接口显式设置了security字段：
                #    - security: [] 空数组 → 公开接口，不需要认证
                #    - security: [{"bearerAuth": []}] → 需要认证
                # 2. 如果接口没有security字段：
                #    - 使用全局security配置判断
                if endpoint_security is not None:
                    # 接口显式设置了security
                    if isinstance(endpoint_security, list) and len(endpoint_security) == 0:
                        # security: [] → 公开接口，不需要认证
                        requires_auth = False
                        logger.debug(f"接口 {method} {path} 是公开接口（security: []）")
                    else:
                        # security: [{"bearerAuth": []}] → 需要认证
                        requires_auth = True
                        logger.debug(f"接口 {method} {path} 需要认证（security: {endpoint_security}）")
                else:
                    # 接口没有显式security字段，使用全局配置
                    requires_auth = has_global_security
                    if requires_auth:
                        logger.debug(f"接口 {method} {path} 需要认证（继承全局security）")
                    else:
                        logger.debug(f"接口 {method} {path} 不需要认证（无认证配置）")
                
                # 检查是否是登录接口
                is_login_endpoint = self._is_login_endpoint(path, method.upper(), spec)
                
                # 登录接口本身不需要前置认证
                if is_login_endpoint:
                    requires_auth = False
                    logger.debug(f"接口 {method} {path} 是登录接口，不需要前置认证")
                
                endpoint = {
                    "path": path,
                    "method": method.upper(),
                    "tag": tag,
                    "summary": spec.get("summary", ""),
                    "description": spec.get("description", ""),
                    "parameters": spec.get("parameters", []),
                    "request_body": spec.get("requestBody") or spec.get("body"),
                    "responses": spec.get("responses", {}),
                    "security": endpoint_security if endpoint_security is not None else global_security,
                    "security_definitions": security_definitions,
                    "requires_auth": requires_auth,
                    "is_login_endpoint": is_login_endpoint,
                    "deprecated": spec.get("deprecated", False)
                }
                endpoints.append(endpoint)
        
        # 统计认证需求
        auth_required_count = sum(1 for ep in endpoints if ep.get("requires_auth"))
        public_count = len(endpoints) - auth_required_count
        logger.info(f"解析完成: 共{len(endpoints)}个接口，需要认证{auth_required_count}个，公开接口{public_count}个")
        
        return endpoints
    
    def _parse_security_definitions(self, swagger: Dict[str, Any]) -> Dict[str, Any]:
        """解析Swagger中的认证定义"""
        security_defs = {}
        
        # OpenAPI 3.0 格式
        components = swagger.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        for name, scheme in security_schemes.items():
            security_defs[name] = {
                "type": scheme.get("type", "apiKey"),
                "name": scheme.get("name", "Authorization"),
                "in": scheme.get("in", "header"),
                "description": scheme.get("description", "")
            }
        
        # Swagger 2.0 格式
        swagger_security = swagger.get("securityDefinitions", {})
        for name, scheme in swagger_security.items():
            if name not in security_defs:
                security_defs[name] = {
                    "type": scheme.get("type", "apiKey"),
                    "name": scheme.get("name", "Authorization"),
                    "in": scheme.get("in", "header"),
                    "description": scheme.get("description", "")
                }
        
        # 全局安全要求
        global_security = swagger.get("security", [])
        if global_security and not security_defs:
            # 如果有全局安全要求但没有定义，默认使用Bearer
            security_defs["default_auth"] = {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "默认认证"
            }
        
        return security_defs
    
    def _identify_login_endpoint(self, paths: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """识别登录接口"""
        login_paths = ["login", "auth/login", "signin", "sign-in", "token", "auth/token", "authenticate"]
        
        for path, methods in paths.items():
            path_lower = path.lower().rstrip("/")
            for login_path in login_paths:
                if login_path in path_lower or path_lower.endswith(login_path):
                    for method, spec in methods.items():
                        if method.upper() == "POST":
                            return {
                                "path": path,
                                "method": "POST",
                                "summary": spec.get("summary", "登录接口"),
                                "parameters": spec.get("parameters", []),
                                "request_body": spec.get("requestBody") or spec.get("body"),
                                "responses": spec.get("responses", {})
                            }
        
        return None
    
    def _is_login_endpoint(self, path: str, method: str, spec: Dict[str, Any]) -> bool:
        """判断是否是登录接口"""
        login_paths = ["login", "auth/login", "signin", "sign-in", "token", "auth/token", "authenticate"]
        path_lower = path.lower().rstrip("/")
        
        for login_path in login_paths:
            if login_path in path_lower or path_lower.endswith(login_path):
                return method.upper() == "POST"
        
        # 检查summary或description中是否有登录相关关键词
        summary = spec.get("summary", "").lower()
        description = spec.get("description", "").lower()
        login_keywords = ["login", "signin", "authenticate", "认证", "登录"]
        
        for keyword in login_keywords:
            if keyword in summary or keyword in description:
                return method.upper() == "POST"
        
        return False
    
    def _extract_request_params_from_endpoint(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """从Swagger endpoint中提取请求参数，生成示例值"""
        query_params = {}
        path_params = {}
        request_body = {}
        headers = {}
        
        parameters = endpoint.get("parameters", [])
        
        for param in parameters:
            if isinstance(param, dict):
                param_name = param.get("name", "")
                param_in = param.get("in", "query")
                param_required = param.get("required", False)
                
                # Swagger 2.0 格式：body 参数直接在 parameters 中
                if param_in == "body":
                    body_schema = param.get("schema", {})
                    if body_schema.get("type") == "object":
                        properties = body_schema.get("properties", {})
                        required_fields = body_schema.get("required", [])
                        
                        for prop_name, prop_spec in properties.items():
                            prop_type = prop_spec.get("type", "string")
                            prop_default = prop_spec.get("default")
                            prop_example = prop_spec.get("example")
                            is_required = prop_name in required_fields
                            
                            example_value = self._generate_param_example(
                                prop_name, prop_type, prop_default, prop_example, is_required
                            )
                            request_body[prop_name] = example_value
                    continue
                
                param_type = param.get("type") or param.get("schema", {}).get("type", "string")
                param_default = param.get("default") or param.get("schema", {}).get("default")
                param_example = param.get("example")
                
                # 生成示例值
                example_value = self._generate_param_example(
                    param_name, param_type, param_default, param_example, param_required
                )
                
                if param_in == "query":
                    query_params[param_name] = example_value
                elif param_in == "path":
                    path_params[param_name] = example_value
                elif param_in == "header":
                    headers[param_name] = example_value
        
        # 处理 OpenAPI 3.0 格式的 requestBody
        request_body_spec = endpoint.get("request_body")
        if request_body_spec and not request_body:
            # OpenAPI 3.0 格式：requestBody.content.application/json.schema
            content = request_body_spec.get("content", {})
            
            # 支持 application/json
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})
            
            # 也支持直接在 requestBody 中有 schema（某些简化格式）
            if not schema:
                schema = request_body_spec.get("schema", {})
            
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                required_fields = schema.get("required", [])
                
                for prop_name, prop_spec in properties.items():
                    prop_type = prop_spec.get("type", "string")
                    prop_default = prop_spec.get("default")
                    prop_example = prop_spec.get("example")
                    is_required = prop_name in required_fields
                    
                    example_value = self._generate_param_example(
                        prop_name, prop_type, prop_default, prop_example, is_required
                    )
                    request_body[prop_name] = example_value
            
            # 处理 $ref 引用（简化处理，直接生成示例）
            elif schema.get("$ref"):
                ref_path = schema.get("$ref", "")
                # 从引用路径推断类型，生成示例
                if "Login" in ref_path or "User" in ref_path:
                    request_body = {"username": "testuser", "password": "test123456"}
        
        # 特殊处理：登录接口如果没有参数，使用默认参数
        path = endpoint.get("path", "").lower()
        method = endpoint.get("method", "POST")
        if not request_body and self._is_login_endpoint(path, method, endpoint):
            request_body = {"username": "testuser", "password": "test123456"}
            logger.info(f"登录接口 {path} 使用默认参数: {request_body}")
        
        logger.debug(f"提取参数: query={query_params}, path={path_params}, body={request_body}")
        
        return {
            "query_params": query_params,
            "path_params": path_params,
            "request_body": request_body,
            "headers": headers
        }
    
    def _generate_param_example(
        self, 
        name: str, 
        param_type: str, 
        default: Any = None,
        example: Any = None,
        required: bool = False
    ) -> Any:
        """根据参数类型生成示例值"""
        # 优先使用提供的示例值或默认值
        if example is not None:
            return example
        if default is not None:
            return default
        
        # 根据参数名称和类型生成智能示例
        name_lower = name.lower()
        
        # 根据常见参数名称推断示例值
        if "id" in name_lower:
            if param_type == "integer":
                return 1
            elif param_type == "string":
                return "id_001"
        elif "name" in name_lower:
            return "test_name"
        elif "email" in name_lower or "mail" in name_lower:
            return "test@example.com"
        elif "phone" in name_lower or "mobile" in name_lower:
            return "13800138000"
        elif "username" in name_lower or "user" in name_lower:
            return "testuser"
        elif "password" in name_lower or "pwd" in name_lower:
            return "test123456"
        elif "token" in name_lower:
            return "test_token_123"
        elif "date" in name_lower or "time" in name_lower:
            return "2026-01-01"
        elif "page" in name_lower:
            return 1
        elif "size" in name_lower or "limit" in name_lower:
            return 10
        elif "status" in name_lower:
            return 1
        elif "type" in name_lower:
            return 1
        elif "url" in name_lower or "link" in name_lower:
            return "https://example.com"
        elif "file" in name_lower or "path" in name_lower:
            return "/test/path"
        
        # 根据类型生成通用示例
        type_examples = {
            "string": "test_value",
            "integer": 1,
            "number": 1.0,
            "boolean": True,
            "array": ["item1"],
            "object": {"key": "value"}
        }
        
        return type_examples.get(param_type, "test_value")
    
    def _generate_error_params(
        self, 
        query_params: Dict[str, Any],
        request_body: Dict[str, Any],
        endpoint: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """生成错误场景的参数（空值或错误格式）"""
        error_query_params = {}
        error_request_body = {}
        
        # 对于query参数，必填参数设为空字符串
        for key, value in query_params.items():
            if isinstance(value, str):
                error_query_params[key] = ""  # 空字符串
            elif isinstance(value, int):
                error_query_params[key] = -1  # 错误数值
            else:
                error_query_params[key] = None
        
        # 对于request body，生成异常参数
        if request_body:
            # 只取第一个字段设为空值，其他删除
            first_key = list(request_body.keys())[0] if request_body else None
            if first_key:
                error_request_body[first_key] = ""
        else:
            # 如果原始request_body为空，根据接口特点推断可能的必填参数
            if endpoint:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "")
                
                # POST/PUT/PATCH 通常需要request body，生成空的body表示缺少必填参数
                if method in ["POST", "PUT", "PATCH"]:
                    # 根据路径推断可能的参数名
                    path_lower = path.lower()
                    
                    # 根据常见接口路径推断参数
                    if "project" in path_lower:
                        error_request_body = {"name": ""}
                    elif "user" in path_lower:
                        error_request_body = {"username": ""}
                    elif "login" in path_lower or "auth" in path_lower:
                        error_request_body = {"username": "", "password": ""}
                    elif "version" in path_lower:
                        error_request_body = {"version_number": ""}
                    elif "requirement" in path_lower:
                        error_request_body = {"content": ""}
                    elif "test" in path_lower and "case" in path_lower:
                        error_request_body = {"title": ""}
                    elif "skill" in path_lower:
                        error_request_body = {"name": ""}
                    elif "pipeline" in path_lower or "cicd" in path_lower:
                        error_request_body = {"name": ""}
                    elif "notification" in path_lower:
                        error_request_body = {"channel_type": ""}
                    elif "issue" in path_lower:
                        error_request_body = {"title": ""}
                    elif "performance" in path_lower:
                        error_request_body = {"name": ""}
                    else:
                        # 通用场景：发送空的JSON对象，测试服务器的参数校验
                        error_request_body = {}
        
        return {
            "query_params": error_query_params,
            "request_body": error_request_body
        }
    
    def generate_cases_for_endpoint(
        self,
        endpoint: Dict[str, Any],
        include_normal: bool,
        include_error: bool,
        include_boundary: bool,
        include_auth: bool,
        max_cases: int
    ) -> Optional[List[Dict[str, Any]]]:
        """为单个接口生成测试用例"""
        
        def safe_json_str(obj):
            """安全地将对象转换为JSON字符串"""
            if obj is None:
                return "无"
            try:
                if isinstance(obj, str):
                    return obj
                return json.dumps(obj, ensure_ascii=False, indent=2)
            except:
                return str(obj)
        
        prompt = self.CASE_GENERATION_PROMPT.format(
            path=endpoint.get("path", ""),
            method=endpoint.get("method", "GET"),
            summary=endpoint.get("summary", ""),
            tag=endpoint.get("tag", ""),
            parameters=safe_json_str(endpoint.get("parameters")),
            request_body=safe_json_str(endpoint.get("request_body")),
            responses=safe_json_str(endpoint.get("responses")),
            security=safe_json_str(endpoint.get("security")),
            include_normal="是" if include_normal else "否",
            include_error="是" if include_error else "否",
            include_boundary="是" if include_boundary else "否",
            include_auth="是" if include_auth else "否",
            max_cases=max_cases
        )
        
        response = self.llm_service.call_llm(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=self.llm_service.get_scaled_max_tokens()
        )
        
        if not response:
            logger.warning(f"LLM returned no response for endpoint {endpoint.get('path')}")
            return self._generate_fallback_cases(endpoint)
        
        try:
            json_str = response.strip()
            
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str)
            if json_match:
                json_str = json_match.group(1).strip()
            
            start = json_str.find('[')
            end = json_str.rfind(']')
            if start != -1 and end != -1 and end > start:
                json_str = json_str[start:end+1]
            else:
                obj_start = json_str.find('{')
                obj_end = json_str.rfind('}')
                if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
                    json_str = "[" + json_str[obj_start:obj_end+1] + "]"
                else:
                    logger.warning(f"No valid JSON structure found in response for {endpoint.get('path')}")
                    return self._generate_fallback_cases(endpoint)
            
            json_str = json_str.replace('\n', ' ').replace('\r', ' ')
            json_str = re.sub(r'\s+', ' ', json_str)
            
            logger.debug(f"Attempting to parse JSON for {endpoint.get('path')}: {json_str[:200]}")
            
            cases = json.loads(json_str)
            
            if isinstance(cases, list):
                valid_cases = []
                for case in cases:
                    if isinstance(case, dict) and "name" in case:
                        valid_cases.append(case)
                logger.info(f"Generated {len(valid_cases)} cases for endpoint {endpoint.get('path')}")
                return valid_cases
            
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response for endpoint {endpoint.get('path')}: {str(e)}")
            logger.debug(f"Response: {response[:500]}")
            return self._generate_fallback_cases(endpoint)
    
    def _is_health_check_endpoint(self, endpoint: Dict[str, Any]) -> bool:
        """判断是否是健康检查/简单接口，这类接口不需要参数校验测试"""
        path = endpoint.get("path", "").lower()
        method = endpoint.get("method", "GET")
        summary = endpoint.get("summary", "").lower()
        
        health_check_paths = [
            "/ping", "/health", "/healthz", "/status", 
            "/api/status", "/api/health", "/api/ping",
            "/info", "/version", "/metrics",
            "/", "/api", "/api/v1"
        ]
        
        health_keywords = ["health", "ping", "status", "info", "metrics", "version", "健康", "状态"]
        
        for hc_path in health_check_paths:
            if path == hc_path or path.rstrip("/") == hc_path.rstrip("/"):
                return True
        
        for keyword in health_keywords:
            if keyword in summary or keyword in path:
                if method == "GET":
                    return True
        
        parameters = endpoint.get("parameters", [])
        request_body = endpoint.get("request_body")
        
        if method == "GET" and len(parameters) == 0 and not request_body:
            if "/" == path or path in health_check_paths:
                return True
        
        return False
    
    def _is_simple_get_endpoint(self, endpoint: Dict[str, Any]) -> bool:
        """判断是否是无参数的简单GET接口（不需要参数校验异常用例）"""
        path = endpoint.get("path", "").lower()
        method = endpoint.get("method", "GET")
        
        parameters = endpoint.get("parameters", [])
        request_body = endpoint.get("request_body")
        
        if method != "GET":
            return False
        
        if len(parameters) > 0 or request_body:
            return False
        
        simple_get_paths = [
            "/auth/me", "/users/me", "/user/me", "/user/profile", "/profile",
            "/api/v1/auth/me", "/api/v1/users/me", "/api/v1/user/me",
            "/api/v1/user/profile", "/api/v1/profile",
            "/me", "/current-user", "/current_user", "/my-info", "/my_info",
            "/config", "/settings", "/api/config", "/api/settings",
            "/api/v1/config", "/api/v1/settings"
        ]
        
        for simple_path in simple_get_paths:
            if path == simple_path or path.endswith(simple_path):
                return True
        
        current_user_keywords = ["me", "current", "profile", "my", "self", "当前用户", "currentuser"]
        for keyword in current_user_keywords:
            if keyword in path:
                return True
        
        return False
    
    def _generate_fallback_cases(self, endpoint: Dict[str, Any], swagger_doc: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """生成测试用例 - 使用基于 openapi-testgen 最佳实践的新生成器"""
        from app.core.services.openapi_test_generator import OpenApiTestGenerator
        
        generator = OpenApiTestGenerator()
        # 传递完整的Swagger文档给schema_parser，以便解析$ref引用
        if swagger_doc:
            generator.schema_parser.set_swagger_doc(swagger_doc)
            logger.debug(f"已传递Swagger文档给schema_parser，组件数={len(swagger_doc.get('components', {}).get('schemas', {}))}")
        else:
            logger.warning(f"未传递Swagger文档，无法解析$ref引用: {endpoint.get('path')}")
        
        cases = generator.generate_test_cases(endpoint)
        
        logger.info(f"使用新生成器为 {endpoint.get('method')} {endpoint.get('path')} 生成了 {len(cases)} 个测试用例")
        
        return cases
    
    def _extract_key_fields_from_response_schema(
        self,
        response_schema: Dict[str, Any],
        swagger_doc: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """从响应schema中智能提取关键字字段
        
        分析响应结构，自动识别并提取：
        - token类字段：token, access_token, refresh_token, auth_token
        - code类字段：code, verification_code, otp, verify_code
        - id类字段：id, order_id, request_id, transaction_id, user_id
        
        Args:
            response_schema: 响应的schema定义
            swagger_doc: 完整的swagger文档（用于解析$ref）
        
        Returns:
            变量提取配置列表：
            [
                {
                    "name": "auth_token",
                    "source": "response_body",
                    "path": "data.token",
                    "field_type": "token"
                }
            ]
        """
        from app.core.services.openapi_test_generator import OpenApiSchemaParser
        
        variable_extractions = []
        
        # 关键字段类型定义
        key_field_patterns = {
            "token": ["token", "access_token", "refresh_token", "auth_token", "reset_token", "confirmation_token"],
            "code": ["code", "verification_code", "verify_code", "otp", "captcha"],
            "id": ["id", "order_id", "request_id", "transaction_id", "user_id", "task_id", "job_id"],
            "session": ["session_id", "session", "session_key"]
        }
        
        # 排除字段（不应提取的字段）
        exclude_fields = ["token_type", "code_type", "id_type"]  # 类型字段不提取
        
        # 如果是$ref引用，先解析
        if response_schema.get("$ref"):
            if swagger_doc:
                parser = OpenApiSchemaParser()
                parser.set_swagger_doc(swagger_doc)
                response_schema = parser._resolve_ref(response_schema["$ref"])
        
        if not response_schema or not isinstance(response_schema, dict):
            return variable_extractions
        
        # 递归遍历schema的properties，提取关键字字段
        def traverse_schema(schema: Dict[str, Any], current_path: str = "", depth: int = 0):
            if depth > 5:  # 限制递归深度
                return
            
            properties = schema.get("properties", {})
            if not properties:
                return
            
            for prop_name, prop_spec in properties.items():
                # 构建当前字段的完整路径
                field_path = f"{current_path}.{prop_name}" if current_path else prop_name
                
                # 检查是否是关键字字段
                prop_name_lower = prop_name.lower()
                field_type = None
                matched_field = None
                
                for ftype, patterns in key_field_patterns.items():
                    for pattern in patterns:
                        if pattern in prop_name_lower or prop_name_lower in pattern:
                            field_type = ftype
                            matched_field = prop_name
                            break
                    if field_type:
                        break
                
                if field_type and matched_field:
                    # 检查是否在排除列表中
                    if matched_field in exclude_fields:
                        logger.debug(f"跳过排除字段: {field_path}")
                        continue
                    
                    # 检查字段类型是否是对象（对象不应作为整体提取）
                    # 处理anyOf/oneOf结构
                    field_types_to_check = []
                    if prop_spec.get("anyOf"):
                        for item in prop_spec["anyOf"]:
                            if isinstance(item, dict) and item.get("type"):
                                field_types_to_check.append(item["type"])
                    elif prop_spec.get("oneOf"):
                        for item in prop_spec["oneOf"]:
                            if isinstance(item, dict) and item.get("type"):
                                field_types_to_check.append(item["type"])
                    else:
                        field_types_to_check.append(prop_spec.get("type", "string"))
                    
                    # 如果字段类型包含object且不是null，跳过（对象不应作为整体提取）
                    if "object" in field_types_to_check and prop_spec.get("properties"):
                        logger.debug(f"跳过对象类型字段: {field_path}")
                        continue
                    
                    # 找到关键字字段，添加到提取配置
                    var_name = matched_field
                    
                    # 对于token类字段，统一命名为auth_token
                    if field_type == "token":
                        var_name = "auth_token"
                    # 对于其他字段，保持原字段名
                    
                    extraction_config = {
                        "name": var_name,
                        "source": "response_body",
                        "path": field_path,
                        "field_type": field_type,
                        "original_field": matched_field
                    }
                    
                    # 避免重复添加
                    existing = [v for v in variable_extractions if v.get("path") == field_path]
                    if not existing:
                        variable_extractions.append(extraction_config)
                        logger.info(f"从响应schema自动识别关键字字段: {field_path} (类型={field_type}, 变量名={var_name})")
                
                # 如果字段是对象类型，继续递归
                if prop_spec.get("type") == "object" or prop_spec.get("properties"):
                    traverse_schema(prop_spec, field_path, depth + 1)
                
                # 如果字段有$ref引用，解析并递归
                elif prop_spec.get("$ref") and swagger_doc:
                    parser = OpenApiSchemaParser()
                    parser.set_swagger_doc(swagger_doc)
                    resolved_spec = parser._resolve_ref(prop_spec["$ref"])
                    if resolved_spec:
                        traverse_schema(resolved_spec, field_path, depth + 1)
        
        traverse_schema(response_schema)
        
        return variable_extractions
    
    def _identify_workflow_dependencies(self, endpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
        """识别业务流程依赖关系
        
        分析接口路径，识别常见的业务流程模式：
        - /xxx/request → /xxx/confirm (需要token)
        - /xxx/send → /xxx/verify (需要验证码)
        - /xxx/create → /xxx/process → /xxx/complete
        
        Returns:
            {
                "workflow_chains": [
                    {
                        "base_path": "/password-reset",
                        "predecessor_path": "/password-reset/request",
                        "successor_path": "/password-reset/confirm",
                        "transfer_field": "token",
                        "extraction_paths": ["data.token", "token", "reset_token"]
                    }
                ],
                "path_to_workflow": {
                    "/password-reset/confirm": "password-reset_workflow_0"
                }
            }
        """
        workflow_chains = []
        path_to_workflow = {}
        
        workflow_patterns = [
            {
                "predecessor_suffix": ["request", "send", "create", "init", "start"],
                "successor_suffix": ["confirm", "verify", "process", "complete", "execute", "finish"],
                "transfer_fields": {
                    "confirm": ["token", "reset_token", "confirmation_token"],
                    "verify": ["code", "verification_code", "otp", "verify_code"],
                    "process": ["id", "order_id", "request_id", "transaction_id"],
                    "complete": ["id", "order_id", "request_id", "transaction_id"],
                    "execute": ["id", "task_id", "job_id"],
                    "finish": ["id", "order_id", "request_id"]
                },
                "extraction_path_templates": {
                    "token": ["data.token", "token", "reset_token", "data.reset_token"],
                    "code": ["data.code", "code", "verification_code", "data.verification_code"],
                    "id": ["data.id", "id", "data.order_id", "order_id", "request_id"],
                    "reset_token": ["data.token", "token", "reset_token", "data.reset_token"],
                    "confirmation_token": ["data.token", "token", "confirmation_token"],
                    "verification_code": ["data.code", "code", "verification_code"],
                    "otp": ["data.otp", "otp", "data.code", "code"],
                    "order_id": ["data.id", "id", "data.order_id", "order_id"],
                    "request_id": ["data.id", "id", "request_id", "data.request_id"],
                    "task_id": ["data.id", "id", "task_id", "data.task_id"],
                    "job_id": ["data.id", "id", "job_id", "data.job_id"],
                    "transaction_id": ["data.id", "id", "transaction_id"]
                }
            }
        ]
        
        path_groups = {}
        for ep in endpoints:
            path = ep.get("path", "")
            method = ep.get("method", "").upper()
            
            if method not in ["POST", "PUT", "PATCH"]:
                continue
            
            parts = path.rstrip("/").split("/")
            if len(parts) < 3:
                continue
            
            last_part = parts[-1].lower()
            base_path = "/".join(parts[:-1])
            
            if base_path not in path_groups:
                path_groups[base_path] = []
            
            path_groups[base_path].append({
                "path": path,
                "suffix": last_part,
                "endpoint": ep
            })
        
        for base_path, group in path_groups.items():
            if len(group) < 2:
                continue
            
            for pattern in workflow_patterns:
                predecessors = []
                successors = []
                
                for item in group:
                    if item["suffix"] in pattern["predecessor_suffix"]:
                        predecessors.append(item)
                    elif item["suffix"] in pattern["successor_suffix"]:
                        successors.append(item)
                
                if predecessors and successors:
                    for pred in predecessors:
                        for succ in successors:
                            transfer_field = None
                            extraction_paths = []
                            possible_fields = ["token", "id"]
                            
                            succ_suffix = succ["suffix"]
                            if succ_suffix in pattern["transfer_fields"]:
                                possible_fields = pattern["transfer_fields"][succ_suffix]
                            
                            if succ_suffix in pattern["transfer_fields"]:
                                pred_endpoint = pred["endpoint"]
                                responses = pred_endpoint.get("responses", {})
                                if "200" in responses:
                                    response_200 = responses["200"]
                                    content = response_200.get("content", {})
                                    json_content = content.get("application/json", {})
                                    schema = json_content.get("schema", {})
                                    
                                    if schema.get("properties"):
                                        response_props = schema.get("properties", {})
                                        for field in possible_fields:
                                            if field in response_props:
                                                transfer_field = field
                                                break
                                    elif schema.get("$ref"):
                                        from app.core.services.openapi_test_generator import OpenApiSchemaParser
                                        parser = OpenApiSchemaParser(self.swagger_doc if hasattr(self, 'swagger_doc') else None)
                                        resolved = parser._resolve_ref(schema["$ref"])
                                        if resolved and resolved.get("properties"):
                                            for field in possible_fields:
                                                if field in resolved["properties"]:
                                                    transfer_field = field
                                                    break
                            
                            if not transfer_field and possible_fields:
                                for field in possible_fields:
                                    transfer_field = field
                                    break
                            
                            if transfer_field:
                                extraction_paths = pattern["extraction_path_templates"].get(transfer_field, [f"data.{transfer_field}", transfer_field])
                            
                            workflow_id = f"{base_path.replace('/', '_')}_workflow_{len(workflow_chains)}"
                            workflow = {
                                "workflow_id": workflow_id,
                                "base_path": base_path,
                                "predecessor": {
                                    "path": pred["path"],
                                    "suffix": pred["suffix"]
                                },
                                "successor": {
                                    "path": succ["path"],
                                    "suffix": succ["suffix"]
                                },
                                "transfer_field": transfer_field,
                                "extraction_paths": extraction_paths
                            }
                            workflow_chains.append(workflow)
                            
                            path_to_workflow[succ["path"]] = workflow_id
                            
                            logger.info(f"识别业务流程依赖: {pred['path']} → {succ['path']}, 传递字段: {transfer_field}")
        
        return {
            "workflow_chains": workflow_chains,
            "path_to_workflow": path_to_workflow
        }
    
    def _generate_login_precondition_case(
        self,
        project_id: int,
        version_id: Optional[int],
        base_url: str,
        security_defs: Dict[str, Any],
        user_id: int,
        swagger: Dict[str, Any]
    ) -> Optional[ApiTestCase]:
        """生成登录前置用例，用于获取认证token"""
        
        # 尝试从Swagger中找到登录接口
        login_endpoint = self._find_login_endpoint_in_swagger(swagger)
        
        if not login_endpoint:
            # 如果没有找到登录接口，创建一个通用的登录用例
            logger.info("No login endpoint found in Swagger, creating generic login case")
            login_endpoint = {
                "path": "/api/v1/auth/login/json",
                "method": "POST",
                "summary": "用户登录获取认证token",
                "responses": {
                    "200": {
                        "description": "Successful Response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "code": {"type": "integer"},
                                        "message": {"type": "string"},
                                        "data": {
                                            "type": "object",
                                            "properties": {
                                                "access_token": {"type": "string"},
                                                "refresh_token": {"type": "string"},
                                                "token": {"type": "string"},
                                                "token_type": {"type": "string"},
                                                "expires_in": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        
        from app.core.services.api_assert_executor import generate_assert_rules_from_response_spec
        
        # 根据Swagger响应定义自动生成断言规则
        response_spec = login_endpoint.get("responses", {})
        login_assert_rules = generate_assert_rules_from_response_spec(response_spec, "normal")
        
        # 确保有HTTP状态码断言
        has_http_status = any(r.get("type") == "http_status" for r in login_assert_rules)
        if not has_http_status:
            login_assert_rules.insert(0, {
                "type": "http_status",
                "value": [200, 201],
                "description": "HTTP状态码应为200(登录成功)"
            })
        
        # 智能提取响应中的关键字字段（从Swagger responses定义自动推断）
        variable_extractions = []
        
        # 分析登录接口的响应定义
        login_responses = login_endpoint.get("responses", {})
        if "200" in login_responses:
            response_200 = login_responses["200"]
            content = response_200.get("content", {})
            json_content = content.get("application/json", {})
            response_schema = json_content.get("schema", {})
            
            if response_schema:
                # 使用智能响应解析提取关键字字段
                extracted_fields = self._extract_key_fields_from_response_schema(
                    response_schema, swagger
                )
                
                if extracted_fields:
                    # 将提取的配置转换为标准的variable_extractions格式
                    for field in extracted_fields:
                        variable_extractions.append({
                            "name": field["name"],
                            "source": "response_body",
                            "path": field["path"]
                        })
                    logger.info(f"从登录接口响应schema智能提取了 {len(extracted_fields)} 个关键字字段")
                else:
                    # 如果智能提取失败，使用fallback配置
                    logger.warning("智能响应提取未找到关键字字段，使用默认提取配置")
                    variable_extractions = [
                        {"name": "auth_token", "source": "response_body", "path": "token"},
                        {"name": "auth_token", "source": "response_body", "path": "data.token"},
                        {"name": "auth_token", "source": "response_body", "path": "access_token"},
                        {"name": "refresh_token", "source": "response_body", "path": "refresh_token"}
                    ]
        else:
            # 响应定义缺失，使用fallback配置
            logger.warning("登录接口缺少200响应定义，使用默认提取配置")
            variable_extractions = [
                {"name": "auth_token", "source": "response_body", "path": "token"},
                {"name": "auth_token", "source": "response_body", "path": "data.token"},
                {"name": "auth_token", "source": "response_body", "path": "access_token"}
            ]
        
        # 登录请求体（使用测试账号）
        login_request_body = {
            "username": "admin",
            "password": "admin123"
        }
        
        # 检查Swagger中是否有登录接口的请求体定义
        if login_endpoint.get("request_body"):
            try:
                rb = login_endpoint.get("request_body")
                if isinstance(rb, dict):
                    content = rb.get("content", {})
                    json_content = content.get("application/json", {})
                    schema = json_content.get("schema", {})
                    if schema:
                        # 根据schema生成请求体
                        properties = schema.get("properties", {})
                        login_request_body = {}
                        for prop_name, prop_spec in properties.items():
                            if prop_name in ["username", "email", "login"]:
                                login_request_body[prop_name] = "admin"
                            elif prop_name == "password":
                                login_request_body[prop_name] = "admin123"
                            elif prop_spec.get("example"):
                                login_request_body[prop_name] = prop_spec.get("example")
            except Exception as e:
                logger.warning(f"Failed to parse login request body schema: {e}")
        
        login_case = ApiTestCase(
            project_id=project_id,
            version_id=version_id,
            name=f"[前置] 登录获取认证token",
            description="前置用例：执行登录接口获取认证token，供后续需要认证的接口使用",
            method="POST",
            path="/api/v1/auth/login/json",
            base_url=base_url,
            headers={"Content-Type": "application/json"},
            query_params={},
            request_body=login_request_body,
            expected_status=200,
            assert_rules=login_assert_rules,
            preconditions="1. 系统正常运行\n2. 测试账号已创建(admin/admin123)",
            test_steps=[
                {"step": 1, "action": "发送POST请求到登录接口", "expected": "HTTP状态码200"},
                {"step": 2, "action": "检查响应包含token字段", "expected": "token字段存在"},
                {"step": 3, "action": "提取token保存为变量auth_token", "expected": "变量提取成功"}
            ],
            expected_result="成功获取认证token，变量auth_token可用于后续用例",
            case_type="normal",
            priority="P0",
            status="active",
            generated_by="ai",
            created_by=user_id,
            created_at=datetime.utcnow(),
            depends_on=None,
            variable_extractions=variable_extractions
        )
        
        return login_case
    
    def _find_login_endpoint_in_swagger(self, swagger: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在Swagger中查找登录接口"""
        paths = swagger.get("paths", {})
        
        login_keywords = ["login", "signin", "sign-in", "auth/login", "authenticate", "token"]
        
        for path, methods in paths.items():
            path_lower = path.lower()
            for keyword in login_keywords:
                if keyword in path_lower:
                    for method, spec in methods.items():
                        if method.upper() == "POST":
                            return {
                                "path": path,
                                "method": "POST",
                                "summary": spec.get("summary", "登录接口"),
                                "request_body": spec.get("requestBody") or spec.get("body"),
                                "responses": spec.get("responses", {})
                            }
        
        return None
    
    def create_test_case_model(
        self,
        case_data: Dict[str, Any],
        project_id: int,
        version_id: Optional[int],
        endpoint: Dict[str, Any],
        base_url: str,
        user_id: int
    ) -> ApiTestCase:
        """创建测试用例模型"""
        
        test_steps = case_data.get("test_steps", [])
        if test_steps and isinstance(test_steps, list):
            test_steps_json = test_steps
        else:
            test_steps_json = [{"step": 1, "action": f"发送{endpoint.get('method')}请求到{endpoint.get('path')}", "expected": case_data.get("expected_result", "")}]
        
        test_case = ApiTestCase(
            project_id=project_id,
            version_id=version_id,
            name=case_data.get("name", f"{endpoint.get('method')} {endpoint.get('path')} - {case_data.get('case_type', 'normal')}"),
            description=case_data.get("description", ""),
            method=endpoint.get("method", "GET"),
            path=endpoint.get("path", ""),
            base_url=base_url,
            headers=case_data.get("headers", {}),
            query_params=case_data.get("query_params", {}),
            request_body=case_data.get("request_body", {}),
            expected_status=case_data.get("expected_status", 200),
            assert_rules=case_data.get("assert_rules", []),
            preconditions=case_data.get("preconditions", ""),
            test_steps=test_steps_json,
            expected_result=case_data.get("expected_result", ""),
            case_type=case_data.get("case_type", "normal"),
            priority=case_data.get("priority", "P2"),
            status="active",
            generated_by="ai",
            created_by=user_id,
            created_at=datetime.utcnow()
        )
        
        return test_case
    
    async def auto_generate_from_swagger(
        self,
        project_id: int,
        version_id: Optional[int],
        swagger_url: str,
        base_url: Optional[str],
        include_normal: bool,
        include_error: bool,
        include_boundary: bool,
        include_auth: bool,
        max_cases_per_endpoint: int,
        user_id: int
    ) -> Dict[str, Any]:
        """从Swagger URL自动生成测试用例"""
        
        swagger = await self.fetch_swagger(swagger_url)
        if not swagger:
            return {
                "success": False,
                "message": f"无法获取Swagger文档: {swagger_url}",
                "endpoints_count": 0,
                "generated_count": 0,
                "test_cases": [],
                "generation_summary": None
            }
        
        openapi_version = swagger.get("openapi") or swagger.get("swagger", "2.0")
        
        if not base_url:
            if "servers" in swagger and swagger["servers"]:
                base_url = swagger["servers"][0].get("url", "")
            elif "host" in swagger:
                base_url = f"http://{swagger['host']}{swagger.get('basePath', '')}"
        
        if not base_url:
            base_url = "http://localhost"
        
        self.swagger_doc = swagger
        
        definition = ApiDefinition(
            project_id=project_id,
            name=swagger.get("info", {}).get("title", "API文档"),
            source_type="url",
            source_url=swagger_url,
            content=swagger,
            version=openapi_version,
            base_url=base_url,
            description=swagger.get("info", {}).get("description", ""),
            imported_at=datetime.utcnow()
        )
        self.db.add(definition)
        self.db.flush()
        
        endpoints = self.parse_endpoints(swagger)
        
        workflow_info = self._identify_workflow_dependencies(endpoints)
        workflow_chains = workflow_info.get("workflow_chains", [])
        path_to_workflow = workflow_info.get("path_to_workflow", {})
        logger.info(f"识别到 {len(workflow_chains)} 个业务流程依赖链")
        
        predecessor_case_ids = {}
        
        login_case_id = None
        has_auth_requirement = any(ep.get("requires_auth") for ep in endpoints)
        security_defs = {}
        
        if has_auth_requirement:
            # 获取第一个接口的认证定义（所有接口共享）
            for ep in endpoints:
                if ep.get("security_definitions"):
                    security_defs = ep.get("security_definitions")
                    break
            
            # 生成登录前置用例
            login_case = self._generate_login_precondition_case(
                project_id, version_id, base_url, security_defs, user_id, swagger
            )
            if login_case:
                self.db.add(login_case)
                self.db.flush()
                login_case_id = login_case.id
                logger.info(f"Generated login precondition case with id: {login_case_id}")
        
        # 限制处理的接口数量，避免超时
        max_endpoints = 20
        if len(endpoints) > max_endpoints:
            logger.warning(f"Too many endpoints ({len(endpoints)}), limiting to {max_endpoints}")
            endpoints = endpoints[:max_endpoints]
        
        endpoint_models = []
        for ep in endpoints:
            endpoint_model = ApiEndpoint(
                definition_id=definition.id,
                path=ep["path"],
                method=ep["method"],
                tag=ep.get("tag"),
                summary=ep.get("summary"),
                description=ep.get("description"),
                parameters=ep.get("parameters"),
                request_body=ep.get("request_body"),
                responses=ep.get("responses"),
                security=ep.get("security"),
                deprecated=ep.get("deprecated", False)
            )
            endpoint_models.append(endpoint_model)
            self.db.add(endpoint_model)
        
        self.db.flush()
        
        generated_cases = []
        case_type_stats = {"normal": 0, "error": 0, "boundary": 0, "auth": 0}
        
        # 如果生成了登录用例，先加入列表
        if login_case_id:
            login_case_obj = self.db.query(ApiTestCase).filter(ApiTestCase.id == login_case_id).first()
            if login_case_obj:
                generated_cases.append(login_case_obj)
                case_type_stats["normal"] += 1
        
        # 直接使用fallback生成基本测试用例（避免LLM超时和额度问题）
        logger.info(f"Generating test cases for {len(endpoints)} endpoints using fallback mode")
        logger.info(f"Swagger文档状态: {'有' if swagger else '空'}, 组件schemas数={len(swagger.get('components', {}).get('schemas', {})) if swagger else 0}")
        
        for i, endpoint in enumerate(endpoints):
            endpoint_path = endpoint.get("path", "")
            
            if endpoint.get("is_login_endpoint") and login_case_id:
                login_case_obj = self.db.query(ApiTestCase).filter(ApiTestCase.id == login_case_id).first()
                if login_case_obj and login_case_obj.path == endpoint_path:
                    logger.info(f"Skipping duplicate login endpoint: {endpoint_path} (precondition case {login_case_id} already created)")
                    continue
            
            is_workflow_predecessor = False
            workflow_for_successor = None
            
            for workflow in workflow_chains:
                if workflow["predecessor"]["path"] == endpoint_path:
                    is_workflow_predecessor = True
                    break
                if workflow["successor"]["path"] == endpoint_path:
                    workflow_for_successor = workflow
                    break
            
            cases_data = self._generate_fallback_cases(endpoint, swagger)
            
            for case_data in cases_data:
                try:
                    depends_on = None
                    variable_extractions = None
                    
                    if endpoint.get("requires_auth") and case_data.get("case_type") != "auth" and login_case_id:
                        depends_on = [login_case_id]
                        variable_extractions = [
                            {
                                "name": "auth_token",
                                "source": "response_body",
                                "path": "token"
                            },
                            {
                                "name": "auth_token",
                                "source": "response_body",
                                "path": "data.token"
                            },
                            {
                                "name": "auth_token",
                                "source": "response_body",
                                "path": "access_token"
                            }
                        ]
                    
                    if is_workflow_predecessor and case_data.get("case_type") == "normal":
                        workflow_match = None
                        for workflow in workflow_chains:
                            if workflow["predecessor"]["path"] == endpoint_path:
                                workflow_match = workflow
                                break
                        
                        if workflow_match:
                            # 智能响应解析：从endpoint的responses定义提取关键字字段
                            endpoint_responses = endpoint.get("responses", {})
                            if "200" in endpoint_responses:
                                response_200 = endpoint_responses["200"]
                                content = response_200.get("content", {})
                                json_content = content.get("application/json", {})
                                response_schema = json_content.get("schema", {})
                                
                                if response_schema:
                                    # 使用智能响应解析
                                    extracted_fields = self._extract_key_fields_from_response_schema(
                                        response_schema, swagger
                                    )
                                    
                                    if extracted_fields:
                                        predecessor_extractions = []
                                        for field in extracted_fields:
                                            predecessor_extractions.append({
                                                "name": field["name"],
                                                "source": "response_body",
                                                "path": field["path"]
                                            })
                                        
                                        logger.info(f"前置接口 {endpoint_path} 智能提取了 {len(extracted_fields)} 个关键字字段")
                                    else:
                                        # Fallback: 使用预定义的提取路径
                                        transfer_field = workflow_match.get("transfer_field", "token")
                                        extraction_paths = workflow_match.get("extraction_paths", [f"data.{transfer_field}", transfer_field])
                                        
                                        predecessor_extractions = []
                                        for path in extraction_paths:
                                            predecessor_extractions.append({
                                                "name": transfer_field,
                                                "source": "response_body",
                                                "path": path
                                            })
                                        logger.info(f"前置接口 {endpoint_path} 使用fallback提取路径: {transfer_field} from {extraction_paths}")
                                else:
                                    # 缺少响应schema，使用fallback
                                    transfer_field = workflow_match.get("transfer_field", "token")
                                    extraction_paths = workflow_match.get("extraction_paths", [f"data.{transfer_field}", transfer_field])
                                    
                                    predecessor_extractions = []
                                    for path in extraction_paths:
                                        predecessor_extractions.append({
                                            "name": transfer_field,
                                            "source": "response_body",
                                            "path": path
                                        })
                            else:
                                # 缺少200响应定义，使用fallback
                                transfer_field = workflow_match.get("transfer_field", "token")
                                extraction_paths = workflow_match.get("extraction_paths", [f"data.{transfer_field}", transfer_field])
                                
                                predecessor_extractions = []
                                for path in extraction_paths:
                                    predecessor_extractions.append({
                                        "name": transfer_field,
                                        "source": "response_body",
                                        "path": path
                                    })
                            
                            if predecessor_extractions:
                                if variable_extractions:
                                    variable_extractions.extend(predecessor_extractions)
                                else:
                                    variable_extractions = predecessor_extractions
                    
                    if workflow_for_successor and case_data.get("case_type") == "normal":
                        predecessor_path = workflow_for_successor["predecessor"]["path"]
                        predecessor_case_id = predecessor_case_ids.get(predecessor_path)
                        
                        if predecessor_case_id:
                            if depends_on:
                                if predecessor_case_id not in depends_on:
                                    depends_on.append(predecessor_case_id)
                            else:
                                depends_on = [predecessor_case_id]
                            
                            transfer_field = workflow_for_successor.get("transfer_field", "token")
                            request_body = case_data.get("request_body", {})
                            
                            if request_body and isinstance(request_body, dict):
                                if transfer_field in request_body:
                                    request_body[transfer_field] = f"${{{transfer_field}}}"
                                    logger.info(f"后续接口 {endpoint_path} request_body字段 {transfer_field} 替换为变量引用")
                            
                            case_data["request_body"] = request_body
                    
                    test_case = ApiTestCase(
                        project_id=project_id,
                        version_id=version_id,
                        name=case_data.get("name", f"{endpoint.get('method')} {endpoint.get('path')}"),
                        description=case_data.get("description", ""),
                        method=endpoint.get("method", "GET"),
                        path=endpoint.get("path", ""),
                        base_url=base_url,
                        headers=case_data.get("headers", {}),
                        query_params=case_data.get("query_params", {}),
                        request_body=case_data.get("request_body", {}),
                        expected_status=case_data.get("expected_status", 200),
                        assert_rules=case_data.get("assert_rules", []),
                        preconditions=case_data.get("preconditions", ""),
                        test_steps=case_data.get("test_steps", []),
                        expected_result=case_data.get("expected_result", ""),
                        case_type=case_data.get("case_type", "normal"),
                        priority=case_data.get("priority", "P2"),
                        status="active",
                        generated_by="ai",
                        created_by=user_id,
                        created_at=datetime.utcnow(),
                        endpoint_id=endpoint_models[i].id,
                        depends_on=depends_on,
                        variable_extractions=variable_extractions
                    )
                    self.db.add(test_case)
                    self.db.flush()
                    
                    if is_workflow_predecessor and case_data.get("case_type") == "normal":
                        predecessor_case_ids[endpoint_path] = test_case.id
                        logger.info(f"记录前置接口 {endpoint_path} 的case_id: {test_case.id}")
                    
                    generated_cases.append(test_case)
                    
                    case_type = case_data.get('case_type', 'normal')
                    if case_type in case_type_stats:
                        case_type_stats[case_type] += 1
                except Exception as e:
                    logger.warning(f"Failed to create test case for {endpoint.get('path')}: {e}")
        
        self.db.commit()
        
        for case in generated_cases:
            self.db.refresh(case)
        
        generation_summary = {
            "total_endpoints": len(endpoints),
            "generated_cases": len(generated_cases),
            "case_type_distribution": case_type_stats,
            "base_url": base_url,
            "swagger_version": openapi_version
        }
        
        logger.info(f"Auto-generated {len(generated_cases)} test cases from {len(endpoints)} endpoints")
        
        return {
            "success": True,
            "message": f"成功生成 {len(generated_cases)} 个测试用例，覆盖 {len(endpoints)} 个接口",
            "definition_id": definition.id,
            "endpoints_count": len(endpoints),
            "generated_count": len(generated_cases),
            "test_cases": generated_cases,
            "generation_summary": generation_summary,
            "raw_spec": swagger,
        }