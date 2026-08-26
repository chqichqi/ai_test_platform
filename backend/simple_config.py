"""
简化配置
"""

import os
from typing import Dict, Any

class SimpleSettings:
    # 应用配置
    APP_NAME = "AI Agent Test Platform"
    APP_VERSION = "0.1.0"
    APP_ENV = "development"
    DEBUG = True
    SECRET_KEY = "dev-secret-key-change-in-production"
    API_V1_STR = "/api/v1"
    
    # 服务器配置
    HOST = "0.0.0.0"
    PORT = 8000
    WORKERS = 1
    RELOAD = True
    
    # 数据库配置（使用SQLite简化）
    DATABASE_URL = "sqlite:///./test.db"
    DATABASE_POOL_SIZE = 5
    DATABASE_MAX_OVERFLOW = 10
    DATABASE_POOL_RECYCLE = 3600
    
    # JWT配置
    JWT_SECRET_KEY = "jwt-secret-key-change-in-production"
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    # 文件上传配置
    UPLOAD_DIR = "./data/uploads"
    MAX_UPLOAD_SIZE = 10485760  # 10MB
    ALLOWED_EXTENSIONS = ["pdf", "doc", "docx", "txt", "md"]
    
    # CORS配置
    BACKEND_CORS_ORIGINS = ["http://localhost:3000"]
    
    # 日志配置
    LOG_LEVEL = "INFO"
    
    @classmethod
    def get_cors_origins(cls):
        """获取CORS origins"""
        return cls.BACKEND_CORS_ORIGINS
    
    @classmethod
    def get_allowed_extensions(cls):
        """获取允许的文件扩展名"""
        return cls.ALLOWED_EXTENSIONS
    
    @classmethod
    def get_database_config(cls) -> Dict[str, Any]:
        """获取数据库配置"""
        return {
            "url": cls.DATABASE_URL,
            "pool_size": cls.DATABASE_POOL_SIZE,
            "max_overflow": cls.DATABASE_MAX_OVERFLOW,
            "pool_recycle": cls.DATABASE_POOL_RECYCLE,
        }
    
    @classmethod
    def get_jwt_config(cls) -> Dict[str, Any]:
        """获取JWT配置"""
        return {
            "secret_key": cls.JWT_SECRET_KEY,
            "algorithm": cls.JWT_ALGORITHM,
            "access_token_expire_minutes": cls.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": cls.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        }

settings = SimpleSettings()