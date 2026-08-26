"""
应用配置管理模块
使用pydantic-settings进行配置管理
"""

import os
from typing import List, Optional
from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "AI Agent Test Platform"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"  # development, testing, production
    DEBUG: bool = True
    SECRET_KEY: str
    API_V1_STR: str = "/api/v1"
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    RELOAD: bool = True
    
    # 数据库配置
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 50
    DATABASE_MAX_OVERFLOW: int = 100
    DATABASE_POOL_RECYCLE: int = 3600
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 20
    
    # JWT配置
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # 文件上传配置
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE: int = 104857600  # 100MB
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "doc", "docx", "txt", "md", "jpg", "jpeg", "png"]
    
    # RAG配置
    VECTOR_DB_PATH: str = "./data/vector_store"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # AI/LLM配置
    # LLM提供商: openai, deepseek, minimax, zhipuai, moonshot, custom
    LLM_PROVIDER: str = "openai"
    
    # OpenAI配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4-1106-preview"
    
    # DeepSeek配置
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # MiniMax配置
    MINIMAX_API_KEY: Optional[str] = None
    MINIMAX_BASE_URL: str = "https://api.minimax.chat/v1"
    MINIMAX_MODEL: str = "abab6.5-chat"
    
    # 智谱AI (ZhipuAI) 配置
    ZHIPUAI_API_KEY: Optional[str] = None
    ZHIPUAI_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPUAI_MODEL: str = "glm-4"
    
    # Moonshot (Kimi) 配置
    MOONSHOT_API_KEY: Optional[str] = None
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1"
    MOONSHOT_MODEL: str = "moonshot-v1-8k"
    
    # 自定义LLM配置
    CUSTOM_API_KEY: Optional[str] = None
    CUSTOM_BASE_URL: Optional[str] = None
    CUSTOM_MODEL: Optional[str] = None
    
    # 通用LLM参数
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    # CORS配置
    CORS_ORIGINS: List[AnyHttpUrl] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://192.168.1.8:3000",
        "http://192.168.1.8:3001",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # 邮件配置
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    SMTP_FROM: Optional[str] = None
    
    # 安全配置
    RATE_LIMIT_PER_MINUTE: int = 60
    API_KEY_HEADER: str = "X-API-Key"
    
    # 项目根目录
    PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                # 如果是JSON数组字符串，尝试解析
                import json
                try:
                    return json.loads(v)
                except:
                    pass
            # 否则按逗号分割
            return [i.strip() for i in v.split(",") if i.strip()]
        return v
    
    @validator("ALLOWED_EXTENSIONS", pre=True)
    def assemble_allowed_extensions(cls, v):
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                # 如果是JSON数组字符串，尝试解析
                import json
                try:
                    return json.loads(v)
                except:
                    pass
            # 否则按逗号分割
            return [i.strip().lower() for i in v.split(",") if i.strip()]
        return v
    
    @validator("UPLOAD_DIR", "VECTOR_DB_PATH", "LOG_FILE")
    def resolve_paths(cls, v, values):
        """解析相对路径为绝对路径"""
        if v.startswith("./"):
            project_root = values.get("PROJECT_ROOT", "")
            return os.path.join(project_root, v[2:])
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
