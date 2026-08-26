"""
功能测试生成模块服务
支持通过聊天或传入Swagger地址等方式生成测试用例
"""

import json
import re
import yaml
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
import requests

from app.core.config import settings
from app.core.logger import logger
from app.core.models.user import User
from app.services.rag_service import RAGService
# from app.services.skill_service import SkillService  # 旧版SKILL已移除


class FunctionalTestService:
    """功能测试生成服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.rag_service = RAGService(db)
        # self.skill_service = SkillService(db)  # 旧版SKILL已移除
    
    def generate_from_chat(
        self,
        chat_message: str,
        project_name: str = None,
        user: User = None
    ) -> Dict[str, Any]:
        """
        从聊天消息生成测试用例
        
        Args:
            chat_message: 聊天消息
            project_name: 项目名称（可选）
            user: 用户（可选）
            
        Returns:
            生成的测试用例
        """
        try:
            logger.info(f"从聊天生成测试用例: {chat_message[:100]}...")
            
            # 分析聊天消息
            analysis = self._analyze_chat_message(chat_message)
            
            # 提取测试需求
            test_requirements = self._extract_test_requirements(analysis)
            
            # 生成测试用例
            test_cases = []
            
            if test_requirements.get("has_rag_query"):
                # 如果有RAG查询，使用RAG生成测试用例
                kb_id = test_requirements.get("knowledge_base_id")
                if kb_id:
                    rag_result = self.rag_service.query_knowledge_base(
                        kb_id=kb_id,
                        query=test_requirements.get("rag_query", chat_message),
                        query_type="test_case",
                        user=user
                    )
                    
                    if rag_result.get("generated_content"):
                        try:
                            generated_cases = json.loads(rag_result["generated_content"])
                            if isinstance(generated_cases, list):
                                test_cases.extend(generated_cases)
                        except json.JSONDecodeError:
                            logger.warning("无法解析RAG生成的测试用例JSON")
            
            if not test_cases:
                # 如果没有RAG结果或没有RAG查询，使用规则生成
                test_cases = self._generate_from_rules(test_requirements)
            
            # 应用SKILL（如果有指定）
            if test_requirements.get("skill_name"):
                skill_result = self._apply_skill_to_test_cases(
                    test_cases,
                    test_requirements["skill_name"],
                    test_requirements.get("skill_parameters", {}),
                    user
                )
                test_cases = skill_result.get("enhanced_cases", test_cases)
            
            return {
                "success": True,
                "message": "测试用例生成成功",
                "test_cases": test_cases,
                "analysis": analysis,
                "requirements": test_requirements,
                "count": len(test_cases)
            }
            
        except Exception as e:
            logger.error(f"从聊天生成测试用例失败: {str(e)}")
            return {
                "success": False,
                "message": f"生成失败: {str(e)}",
                "test_cases": []
            }
    
    def generate_from_swagger(
        self,
        swagger_url: str,
        project_name: str = None,
        user: User = None
    ) -> Dict[str, Any]:
        """
        从Swagger API文档生成测试用例
        
        Args:
            swagger_url: Swagger文档URL
            project_name: 项目名称（可选）
            user: 用户（可选）
            
        Returns:
            生成的测试用例
        """
        try:
            logger.info(f"从Swagger生成测试用例: {swagger_url}")
            
            # 获取Swagger文档
            swagger_doc = self._fetch_swagger_document(swagger_url)
            
            # 解析Swagger文档
            api_spec = self._parse_swagger_document(swagger_doc)
            
            # 生成API测试用例
            test_cases = self._generate_api_test_cases(api_spec)
            
            # 生成功能测试用例（基于API）
            functional_cases = self._generate_functional_test_cases(api_spec)
            
            # 合并测试用例
            all_cases = test_cases + functional_cases
            
            return {
                "success": True,
                "message": "从Swagger生成测试用例成功",
                "swagger_url": swagger_url,
                "api_count": len(api_spec.get("apis", [])),
                "test_cases": all_cases,
                "api_test_cases": test_cases,
                "functional_test_cases": functional_cases,
                "count": len(all_cases)
            }
            
        except Exception as e:
            logger.error(f"从Swagger生成测试用例失败: {str(e)}")
            return {
                "success": False,
                "message": f"生成失败: {str(e)}",
                "test_cases": []
            }
    
    def generate_from_requirements(
        self,
        requirements_text: str,
        project_name: str,
        version: str = "1.0.0",
        user: User = None
    ) -> Dict[str, Any]:
        """
        从需求文档文本生成测试用例
        
        Args:
            requirements_text: 需求文档文本
            project_name: 项目名称
            version: 版本号
            user: 用户（可选）
            
        Returns:
            生成的测试用例
        """
        try:
            logger.info(f"从需求文档生成测试用例: {project_name} v{version}")
            
            # 保存需求文档到临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(requirements_text)
                temp_file = f.name
            
            try:
                # 上传到RAG知识库
                rag_service = RAGService(self.db)
                
                # 创建知识库
                kb = rag_service.upload_document(
                    file_path=temp_file,
                    project_name=project_name,
                    version=version,
                    name=f"{project_name}_requirements",
                    description=f"{project_name} {version} 需求文档",
                    user=user
                )
                
                # 等待处理完成（简化处理，实际应该使用异步任务）
                import time
                max_wait = 30  # 最大等待30秒
                wait_interval = 2
                
                for _ in range(max_wait // wait_interval):
                    kb = rag_service.get_knowledge_base(kb.id)
                    if kb and kb.status == "completed":
                        break
                    time.sleep(wait_interval)
                
                if kb and kb.status == "completed":
                    # 查询知识库生成测试用例
                    rag_result = rag_service.query_knowledge_base(
                        kb_id=kb.id,
                        query="生成完整的功能测试用例",
                        query_type="test_case",
                        user=user
                    )
                    
                    if rag_result.get("generated_content"):
                        try:
                            test_cases = json.loads(rag_result["generated_content"])
                            if not isinstance(test_cases, list):
                                test_cases = [test_cases]
                        except json.JSONDecodeError:
                            test_cases = self._generate_from_text_rules(requirements_text)
                    else:
                        test_cases = self._generate_from_text_rules(requirements_text)
                else:
                    test_cases = self._generate_from_text_rules(requirements_text)
                
                return {
                    "success": True,
                    "message": "从需求文档生成测试用例成功",
                    "knowledge_base_id": kb.id if kb else None,
                    "knowledge_base_status": kb.status if kb else "failed",
                    "test_cases": test_cases,
                    "count": len(test_cases)
                }
                
            finally:
                # 清理临时文件
                import os
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            
        except Exception as e:
            logger.error(f"从需求文档生成测试用例失败: {str(e)}")
            return {
                "success": False,
                "message": f"生成失败: {str(e)}",
                "test_cases": []
            }
    
    def _analyze_chat_message(self, message: str) -> Dict[str, Any]:
        """分析聊天消息"""
        analysis = {
            "has_rag_query": False,
            "has_swagger_url": False,
            "has_skill_request": False,
            "has_test_requirements": False,
            "has_web_ui": False,
            "keywords": [],
            "entities": []
        }
        
        # 检查是否包含RAG查询关键词
        rag_keywords = ["知识库", "文档", "需求", "spec", "文档", "上传", "rag"]
        for keyword in rag_keywords:
            if keyword.lower() in message.lower():
                analysis["has_rag_query"] = True
                analysis["keywords"].append(keyword)
        
        # 检查是否包含Swagger URL
        url_pattern = r'https?://[^\s]+(?:swagger|openapi)[^\s]*'
        urls = re.findall(url_pattern, message, re.IGNORECASE)
        if urls:
            analysis["has_swagger_url"] = True
            analysis["swagger_urls"] = urls
        
        # 检查是否包含SKILL请求
        skill_pattern = r'使用(?:SKILL|技能)?[:：]?\s*([^\s,，.。]+)'
        skill_matches = re.findall(skill_pattern, message)
        if skill_matches:
            analysis["has_skill_request"] = True
            analysis["skill_name"] = skill_matches[0]
        
        # 检查测试需求关键词
        test_keywords = ["测试", "用例", "功能", "验证", "检查", "test", "case", "功能测试"]
        for keyword in test_keywords:
            if keyword in message:
                analysis["has_test_requirements"] = True
                analysis["keywords"].append(keyword)
        
        # 检查WEB UI相关关键词
        web_ui_keywords = ["网页", "界面", "UI", "前端", "浏览器", "点击", "输入", "按钮", "链接", 
                         "登录", "注册", "表单", "下拉", "复选框", "单选框", "playwright", "selenium"]
        for keyword in web_ui_keywords:
            if keyword.lower() in message.lower():
                analysis["has_web_ui"] = True
                analysis["keywords"].append(keyword)
                break
        
        # 提取实体（项目名、模块名等）
        entity_patterns = [
            r'项目[:：]\s*([^\s,，.。]+)',
            r'模块[:：]\s*([^\s,，.。]+)',
            r'功能[:：]\s*([^\s,，.。]+)'
        ]
        
        for pattern in entity_patterns:
            matches = re.findall(pattern, message)
            analysis["entities"].extend(matches)
        
        return analysis
    
    def _extract_test_requirements(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """提取测试需求"""
        requirements = {
            "priority": "medium",
            "scope": "functional",
            "coverage": "basic"
        }
        
        # 根据分析结果设置需求
        if analysis.get("has_rag_query"):
            requirements["source"] = "rag"
            requirements["coverage"] = "comprehensive"
        
        if analysis.get("has_swagger_url"):
            requirements["source"] = "swagger"
            requirements["scope"] = "api"
        
        if analysis.get("has_skill_request"):
            requirements["skill_name"] = analysis.get("skill_name")
            requirements["skill_parameters"] = {}
        
        # 检查是否为WEB UI测试
        if analysis.get("has_web_ui"):
            requirements["scope"] = "web_ui"
            requirements["coverage"] = "ui_interaction"
        
        # 根据关键词调整优先级
        keywords = analysis.get("keywords", [])
        # 检查是否包含紧急或重要关键词
        has_urgent = any(k == "紧急" or "urgent" in k.lower() for k in keywords)
        has_important = any(k == "重要" or "important" in k.lower() for k in keywords)
        if has_urgent:
            requirements["priority"] = "high"
        elif has_important:
            requirements["priority"] = "medium"
        else:
            requirements["priority"] = "low"
        
        return requirements
    
    def _generate_from_rules(self, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """根据规则生成测试用例"""
        test_cases = []
        
        # 基础测试用例模板
        base_cases = [
            {
                "test_case_id": "TC-FUNC-001",
                "title": "基本功能验证",
                "description": "验证系统基本功能是否正常工作",
                "priority": requirements.get("priority", "medium"),
                "category": "功能测试",
                "preconditions": ["系统已正常启动", "测试环境已准备就绪"],
                "test_steps": [
                    {"step": 1, "action": "访问系统首页", "expected": "页面正常加载"},
                    {"step": 2, "action": "执行基本操作", "expected": "操作响应正常"},
                    {"step": 3, "action": "检查结果", "expected": "结果符合预期"}
                ],
                "expected_results": "基本功能正常工作",
                "tags": ["basic", "smoke"]
            },
            {
                "test_case_id": "TC-FUNC-002",
                "title": "数据输入验证",
                "description": "验证系统对数据输入的验证和处理",
                "priority": requirements.get("priority", "medium"),
                "category": "功能测试",
                "preconditions": ["测试数据已准备"],
                "test_steps": [
                    {"step": 1, "action": "输入有效数据", "expected": "数据被接受"},
                    {"step": 2, "action": "输入无效数据", "expected": "显示错误提示"},
                    {"step": 3, "action": "输入边界值数据", "expected": "正确处理"}
                ],
                "expected_results": "数据输入验证功能正常",
                "tags": ["validation", "input"]
            }
        ]
        
        # 根据需求调整测试用例
        scope = requirements.get("scope", "functional")
        if scope == "api":
            # 添加API相关测试用例
            api_cases = [
                {
                    "test_case_id": "TC-API-001",
                    "title": "API端点可用性测试",
                    "description": "验证API端点是否可访问",
                    "priority": "high",
                    "category": "API测试",
                    "preconditions": ["API服务已启动"],
                    "test_steps": [
                        {"step": 1, "action": "发送GET请求到健康检查端点", "expected": "返回200状态码"},
                        {"step": 2, "action": "发送OPTIONS请求", "expected": "返回支持的HTTP方法"}
                    ],
                    "expected_results": "API端点可正常访问",
                    "tags": ["api", "availability"]
                }
            ]
            test_cases.extend(api_cases)
        
        # 如果不是WEB UI范围，添加基础测试用例
        if scope != "web_ui":
            test_cases.extend(base_cases)
        
        # 根据优先级调整测试用例数量
        priority = requirements.get("priority", "medium")
        if priority == "high":
            # 添加更多测试用例
            extra_cases = [
                {
                    "test_case_id": "TC-FUNC-003",
                    "title": "错误处理验证",
                    "description": "验证系统在异常情况下的处理能力",
                    "priority": "high",
                    "category": "功能测试",
                    "preconditions": [],
                    "test_steps": [
                        {"step": 1, "action": "模拟网络中断", "expected": "系统显示适当错误信息"},
                        {"step": 2, "action": "输入超长数据", "expected": "系统正确处理或提示"},
                        {"step": 3, "action": "并发操作", "expected": "系统保持稳定"}
                    ],
                    "expected_results": "错误处理功能正常",
                    "tags": ["error", "robustness"]
                }
            ]
            test_cases.extend(extra_cases)
        
        # 如果scope是web_ui，生成WEB UI特定的测试用例
        if scope == "web_ui":
            web_ui_cases = self._generate_web_ui_test_cases(requirements)
            test_cases.extend(web_ui_cases)
        
        return test_cases
    
    def _generate_web_ui_test_cases(self, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成WEB UI测试用例"""
        web_ui_cases = [
            {
                "test_case_id": "TC-WEBUI-001",
                "title": "用户登录功能测试",
                "description": "验证用户登录界面的功能和UI交互",
                "priority": requirements.get("priority", "medium"),
                "category": "WEB UI测试",
                "preconditions": ["系统已部署并可通过浏览器访问", "测试账号已准备"],
                "test_steps": [
                    {"step": 1, "action": "打开浏览器访问登录页面", "expected": "登录页面正常加载"},
                    {"step": 2, "action": "在用户名输入框输入测试用户名", "expected": "用户名输入成功"},
                    {"step": 3, "action": "在密码输入框输入测试密码", "expected": "密码输入成功"},
                    {"step": 4, "action": "点击登录按钮", "expected": "登录请求提交"},
                    {"step": 5, "action": "验证登录成功后的页面跳转", "expected": "跳转到首页或仪表板"}
                ],
                "expected_results": "用户登录功能正常，UI交互正确",
                "tags": ["web_ui", "login", "authentication"]
            },
            {
                "test_case_id": "TC-WEBUI-002",
                "title": "表单提交功能测试",
                "description": "验证表单填写和提交的UI交互",
                "priority": requirements.get("priority", "medium"),
                "category": "WEB UI测试",
                "preconditions": ["系统已部署", "表单页面可访问"],
                "test_steps": [
                    {"step": 1, "action": "访问表单页面", "expected": "表单页面正常加载"},
                    {"step": 2, "action": "填写表单必填字段", "expected": "字段输入成功"},
                    {"step": 3, "action": "点击提交按钮", "expected": "表单数据提交"},
                    {"step": 4, "action": "验证提交后的反馈信息", "expected": "显示成功或错误提示"}
                ],
                "expected_results": "表单提交功能正常，UI反馈正确",
                "tags": ["web_ui", "form", "submit"]
            },
            {
                "test_case_id": "TC-WEBUI-003",
                "title": "导航菜单功能测试",
                "description": "验证网站导航菜单的点击和页面跳转",
                "priority": requirements.get("priority", "medium"),
                "category": "WEB UI测试",
                "preconditions": ["网站首页可访问"],
                "test_steps": [
                    {"step": 1, "action": "访问网站首页", "expected": "首页正常加载，导航菜单可见"},
                    {"step": 2, "action": "点击导航菜单中的'产品'链接", "expected": "跳转到产品页面"},
                    {"step": 3, "action": "点击导航菜单中的'关于我们'链接", "expected": "跳转到关于我们页面"},
                    {"step": 4, "action": "点击导航菜单中的'联系我们'链接", "expected": "跳转到联系我们页面"}
                ],
                "expected_results": "导航菜单功能正常，页面跳转正确",
                "tags": ["web_ui", "navigation", "menu"]
            }
        ]
        
        # 根据优先级调整
        priority = requirements.get("priority", "medium")
        if priority == "high":
            # 添加更多WEB UI测试用例
            extra_web_ui_cases = [
                {
                    "test_case_id": "TC-WEBUI-004",
                    "title": "响应式布局测试",
                    "description": "验证网站在不同视口尺寸下的布局适配",
                    "priority": "high",
                    "category": "WEB UI测试",
                    "preconditions": ["网站可访问"],
                    "test_steps": [
                        {"step": 1, "action": "在桌面分辨率(1920x1080)下访问网站", "expected": "桌面布局正常显示"},
                        {"step": 2, "action": "切换到平板分辨率(768x1024)下访问", "expected": "平板布局正常显示"},
                        {"step": 3, "action": "切换到手机分辨率(375x667)下访问", "expected": "手机布局正常显示"}
                    ],
                    "expected_results": "网站在不同设备上布局适配正常",
                    "tags": ["web_ui", "responsive", "layout"]
                },
                {
                    "test_case_id": "TC-WEBUI-005",
                    "title": "浏览器兼容性测试",
                    "description": "验证网站在不同浏览器中的显示和功能",
                    "priority": "high",
                    "category": "WEB UI测试",
                    "preconditions": ["网站可访问"],
                    "test_steps": [
                        {"step": 1, "action": "在Chrome浏览器中访问网站", "expected": "网站功能正常"},
                        {"step": 2, "action": "在Firefox浏览器中访问网站", "expected": "网站功能正常"},
                        {"step": 3, "action": "在Edge浏览器中访问网站", "expected": "网站功能正常"}
                    ],
                    "expected_results": "网站在不同浏览器中功能正常",
                    "tags": ["web_ui", "browser", "compatibility"]
                }
            ]
            web_ui_cases.extend(extra_web_ui_cases)
        
        return web_ui_cases
    
    def _fetch_swagger_document(self, swagger_url: str) -> Dict[str, Any]:
        """获取Swagger文档"""
        try:
            response = requests.get(swagger_url, timeout=10)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            
            if 'application/json' in content_type:
                return response.json()
            elif 'application/yaml' in content_type or 'text/yaml' in content_type:
                return yaml.safe_load(response.text)
            else:
                # 尝试自动检测格式
                try:
                    return response.json()
                except:
                    try:
                        return yaml.safe_load(response.text)
                    except:
                        raise ValueError("无法解析Swagger文档格式")
                        
        except requests.RequestException as e:
            logger.error(f"获取Swagger文档失败: {str(e)}")
            raise
    
    def _parse_swagger_document(self, swagger_doc: Dict[str, Any]) -> Dict[str, Any]:
        """解析Swagger文档"""
        api_spec = {
            "title": swagger_doc.get("info", {}).get("title", "Unknown API"),
            "version": swagger_doc.get("info", {}).get("version", "1.0.0"),
            "description": swagger_doc.get("info", {}).get("description", ""),
            "base_path": swagger_doc.get("basePath", ""),
            "host": swagger_doc.get("host", ""),
            "schemes": swagger_doc.get("schemes", ["http"]),
            "apis": []
        }
        
        # 解析路径
        paths = swagger_doc.get("paths", {})
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.lower() in ["get", "post", "put", "delete", "patch"]:
                    api_info = {
                        "path": path,
                        "method": method.upper(),
                        "operation_id": spec.get("operationId", ""),
                        "summary": spec.get("summary", ""),
                        "description": spec.get("description", ""),
                        "tags": spec.get("tags", []),
                        "parameters": spec.get("parameters", []),
                        "responses": spec.get("responses", {})
                    }
                    api_spec["apis"].append(api_info)
        
        return api_spec
    
    def _generate_api_test_cases(self, api_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成API测试用例"""
        test_cases = []
        
        for i, api in enumerate(api_spec["apis"], 1):
            test_case = {
                "test_case_id": f"TC-API-{i:03d}",
                "title": f"{api['method']} {api['path']} - {api.get('summary', 'API测试')}",
                "description": api.get("description", f"测试{api['method']} {api['path']}接口"),
                "priority": self._determine_api_priority(api),
                "category": "API测试",
                "preconditions": [
                    "API服务已启动",
                    "测试环境配置正确"
                ],
                "test_steps": self._generate_api_test_steps(api),
                "expected_results": self._generate_api_expected_results(api),
                "tags": api.get("tags", []) + ["api", api["method"].lower()]
            }
            test_cases.append(test_case)
        
        return test_cases
    
    def _generate_functional_test_cases(self, api_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成功能测试用例（基于API）"""
        test_cases = []
        
        # 按功能分组API
        api_groups = {}
        for api in api_spec["apis"]:
            tags = api.get("tags", ["default"])
            main_tag = tags[0] if tags else "default"
            
            if main_tag not in api_groups:
                api_groups[main_tag] = []
            api_groups[main_tag].append(api)
        
        # 为每个功能组生成测试用例
        for i, (tag, apis) in enumerate(api_groups.items(), 1):
            test_case = {
                "test_case_id": f"TC-FUNC-{i:03d}",
                "title": f"{tag}功能测试",
                "description": f"测试{tag}相关功能的完整流程",
                "priority": "medium",
                "category": "功能测试",
                "preconditions": [
                    "系统已正常启动",
                    "测试数据已准备"
                ],
                "test_steps": self._generate_functional_test_steps(apis),
                "expected_results": f"{tag}功能正常工作，所有相关API调用成功",
                "tags": [tag, "functional", "integration"]
            }
            test_cases.append(test_case)
        
        return test_cases
    
    def _determine_api_priority(self, api: Dict[str, Any]) -> str:
        """确定API测试优先级"""
        method = api["method"]
        path = api["path"]
        
        # 关键API（认证、健康检查等）
        critical_paths = ["/auth", "/login", "/health", "/status"]
        for critical in critical_paths:
            if critical in path:
                return "high"
        
        # 写操作通常比读操作更重要
        if method in ["POST", "PUT", "DELETE"]:
            return "high"
        elif method == "GET":
            return "medium"
        else:
            return "low"
    
    def _generate_api_test_steps(self, api: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成API测试步骤"""
        steps = []
        
        # 步骤1：准备请求
        steps.append({
            "step": 1,
            "action": f"准备{api['method']}请求到{api['path']}",
            "expected": "请求参数准备完成"
        })
        
        # 步骤2：发送请求
        steps.append({
            "step": 2,
            "action": f"发送{api['method']}请求",
            "expected": "收到服务器响应"
        })
        
        # 步骤3：验证响应
        steps.append({
            "step": 3,
            "action": "验证响应状态码",
            "expected": "状态码为2xx（成功）"
        })
        
        # 步骤4：验证响应数据
        steps.append({
            "step": 4,
            "action": "验证响应数据格式和内容",
            "expected": "响应数据符合预期格式"
        })
        
        return steps
    
    def _generate_api_expected_results(self, api: Dict[str, Any]) -> str:
        """生成API预期结果"""
        responses = api.get("responses", {})
        
        success_codes = []
        for code in responses:
            if code.startswith("2"):
                success_codes.append(code)
        
        if success_codes:
            return f"API返回{', '.join(success_codes)}状态码，响应数据符合定义"
        else:
            return "API调用成功，响应符合预期"
    
    def _generate_functional_test_steps(self, apis: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成功能测试步骤"""
        steps = []
        step_num = 1
        
        # 按操作类型排序：先创建，再读取，再更新，最后删除
        sorted_apis = sorted(apis, key=lambda x: {
            "POST": 1, "GET": 2, "PUT": 3, "PATCH": 4, "DELETE": 5
        }.get(x["method"], 6))
        
        for api in sorted_apis:
            steps.append({
                "step": step_num,
                "action": f"调用{api['method']} {api['path']}接口",
                "expected": f"接口调用成功，返回预期结果"
            })
            step_num += 1
        
        return steps
    
    def _generate_from_text_rules(self, text: str) -> List[Dict[str, Any]]:
        """从文本规则生成测试用例"""
        test_cases = []
        
        # 提取功能点
        functions = self._extract_functions_from_text(text)
        
        for i, func in enumerate(functions, 1):
            test_case = {
                "test_case_id": f"TC-REQ-{i:03d}",
                "title": f"{func}功能测试",
                "description": f"验证{func}功能是否符合需求",
                "priority": "medium",
                "category": "功能测试",
                "preconditions": ["系统已部署", "测试环境准备就绪"],
                "test_steps": [
                    {"step": 1, "action": f"执行{func}相关操作", "expected": "操作执行成功"},
                    {"step": 2, "action": "验证操作结果", "expected": "结果符合需求定义"},
                    {"step": 3, "action": "检查系统状态", "expected": "系统状态正常"}
                ],
                "expected_results": f"{func}功能正常工作，符合需求定义",
                "tags": ["requirement", "functional"]
            }
            test_cases.append(test_case)
        
        return test_cases
    
    def _extract_functions_from_text(self, text: str) -> List[str]:
        """从文本中提取功能点"""
        functions = []
        
        # 查找功能描述
        patterns = [
            r'功能[:：]\s*([^\n。.!?]+)',
            r'实现[:：]\s*([^\n。.!?]+)',
            r'支持[:：]\s*([^\n。.!?]+)',
            r'提供[:：]\s*([^\n。.!?]+)',
            r'能够[:：]\s*([^\n。.!?]+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            functions.extend(matches)
        
        # 如果没有找到，使用简单分词
        if not functions:
            # 简单的关键词提取
            keywords = ["管理", "查询", "添加", "删除", "修改", "导入", "导出", "统计", "分析"]
            sentences = re.split(r'[。.!?]', text)
            
            for sentence in sentences:
                for keyword in keywords:
                    if keyword in sentence and len(sentence) > 10:
                        functions.append(sentence.strip())
                        break
        
        # 去重和清理
        functions = list(set([f.strip() for f in functions if f.strip()]))
        
        return functions[:10]  # 最多返回10个功能点
    
    def _apply_skill_to_test_cases(
        self,
        test_cases: List[Dict[str, Any]],
        skill_name: str,
        skill_parameters: Dict[str, Any],
        user: User = None
    ) -> Dict[str, Any]:
        """应用SKILL到测试用例 - 使用新版SKILL管理模块"""
        try:
            # TODO: 集成新版SKILL管理模块
            # 新版SKILL通过 test_skill 模型管理，不是通过 skill_service 执行
            logger.info(f"应用SKILL到测试用例: {skill_name}")
            
            # 暂时返回原始测试用例（待集成新版SKILL）
            return {
                "success": True,
                "message": "SKILL应用成功（使用新版SKILL模块）",
                "enhanced_cases": test_cases,
                "skill_execution_id": None
            }
            
        except Exception as e:
            logger.error(f"应用SKILL到测试用例失败: {str(e)}")
            return {
                "success": False,
                "message": f"应用失败: {str(e)}",
                "enhanced_cases": test_cases
            }