"""
检查Tesseract OCR是否已安装
"""
import sys

try:
    import pytesseract
    from PIL import Image
    
    print("="*60)
    print("检查Tesseract OCR安装状态")
    print("="*60)
    print()
    
    # 检查Tesseract版本
    try:
        version = pytesseract.get_tesseract_version()
        print(f"✅ Tesseract已安装")
        print(f"   版本: {version}")
    except Exception as e:
        print(f"❌ Tesseract未安装或配置错误")
        print(f"   错误: {e}")
        print()
        print("请按以下步骤安装：")
        print("1. 下载安装程序：")
        print("   https://github.com/UB-Mannheim/tesseract/releases")
        print("2. 运行安装程序，选择安装路径：")
        print("   C:\\Program Files\\Tesseract-OCR")
        print("3. 确保勾选中文语言包 (Chinese - Simplified)")
        print("4. 安装完成后重启后端服务")
        sys.exit(1)
    
    # 检查语言包
    print()
    print("检查语言包...")
    try:
        langs = pytesseract.get_languages()
        print(f"   可用语言: {', '.join(langs[:10])}...")
        
        if 'chi_sim' in langs:
            print(f"   ✅ 中文简体语言包已安装")
        else:
            print(f"   ⚠️  中文简体语言包未安装")
            print(f"   请安装中文语言包或重新运行Tesseract安装程序")
    except Exception as e:
        print(f"   ⚠️  无法获取语言包列表: {e}")
    
    # 测试OCR识别
    print()
    print("测试OCR识别...")
    try:
        # 创建一个简单的测试图片
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (200, 50), color='white')
        draw = ImageDraw.Draw(img)
        
        # 尝试使用默认字体
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        draw.text((10, 10), "Hello World 测试", fill='black', font=font)
        
        # OCR识别
        text = pytesseract.image_to_string(img, lang='eng+chi_sim')
        
        if text.strip():
            print(f"   ✅ 测试识别成功")
            print(f"   识别结果: {text.strip()[:50]}")
        else:
            print(f"   ⚠️  测试识别未返回文本")
    except Exception as e:
        print(f"   ❌ 测试识别失败: {e}")
    
    print()
    print("="*60)
    print("检查完成")
    print("="*60)
    
except ImportError as e:
    print(f"❌ Python依赖未安装: {e}")
    print("请运行: pip install pytesseract pillow")
    sys.exit(1)
