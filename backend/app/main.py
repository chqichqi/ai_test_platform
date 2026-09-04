"""
FastAPI应用主文件
"""

# === Windows Playwright 兼容：必须在所有 asyncio 使用前设置 ===
import sys as _sys
if _sys.platform == 'win32':
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())

import time
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.simple_logger import logger
from app.core.database import init_db, check_db_health
from app.api.api_v1.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    from datetime import datetime
    
    # 启动时执行
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")

    # 关闭 SQLAlchemy 查询日志（避免刷屏）
    import logging as _logging
    _logging.getLogger('sqlalchemy.engine').setLevel(_logging.WARNING)

    # 初始化数据库
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
    
    # 清理僵尸任务（状态为RUNNING但没有进程执行的任务）
    try:
        from app.core.database import SessionLocal
        from app.core.models.generation_task import GenerationTask, TaskStatus
        
        db = SessionLocal()
        zombie_tasks = db.query(GenerationTask).filter(
            GenerationTask.status == TaskStatus.RUNNING
        ).all()
        
        if zombie_tasks:
            logger.warning(f"发现 {len(zombie_tasks)} 个僵尸任务，正在清理...")
            for task in zombie_tasks:
                task.status = TaskStatus.FAILED
                task.error_message = "后台进程被终止，任务中断"
                task.completed_at = datetime.utcnow()
                logger.info(f"任务 {task.id} 已标记为 FAILED")
            db.commit()
            logger.info(f"僵尸任务清理完成")
        db.close()
    except Exception as e:
        logger.error(f"清理僵尸任务失败: {str(e)}")
    
    # 检查数据库连接
    if check_db_health():
        logger.info("Database connection is healthy")
    else:
        logger.warning("Database connection check failed")
    
    yield
    
    # 关闭时执行
    logger.info("Shutting down application...")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Agent based automated testing platform",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# 挂载静态文件
static_dir = os.path.join(settings.PROJECT_ROOT, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Allure 测试报告静态资源（/reports/{project}/{version}/{run_id}/allure-report/...）
# 与 ReportManager.BASE_DIR(backend/test-reports) 一致，供浏览器直接加载 allure HTML
# 及其相对资源(css/js)，否则 serve 端点无法分发子资源导致报告打不开。
_reports_dir = os.path.join(settings.PROJECT_ROOT, "test-reports")
os.makedirs(_reports_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=_reports_dir), name="reports")

# 添加中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    
    # 记录请求
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"from {request.client.host if request.client else 'unknown'} "
        f"({request.headers.get('user-agent', 'no-agent')})"
    )
    
    try:
        response = await call_next(request)
    except Exception as e:
        # 记录异常
        logger.opt(exception=True).error("Request failed")
        raise
    
    # 计算处理时间
    process_time = (time.time() - start_time) * 1000
    
    # 记录响应
    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"-> {response.status_code} "
        f"(took {process_time:.2f}ms)"
    )
    
    # 添加处理时间头
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """安全头中间件"""
    response = await call_next(request)
    
    # 添加安全相关的HTTP头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # 在生产环境下添加更多安全头
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
    
    return response


# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003"
    ],
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# 添加GZip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 添加可信主机检查（生产环境）
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.ai-test-platform.com"],
    )


# 异常处理
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP异常处理"""
    logger.warning(
        f"HTTP Exception: {exc.status_code} - {exc.detail}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": exc.status_code,
            "message": exc.detail,
            "data": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证异常处理"""
    logger.warning(
        "Validation Error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors(),
        }
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "code": 422,
            "message": "Validation Error",
            "errors": exc.errors(),
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    logger.opt(exception=True).error(
        "Unhandled Exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": exc.__class__.__name__,
        }
    )
    
    # 在生产环境下隐藏详细错误信息
    if settings.DEBUG:
        error_detail = str(exc)
    else:
        error_detail = "Internal server error"
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "code": 500,
            "message": "Internal Server Error",
            "error": error_detail,
            "data": None,
        },
    )


# 健康检查端点
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查端点"""
    health_status = {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "timestamp": time.time(),
    }
    
    # 检查数据库连接
    if check_db_health():
        health_status["database"] = "connected"
    else:
        health_status["database"] = "disconnected"
        health_status["status"] = "unhealthy"
    
    return health_status


@app.get("/", response_class=HTMLResponse)
async def root():
    """根端点 - 返回HTML控制面板"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    # 如果HTML文件不存在，返回JSON
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "api_status": "/api/status",
        "auth_test": f"{settings.API_V1_STR}/auth/test",
        "endpoints": [
            f"{settings.API_V1_STR}/auth/register",
            f"{settings.API_V1_STR}/auth/login",
            f"{settings.API_V1_STR}/auth/refresh",
            f"{settings.API_V1_STR}/auth/me",
        ]
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """控制面板 - 重定向到首页"""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"message": "Dashboard HTML not found"}


@app.get("/api/status")
async def api_status():
    """API状态"""
    return {
        "api_version": "v1",
        "base_path": settings.API_V1_STR,
        "status": "active",
        "available_endpoints": [
            f"{settings.API_V1_STR}/auth/register",
            f"{settings.API_V1_STR}/auth/login",
            f"{settings.API_V1_STR}/auth/refresh",
            f"{settings.API_V1_STR}/auth/me",
        ],
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi_json": f"{settings.API_V1_STR}/openapi.json",
        },
        "health": "/health",
        "timestamp": time.time(),
    }


@app.get("/info")
async def app_info():
    """应用信息"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "AI Agent based automated testing platform",
        "environment": settings.APP_ENV,
        "debug": settings.DEBUG,
        "database": {
            "url": settings.DATABASE_URL[:50] + "..." if len(settings.DATABASE_URL) > 50 else settings.DATABASE_URL,
            "pool_size": settings.DATABASE_POOL_SIZE,
        },
        "security": {
            "jwt_algorithm": settings.JWT_ALGORITHM,
            "access_token_expire_minutes": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        },
        "features": {
            "authentication": True,
            "rbac_permissions": True,
            "file_upload": True,
            "rag_knowledge_base": True,
            "ai_test_generation": True,
        }
    }


@app.get("/ping")
async def ping():
    """简单的ping端点"""
    return {"message": "pong", "timestamp": time.time()}


@app.get("/version")
async def version():
    """版本信息"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "api_version": "v1",
        "environment": settings.APP_ENV,
    }


# 包含API路由
app.include_router(api_router, prefix=settings.API_V1_STR)


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server on {settings.HOST}:{settings.PORT}")

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        workers=settings.WORKERS if not settings.RELOAD else 1,
        log_level="info",
    )