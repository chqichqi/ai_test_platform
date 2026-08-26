@echo off
echo ==========================================
echo 配置Tesseract环境变量
echo ==========================================
echo.

:: 设置Tesseract路径
set TESS_PATH=C:\Program Files\Tesseract-OCR

if not exist "%TESS_PATH%\tesseract.exe" (
    echo 错误：未找到Tesseract安装！
    echo 请确认安装路径: %TESS_PATH%
    pause
    exit /b 1
)

:: 添加到用户PATH
echo 正在添加到环境变量...
setx PATH "%PATH%;%TESS_PATH%"
setx TESSDATA_PREFIX "%TESS_PATH%\tessdata"

echo.
echo ==========================================
echo 配置完成！
echo ==========================================
echo.
echo 请重新打开命令提示符，然后运行：
echo   tesseract --version
echo.
pause
