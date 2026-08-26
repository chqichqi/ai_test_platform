"""
CI/CD集成服务
支持Jenkins、GitLab CI、GitHub Actions
"""

import httpx
import json
import base64
import hashlib
import hmac
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.models.cicd import (
    CICDConfig, PipelineDefinition, PipelineExecution, WebhookEvent,
    CICDPlatform, PipelineStatus, TriggerType
)
from app.core.logger import logger


class JenkinsService:
    """Jenkins集成服务"""
    
    def __init__(self, config: CICDConfig):
        self.config = config
        self.base_url = config.platform_url.rstrip('/')
        self.username = config.username
        self.api_token = config.api_token
        self.auth = (self.username, self.api_token) if self.username and self.api_token else None
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/json",
                    auth=self.auth
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message": "连接成功",
                        "version": data.get("_version", "unknown")
                    }
                return {
                    "success": False,
                    "message": f"连接失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {str(e)}"
            }
    
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """获取Job列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/json?tree=jobs[name,url,color,lastBuild[number,result,timestamp,duration]]",
                    auth=self.auth
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("jobs", [])
                return []
        except Exception as e:
            logger.error(f"获取Jenkins Job列表失败: {str(e)}")
            return []
    
    async def get_job_info(self, job_name: str) -> Optional[Dict[str, Any]]:
        """获取Job详情"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/job/{job_name}/api/json",
                    auth=self.auth
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"获取Jenkins Job详情失败: {str(e)}")
            return None
    
    async def trigger_build(
        self,
        job_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """触发构建"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/job/{job_name}"
                
                if parameters or branch:
                    url += "/buildWithParameters"
                    params = {}
                    if branch:
                        params["BRANCH"] = branch
                    if parameters:
                        params.update(parameters)
                    response = await client.post(url, auth=self.auth, params=params)
                else:
                    url += "/build"
                    response = await client.post(url, auth=self.auth)
                
                if response.status_code in [200, 201, 302]:
                    queue_url = response.headers.get("Location", "")
                    return {
                        "success": True,
                        "message": "构建已触发",
                        "queue_url": queue_url
                    }
                return {
                    "success": False,
                    "message": f"触发失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"触发失败: {str(e)}"
            }
    
    async def get_build_status(self, job_name: str, build_number: int) -> Optional[Dict[str, Any]]:
        """获取构建状态"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/job/{job_name}/{build_number}/api/json",
                    auth=self.auth
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"获取Jenkins构建状态失败: {str(e)}")
            return None
    
    async def get_build_log(self, job_name: str, build_number: int) -> Optional[str]:
        """获取构建日志"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/job/{job_name}/{build_number}/consoleText",
                    auth=self.auth
                )
                if response.status_code == 200:
                    return response.text
                return None
        except Exception as e:
            logger.error(f"获取Jenkins构建日志失败: {str(e)}")
            return None


class GitLabService:
    """GitLab CI集成服务"""
    
    def __init__(self, config: CICDConfig):
        self.config = config
        self.base_url = config.platform_url.rstrip('/')
        self.api_token = config.api_token
        self.headers = {"PRIVATE-TOKEN": self.api_token} if self.api_token else {}
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v4/user",
                    headers=self.headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message": "连接成功",
                        "user": data.get("username", "unknown")
                    }
                return {
                    "success": False,
                    "message": f"连接失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {str(e)}"
            }
    
    async def list_projects(self) -> List[Dict[str, Any]]:
        """获取项目列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v4/projects?membership=true&per_page=100",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            logger.error(f"获取GitLab项目列表失败: {str(e)}")
            return []
    
    async def list_pipelines(self, project_id: int) -> List[Dict[str, Any]]:
        """获取Pipeline列表"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v4/projects/{project_id}/pipelines",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception as e:
            logger.error(f"获取GitLab Pipeline列表失败: {str(e)}")
            return []
    
    async def trigger_pipeline(
        self,
        project_id: int,
        ref: str = "main",
        variables: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """触发Pipeline"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                data = {"ref": ref}
                if variables:
                    data["variables"] = [{"key": k, "value": v} for k, v in variables.items()]
                
                response = await client.post(
                    f"{self.base_url}/api/v4/projects/{project_id}/pipeline",
                    headers=self.headers,
                    json=data
                )
                
                if response.status_code in [200, 201]:
                    result = response.json()
                    return {
                        "success": True,
                        "message": "Pipeline已触发",
                        "pipeline_id": result.get("id"),
                        "web_url": result.get("web_url")
                    }
                return {
                    "success": False,
                    "message": f"触发失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"触发失败: {str(e)}"
            }
    
    async def get_pipeline_status(self, project_id: int, pipeline_id: int) -> Optional[Dict[str, Any]]:
        """获取Pipeline状态"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"获取GitLab Pipeline状态失败: {str(e)}")
            return None


class GitHubService:
    """GitHub Actions集成服务"""
    
    def __init__(self, config: CICDConfig):
        self.config = config
        self.base_url = "https://api.github.com"
        self.api_token = config.api_token
        self.headers = {
            "Authorization": f"token {self.api_token}",
            "Accept": "application/vnd.github.v3+json"
        } if self.api_token else {}
        
        config_data = config.config_data or {}
        self.owner = config_data.get("owner", "")
        self.repo = config_data.get("repo", "")
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/user",
                    headers=self.headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message": "连接成功",
                        "user": data.get("login", "unknown")
                    }
                return {
                    "success": False,
                    "message": f"连接失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {str(e)}"
            }
    
    async def list_workflows(self) -> List[Dict[str, Any]]:
        """获取Workflow列表"""
        if not self.owner or not self.repo:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows",
                    headers=self.headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("workflows", [])
                return []
        except Exception as e:
            logger.error(f"获取GitHub Workflow列表失败: {str(e)}")
            return []
    
    async def list_workflow_runs(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取Workflow运行列表"""
        if not self.owner or not self.repo:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs"
                if workflow_id:
                    url = f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows/{workflow_id}/runs"
                
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("workflow_runs", [])
                return []
        except Exception as e:
            logger.error(f"获取GitHub Workflow运行列表失败: {str(e)}")
            return []
    
    async def trigger_workflow(
        self,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """触发Workflow"""
        if not self.owner or not self.repo:
            return {"success": False, "message": "未配置仓库信息"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                data = {"ref": ref}
                if inputs:
                    data["inputs"] = inputs
                
                response = await client.post(
                    f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/workflows/{workflow_id}/dispatches",
                    headers=self.headers,
                    json=data
                )
                
                if response.status_code in [200, 204]:
                    return {
                        "success": True,
                        "message": "Workflow已触发"
                    }
                return {
                    "success": False,
                    "message": f"触发失败: HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"触发失败: {str(e)}"
            }
    
    async def get_workflow_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """获取Workflow运行详情"""
        if not self.owner or not self.repo:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"获取GitHub Workflow运行详情失败: {str(e)}")
            return None
    
    async def cancel_workflow_run(self, run_id: int) -> bool:
        """取消Workflow运行"""
        if not self.owner or not self.repo:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/cancel",
                    headers=self.headers
                )
                return response.status_code in [200, 202]
        except Exception as e:
            logger.error(f"取消GitHub Workflow运行失败: {str(e)}")
            return False
    
    async def rerun_workflow(self, run_id: int) -> bool:
        """重新运行Workflow"""
        if not self.owner or not self.repo:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/rerun",
                    headers=self.headers
                )
                return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"重新运行GitHub Workflow失败: {str(e)}")
            return False


class CICDService:
    """CI/CD服务统一入口"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_service(self, config: CICDConfig):
        """根据平台获取对应服务"""
        if config.platform == CICDPlatform.JENKINS.value:
            return JenkinsService(config)
        elif config.platform == CICDPlatform.GITLAB.value:
            return GitLabService(config)
        elif config.platform == CICDPlatform.GITHUB.value:
            return GitHubService(config)
        raise ValueError(f"不支持的平台: {config.platform}")
    
    async def test_config(self, config_id: int) -> Dict[str, Any]:
        """测试配置连接"""
        config = self.db.query(CICDConfig).filter(CICDConfig.id == config_id).first()
        if not config:
            return {"success": False, "message": "配置不存在"}
        
        service = self.get_service(config)
        result = await service.test_connection()
        
        config.sync_status = "success" if result["success"] else "failed"
        config.sync_message = result["message"]
        config.last_sync_at = datetime.utcnow()
        self.db.commit()
        
        return result
    
    async def trigger_pipeline(
        self,
        pipeline_id: int,
        branch: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """触发Pipeline"""
        pipeline = self.db.query(PipelineDefinition).filter(
            PipelineDefinition.id == pipeline_id,
            PipelineDefinition.enabled == True
        ).first()
        
        if not pipeline:
            return {"success": False, "message": "Pipeline不存在或已禁用"}
        
        config = self.db.query(CICDConfig).filter(CICDConfig.id == pipeline.config_id).first()
        if not config:
            return {"success": False, "message": "CI/CD配置不存在"}
        
        service = self.get_service(config)
        
        execution = PipelineExecution(
            pipeline_id=pipeline_id,
            project_id=pipeline.project_id,
            status=PipelineStatus.PENDING.value,
            trigger_type=TriggerType.MANUAL.value,
            trigger_by=str(user_id) if user_id else "api",
            trigger_ref=branch
        )
        self.db.add(execution)
        self.db.flush()
        
        trigger_params = pipeline.test_params or {}
        if parameters:
            trigger_params.update(parameters)
        
        if config.platform == CICDPlatform.JENKINS.value:
            result = await service.trigger_build(
                pipeline.external_id,
                parameters=trigger_params,
                branch=branch
            )
        elif config.platform == CICDPlatform.GITLAB.value:
            project_id = config.config_data.get("project_id") if config.config_data else None
            if not project_id:
                result = {"success": False, "message": "未配置GitLab项目ID"}
            else:
                result = await service.trigger_pipeline(
                    project_id,
                    ref=branch or "main",
                    variables=trigger_params
                )
                if result.get("success"):
                    execution.external_build_id = str(result.get("pipeline_id"))
        elif config.platform == CICDPlatform.GITHUB.value:
            result = await service.trigger_workflow(
                pipeline.external_id,
                ref=branch or "main",
                inputs=trigger_params
            )
        else:
            result = {"success": False, "message": "不支持的平台"}
        
        if result.get("success"):
            execution.status = PipelineStatus.RUNNING.value
            execution.started_at = datetime.utcnow()
        else:
            execution.status = PipelineStatus.FAILED.value
            execution.error_message = result.get("message")
        
        self.db.commit()
        self.db.refresh(execution)
        
        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "execution_id": execution.id
        }
    
    async def handle_webhook(
        self,
        platform: str,
        headers: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理Webhook回调"""
        event = WebhookEvent(
            source=platform,
            headers=headers,
            payload=payload,
            event_type=self._detect_event_type(platform, headers, payload)
        )
        self.db.add(event)
        self.db.flush()
        
        try:
            if platform == CICDPlatform.JENKINS.value:
                result = await self._handle_jenkins_webhook(event, payload)
            elif platform == CICDPlatform.GITLAB.value:
                result = await self._handle_gitlab_webhook(event, payload)
            elif platform == CICDPlatform.GITHUB.value:
                result = await self._handle_github_webhook(event, headers, payload)
            else:
                result = {"success": False, "message": "不支持的平台"}
            
            event.processed = True
            event.process_result = json.dumps(result)
            event.processed_at = datetime.utcnow()
            
        except Exception as e:
            result = {"success": False, "message": str(e)}
            event.process_error = str(e)
            event.processed_at = datetime.utcnow()
        
        self.db.commit()
        return result
    
    def _detect_event_type(self, platform: str, headers: Dict[str, Any], payload: Dict[str, Any]) -> str:
        """检测事件类型"""
        if platform == CICDPlatform.GITHUB.value:
            return headers.get("x-github-event", "unknown")
        elif platform == CICDPlatform.GITLAB.value:
            return payload.get("object_kind", "unknown")
        elif platform == CICDPlatform.JENKINS.value:
            return "build"
        return "unknown"
    
    async def _handle_jenkins_webhook(self, event: WebhookEvent, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理Jenkins Webhook"""
        return {"success": True, "message": "Jenkins webhook received"}
    
    async def _handle_gitlab_webhook(self, event: WebhookEvent, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理GitLab Webhook"""
        object_kind = payload.get("object_kind", "")
        
        if object_kind == "pipeline":
            status = payload.get("object_attributes", {}).get("status", "")
            project_id = payload.get("project", {}).get("id")
            pipeline_id = payload.get("object_attributes", {}).get("id")
            
            execution = self.db.query(PipelineExecution).filter(
                PipelineExecution.external_build_id == str(pipeline_id)
            ).first()
            
            if execution:
                status_map = {
                    "pending": PipelineStatus.PENDING.value,
                    "running": PipelineStatus.RUNNING.value,
                    "success": PipelineStatus.SUCCESS.value,
                    "failed": PipelineStatus.FAILED.value,
                    "canceled": PipelineStatus.CANCELLED.value
                }
                execution.status = status_map.get(status, PipelineStatus.RUNNING.value)
                
                if status in ["success", "failed", "canceled"]:
                    execution.finished_at = datetime.utcnow()
                    if execution.started_at:
                        execution.duration = int(
                            (execution.finished_at - execution.started_at).total_seconds()
                        )
                
                self.db.commit()
        
        return {"success": True, "message": f"GitLab {object_kind} event processed"}
    
    async def _handle_github_webhook(self, event: WebhookEvent, headers: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理GitHub Webhook"""
        event_type = headers.get("x-github-event", "")
        
        if event_type == "workflow_run":
            action = payload.get("action", "")
            workflow_run = payload.get("workflow_run", {})
            run_id = workflow_run.get("id")
            
            execution = self.db.query(PipelineExecution).filter(
                PipelineExecution.external_build_id == str(run_id)
            ).first()
            
            if execution:
                status_map = {
                    "queued": PipelineStatus.PENDING.value,
                    "in_progress": PipelineStatus.RUNNING.value,
                    "completed": PipelineStatus.SUCCESS.value if workflow_run.get("conclusion") == "success" else PipelineStatus.FAILED.value
                }
                
                execution.status = status_map.get(workflow_run.get("status"), PipelineStatus.RUNNING.value)
                execution.build_url = workflow_run.get("html_url")
                
                if action == "completed":
                    execution.finished_at = datetime.utcnow()
                    if execution.started_at:
                        execution.duration = int(
                            (execution.finished_at - execution.started_at).total_seconds()
                        )
                
                self.db.commit()
        
        return {"success": True, "message": f"GitHub {event_type} event processed"}
    
    def get_dashboard_stats(self, project_id: int) -> Dict[str, Any]:
        """获取CI/CD仪表盘统计"""
        total_configs = self.db.query(CICDConfig).filter(
            CICDConfig.project_id == project_id
        ).count()
        
        active_configs = self.db.query(CICDConfig).filter(
            CICDConfig.project_id == project_id,
            CICDConfig.enabled == True
        ).count()
        
        total_pipelines = self.db.query(PipelineDefinition).filter(
            PipelineDefinition.project_id == project_id
        ).count()
        
        active_pipelines = self.db.query(PipelineDefinition).filter(
            PipelineDefinition.project_id == project_id,
            PipelineDefinition.enabled == True
        ).count()
        
        total_executions = self.db.query(PipelineExecution).filter(
            PipelineExecution.project_id == project_id
        ).count()
        
        success_executions = self.db.query(PipelineExecution).filter(
            PipelineExecution.project_id == project_id,
            PipelineExecution.status == PipelineStatus.SUCCESS.value
        ).count()
        
        success_rate = (success_executions / total_executions * 100) if total_executions > 0 else 0
        
        recent_executions = self.db.query(PipelineExecution).filter(
            PipelineExecution.project_id == project_id
        ).order_by(PipelineExecution.created_at.desc()).limit(10).all()
        
        return {
            "total_configs": total_configs,
            "active_configs": active_configs,
            "total_pipelines": total_pipelines,
            "active_pipelines": active_pipelines,
            "total_executions": total_executions,
            "success_rate": round(success_rate, 2),
            "recent_executions": [
                {
                    "id": e.id,
                    "pipeline_id": e.pipeline_id,
                    "status": e.status,
                    "trigger_type": e.trigger_type,
                    "trigger_by": e.trigger_by,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "duration": e.duration,
                    "pass_rate": e.pass_rate
                }
                for e in recent_executions
            ]
        }