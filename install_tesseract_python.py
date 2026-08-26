"""
Tesseract OCR自动下载安装脚本
"""
import os
import sys
import urllib.request
import subprocess
import zipfile
from pathlib import Path

TESSERACT_VERSION = "5.3.1"
TESSERACT_URL = f"https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-{TESSERACT_VERSION}.20230401.exe"
INSTALL_DIR = r"C:\Program Files\Tesseract-OCR"

def download_file(url, dest):
    """下载文件"""
    print(f"正在下载: {url}")
    print(f"保存到: {dest}")
    
    def progress_hook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        sys.stdout.write(f"\r进度: {percent}%")
        sys.stdout.flush()
    
    urllib.request.urlretrieve(url, dest, reporthook=progress_hook)
    print("\n下载完成！")

def install_tesseract():
    """安装Tesseract"""
    print("=" * 60)
    print("Tesseract OCR安装程序")
    print("=" * 60)
    print()
    
    # 检查是否已安装
    if os.path.exists(os.path.join(INSTALL_DIR, "tesseract.exe")):
        print("✓ Tesseract已安装！")
        return True
    
    # 创建临时目录
    temp_dir = os.path.join(os.environ.get('TEMP', 'C:\\temp'), 'tesseract_install')
    os.makedirs(temp_dir, exist_ok=True)
    
    installer_path = os.path.join(temp_dir, "tesseract-installer.exe")
    
    # 下载安装程序
    if not os.path.exists(installer_path):
        try:
            download_file(TESSERACT_URL, installer_path)
        except Exception as e:
            print(f"下载失败: {e}")
            print("请手动下载安装:")
            print("https://github.com/UB-Mannheim/tesseract/releases")
            return False
    
    print()
    print("正在安装Tesseract...")
    print(f"安装目录: {INSTALL_DIR}")
    print()
    
    # 运行安装程序
    try:
        # 静默安装
        result = subprocess.run(
            [installer_path, "/S", f"/D={INSTALL_DIR}"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✓ 安装成功！")
            
            # 配置环境变量
            print()
            print("正在配置环境变量...")
            
            # 添加到PATH（当前会话）
            os.environ['PATH'] = f"{os.environ.get('PATH', '')};{INSTALL_DIR}"
            
            print("✓ 环境变量配置完成")
            print()
            print("注意：请重新打开命令提示符以使用新安装的Tesseract")
            
            return True
        else:
            print(f"安装失败，返回码: {result.returncode}")
            print(f"错误信息: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("安装超时！")
        return False
    except Exception as e:
        print(f"安装出错: {e}")
        return False

if __name__ == "__main__":
    success = install_tesseract()
    
    if success:
        print()
        print("=" * 60)
        print("安装完成！")
        print("=" * 60)
        print()
        print("请重新打开命令提示符，然后运行:")
        print("  tesseract --version")
        print()
    else:
        print()
        print("安装失败，请尝试手动安装:")
        print("1. 访问: https://github.com/UB-Mannheim/tesseract/releases")
        print("2. 下载 tesseract-ocr-w64-setup-5.3.1.20230401.exe")
        print("3. 运行安装程序")
        print()
    
    input("按回车键退出...")
