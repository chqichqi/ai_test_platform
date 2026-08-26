"""
Production-ready backend with SQLite database and JWT authentication
"""
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import local modules
from database import get_db, init_database, User, Document, Skill, Test, Report, Query, APIMonitor
from auth_utils import (
    verify_password, get_password_hash, create_tokens_for_user,
    verify_token, get_user_id_from_token
)

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-for-development-change-in-production")
APP_NAME = "AI Agent Test Platform"
APP_VERSION = "1.0.0"
APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
RELOAD = APP_ENV == "development"

# Create FastAPI app
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/docs" if APP_ENV != "production" else None,
    redoc_url="/redoc" if APP_ENV != "production" else None,
)

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
]

if APP_ENV == "production":
    # Add production origins
    origins.extend([
        "https://your-production-domain.com",
        "https://www.your-production-domain.com",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Dependency to get current user
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current authenticated user"""
    token = credentials.credentials
    user_id = get_user_id_from_token(token)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

def get_current_admin(user: User = Depends(get_current_user)):
    """Get current admin user"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return user

# Health check endpoints
@app.get("/")
async def root():
    return {
        "message": f"Welcome to {APP_NAME}",
        "version": APP_VERSION,
        "environment": APP_ENV,
        "docs": "/docs" if APP_ENV != "production" else None,
        "health": "/health",
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database connection test"""
    try:
        # Test database connection
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "environment": APP_ENV,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )

# Authentication endpoints
@app.post("/api/v1/auth/login")
async def login(
    request: Request,
    db: Session = Depends(get_db)
):
    """User login with JWT token generation"""
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required"
        )
    
    # Find user
    user = db.query(User).filter(
        (User.username == username) | (User.email == username),
        User.is_active == True
    ).first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create tokens
    tokens = create_tokens_for_user(user.id, user.username, user.role)
    
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        },
        "token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "expires_in": tokens["expires_in"]
    }

@app.post("/api/v1/auth/register")
async def register(
    request: Request,
    db: Session = Depends(get_db)
):
    """User registration"""
    data = await request.json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    
    if not username or not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username, email and password are required"
        )
    
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    new_user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role="user"
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Create tokens
    tokens = create_tokens_for_user(new_user.id, new_user.username, new_user.role)
    
    return {
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": new_user.role
        },
        "token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "expires_in": tokens["expires_in"]
    }

@app.get("/api/v1/auth/me")
async def get_current_user_info(
    user: User = Depends(get_current_user)
):
    """Get current user information"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None
    }

@app.post("/api/v1/auth/logout")
async def logout():
    """User logout (client should discard token)"""
    return {"message": "Successfully logged out"}

@app.post("/api/v1/auth/refresh")
async def refresh_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    data = await request.json()
    refresh_token = data.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )
    
    # Verify refresh token
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new access token
    tokens = create_tokens_for_user(user.id, user.username, user.role)
    
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "expires_in": tokens["expires_in"]
    }

# RAG endpoints
@app.get("/api/v1/rag/documents")
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get documents list with pagination"""
    documents = db.query(Document).filter(
        Document.owner_id == user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(Document).filter(Document.owner_id == user.id).count()
    
    return {
        "documents": [
            {
                "id": doc.id,
                "name": doc.name,
                "description": doc.description,
                "type": doc.file_type,
                "size": f"{doc.file_size / 1024 / 1024:.1f} MB" if doc.file_size else "Unknown",
                "status": doc.status,
                "date": doc.created_at.strftime("%Y-%m-%d") if doc.created_at else None
            }
            for doc in documents
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@app.post("/api/v1/rag/query")
async def query_document(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Query documents (simulated RAG)"""
    data = await request.json()
    query = data.get("query", "")
    document_id = data.get("document_id")
    
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query is required"
        )
    
    # Find document
    document = None
    if document_id:
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == user.id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
    
    # Simulate RAG query (in production, this would use actual RAG)
    results = [
        {
            "id": 1,
            "content": f"Relevant information for query: '{query}'",
            "score": 0.95,
            "source": document.name if document else "General Knowledge"
        }
    ]
    
    # Save query to database
    if document:
        new_query = Query(
            query_text=query,
            response=str(results),
            document_id=document.id,
            similarity_score=0.95
        )
        db.add(new_query)
        db.commit()
    
    return {
        "results": results,
        "query": query,
        "document": document.name if document else None
    }

# SKILLS endpoints
@app.get("/api/v1/skills")
async def get_skills(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get SKILLS list"""
    skills = db.query(Skill).filter(
        Skill.status == "active"
    ).offset(skip).limit(limit).all()
    
    total = db.query(Skill).filter(Skill.status == "active").count()
    
    return {
        "skills": [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "status": skill.status,
                "version": skill.version
            }
            for skill in skills
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

# Test endpoints
@app.get("/api/v1/tests/functional")
async def get_functional_tests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get functional tests"""
    tests = db.query(Test).filter(
        Test.test_type == "functional",
        Test.created_by_id == user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(Test).filter(
        Test.test_type == "functional",
        Test.created_by_id == user.id
    ).count()
    
    return {
        "tests": [
            {
                "id": test.id,
                "name": test.name,
                "status": test.status,
                "duration": f"{test.duration}s" if test.duration else None,
                "date": test.created_at.strftime("%Y-%m-%d") if test.created_at else None
            }
            for test in tests
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@app.get("/api/v1/tests/api")
async def get_api_tests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get API tests"""
    tests = db.query(Test).filter(
        Test.test_type == "api",
        Test.created_by_id == user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(Test).filter(
        Test.test_type == "api",
        Test.created_by_id == user.id
    ).count()
    
    return {
        "tests": [
            {
                "id": test.id,
                "name": test.name,
                "status": test.status,
                "duration": f"{test.duration}s" if test.duration else None,
                "date": test.created_at.strftime("%Y-%m-%d") if test.created_at else None
            }
            for test in tests
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

# Report endpoints
@app.get("/api/v1/reports")
async def get_reports(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get reports"""
    reports = db.query(Report).filter(
        Report.generated_by_id == user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(Report).filter(Report.generated_by_id == user.id).count()
    
    return {
        "reports": [
            {
                "id": report.id,
                "name": report.name,
                "type": report.report_type,
                "date": report.created_at.strftime("%Y-%m-%d") if report.created_at else None,
                "status": report.status
            }
            for report in reports
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

# Monitoring endpoint
@app.get("/api/v1/monitoring")
async def get_monitoring(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin)  # Only admins can view monitoring
):
    """Get API monitoring data"""
    # Get recent monitoring entries
    monitors = db.query(APIMonitor).order_by(
        APIMonitor.checked_at.desc()
    ).limit(10).all()
    
    # Get system stats
    user_count = db.query(User).count()
    document_count = db.query(Document).count()
    test_count = db.query(Test).count()
    
    return {
        "monitoring": [
            {
                "id": monitor.id,
                "name": f"{monitor.method} {monitor.endpoint}",
                "method": monitor.method,
                "url": monitor.endpoint,
                "status": monitor.status,
                "responseTime": f"{monitor.response_time}ms" if monitor.response_time else None
            }
            for monitor in monitors
        ],
        "stats": {
            "users": user_count,
            "documents": document_count,
            "tests": test_count,
            "skills": db.query(Skill).count(),
            "reports": db.query(Report).count()
        }
    }

# Admin endpoints
@app.get("/api/v1/admin/users")
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """Get all users (admin only)"""
    users = db.query(User).offset(skip).limit(limit).all()
    total = db.query(User).count()
    
    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
            for user in users
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup"""
    print(f"Starting {APP_NAME} v{APP_VERSION} in {APP_ENV} mode...")
    init_database()
    print("Database initialized successfully")

if __name__ == "__main__":
    uvicorn.run(
        "production_backend:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level="info"
    )