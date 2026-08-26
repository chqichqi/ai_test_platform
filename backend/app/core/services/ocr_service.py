"""
OCR图像识别服务
支持多种OCR引擎：百度OCR、阿里OCR、腾讯OCR、本地Tesseract等
"""

import base64
import json
import logging
import shutil
import os
from typing import Optional, Dict, List
from PIL import Image
import pytesseract
import io

logger = logging.getLogger(__name__)


def configure_tesseract_path():
    """自动配置Tesseract路径"""
    # 尝试从PATH中查找
    tesseract_path = shutil.which('tesseract')
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        logger.info(f"Tesseract路径已配置: {tesseract_path}")
        return True
    
    # 尝试常见安装路径
    common_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'D:\Program Files\Tesseract-OCR\tesseract.exe',
        r'D:\Tesseract-OCR\tesseract.exe',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Tesseract路径已配置: {path}")
            return True
    
    # 尝试从环境变量查找
    if 'TESSDATA_PREFIX' in os.environ:
        base_path = os.environ['TESSDATA_PREFIX'].replace('\\tessdata', '').replace('/tessdata', '')
        exe_path = os.path.join(base_path, 'tesseract.exe')
        if os.path.exists(exe_path):
            pytesseract.pytesseract.tesseract_cmd = exe_path
            logger.info(f"Tesseract路径已配置: {exe_path}")
            return True
    
    return False


# 启动时自动配置
_tesseract_configured = configure_tesseract_path()


class OCRService:
    """OCR图像识别服务"""
    
    def __init__(self, engine: str = 'tesseract'):
        """
        初始化OCR服务
        
        Args:
            engine: OCR引擎，可选 'tesseract', 'baidu', 'aliyun', 'tencent'
        """
        self.engine = engine
        self.api_key = None
        self.api_secret = None
    
    def configure(self, api_key: str, api_secret: str):
        """配置API密钥（用于在线OCR服务）"""
        self.api_key = api_key
        self.api_secret = api_secret
    
    def recognize_text(self, image_data: bytes, language: str = 'chi_sim+eng') -> Dict:
        """
        识别图片中的文本
        
        Args:
            image_data: 图片二进制数据
            language: 语言，默认中英文混合
            
        Returns:
            {
                'success': bool,
                'text': str,  # 识别出的文本
                'raw_result': dict,  # 原始识别结果
                'error': str  # 错误信息（如果有）
            }
        """
        try:
            if self.engine == 'tesseract':
                return self._recognize_with_tesseract(image_data, language)
            elif self.engine == 'baidu':
                return self._recognize_with_baidu(image_data)
            elif self.engine == 'aliyun':
                return self._recognize_with_aliyun(image_data)
            else:
                return {
                    'success': False,
                    'text': '',
                    'raw_result': {},
                    'error': f'不支持的OCR引擎: {self.engine}'
                }
        except Exception as e:
            logger.error(f'OCR识别失败: {str(e)}')
            return {
                'success': False,
                'text': '',
                'raw_result': {},
                'error': str(e)
            }
    
    def _recognize_with_tesseract(self, image_data: bytes, language: str = 'chi_sim+eng') -> Dict:
        """使用Tesseract进行OCR识别"""
        try:
            # 确保Tesseract路径已配置
            if not _tesseract_configured:
                configure_tesseract_path()
            
            # 检查Tesseract是否安装
            try:
                version = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract版本: {version}")
            except Exception as e:
                logger.error(f"Tesseract未安装或配置错误: {e}")
                # 尝试重新配置
                if configure_tesseract_path():
                    try:
                        version = pytesseract.get_tesseract_version()
                        logger.info(f"重新配置后Tesseract版本: {version}")
                    except:
                        pass
                return {
                    'success': False,
                    'text': '',
                    'raw_result': {},
                    'error': 'Tesseract OCR引擎未安装或未正确配置。请确保Tesseract已安装并在系统PATH中。'
                }
            
            # 打开图片
            image = Image.open(io.BytesIO(image_data))
            logger.info(f"图片格式: {image.format}, 大小: {image.size}, 模式: {image.mode}")
            
            # OCR识别
            text = pytesseract.image_to_string(image, lang=language)
            
            # 清理文本
            text = text.strip()
            
            logger.info(f"OCR识别结果长度: {len(text)}")
            
            if not text:
                return {
                    'success': True,
                    'text': '',
                    'raw_result': {
                        'engine': 'tesseract',
                        'language': language,
                        'warning': '图片中未识别到文本'
                    },
                    'error': None
                }
            
            return {
                'success': True,
                'text': text,
                'raw_result': {
                    'engine': 'tesseract',
                    'language': language
                },
                'error': None
            }
        except Exception as e:
            logger.error(f'Tesseract OCR失败: {str(e)}')
            return {
                'success': False,
                'text': '',
                'raw_result': {},
                'error': f'Tesseract OCR失败: {str(e)}'
            }
    
    def _recognize_with_baidu(self, image_data: bytes) -> Dict:
        """使用百度OCR进行识别"""
        import requests
        
        try:
            # 获取access_token
            token_url = f"https://aip.baidubce.com/oauth/2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.api_key,
                'client_secret': self.api_secret
            }
            
            token_response = requests.post(token_url, data=token_data, timeout=10)
            access_token = token_response.json().get('access_token')
            
            if not access_token:
                return {
                    'success': False,
                    'text': '',
                    'raw_result': {},
                    'error': '获取百度OCR token失败'
                }
            
            # OCR识别
            ocr_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            response = requests.post(
                f"{ocr_url}?access_token={access_token}",
                headers=headers,
                data={'image': image_base64}
            )
            
            result = response.json()
            
            if 'error_code' in result:
                return {
                    'success': False,
                    'text': '',
                    'raw_result': result,
                    'error': f"百度OCR错误: {result.get('error_msg', '未知错误')}"
                }
            
            # 提取文本
            words_result = result.get('words_result', [])
            text = '\n'.join([item.get('words', '') for item in words_result])
            
            return {
                'success': True,
                'text': text,
                'raw_result': result,
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'text': '',
                'raw_result': {},
                'error': f'百度OCR请求失败: {str(e)}'
            }
    
    def _recognize_with_aliyun(self, image_data: bytes) -> Dict:
        """使用阿里云OCR进行识别（预留接口）"""
        # 阿里云OCR实现类似，需要配置AccessKey
        return {
            'success': False,
            'text': '',
            'raw_result': {},
            'error': '阿里云OCR暂未实现'
        }
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """图片预处理（提高OCR准确率）"""
        # 转换为灰度图
        image = image.convert('L')
        
        # 二值化
        # image = image.point(lambda x: 0 if x < 128 else 255, '1')
        
        return image
    
    def analyze_layout(self, image_data: bytes) -> Dict:
        """
        分析页面布局（高级OCR功能）
        识别UI元素位置、类型等
        """
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # 使用Tesseract的表格识别功能
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            # 提取元素位置信息
            elements = []
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 60:  # 置信度大于60%
                    elements.append({
                        'text': data['text'][i],
                        'confidence': data['conf'][i],
                        'x': data['left'][i],
                        'y': data['top'][i],
                        'width': data['width'][i],
                        'height': data['height'][i]
                    })
            
            return {
                'success': True,
                'elements': elements,
                'raw_data': data
            }
            
        except Exception as e:
            return {
                'success': False,
                'elements': [],
                'error': str(e)
            }


# 全局OCR服务实例
_ocr_service: Optional[OCRService] = None


def get_ocr_service(engine: str = 'tesseract') -> OCRService:
    """获取OCR服务实例"""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService(engine)
    return _ocr_service
