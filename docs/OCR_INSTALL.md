# OCR图像识别功能安装说明

## 概述
AI助手聊天现在支持上传图片进行OCR识别，并基于识别内容生成测试用例。

## 安装Tesseract OCR引擎

### Windows
1. 下载Tesseract安装包：https://github.com/UB-Mannheim/tesseract/wiki
2. 运行安装程序（建议安装到 `C:\Program Files\Tesseract-OCR`）
3. 将安装路径添加到系统环境变量PATH
4. 验证安装：打开CMD，运行 `tesseract --version`

### macOS
```bash
brew install tesseract
brew install tesseract-lang  # 安装中文语言包
```

### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-chi-sim  # 中文语言包
```

### Linux (CentOS/RHEL)
```bash
sudo yum install tesseract
sudo yum install tesseract-langpack-chi_sim  # 中文语言包
```

## 安装Python依赖

在backend目录运行：
```bash
cd backend
pip install pytesseract pillow
```

或者安装所有依赖：
```bash
pip install -r requirements.txt
```

## 配置说明

### 配置Tesseract路径（Windows）

如果Tesseract未安装在默认路径，需要在代码中配置：

```python
import pytesseract

# Windows示例
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### 语言包

系统默认使用中英文混合识别 (`chi_sim+eng`)。

如需其他语言，请安装对应的语言包：
- 中文简体：`chi_sim`
- 中文繁体：`chi_tra`
- 英文：`eng`
- 日文：`jpn`
- 韩文：`kor`

## 功能使用

1. 打开AI助手聊天页面
2. 点击"图片"按钮上传截图
3. 支持上传多张图片
4. 点击"发送"按钮
5. AI会自动识别图片内容并生成测试用例

## 支持的图片格式

- JPG/JPEG
- PNG
- GIF
- BMP
- WebP

## 注意事项

1. **图片质量**：图片清晰度会影响OCR识别准确率
2. **文件大小**：单张图片不超过5MB
3. **文字方向**：支持正常方向的文字，倾斜或旋转文字识别率可能降低
4. **手写文字**：对手写文字识别效果有限

## 故障排查

### OCR识别失败
1. 检查Tesseract是否正确安装：`tesseract --version`
2. 检查语言包是否安装：`tesseract --list-langs`
3. 查看后端日志获取详细错误信息

### 识别准确率低
1. 确保图片清晰度足够
2. 避免图片中有过多干扰元素
3. 调整图片对比度和亮度
4. 对于复杂表格，可能需要手动校对

## 在线OCR服务（可选）

如果本地Tesseract效果不理想，可以配置使用在线OCR服务：

### 百度OCR
1. 注册百度智能云账号
2. 创建应用获取API Key和Secret Key
3. 在系统中配置API密钥

### 阿里云OCR
1. 注册阿里云账号
2. 开通文字识别服务
3. 获取AccessKey ID和Secret

## API端点

- **OCR识别**：`POST /api/v1/web-ui-tests/ocr/analyze`
- **图片生成用例**：`POST /api/v1/web-ui-tests/generate-from-image`
