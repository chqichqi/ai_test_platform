"""
Database configuration and models for AI Agent Test Platform
"""
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# Database URL - SQLite for development
DATABASE_URL = "sqlite:///./ai_agent_test.db"

# Create engine
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}  # Needed for SQLite
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Models
class User(Base):
    """User model for authentication"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin, user
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship("Document", back_populates="owner")
    tests = relationship("Test", back_populates="created_by")
    reports = relationship("Report", back_populates="generated_by")

class Document(Base):
    """Document model for RAG testing"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    file_path = Column(String(500))
    file_type = Column(String(50))  # pdf, txt, md, docx
    file_size = Column(Integer)  # in bytes
    status = Column(String(20), default="uploaded")  # uploaded, processing, processed, error
    content = Column(Text)  # Extracted text content
    doc_metadata = Column(Text)  # JSON metadata
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = relationship("User", back_populates="documents")
    queries = relationship("Query", back_populates="document")

class Query(Base):
    """Query model for RAG queries"""
    __tablename__ = "queries"
    
    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(Text, nullable=False)
    response = Column(Text)
    document_id = Column(Integer, ForeignKey("documents.id"))
    similarity_score = Column(Float)
    tokens_used = Column(Integer)
    processing_time = Column(Float)  # in seconds
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="queries")

class Skill(Base):
    """SKILL model for skills management"""
    __tablename__ = "skills"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    version = Column(String(20))
    status = Column(String(20), default="active")  # active, inactive, deprecated
    config = Column(Text)  # JSON configuration
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Test(Base):
    """Test model for functional and API tests"""
    __tablename__ = "tests"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    test_type = Column(String(50))  # functional, api, performance
    description = Column(Text)
    status = Column(String(20), default="pending")  # pending, running, passed, failed, error
    result = Column(Text)  # JSON test results
    duration = Column(Float)  # in seconds
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    created_by = relationship("User", back_populates="tests")

class Report(Base):
    """Report model for test reports"""
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    report_type = Column(String(50))  # test, performance, audit
    description = Column(Text)
    content = Column(Text)  # JSON or HTML report content
    file_path = Column(String(500))
    status = Column(String(20), default="generating")  # generating, completed, error
    generated_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    generated_by = relationship("User", back_populates="reports")

class APIMonitor(Base):
    """API monitoring model"""
    __tablename__ = "api_monitors"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String(500), nullable=False)
    method = Column(String(10))  # GET, POST, PUT, DELETE
    status = Column(String(20))  # healthy, warning, error
    response_time = Column(Float)  # in milliseconds
    status_code = Column(Integer)
    checked_at = Column(DateTime, default=datetime.utcnow)


class LLMConfig(Base):
    """LLM配置模型 - 保存多个LLM配置"""
    __tablename__ = "llm_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    api_key = Column(String(255), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4000)
    is_active = Column(Boolean, default=False)
    status = Column(String(20), default="pending")
    last_test_at = Column(DateTime, nullable=True)
    last_test_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    user = relationship("User", backref="llm_configs")

# Create tables
def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    """Initialize database with sample data"""
    db = SessionLocal()
    
    try:
        # Create tables if they don't exist
        create_tables()
        
        # Check if we already have data
        user_count = db.query(User).count()
        
        if user_count == 0:
            # Create admin user
            from auth_utils import get_password_hash
            
            # Use simpler passwords and fix bcrypt issues
            from auth_utils import get_password_hash
            admin_user = User(
                username="admin",
                email="admin@test.com",
                hashed_password=get_password_hash("admin123"),  # Fixed password
                role="admin"
            )
            db.add(admin_user)
            
            # Create regular user
            regular_user = User(
                username="user",
                email="user@test.com",
                hashed_password=get_password_hash("user123"),  # Fixed password
                role="user"
            )
            db.add(regular_user)
            
            # Create sample skills
            skills = [
                Skill(
                    name="webapp-testing",
                    description="Testing web applications with Playwright",
                    version="1.2.0",
                    status="active"
                ),
                Skill(
                    name="xlsx",
                    description="Spreadsheet file processing and analysis",
                    version="1.1.0",
                    status="active"
                ),
                Skill(
                    name="docx",
                    description="Word document processing and generation",
                    version="1.0.0",
                    status="active"
                )
            ]
            for skill in skills:
                db.add(skill)
            
            # Create sample documents
            documents = [
                Document(
                    name="Technical Documentation",
                    description="System technical documentation",
                    file_type="PDF",
                    file_size=2500000,
                    status="processed",
                    owner=admin_user
                ),
                Document(
                    name="API Specifications",
                    description="API endpoint specifications",
                    file_type="Markdown",
                    file_size=1100000,
                    status="processing",
                    owner=admin_user
                )
            ]
            for doc in documents:
                db.add(doc)
            
            # Create sample tests
            tests = [
                Test(
                    name="Login Test",
                    test_type="functional",
                    description="Test user login functionality",
                    status="passed",
                    duration=2.3,
                    created_by=admin_user
                ),
                Test(
                    name="API Authentication Test",
                    test_type="api",
                    description="Test API authentication endpoints",
                    status="failed",
                    duration=1.8,
                    created_by=admin_user
                )
            ]
            for test in tests:
                db.add(test)
            
            # Create sample reports
            reports = [
                Report(
                    name="Weekly Test Report",
                    report_type="test",
                    description="Weekly test execution summary",
                    status="completed",
                    generated_by=admin_user
                )
            ]
            for report in reports:
                db.add(report)
            
            db.commit()
            print("Database initialized with sample data")
        else:
            print("Database already contains data")
            
    except Exception as e:
        db.rollback()
        print(f"Error initializing database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_database()