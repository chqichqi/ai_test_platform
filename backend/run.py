"""
应用启动脚本
"""

# ⚠️ Windows: 必须在任何 asyncio 使用前设置 ProactorEventLoop
# Playwright 启动浏览器子进程依赖此策略
import sys as _sys
if _sys.platform == 'win32':
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())

import uvicorn
from app.core.config import settings
from app.core.simple_logger import logger


def main():
    """主启动函数"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Server: {settings.HOST}:{settings.PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS if not settings.RELOAD else 1,
        log_level="info",
        access_log=False,  # 使用自定义日志中间件
    )


if __name__ == "__main__":
    main()