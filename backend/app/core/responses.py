"""
统一API响应格式
"""

from typing import Any, Dict, Optional, Union, List, Generic, TypeVar
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模型"""
    data: List[T]
    total: int
    skip: int
    limit: int
    has_more: bool
    
    @classmethod
    def create(cls, data: List[T], total: int, skip: int, limit: int) -> 'PaginatedResponse[T]':
        """创建分页响应"""
        has_more = (skip + limit) < total
        return cls(
            data=data,
            total=total,
            skip=skip,
            limit=limit,
            has_more=has_more
        )


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    code: int
    message: str
    errors: Optional[List[Dict[str, Any]]] = None
    data: Optional[Any] = None


class APIResponse:
    """统一API响应类"""
    
    @staticmethod
    def success(
        data: Any = None,
        message: str = "Success",
        code: int = 200,
        **kwargs
    ) -> JSONResponse:
        """成功响应"""
        content = {
            "success": True,
            "code": code,
            "message": message,
            "data": data,
        }
        content.update(kwargs)
        
        return JSONResponse(
            status_code=code,
            content=jsonable_encoder(content),
        )
    
    @staticmethod
    def error(
        message: str = "Error",
        code: int = 400,
        errors: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> JSONResponse:
        """错误响应"""
        content = {
            "success": False,
            "code": code,
            "message": message,
            "errors": errors,
            "data": None,
        }
        content.update(kwargs)
        
        return JSONResponse(
            status_code=code,
            content=jsonable_encoder(content),
        )
    
    @staticmethod
    def not_found(
        message: str = "Resource not found",
        **kwargs
    ) -> JSONResponse:
        """资源未找到"""
        return APIResponse.error(
            message=message,
            code=404,
            **kwargs
        )
    
    @staticmethod
    def unauthorized(
        message: str = "Unauthorized",
        **kwargs
    ) -> JSONResponse:
        """未授权"""
        return APIResponse.error(
            message=message,
            code=401,
            **kwargs
        )
    
    @staticmethod
    def forbidden(
        message: str = "Forbidden",
        **kwargs
    ) -> JSONResponse:
        """禁止访问"""
        return APIResponse.error(
            message=message,
            code=403,
            **kwargs
        )
    
    @staticmethod
    def validation_error(
        errors: List[Dict[str, Any]],
        message: str = "Validation error",
        **kwargs
    ) -> JSONResponse:
        """验证错误"""
        return APIResponse.error(
            message=message,
            code=422,
            errors=errors,
            **kwargs
        )
    
    @staticmethod
    def internal_error(
        message: str = "Internal server error",
        error_detail: Optional[str] = None,
        **kwargs
    ) -> JSONResponse:
        """内部服务器错误"""
        content = {}
        if error_detail:
            content["error"] = error_detail
        
        return APIResponse.error(
            message=message,
            code=500,
            **content,
            **kwargs
        )
    
    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        page: int,
        page_size: int,
        message: str = "Success",
        **kwargs
    ) -> JSONResponse:
        """分页响应"""
        data = {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }
        
        return APIResponse.success(
            data=data,
            message=message,
            **kwargs
        )


# 快捷函数
def success_response(data: Any = None, message: str = "Success", **kwargs) -> JSONResponse:
    """成功响应快捷函数"""
    return APIResponse.success(data=data, message=message, **kwargs)


def error_response(message: str = "Error", code: int = 400, **kwargs) -> JSONResponse:
    """错误响应快捷函数"""
    return APIResponse.error(message=message, code=code, **kwargs)