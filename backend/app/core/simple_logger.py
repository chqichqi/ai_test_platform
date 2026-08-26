"""
简化日志配置 - 避免timestamp错误
"""

import sys
from pathlib import Path
from loguru import logger
from app.core.config import settings


def setup_logger():
    """设置简化的日志器"""
    # 移除默认处理器
    logger.remove()
    
    # 创建日志目录
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 控制台输出 - 简单格式
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True,
    )
    
    # 文件输出 - 简单文本格式（多进程安全）
    logger.add(
        str(log_file),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        encoding="utf-8",
        enqueue=True,  # 多进程安全：使用队列异步处理日志写入
    )
    
    return logger


# 创建全局日志实例
logger = setup_logger()