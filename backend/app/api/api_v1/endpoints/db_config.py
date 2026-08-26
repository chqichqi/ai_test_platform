"""
数据库配置相关API
用于系统首次启动时的数据库配置向导
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.db_config import db_config_service
from app.core.responses import success_response, error_response
from app.core.logger import logger

router = APIRouter()


class MySQLConfigRequest(BaseModel):
    """MySQL配置请求"""
    host: str = Field(default="localhost", description="MySQL主机地址")
    port: int = Field(default=3306, description="MySQL端口")
    database: str = Field(default="ai_test_platform", description="数据库名")
    username: str = Field(default="root", description="用户名")
    password: str = Field(..., description="密码")


class DatabaseInitRequest(BaseModel):
    """数据库初始化请求"""
    db_type: str = Field(..., description="数据库类型: mysql/sqlite")
    host: Optional[str] = Field(default=None, description="MySQL主机")
    port: Optional[int] = Field(default=None, description="MySQL端口")
    database: Optional[str] = Field(default=None, description="数据库名")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    init_data: bool = Field(default=True, description="是否初始化基础数据")


@router.get("/db-config/status", tags=["Database Config"])
async def check_db_config_status():
    """
    检查数据库配置状态
    
    用于前端判断是否需要显示配置向导
    """
    try:
        is_configured = db_config_service.check_db_configured()
        config = db_config_service.get_db_config()
        
        return success_response({
            "configured": is_configured,
            "db_type": config.get("db_type"),
            "message": "数据库已配置" if is_configured else "数据库未配置"
        })
    except Exception as e:
        logger.error(f"检查数据库配置状态失败: {e}")
        return success_response({
            "configured": False,
            "db_type": None,
            "message": "数据库未配置"
        })


@router.post("/db-config/test", tags=["Database Config"])
async def test_db_connection(config: MySQLConfigRequest):
    """
    测试MySQL数据库连接
    
    在保存配置前测试连接是否可用
    """
    try:
        result = db_config_service.test_mysql_connection(
            host=config.host,
            port=config.port,
            database=config.database,
            username=config.username,
            password=config.password
        )
        
        if result["success"]:
            return success_response(result)
        else:
            return error_response(message=result["message"], code="CONNECTION_FAILED")
            
    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        return error_response(message=f"测试连接失败: {str(e)}", code="TEST_FAILED")


@router.post("/db-config/init", tags=["Database Config"])
async def init_database(request: DatabaseInitRequest):
    """
    初始化数据库
    
    创建数据库、数据表和基础数据
    """
    try:
        if request.db_type == "mysql":
            if not all([request.host, request.port, request.database, request.username, request.password]):
                return error_response(
                    message="MySQL配置不完整，请提供所有必需参数",
                    code="INCOMPLETE_CONFIG"
                )
            
            result = db_config_service.init_database(
                db_type="mysql",
                host=request.host,
                port=request.port,
                database=request.database,
                username=request.username,
                password=request.password,
                init_data=request.init_data
            )
            
        elif request.db_type == "sqlite":
            result = db_config_service.init_database(
                db_type="sqlite",
                database=request.database or "./data/app.db",
                init_data=request.init_data
            )
        else:
            return error_response(
                message=f"不支持的数据库类型: {request.db_type}",
                code="UNSUPPORTED_DB_TYPE"
            )
        
        if result["success"]:
            return success_response(result)
        else:
            return error_response(
                message=result.get("message", "初始化失败"),
                code="INIT_FAILED",
                data={"steps": result.get("steps", [])}
            )
            
    except Exception as e:
        logger.error(f"初始化数据库失败: {e}")
        return error_response(
            message=f"初始化数据库失败: {str(e)}",
            code="INIT_ERROR"
        )


@router.post("/db-config/quick-sqlite", tags=["Database Config"])
async def quick_sqlite_setup():
    """
    快速设置SQLite（用于测试）
    
    使用默认配置快速创建SQLite数据库
    """
    try:
        result = db_config_service.init_database(
            db_type="sqlite",
            database="./data/app.db",
            init_data=True
        )
        
        if result["success"]:
            return success_response({
                "success": True,
                "message": "SQLite数据库配置成功",
                "db_path": "./data/app.db"
            })
        else:
            return error_response(
                message=result.get("message", "配置失败"),
                code="SQLITE_SETUP_FAILED"
            )
            
    except Exception as e:
        logger.error(f"SQLite快速设置失败: {e}")
        return error_response(
            message=f"SQLite配置失败: {str(e)}",
            code="SQLITE_ERROR"
        )


@router.get("/db-config/info", tags=["Database Config"])
async def get_db_config_info():
    """
    获取数据库配置信息（不含密码）
    
    用于配置页面显示当前配置
    """
    try:
        config = db_config_service.get_db_config()
        return success_response({
            "db_type": config.get("db_type"),
            "host": config.get("host"),
            "port": config.get("port"),
            "database": config.get("database"),
            "username": config.get("username")
        })
    except Exception as e:
        logger.error(f"获取配置信息失败: {e}")
        return error_response(
            message=f"获取配置信息失败: {str(e)}",
            code="GET_CONFIG_FAILED"
        )
