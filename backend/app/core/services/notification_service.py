"""
通知服务
支持飞书、钉钉、企业微信、邮件通知
"""

import httpx
import json
import smtplib
import hmac
import hashlib
import base64
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.models.notification import (
    NotificationChannel, AlertRule, MessageTemplate, NotificationHistory,
    NotificationType, AlertConditionType
)
from app.core.logger import logger


class NotificationService:
    """通知服务基类"""
    
    def __init__(self, channel: NotificationChannel):
        self.channel = channel
    
    async def send(self, title: str, content: str, recipients: List[str] = None) -> Dict[str, Any]:
        raise NotImplementedError


class FeishuNotification(NotificationService):
    """飞书通知"""
    
    async def send(self, title: str, content: str, recipients: List[str] = None) -> Dict[str, Any]:
        webhook_url = self.channel.webhook_url
        if not webhook_url:
            return {"success": False, "message": "未配置Webhook URL"}
        
        message = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "red"
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "plain_text", "content": content}}
                ]
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=message)
                result = response.json()
                
                if result.get("StatusCode") == 0 or result.get("code") == 0:
                    return {"success": True, "message": "发送成功"}
                return {"success": False, "message": result.get("msg", "发送失败")}
        except Exception as e:
            return {"success": False, "message": str(e)}


class DingtalkNotification(NotificationService):
    """钉钉通知"""
    
    async def send(self, title: str, content: str, recipients: List[str] = None) -> Dict[str, Any]:
        webhook_url = self.channel.webhook_url
        if not webhook_url:
            return {"success": False, "message": "未配置Webhook URL"}
        
        message = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content
            }
        }
        
        if self.channel.secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{self.channel.secret}"
            hmac_code = hmac.new(
                self.channel.secret.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')
            webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=message)
                result = response.json()
                
                if result.get("errcode") == 0:
                    return {"success": True, "message": "发送成功"}
                return {"success": False, "message": result.get("errmsg", "发送失败")}
        except Exception as e:
            return {"success": False, "message": str(e)}


class WechatNotification(NotificationService):
    """企业微信通知"""
    
    async def send(self, title: str, content: str, recipients: List[str] = None) -> Dict[str, Any]:
        webhook_url = self.channel.webhook_url
        if not webhook_url:
            return {"success": False, "message": "未配置Webhook URL"}
        
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{content}"
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=message)
                result = response.json()
                
                if result.get("errcode") == 0:
                    return {"success": True, "message": "发送成功"}
                return {"success": False, "message": result.get("errmsg", "发送失败")}
        except Exception as e:
            return {"success": False, "message": str(e)}


class EmailNotification(NotificationService):
    """邮件通知"""
    
    async def send(self, title: str, content: str, recipients: List[str] = None) -> Dict[str, Any]:
        config = self.channel.email_config or {}
        
        smtp_server = config.get("smtp_server")
        smtp_port = config.get("smtp_port", 465)
        username = config.get("username")
        password = config.get("password")
        from_addr = config.get("from_addr", username)
        
        if not all([smtp_server, username, password]):
            return {"success": False, "message": "邮件配置不完整"}
        
        if not recipients:
            return {"success": False, "message": "未指定收件人"}
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = title
            msg['From'] = from_addr
            msg['To'] = ', '.join(recipients)
            
            msg.attach(MIMEText(content, 'plain', 'utf-8'))
            msg.attach(MIMEText(content.replace('\n', '<br>'), 'html', 'utf-8'))
            
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(username, password)
                server.sendmail(from_addr, recipients, msg.as_string())
            
            return {"success": True, "message": "发送成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}


class NotificationManager:
    """通知管理器"""
    
    CHANNEL_SERVICES = {
        NotificationType.FEISHU.value: FeishuNotification,
        NotificationType.DINGTALK.value: DingtalkNotification,
        NotificationType.WECHAT.value: WechatNotification,
        NotificationType.EMAIL.value: EmailNotification,
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_service(self, channel: NotificationChannel) -> NotificationService:
        service_class = self.CHANNEL_SERVICES.get(channel.type)
        if not service_class:
            raise ValueError(f"不支持的通知类型: {channel.type}")
        return service_class(channel)
    
    async def test_channel(self, channel_id: int) -> Dict[str, Any]:
        """测试通知渠道"""
        channel = self.db.query(NotificationChannel).filter(
            NotificationChannel.id == channel_id
        ).first()
        
        if not channel:
            return {"success": False, "message": "渠道不存在"}
        
        service = self.get_service(channel)
        result = await service.send(
            title="测试通知",
            content="这是一条测试通知消息，用于验证渠道配置是否正确。"
        )
        
        channel.test_status = "success" if result["success"] else "failed"
        channel.test_message = result["message"]
        channel.last_test_at = datetime.utcnow()
        self.db.commit()
        
        return result
    
    async def send_notification(
        self,
        channel_id: int,
        title: str,
        content: str,
        recipients: List[str] = None,
        rule_id: int = None,
        triggered_by: str = None,
        trigger_data: Dict = None
    ) -> Dict[str, Any]:
        """发送通知"""
        channel = self.db.query(NotificationChannel).filter(
            NotificationChannel.id == channel_id
        ).first()
        
        if not channel:
            return {"success": False, "message": "渠道不存在"}
        
        if not channel.enabled:
            return {"success": False, "message": "渠道已禁用"}
        
        history = NotificationHistory(
            project_id=channel.project_id,
            channel_id=channel_id,
            rule_id=rule_id,
            recipient=', '.join(recipients) if recipients else '',
            subject=title,
            content=content,
            triggered_by=triggered_by,
            trigger_data=trigger_data
        )
        self.db.add(history)
        self.db.flush()
        
        service = self.get_service(channel)
        result = await service.send(title, content, recipients)
        
        history.status = "success" if result["success"] else "failed"
        history.error_message = result.get("message") if not result["success"] else None
        history.sent_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info(f"发送通知: channel={channel.type}, status={history.status}")
        
        return result
    
    async def trigger_alert(
        self,
        rule_id: int,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """触发告警"""
        rule = self.db.query(AlertRule).filter(
            AlertRule.id == rule_id,
            AlertRule.enabled == True
        ).first()
        
        if not rule:
            return [{"success": False, "message": "规则不存在或已禁用"}]
        
        title, content = self.render_message(rule, context)
        
        channel_ids = rule.channel_ids or []
        results = []
        
        for channel_id in channel_ids:
            result = await self.send_notification(
                channel_id=channel_id,
                title=title,
                content=content,
                recipients=rule.receivers,
                rule_id=rule_id,
                triggered_by=context.get("triggered_by"),
                trigger_data=context
            )
            results.append(result)
        
        rule.last_triggered_at = datetime.utcnow()
        rule.trigger_count = (rule.trigger_count or 0) + 1
        self.db.commit()
        
        return results
    
    def render_message(self, rule: AlertRule, context: Dict[str, Any]) -> tuple:
        """渲染消息"""
        if rule.custom_template:
            template = rule.custom_template
        else:
            template = self.get_default_template(rule.condition_type)
        
        title = template.get("title", "告警通知")
        content = template.get("content", "")
        
        for key, value in context.items():
            placeholder = f"${{{key}}}"
            title = title.replace(placeholder, str(value))
            content = content.replace(placeholder, str(value))
        
        return title, content
    
    def get_default_template(self, condition_type: str) -> Dict[str, str]:
        """获取默认模板"""
        templates = {
            AlertConditionType.EXECUTION_FAILED.value: {
                "title": "🔴 测试执行失败通知",
                "content": """项目: ${project_name}
版本: ${version}
计划: ${plan_name}
执行时间: ${execution_time}
执行人: ${executor}

执行结果:
- 总用例: ${total_cases}
- 通过: ${passed_cases}
- 失败: ${failed_cases}
- 通过率: ${pass_rate}%

请及时处理！"""
            },
            AlertConditionType.PASS_RATE_LOW.value: {
                "title": "⚠️ 测试通过率过低告警",
                "content": """项目: ${project_name}
版本: ${version}
当前通过率: ${pass_rate}%
阈值: ${threshold}%

建议检查：
1. 是否有阻塞性问题
2. 测试用例是否需要更新
3. 环境是否正常"""
            },
            AlertConditionType.CI_FAILED.value: {
                "title": "🔴 CI构建失败通知",
                "content": """项目: ${project_name}
Pipeline: ${pipeline_name}
构建号: ${build_number}
分支: ${branch}
触发人: ${trigger_by}

错误信息:
${error_message}

构建链接: ${build_url}"""
            },
            AlertConditionType.ISSUE_CREATED.value: {
                "title": "📢 新问题创建通知",
                "content": """项目: ${project_name}
问题标题: ${issue_title}
严重程度: ${severity}
优先级: ${priority}
报告人: ${reporter}

问题描述:
${description}"""
            }
        }
        
        return templates.get(condition_type, {
            "title": "📢 系统通知",
            "content": "${message}"
        })
    
    def check_alert_conditions(self, project_id: int, event_type: str, data: Dict[str, Any]) -> List[Dict]:
        """检查告警条件"""
        rules = self.db.query(AlertRule).filter(
            AlertRule.project_id == project_id,
            AlertRule.enabled == True,
            AlertRule.condition_type == event_type
        ).all()
        
        triggered_rules = []
        
        for rule in rules:
            should_trigger = self._evaluate_condition(rule, data)
            if should_trigger:
                triggered_rules.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name
                })
        
        return triggered_rules
    
    def _evaluate_condition(self, rule: AlertRule, data: Dict[str, Any]) -> bool:
        """评估告警条件"""
        config = rule.condition_config or {}
        
        if rule.condition_type == AlertConditionType.EXECUTION_FAILED.value:
            return data.get("status") == "failed"
        
        elif rule.condition_type == AlertConditionType.PASS_RATE_LOW.value:
            threshold = config.get("threshold", 80)
            return data.get("pass_rate", 100) < threshold
        
        elif rule.condition_type == AlertConditionType.CI_FAILED.value:
            return data.get("status") in ["failed", "timeout"]
        
        elif rule.condition_type == AlertConditionType.ISSUE_CREATED.value:
            severity_filter = config.get("severity_filter", [])
            if severity_filter:
                return data.get("severity") in severity_filter
            return True
        
        return False


DEFAULT_TEMPLATES = [
    {
        "name": "测试执行失败通知",
        "type": "feishu",
        "condition_type": "execution_failed",
        "title_template": "🔴 测试执行失败通知",
        "content_template": """项目: ${project_name}
版本: ${version}
计划: ${plan_name}
执行时间: ${execution_time}
执行人: ${executor}

执行结果:
- 总用例: ${total_cases}
- 通过: ${passed_cases}
- 失败: ${failed_cases}
- 通过率: ${pass_rate}%

请及时处理！"""
    },
    {
        "name": "CI构建失败通知",
        "type": "feishu",
        "condition_type": "ci_failed",
        "title_template": "🔴 CI构建失败通知",
        "content_template": """项目: ${project_name}
Pipeline: ${pipeline_name}
构建号: ${build_number}
分支: ${branch}
触发人: ${trigger_by}

错误信息:
${error_message}

构建链接: ${build_url}"""
    }
]


CHANNEL_TYPE_OPTIONS = [
    {"value": "feishu", "label": "飞书", "icon": "📨"},
    {"value": "dingtalk", "label": "钉钉", "icon": "📱"},
    {"value": "wechat", "label": "企业微信", "icon": "💬"},
    {"value": "email", "label": "邮件", "icon": "📧"}
]

CONDITION_TYPE_OPTIONS = [
    {"value": "execution_failed", "label": "测试执行失败"},
    {"value": "pass_rate_low", "label": "通过率过低"},
    {"value": "performance_abnormal", "label": "性能异常"},
    {"value": "ci_failed", "label": "CI构建失败"},
    {"value": "issue_created", "label": "问题创建"},
    {"value": "issue_unresolved", "label": "问题未解决"}
]