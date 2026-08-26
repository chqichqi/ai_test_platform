@echo off
chcp 65001
cls
echo ==========================================
echo AI测试平台 - OCR功能安装助手
echo ==========================================
echo.

:: 检查是否以管理员身份运行
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 请以管理员身份运行此脚本！
    echo 右键点击脚本，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo [1/4] 正在下载Tesseract OCR...
echo.

:: 创建临时目录
if not exist "%TEMP%\tesseract_install" mkdir "%TEMP%\tesseract_install"
cd /d "%TEMP%\tesseract_install"

:: 下载Tesseract安装包
powershell -Command "Invoke-WebRequest -Uri 'https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.1.20230401.exe' -OutFile 'tesseract-installer.exe'"

if not exist "tesseract-installer.exe" (
    echo 下载失败，尝试备用链接...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/UB-Mannheim/tesseract/releases/download/5.3.1.20230401/tesseract-ocr-w64-setup-5.3.1.20230401.exe' -OutFile 'tesseract-installer.exe'"
)

if not exist "tesseract-installer.exe" (
    echo 下载失败！请手动下载安装：
    echo https://github.com/UB-Mannheim/tesseract/releases
    pause
    exit /b 1
)

echo [2/4] 正在安装Tesseract...
echo.

:: 静默安装
start /wait tesseract-installer.exe /S /D=C:\Program Files\Tesseract-OCR

echo [3/4] 正在配置环境变量...
echo.

:: 添加到PATH
setx PATH "%PATH%;C:\Program Files\Tesseract-OCR" /M

:: 设置TESSDATA_PREFIX
setx TESSDATA_PREFIX "C:\Program Files\Tesseract-OCR\tessdata" /M

echo [4/4] 正在下载中文语言包...
echo.

:: 下载中文语言包
cd /d "C:\Program Files\Tesseract-OCR"
if not exist "tessdata" mkdir tessdata
cd tessdata

powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata' -OutFile 'chi_sim.traineddata'"
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tessdata/raw/main/chi_tra.traineddata' -OutFile 'chi_tra.traineddata'"
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata' -OutFile 'eng.traineddata'"

echo.
echo ==========================================
echo 安装完成！
echo ==========================================
echo.
echo 请重新打开命令提示符或重启电脑以生效
echo.
echo 验证安装：
echo   tesseract --version
echo   tesseract --list-langs
echo.
pause
