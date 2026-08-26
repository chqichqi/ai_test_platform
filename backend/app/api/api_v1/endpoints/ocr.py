"""
OCR图像识别API端点
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.services.ocr_service import get_ocr_service, OCRService
from app.core.middleware.permission_middleware import Permissions
from app.core.logger import logger

router = APIRouter()


@router.post("/ocr/analyze", status_code=status.HTTP_200_OK)
async def analyze_image_ocr(
    images: List[UploadFile] = File(..., description="上传的图片文件"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    分析上传图片的OCR内容
    
    支持多张图片上传，返回识别的文本内容
    """
    if not images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少上传一张图片"
        )
    
    # 初始化OCR服务（使用Tesseract）
    ocr_service = get_ocr_service('tesseract')
    
    combined_text = []
    results = []
    
    for idx, image in enumerate(images):
        try:
            # 读取图片数据
            image_data = await image.read()
            
            # OCR识别
            result = ocr_service.recognize_text(image_data)
            
            if result['success']:
                combined_text.append(f"【图片{idx + 1}】\n{result['text']}")
                results.append({
                    'index': idx + 1,
                    'filename': image.filename,
                    'success': True,
                    'text': result['text'][:500],  # 截取前500字符
                    'full_length': len(result['text'])
                })
            else:
                results.append({
                    'index': idx + 1,
                    'filename': image.filename,
                    'success': False,
                    'error': result['error']
                })
                
        except Exception as e:
            logger.error(f"处理图片{idx + 1}失败: {str(e)}")
            results.append({
                'index': idx + 1,
                'filename': image.filename,
                'success': False,
                'error': str(e)
            })
    
    # 合并所有识别的文本
    final_text = '\n\n'.join(combined_text)
    
    return {
        "success": len([r for r in results if r['success']]) > 0,
        "text": final_text,
        "total_images": len(images),
        "successful": len([r for r in results if r['success']]),
        "results": results
    }


@router.post("/generate-from-image", status_code=status.HTTP_200_OK)
async def generate_test_cases_from_image(
    image_text: str,
    base_url: str = "http://localhost:3000",
    browser: str = "chromium",
    viewport_size: str = "1920x1080",
    headless: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.VERSION_CREATE)
):
    """
    根据OCR识别的图片文本生成测试用例
    
    结合LLM服务，将OCR文本转换为测试用例
    """
    if not image_text or len(image_text.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="识别文本太短，无法生成测试用例"
        )
    
    try:
        from app.core.services.llm_service import LLMService
        from app.core.services.web_ui_test_service import WebUITestService
        
        llm_service = LLMService(db)
        test_service = WebUITestService(db)
        
        # 构建提示
        prompt = f"""请根据以下从需求截图中识别出的内容，生成测试用例：

识别内容：
{image_text}

请生成结构化的测试用例，包括：
1. 测试用例名称
2. 测试步骤
3. 预期结果
4. 测试数据（如有）
5. 优先级
"""
        
        # 调用LLM生成测试用例
        llm_response = llm_service.call_llm(
            prompt=prompt,
            system_prompt="你是一个专业的测试用例设计专家，擅长从需求文档中提取测试点并生成详细的测试用例。",
            temperature=0.3
        )
        
        if not llm_response:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LLM服务调用失败，无法生成测试用例"
            )
        
        # 解析LLM响应并创建测试用例
        # 这里简化处理，实际应该解析JSON格式
        test_cases = []
        
        # TODO: 实现完整的解析逻辑
        
        return {
            "success": True,
            "count": len(test_cases),
            "test_cases": test_cases,
            "raw_response": llm_response[:1000]  # 截取前1000字符
        }
        
    except Exception as e:
        logger.error(f"生成测试用例失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成测试用例失败: {str(e)}"
        )


@router.get("/ocr/config", status_code=status.HTTP_200_OK)
async def get_ocr_config(
    current_user: dict = Depends(Permissions.VERSION_READ)
):
    """
    获取OCR服务配置信息
    """
    return {
        "supported_engines": ["tesseract", "baidu", "aliyun"],
        "current_engine": "tesseract",
        "supported_formats": ["jpg", "jpeg", "png", "gif", "bmp", "webp"],
        "max_file_size": "5MB",
        "max_files": 10
    }
