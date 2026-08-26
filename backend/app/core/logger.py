"""
日志管理系统
使用loguru进行日志管理，支持文件轮转和结构化日志
"""

import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from loguru import logger
from app.core.config import settings


class JSONFormatter:
    """JSON格式日志格式化器"""
    
    def __call__(self, record: Dict[str, Any]) -> str:
        """格式化日志记录为JSON字符串"""
        # 安全地获取时间戳
        try:
            timestamp = datetime.fromtimestamp(record["time"].timestamp()).isoformat()
        except (KeyError, AttributeError):
            timestamp = datetime.now().isoformat()
        
        # 获取日志级别名称
        level_name = "INFO"
        if record.get("level"):
            level_obj = record["level"]
            if hasattr(level_obj, "name"):
                level_name = level_obj.name
        
        # 获取进程ID
        process_id = 0
        if record.get("process"):
            process_obj = record["process"]
            if hasattr(process_obj, "id"):
                process_id = process_obj.id
        
        # 获取线程ID
        thread_id = 0
        if record.get("thread"):
            thread_obj = record["thread"]
            if hasattr(thread_obj, "id"):
                thread_id = thread_obj.id
        
        log_entry = {
            "timestamp": timestamp,
            "level": level_name,
            "message": record.get("message", ""),
            "module": record.get("name", ""),
            "function": record.get("function", ""),
            "line": record.get("line", 0),
            "process": process_id,
            "thread": thread_id,
        }
        
        # 添加额外字段
        if record.get("extra"):
            log_entry.update(record["extra"])
        
        # 添加异常信息
        if record.get("exception"):
            log_entry["exception"] = {
                "type": str(record["exception"].type),
                "value": str(record["exception"].value),
                "traceback": record["exception"].traceback.format(),
            }
        
        return json.dumps(log_entry, ensure_ascii=False)


class Logger:
    """日志管理器"""
    
    def __init__(self):
        self._configure_logger()
    
    def _configure_logger(self):
        """配置日志器"""
        # 移除默认处理器
        logger.remove()

        # 桥接 stdlib logging → loguru：
        # ElementLocator/StepRunner/自适应函数用 logging.getLogger，不桥接则 app.log 看不到它们的执行过程
        import logging as _stdlib_logging

        class _InterceptHandler(_stdlib_logging.Handler):
            def emit(self, record):
                try:
                    _level = logger.level(record.levelname).name
                except ValueError:
                    _level = record.levelno
                _frame = _stdlib_logging.currentframe()
                _depth = 2
                while _frame and _frame.f_code.co_filename == _stdlib_logging.__file__:
                    _frame = _frame.f_back
                    _depth += 1
                logger.opt(depth=_depth, exception=record.exc_info).log(_level, record.getMessage())

        _stdlib_logging.basicConfig(handlers=[_InterceptHandler()], level=_stdlib_logging.INFO, force=True)
        
        # 创建日志目录
        log_file = Path(settings.LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 控制台输出配置
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )
        
        # 文件输出配置（简单文本格式）
        logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=settings.LOG_LEVEL,
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )
        
        # 错误日志单独文件
        error_log_file = log_file.parent / "error.log"
        logger.add(
            str(error_log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )
    
    def get_logger(self):
        """获取日志器实例"""
        return logger
    
    def bind_context(self, **kwargs):
        """绑定上下文信息到日志记录"""
        return logger.bind(**kwargs)
    
    def log_api_request(self, request_info: Dict[str, Any]):
        """记录API请求日志"""
        logger.info(
            "API Request",
            extra={
                "type": "api_request",
                "method": request_info.get("method"),
                "path": request_info.get("path"),
                "client_ip": request_info.get("client_ip"),
                "user_agent": request_info.get("user_agent"),
                "user_id": request_info.get("user_id"),
                "duration_ms": request_info.get("duration_ms"),
                "status_code": request_info.get("status_code"),
            }
        )
    
    def log_api_response(self, response_info: Dict[str, Any]):
        """记录API响应日志"""
        logger.info(
            "API Response",
            extra={
                "type": "api_response",
                "method": response_info.get("method"),
                "path": response_info.get("path"),
                "status_code": response_info.get("status_code"),
                "response_size": response_info.get("response_size"),
                "duration_ms": response_info.get("duration_ms"),
            }
        )
    
    def log_database_operation(self, operation_info: Dict[str, Any]):
        """记录数据库操作日志"""
        logger.debug(
            "Database Operation",
            extra={
                "type": "db_operation",
                "operation": operation_info.get("operation"),
                "table": operation_info.get("table"),
                "query": operation_info.get("query"),
                "parameters": operation_info.get("parameters"),
                "duration_ms": operation_info.get("duration_ms"),
            }
        )
    
    def log_file_operation(self, operation_info: Dict[str, Any]):
        """记录文件操作日志"""
        logger.info(
            "File Operation",
            extra={
                "type": "file_operation",
                "operation": operation_info.get("operation"),
                "file_path": operation_info.get("file_path"),
                "file_size": operation_info.get("file_size"),
                "user_id": operation_info.get("user_id"),
            }
        )
    
    def log_ai_operation(self, operation_info: Dict[str, Any]):
        """记录AI操作日志"""
        logger.info(
            "AI Operation",
            extra={
                "type": "ai_operation",
                "operation": operation_info.get("operation"),
                "model": operation_info.get("model"),
                "prompt_tokens": operation_info.get("prompt_tokens"),
                "completion_tokens": operation_info.get("completion_tokens"),
                "total_tokens": operation_info.get("total_tokens"),
                "duration_ms": operation_info.get("duration_ms"),
            }
        )
    
    def log_security_event(self, event_info: Dict[str, Any]):
        """记录安全事件日志"""
        logger.warning(
            "Security Event",
            extra={
                "type": "security_event",
                "event_type": event_info.get("event_type"),
                "severity": event_info.get("severity"),
                "user_id": event_info.get("user_id"),
                "client_ip": event_info.get("client_ip"),
                "details": event_info.get("details"),
            }
        )
    
    def log_business_event(self, event_info: Dict[str, Any]):
        """记录业务事件日志"""
        logger.info(
            "Business Event",
            extra={
                "type": "business_event",
                "event_type": event_info.get("event_type"),
                "user_id": event_info.get("user_id"),
                "project_id": event_info.get("project_id"),
                "test_case_id": event_info.get("test_case_id"),
                "details": event_info.get("details"),
            }
        )


# 全局日志实例
log_manager = Logger()
logger = log_manager.get_logger()


def setup_logger():
    """设置日志器（兼容性函数）"""
    return logger


def get_logger():
    """获取日志器（兼容性函数）"""
    return logger


def log_api_request(**kwargs):
    """记录API请求（快捷方法）"""
    log_manager.log_api_request(kwargs)


def log_api_response(**kwargs):
    """记录API响应（快捷方法）"""
    log_manager.log_api_response(kwargs)


def log_database_operation(**kwargs):
    """记录数据库操作（快捷方法）"""
    log_manager.log_database_operation(kwargs)


def log_file_operation(**kwargs):
    """记录文件操作（快捷方法）"""
    log_manager.log_file_operation(kwargs)


def log_ai_operation(**kwargs):
    """记录AI操作（快捷方法）"""
    log_manager.log_ai_operation(kwargs)


def log_security_event(**kwargs):
    """记录安全事件（快捷方法）"""
    log_manager.log_security_event(kwargs)


def log_business_event(**kwargs):
    """记录业务事件（快捷方法）"""
    log_manager.log_business_event(kwargs)


# 测试日志配置
if __name__ == "__main__":
    logger.info("Logger initialized successfully")
    logger.debug("Debug message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # 测试结构化日志
    log_api_request(
        method="GET",
        path="/api/v1/projects",
        client_ip="127.0.0.1",
        user_agent="Mozilla/5.0",
        user_id="user-123",
        duration_ms=150,
        status_code=200,
    )
    
    log_business_event(
        event_type="test_case_created",
        user_id="user-123",
        project_id="project-456",
        test_case_id="test-case-789",
        details={"name": "Login Test", "type": "functional"},
    )