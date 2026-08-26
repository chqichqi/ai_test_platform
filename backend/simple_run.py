"""
简化启动脚本
"""

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from simple_config import settings

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 健康检查端点
@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }

# 模拟认证端点 - 匹配前端API结构
# 支持 /api/ 和 /api/v1/ 两种前缀

def create_login_response(username, user_id="1"):
    """创建登录响应"""
    return {
        "user": {
            "id": user_id,
            "username": username,
            "email": f"{username}@test.com",
            "role": "admin" if username == "admin" else "user"
        },
        "token": f"mock-jwt-token-{user_id}"
    }

@app.post("/api/auth/login")
@app.post("/api/v1/auth/login")
async def login(request: Request):
    """用户登录"""
    try:
        data = await request.json()
        username = data.get("username", "")
        password = data.get("password", "")
        
        # 简单验证
        if username and password:
            return create_login_response(username, "1")
        else:
            return JSONResponse({
                "error": "Invalid credentials"
            }, status_code=401)
    except Exception as e:
        return JSONResponse({
            "error": "Login failed",
            "details": str(e)
        }, status_code=500)

@app.post("/api/auth/register")
@app.post("/api/v1/auth/register")
async def register(request: Request):
    """用户注册"""
    try:
        data = await request.json()
        username = data.get("username", "")
        email = data.get("email", "")
        password = data.get("password", "")
        
        if username and email and password:
            return create_login_response(username, "2")
        else:
            return JSONResponse({
                "error": "Missing required fields"
            }, status_code=400)
    except Exception as e:
        return JSONResponse({
            "error": "Registration failed",
            "details": str(e)
        }, status_code=500)

@app.get("/api/auth/me")
@app.get("/api/v1/auth/me")
async def get_current_user(request: Request):
    """获取当前用户信息"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return {
            "id": "1",
            "username": "admin",
            "email": "admin@test.com",
            "role": "admin"
        }
    else:
        return JSONResponse({
            "error": "Unauthorized"
        }, status_code=401)

@app.post("/api/auth/logout")
@app.post("/api/v1/auth/logout")
async def logout():
    """用户登出"""
    return {"message": "Logged out successfully"}


# 模拟RAG端点 - 支持两种前缀
@app.get("/api/rag/documents")
@app.get("/api/v1/rag/documents")
async def get_documents():
    """获取文档列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "documents": [
                {
                    "id": "1",
                    "name": "Technical Documentation",
                    "type": "PDF",
                    "size": "2.4 MB",
                    "status": "Processed",
                    "date": "2026-03-20"
                },
                {
                    "id": "2",
                    "name": "API Specifications",
                    "type": "Markdown",
                    "size": "1.1 MB",
                    "status": "Processing",
                    "date": "2026-03-21"
                }
            ],
            "total": 2
        }
    })

@app.post("/api/rag/query")
@app.post("/api/v1/rag/query")
async def query_document(request: Request):
    """查询文档"""
    try:
        data = await request.json()
        query = data.get("query", "")
        
        return JSONResponse({
            "success": True,
            "data": {
                "results": [
                    {
                        "id": 1,
                        "content": f"Relevant result for query: '{query}'",
                        "score": 0.95,
                        "source": "Technical Documentation.pdf"
                    }
                ],
                "query": query
            }
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": "Query failed",
            "error": str(e)
        }, status_code=500)

# 模拟SKILLS端点 - 支持两种前缀
@app.get("/api/skills")
@app.get("/api/v1/skills")
async def get_skills():
    """获取SKILLS列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "skills": [
                {
                    "id": "1",
                    "name": "webapp-testing",
                    "description": "Testing web applications with Playwright",
                    "status": "active",
                    "version": "1.2.0"
                },
                {
                    "id": "2",
                    "name": "xlsx",
                    "description": "Spreadsheet file processing and analysis",
                    "status": "active",
                    "version": "1.1.0"
                }
            ]
        }
    })

# 模拟测试端点 - 支持两种前缀
@app.get("/api/tests/functional")
@app.get("/api/v1/tests/functional")
async def get_functional_tests():
    """获取功能测试列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "tests": [
                {
                    "id": "1",
                    "name": "Login Test",
                    "status": "passed",
                    "duration": "2.3s",
                    "date": "2026-03-20"
                },
                {
                    "id": "2",
                    "name": "API Test",
                    "status": "failed",
                    "duration": "1.8s",
                    "date": "2026-03-21"
                }
            ]
        }
    })

@app.get("/api/tests/api")
@app.get("/api/v1/tests/api")
async def get_api_tests():
    """获取API测试列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "tests": [
                {
                    "id": "1",
                    "name": "Auth API Test",
                    "status": "passed",
                    "duration": "0.5s",
                    "date": "2026-03-20"
                }
            ]
        }
    })

# 模拟报告端点 - 支持两种前缀
@app.get("/api/reports")
@app.get("/api/v1/reports")
async def get_reports():
    """获取测试报告"""
    return JSONResponse({
        "success": True,
        "data": {
            "reports": [
                {
                    "id": "1",
                    "name": "Weekly Test Report",
                    "type": "PDF",
                    "date": "2026-03-20",
                    "status": "completed"
                }
            ]
        }
    })

@app.post("/api/v1/rag/query")
async def query_document(request: Request):
    """查询文档"""
    try:
        data = await request.json()
        query = data.get("query", "")
        
        return JSONResponse({
            "success": True,
            "data": {
                "results": [
                    {
                        "id": 1,
                        "content": f"Relevant result for query: '{query}'",
                        "score": 0.95,
                        "source": "Technical Documentation.pdf"
                    }
                ],
                "query": query
            }
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": "Query failed",
            "error": str(e)
        }, status_code=500)

# 模拟SKILLS端点
@app.get("/api/v1/skills")
async def get_skills():
    """获取SKILLS列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "skills": [
                {
                    "id": "1",
                    "name": "webapp-testing",
                    "description": "Testing web applications with Playwright",
                    "status": "active",
                    "version": "1.2.0"
                },
                {
                    "id": "2",
                    "name": "xlsx",
                    "description": "Spreadsheet file processing and analysis",
                    "status": "active",
                    "version": "1.1.0"
                }
            ]
        }
    })

# 模拟测试端点
@app.get("/api/v1/tests/functional")
async def get_functional_tests():
    """获取功能测试列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "tests": [
                {
                    "id": "1",
                    "name": "Login Flow Test",
                    "status": "passed",
                    "duration": "2.3s",
                    "lastRun": "2026-03-21"
                },
                {
                    "id": "2",
                    "name": "RAG Query Test",
                    "status": "passed",
                    "duration": "5.1s",
                    "lastRun": "2026-03-21"
                }
            ]
        }
    })

@app.get("/api/v1/tests/api")
async def get_api_tests():
    """获取API测试列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "endpoints": [
                {
                    "id": "1",
                    "name": "Login API",
                    "method": "POST",
                    "url": "/api/auth/login",
                    "status": "healthy",
                    "responseTime": "120ms"
                },
                {
                    "id": "2",
                    "name": "RAG Query API",
                    "method": "POST",
                    "url": "/api/rag/query",
                    "status": "healthy",
                    "responseTime": "450ms"
                }
            ]
        }
    })

# 模拟报告端点
@app.get("/api/v1/reports")
async def get_reports():
    """获取报告列表"""
    return JSONResponse({
        "success": True,
        "data": {
            "reports": [
                {
                    "id": "1",
                    "name": "Weekly Test Summary",
                    "type": "Test Report",
                    "date": "2026-03-21",
                    "status": "completed",
                    "size": "2.4 MB"
                },
                {
                    "id": "2",
                    "name": "RAG Performance Analysis",
                    "type": "Performance Report",
                    "date": "2026-03-20",
                    "status": "completed",
                    "size": "3.1 MB"
                }
            ]
        }
    })

if __name__ == "__main__":
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Server: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"Docs: http://{settings.HOST}:{settings.PORT}/docs")
    
    uvicorn.run(
        "simple_run:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )