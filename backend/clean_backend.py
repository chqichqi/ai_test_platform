"""
Clean backend with support for both /api/ and /api/v1/ prefixes
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

# Configuration
class Settings:
    APP_NAME = "AI Agent Test Platform"
    APP_VERSION = "0.1.0"
    APP_ENV = "development"
    HOST = "0.0.0.0"
    PORT = 8000
    RELOAD = True
    LOG_LEVEL = "INFO"
    
    def get_cors_origins(self):
        return ["http://localhost:3000", "http://127.0.0.1:3000"]

settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper function to create response
def create_response(data=None, success=True, message="", error=None):
    response = {"success": success}
    if data is not None:
        response["data"] = data
    if message:
        response["message"] = message
    if error:
        response["error"] = error
    return response

# Health check endpoints
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
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Authentication endpoints - support both prefixes
def create_login_response(username, user_id="1"):
    """Create login response"""
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
    """User login"""
    try:
        data = await request.json()
        username = data.get("username", "")
        password = data.get("password", "")
        
        if username and password:
            # Return the exact format frontend expects
            return {
                "user": {
                    "id": "1",
                    "username": username,
                    "email": f"{username}@test.com",
                    "role": "admin" if username == "admin" else "user"
                },
                "token": "mock-jwt-token-123456"
            }
        else:
            return JSONResponse(
                {"error": "Invalid credentials"},
                status_code=401
            )
    except Exception as e:
        return JSONResponse(
            {"error": "Login failed", "details": str(e)},
            status_code=500
        )

@app.post("/api/auth/register")
@app.post("/api/v1/auth/register")
async def register(request: Request):
    """User registration"""
    try:
        data = await request.json()
        username = data.get("username", "")
        email = data.get("email", "")
        password = data.get("password", "")
        
        if username and email and password:
            return create_login_response(username, "2")
        else:
            return JSONResponse(
                create_response(success=False, error="Missing required fields"),
                status_code=400
            )
    except Exception as e:
        return JSONResponse(
            create_response(success=False, error="Registration failed", message=str(e)),
            status_code=500
        )

@app.get("/api/auth/me")
@app.get("/api/v1/auth/me")
async def get_current_user(request: Request):
    """Get current user info"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return {
            "id": "1",
            "username": "admin",
            "email": "admin@test.com",
            "role": "admin"
        }
    else:
        return JSONResponse(
            create_response(success=False, error="Unauthorized"),
            status_code=401
        )

@app.post("/api/auth/logout")
@app.post("/api/v1/auth/logout")
async def logout():
    """User logout"""
    return create_response(message="Logged out successfully")

# RAG endpoints
@app.get("/api/rag/documents")
@app.get("/api/v1/rag/documents")
async def get_documents():
    """Get document list"""
    documents = [
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
    ]
    return create_response({"documents": documents, "total": len(documents)})

@app.post("/api/rag/query")
@app.post("/api/v1/rag/query")
async def query_document(request: Request):
    """Query document"""
    try:
        data = await request.json()
        query = data.get("query", "")
        
        results = [
            {
                "id": 1,
                "content": f"Relevant result for query: '{query}'",
                "score": 0.95,
                "source": "Technical Documentation.pdf"
            }
        ]
        return create_response({"results": results, "query": query})
    except Exception as e:
        return JSONResponse(
            create_response(success=False, error="Query failed", message=str(e)),
            status_code=500
        )

# SKILLS endpoints
@app.get("/api/skills")
@app.get("/api/v1/skills")
async def get_skills():
    """Get SKILLS list"""
    skills = [
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
    return create_response({"skills": skills})

# Test endpoints
@app.get("/api/tests/functional")
@app.get("/api/v1/tests/functional")
async def get_functional_tests():
    """Get functional tests"""
    tests = [
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
    return create_response({"tests": tests})

@app.get("/api/tests/api")
@app.get("/api/v1/tests/api")
async def get_api_tests():
    """Get API tests"""
    tests = [
        {
            "id": "1",
            "name": "Auth API Test",
            "status": "passed",
            "duration": "0.5s",
            "date": "2026-03-20"
        }
    ]
    return create_response({"tests": tests})

# Report endpoints
@app.get("/api/reports")
@app.get("/api/v1/reports")
async def get_reports():
    """Get reports"""
    reports = [
        {
            "id": "1",
            "name": "Weekly Test Report",
            "type": "PDF",
            "date": "2026-03-20",
            "status": "completed"
        }
    ]
    return create_response({"reports": reports})

# Monitoring endpoint
@app.get("/api/monitoring")
@app.get("/api/v1/monitoring")
async def get_monitoring():
    """Get monitoring data"""
    monitoring = [
        {
            "id": "1",
            "name": "Auth API",
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
    return create_response({"monitoring": monitoring})

if __name__ == "__main__":
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Server: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"Docs: http://{settings.HOST}:{settings.PORT}/docs")
    
    uvicorn.run(
        "clean_backend:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )