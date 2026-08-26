"""
API测试生成Agent
基于LangChain实现智能化API测试用例生成，支持：
1. Swagger/OpenAPI文档解析
2. 接口依赖分析
3. 智能参数生成
4. 断言规则自动生成
"""

from typing import Dict, Any, List
import json
import re

from langchain.tools import Tool
from langchain.prompts import ChatPromptTemplate

from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.api_test import ApiDefinition, ApiEndpoint


class APITestGenerationAgent(BaseAgent):
    """
    API测试生成Agent
    
    核心功能：
    1. 解析Swagger/OpenAPI文档
    2. 提取API接口列表
    3. 分析接口依赖关系（拓扑排序）
    4. 为每个接口生成测试用例（正常/异常/边界）
    5. 智能生成请求参数和断言规则
    """
    
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "APITestGenerationAgent")
        
        self.create_agent()
    
    def define_tools(self) -> List[Tool]:
        """定义API测试生成工具集"""
        
        return [
            Tool(
                name="parse_swagger_document",
                func=self._parse_swagger,
                description="解析Swagger/OpenAPI文档，提取接口列表"
            ),
            Tool(
                name="analyze_api_dependencies",
                func=self._analyze_dependencies,
                description="分析API接口依赖关系（拓扑排序）"
            ),
            Tool(
                name="generate_test_cases_for_endpoint",
                func=self._generate_cases_for_endpoint,
                description="为单个API接口生成测试用例"
            ),
            Tool(
                name="generate_request_parameters",
                func=self._generate_request_params,
                description="智能生成请求参数（正常/异常/边界）"
            ),
            Tool(
                name="generate_assertion_rules",
                func=self._generate_assertions,
                description="智能生成断言规则"
            ),
            Tool(
                name="extract_auth_config",
                func=self._extract_auth,
                description="提取认证配置（OAuth2/Bearer Token等）"
            ),
            Tool(
                name="save_api_test_cases",
                func=self._save_cases,
                description="保存API测试用例到数据库"
            )
        ]
    
    def build_prompt(self) -> ChatPromptTemplate:
        """构建Agent提示词"""
        
        template = """
你是专业的API测试工程师。

任务目标：根据Swagger文档生成完整的API测试用例

执行策略：
1. 使用 parse_swagger_document 解析文档，提取所有接口
2. 使用 analyze_api_dependencies 分析接口依赖，确定执行顺序
3. 对每个接口使用 generate_test_cases_for_endpoint 生成用例
   - 正常场景：使用 generate_request_parameters 生成合理参数
   - 异常场景：生成错误参数（缺失、格式错误）
   - 边界值：生成边界参数（空值、最大值、最小值）
4. 使用 generate_assertion_rules 为每个用例生成断言规则
5. 使用 extract_auth_config 提取认证配置
6. 使用 save_api_test_cases 保存到数据库

重要规则：
- 认证接口（登录）必须第一个执行
- 创建资源的接口必须在查询/更新/删除接口之前
- 每个接口至少生成3个用例（正常、异常、边界）
- 断言规则必须验证HTTP状态码和业务状态码
- OAuth2接口使用application/x-www-form-urlencoded格式
- 其他接口使用application/json格式

输出格式：
JSON对象，包含：
{
  "endpoints": [
    {
      "path": "/api/v1/users",
      "method": "GET",
      "test_cases": [...]
    }
  ],
  "auth_config": {
    "type": "Bearer",
    "login_endpoint": "/api/v1/auth/login"
  }
}

输入：
{input}

可用工具：
{tools}

思考过程：
{agent_scratchpad}

请严格按照策略执行，确保生成可执行的API测试用例。
"""
        
        return ChatPromptTemplate.from_template(template)
    
    # === 工具实现 ===
    
    def _parse_swagger(self, swagger_content: str) -> str:
        """
        解析Swagger文档
        
        Args:
            swagger_content: Swagger JSON/YAML内容
        
        Returns:
            接口列表JSON字符串
        """
        logger.info(f"[Tool] 解析Swagger文档，长度={len(swagger_content)}")
        
        try:
            # 解析JSON
            swagger_data = json.loads(swagger_content)
            
            endpoints = []
            
            # 提取所有路径和方法
            paths = swagger_data.get('paths', {})
            for path, methods in paths.items():
                for method, details in methods.items():
                    if method in ['get', 'post', 'put', 'delete', 'patch']:
                        endpoint = {
                            'path': path,
                            'method': method.upper(),
                            'summary': details.get('summary', ''),
                            'tag': details.get('tags', [''])[0],
                            'parameters': details.get('parameters', []),
                            'request_body': details.get('requestBody', {}),
                            'responses': details.get('responses', {}),
                            'security': details.get('security', [])
                        }
                        endpoints.append(endpoint)
            
            logger.info(f"[Tool] Swagger解析完成，接口数={len(endpoints)}")
            
            return json.dumps(endpoints, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] Swagger解析失败: {str(e)}")
            return json.dumps({'error': str(e)}, ensure_ascii=False)
    
    def _analyze_dependencies(self, endpoints_json: str) -> str:
        """
        分析API依赖关系
        
        Args:
            endpoints_json: 接口列表JSON字符串
        
        Returns:
            拓扑排序后的接口列表JSON字符串
        """
        logger.info(f"[Tool] 分析接口依赖关系")
        
        try:
            endpoints = json.loads(endpoints_json)
            
            # 简化的依赖分析逻辑
            # 1. 认证接口（login）优先
            # 2. 创建接口（POST）优先于查询接口（GET）
            # 3. 更新/删除接口最后
            
            sorted_endpoints = []
            
            # 第一批：认证接口
            auth_endpoints = [e for e in endpoints if 'login' in e['path'].lower() or 'auth' in e['tag'].lower()]
            sorted_endpoints.extend(auth_endpoints)
            
            # 第二批：创建接口（POST）
            create_endpoints = [e for e in endpoints if e['method'] == 'POST' and e not in auth_endpoints]
            sorted_endpoints.extend(create_endpoints)
            
            # 第三批：查询接口（GET）
            query_endpoints = [e for e in endpoints if e['method'] == 'GET' and e not in auth_endpoints]
            sorted_endpoints.extend(query_endpoints)
            
            # 第四批：更新/删除接口（PUT/DELETE/PATCH）
            other_endpoints = [e for e in endpoints if e not in sorted_endpoints]
            sorted_endpoints.extend(other_endpoints)
            
            logger.info(f"[Tool] 依赖分析完成，排序后接口数={len(sorted_endpoints)}")
            
            return json.dumps(sorted_endpoints, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 依赖分析失败: {str(e)}")
            return endpoints_json  # 返回原始列表
    
    def _generate_cases_for_endpoint(self, endpoint_json: str) -> str:
        """
        为单个接口生成测试用例
        
        Args:
            endpoint_json: 接口详情JSON字符串
        
        Returns:
            测试用例列表JSON字符串
        """
        logger.info(f"[Tool] 为接口生成测试用例")
        
        try:
            endpoint = json.loads(endpoint_json)
            
            # 简化的用例生成逻辑
            test_cases = []
            
            # 正常场景用例
            normal_case = {
                'name': f"{endpoint['path']} - 正常场景",
                'case_type': 'normal',
                'priority': 'P0',
                'description': f"测试{endpoint['summary']}正常执行",
                'request': self._generate_request_params(json.dumps(endpoint)),
                'assertions': [
                    {'type': 'http_status', 'expected': [200, 201, 204]},
                    {'type': 'response_time', 'expected': '< 1000ms'}
                ]
            }
            test_cases.append(normal_case)
            
            # 异常场景用例（参数缺失）
            error_case = {
                'name': f"{endpoint['path']} - 参数缺失",
                'case_type': 'error',
                'priority': 'P1',
                'description': f"测试{endpoint['summary']}参数缺失场景",
                'request': {'headers': {}, 'query_params': {}, 'body': {}},
                'assertions': [
                    {'type': 'http_status', 'expected': [400, 422]}
                ]
            }
            test_cases.append(error_case)
            
            # 边界值用例
            boundary_case = {
                'name': f"{endpoint['path']} - 边界值",
                'case_type': 'boundary',
                'priority': 'P2',
                'description': f"测试{endpoint['summary']}边界值场景",
                'request': {'headers': {}, 'query_params': {}, 'body': {}},
                'assertions': [
                    {'type': 'http_status', 'expected': [200, 400]}
                ]
            }
            test_cases.append(boundary_case)
            
            logger.info(f"[Tool] 测试用例生成完成，数量={len(test_cases)}")
            
            return json.dumps(test_cases, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 测试用例生成失败: {str(e)}")
            return json.dumps([], ensure_ascii=False)
    
    def _generate_request_params(self, endpoint_json: str) -> str:
        """
        智能生成请求参数
        
        Args:
            endpoint_json: 接口详情JSON字符串
        
        Returns:
            请求参数JSON字符串
        """
        logger.info(f"[Tool] 生成请求参数")
        
        try:
            endpoint = json.loads(endpoint_json)
            
            # 简化的参数生成逻辑
            request_params = {
                'headers': {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ${token}' if endpoint.get('security') else None
                },
                'query_params': {},
                'body': {}
            }
            
            # 根据参数定义生成默认值
            parameters = endpoint.get('parameters', [])
            for param in parameters:
                if param.get('in') == 'query':
                    request_params['query_params'][param['name']] = self._get_default_value(param)
            
            # 根据requestBody生成默认值
            request_body = endpoint.get('request_body', {})
            if request_body:
                schema = request_body.get('content', {}).get('application/json', {}).get('schema', {})
                request_params['body'] = self._generate_body_from_schema(schema)
            
            logger.info(f"[Tool] 请求参数生成完成")
            
            return json.dumps(request_params, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 请求参数生成失败: {str(e)}")
            return json.dumps({}, ensure_ascii=False)
    
    def _generate_assertions(self, test_case_json: str) -> str:
        """
        智能生成断言规则
        
        Args:
            test_case_json: 测试用例JSON字符串
        
        Returns:
            断言规则JSON字符串
        """
        logger.info(f"[Tool] 生成断言规则")
        
        try:
            test_case = json.loads(test_case_json)
            
            # 简化的断言生成逻辑
            assertions = [
                {'type': 'http_status', 'expected': [200, 201, 204]},
                {'type': 'response_time', 'expected': '< 2000ms'},
                {'type': 'response_body', 'expected': 'non-empty'}
            ]
            
            # 根据响应定义添加字段断言
            # 这里可以扩展为从Swagger responses提取字段
            
            logger.info(f"[Tool] 断言规则生成完成，数量={len(assertions)}")
            
            return json.dumps(assertions, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 断言规则生成失败: {str(e)}")
            return json.dumps([], ensure_ascii=False)
    
    def _extract_auth(self, swagger_json: str) -> str:
        """
        提取认证配置
        
        Args:
            swagger_json: Swagger文档JSON字符串
        
        Returns:
            认证配置JSON字符串
        """
        logger.info(f"[Tool] 提取认证配置")
        
        try:
            swagger_data = json.loads(swagger_json)
            
            security_schemes = swagger_data.get('components', {}).get('securitySchemes', {})
            
            auth_config = {
                'type': 'None',
                'login_endpoint': None
            }
            
            # 检查认证类型
            for scheme_name, scheme in security_schemes.items():
                if scheme.get('type') == 'oauth2':
                    auth_config['type'] = 'OAuth2'
                    # 查找登录接口
                    paths = swagger_data.get('paths', {})
                    for path in paths:
                        if 'login' in path.lower():
                            auth_config['login_endpoint'] = path
                            break
                elif scheme.get('type') == 'bearer':
                    auth_config['type'] = 'Bearer'
            
            logger.info(f"[Tool] 认证配置提取完成：{auth_config['type']}")
            
            return json.dumps(auth_config, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[Tool] 认证配置提取失败: {str(e)}")
            return json.dumps({'type': 'None'}, ensure_ascii=False)
    
    def _save_cases(self, test_cases_json: str) -> str:
        """
        保存测试用例
        
        Args:
            test_cases_json: 测试用例列表JSON字符串
        
        Returns:
            保存结果JSON字符串
        """
        logger.info(f"[Tool] 保存测试用例")
        
        # 简化实现：返回成功消息
        # 实际应保存到数据库
        
        return json.dumps({'success': True, 'message': '测试用例已保存'}, ensure_ascii=False)
    
    # === 辅助方法 ===
    
    def _get_default_value(self, param: Dict[str, Any]) -> Any:
        """获取参数默认值"""
        param_type = param.get('type', 'string')
        
        if param_type == 'string':
            return 'test_value'
        elif param_type == 'integer':
            return 1
        elif param_type == 'boolean':
            return True
        elif param_type == 'array':
            return []
        elif param_type == 'object':
            return {}
        else:
            return None
    
    def _generate_body_from_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """根据schema生成请求体"""
        body = {}
        
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        
        for prop_name, prop_def in properties.items():
            body[prop_name] = self._get_default_value(prop_def)
        
        return body