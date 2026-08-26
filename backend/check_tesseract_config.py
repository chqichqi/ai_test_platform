"""
检查Tesseract配置
"""
import pytesseract
from PIL import Image
import io

# 尝试检测Tesseract路径
import shutil
import os

tesseract_path = shutil.which('tesseract')
print(f"系统PATH中找到的Tesseract路径: {tesseract_path}")

# 检查pytesseract是否配置了tesseract_cmd
print(f"pytesseract当前配置: {pytesseract.pytesseract.tesseract_cmd}")

# 尝试获取版本
try:
    version = pytesseract.get_tesseract_version()
    print(f"Tesseract版本: {version}")
except Exception as e:
    print(f"获取版本失败: {e}")

# 创建测试图片
print("\n创建测试图片...")
from PIL import Image, ImageDraw, ImageFont
try:
    # 创建一个简单的测试图片
    img = Image.new('RGB', (200, 50), color='white')
    d = ImageDraw.Draw(img)
    
    # 尝试使用默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    d.text((10, 10), "Hello Tesseract", fill='black', font=font)
    
    # OCR测试
    print("测试OCR识别...")
    text = pytesseract.image_to_string(img)
    print(f"识别结果: {text}")
    print("测试成功!")
except Exception as e:
    print(f"测试失败: {e}")
