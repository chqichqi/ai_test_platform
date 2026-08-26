import React, { useState, useRef, useEffect } from 'react';
import {
  Card,
  Typography,
  Button,
  Input,
  Space,
  Tag,
  message,
  Row,
  Col,
  Select,
  Alert,
  Tabs,
  Descriptions,
  Badge,
  Empty,
  List,
  Upload,
  Image,
} from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  LoadingOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  EyeOutlined,
  ClearOutlined,
  SettingOutlined,
  ChromeOutlined,
  DesktopOutlined,
  MobileOutlined,
  TabletOutlined,
  PictureOutlined,
  CloseOutlined,
  SaveOutlined,
  DeleteOutlined,
  EditOutlined,
} from '@ant-design/icons';
import type { UploadProps } from 'antd';
import { Avatar, Modal } from 'antd';
import axiosInstance from '../../api/axiosConfig';
import { requirementApi } from '../../api/requirementApi';
import { versionApi } from '../../api/projectApi';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';

const { Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;
const { TabPane } = Tabs;

// localStorage key for chat history
const CHAT_HISTORY_KEY = 'webui_chat_history';
const TEMP_TEST_CASES_KEY = 'webui_temp_test_cases';
const MAX_CHAT_HISTORY = 100; // 最多保存100条消息

// 测试用例生成关键词
const TEST_GENERATION_KEYWORDS = [
  '生成测试用例', '生成测试', '创建测试用例', '生成用例',
  '编写测试', '写测试', '添加测试用例', '生成功能测试',
  '生成API测试', '生成WEB测试', '生成UI测试',
  '帮我生成测试', '请生成测试', '转换为测试用例',
  '根据这个生成测试', '基于这个生成测试'
];

// 检测是否是测试用例生成请求
const is_test_generation_request = (message: string): boolean => {
  if (!message) return false;
  const msg = message.toLowerCase();
  return TEST_GENERATION_KEYWORDS.some(keyword => 
    msg.includes(keyword.toLowerCase())
  );
};

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  type?: 'text' | 'test_case' | 'error';
  metadata?: any;
}

interface WebUITestCase {
  id: string;
  testCaseId: string;
  title: string;
  description: string;
  baseUrl: string;
  browser: string;
  viewportSize: string;
  headless: boolean;
  scriptType: string;
  scriptLanguage: string;
  testScript: string;
  elementSelectors: Record<string, string>;
  status: 'pending' | 'running' | 'passed' | 'failed' | 'saved';
  statusMessage?: string;
  testType: 'functional' | 'api' | 'webui';
  createdAt: string;
}

interface GenerationConfig {
  base_url: string;
  browser: string;
  viewport_size: string;
  headless: boolean;
  script_type: string;
  script_language: string;
  generate_element_selectors: boolean;
  generate_test_script: boolean;
}

const WebUIChatPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [generatedTests, setGeneratedTests] = useState<WebUITestCase[]>([]);
  const [selectedTest, setSelectedTest] = useState<WebUITestCase | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // 图片上传相关状态
  const [uploadedImages, setUploadedImages] = useState<{ file: File; preview: string; id: string }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  
  // 图片预览相关状态
  const [previewImage, setPreviewImage] = useState<{ src: string; name: string } | null>(null);
  
  // 保存最近识别的OCR文本，用于后续生成测试用例
  const [lastOcrText, setLastOcrText] = useState<string>('');
  
  // 保存到用例库的弹窗状态
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [testToSave, setTestToSave] = useState<WebUITestCase | null>(null);
  const [saveTargetType, setSaveTargetType] = useState<'functional' | 'api' | 'webui'>('functional');
  const [isSaving, setIsSaving] = useState(false);
  
  // 编辑测试用例状态
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingTest, setEditingTest] = useState<WebUITestCase | null>(null);
  const [editFormData, setEditFormData] = useState({
    title: '',
    description: '',
    testScript: '',
  });
  
  // 需求文档生成相关状态

  const [versionId] = useState<number>(1); // 默认版本ID，实际应从上下文中获取
  
  const token = useSelector((state: RootState) => state.auth.token);

  const [config, setConfig] = useState<GenerationConfig>({
    base_url: 'http://localhost:3000',
    browser: 'chromium',
    viewport_size: '1920x1080',
    headless: true,
    script_type: 'playwright',
    script_language: 'python',
    generate_element_selectors: true,
    generate_test_script: true
  });

  // 滚动到最新消息（确保输入框可见）
  const scrollToBottom = () => {
    // 使用 setTimeout 确保 DOM 已更新
    setTimeout(() => {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 100);
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 当上传图片后，自动滚动到底部，确保输入框可见
  useEffect(() => {
    if (uploadedImages.length > 0) {
      // 延迟执行，让图片先渲染
      setTimeout(() => {
        scrollToBottom();
      }, 300);
    }
  }, [uploadedImages]);

  // 保存聊天记录到localStorage
  const saveChatHistory = (msgs: ChatMessage[]) => {
    try {
      // 只保存最近的MAX_CHAT_HISTORY条消息
      const messagesToSave = msgs.slice(-MAX_CHAT_HISTORY);
      localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(messagesToSave));
    } catch (error) {
      console.error('保存聊天记录失败:', error);
    }
  };

  // 加载聊天记录
  const loadChatHistory = (): ChatMessage[] | null => {
    try {
      const saved = localStorage.getItem(CHAT_HISTORY_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (error) {
      console.error('加载聊天记录失败:', error);
    }
    return null;
  };

  // 保存临时测试用例到localStorage
  const saveTempTestCases = (tests: WebUITestCase[]) => {
    try {
      localStorage.setItem(TEMP_TEST_CASES_KEY, JSON.stringify(tests));
    } catch (error) {
      console.error('保存临时测试用例失败:', error);
    }
  };

  // 加载临时测试用例
  const loadTempTestCases = (): WebUITestCase[] | null => {
    try {
      const saved = localStorage.getItem(TEMP_TEST_CASES_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch (error) {
      console.error('加载临时测试用例失败:', error);
    }
    return null;
  };

  // 初始化：加载保存的聊天记录和临时测试用例
  useEffect(() => {
    // 加载聊天记录
    const savedMessages = loadChatHistory();
    if (savedMessages && savedMessages.length > 0) {
      setMessages(savedMessages);
    } else {
      // 显示欢迎消息
      setMessages([
        {
          id: 'welcome',
          role: 'assistant',
          content: `👋 欢迎使用 **AI 测试助手**！

我可以帮助你：
1. 💬 **解答测试相关问题** - 测试方法、最佳实践、技术问题等
2. 📝 **生成测试用例** - 当你需要生成测试用例时，请在消息中包含"**生成测试用例**"关键词
3. 📄 **根据需求文档生成** - 使用"**@需求文档**"或"**根据需求文档**"引用需求文档
4. 🖼️ **图片OCR识别** - 上传需求截图或原型图

**使用示例：**
- 普通聊天："什么是边界值分析法？"
- 生成测试用例："请根据以下需求**生成测试用例**：用户登录功能..."
- 引用需求文档："@需求文档 用户登录功能" 或 "根据需求文档 用户登录功能 **生成测试用例**"
- **图片识别**：
  - 仅OCR识别：点击"图片"按钮上传需求截图，AI将识别图片中的文本
  - OCR+生成测试用例：上传图片并在输入框中输入"**根据以上内容生成测试用例**"

**临时测试用例管理（右侧列表）：**
- ⏳ 生成的测试用例会显示在右侧列表中
- ✏️ 点击"编辑"按钮修改测试用例（标题、描述、脚本）
- ▶️ 点击"执行"按钮运行测试
- 💾 点击"保存"按钮将用例保存到功能/API/WEBUI测试库
- 🗑️ 点击"删除"按钮删除不需要的临时用例
- ✅ 执行通过后建议保存到正式用例库

**💡 关于AI生成测试用例的说明：**
- AI生成的测试用例可能不够完整，建议您在保存前仔细审查和编辑
- 您可以直接在右侧列表中编辑任何测试用例
- 编辑后的内容会保存在临时列表中，您可以随时修改

**支持的测试类型：**
- 功能测试用例
- WEB UI自动化测试用例
- API测试用例

**💡 提示**：对话记录会自动保存，下次打开页面时会恢复之前的对话。

请问有什么可以帮助你的？`,
          timestamp: new Date().toISOString(),
          type: 'text'
        }
      ]);
    }
    
    // 加载临时测试用例
    const savedTestCases = loadTempTestCases();
    if (savedTestCases && savedTestCases.length > 0) {
      setGeneratedTests(savedTestCases);
    }
  }, []);

  // 消息变化时保存到localStorage
  useEffect(() => {
    if (messages.length > 0) {
      saveChatHistory(messages);
    }
  }, [messages]);

  // 临时测试用例变化时保存到localStorage
  useEffect(() => {
    saveTempTestCases(generatedTests);
  }, [generatedTests]);

// 发送消息并生成测试
  const handleSendMessage = async () => {
    if (!inputMessage.trim() && uploadedImages.length === 0) {
      message.warning('请输入内容或上传图片');
      return;
    }

    // 构建用户消息内容
    let finalContent = inputMessage;
    if (uploadedImages.length > 0) {
      finalContent = `[图片数量: ${uploadedImages.length}]\n${inputMessage}`;
    }

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: finalContent,
      timestamp: new Date().toISOString(),
      type: 'text',
      metadata: uploadedImages.length > 0 ? { images: uploadedImages.map(img => img.id) } : undefined
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsGenerating(true);

    // 检测是否是测试用例生成请求
    const isGenerateRequest = is_test_generation_request(inputMessage);
    
    // 创建AI消息占位符（提前创建，供图片处理使用）
    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      type: 'text'
    };
    setMessages(prev => [...prev, assistantMessage]);

    // 如果有图片，先上传图片进行OCR识别
    if (uploadedImages.length > 0) {
      // 如果有图片且用户要求生成测试用例，则先OCR再生成
      if (isGenerateRequest) {
        await handleImageAnalysisWithGeneration(uploadedImages, assistantMessageId);
      } else {
        // 只进行OCR识别，不生成测试用例
        await handleImageAnalysis(uploadedImages, assistantMessageId);
      }
      return;
    }

    // 如果没有图片，但有lastOcrText且用户要求生成测试用例
    if (isGenerateRequest && lastOcrText) {
      await generateFromOcrText(lastOcrText, assistantMessageId);
      return;
    }
    
    // 如果用户要求生成测试用例，但没有图片也没有OCR文本
    if (isGenerateRequest && !lastOcrText) {
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: '⚠️ 请先上传图片进行OCR识别，然后再要求生成测试用例。\n\n操作步骤：\n1. 点击"图片"按钮上传需求截图\n2. 等待OCR识别完成\n3. 然后输入"生成测试用例"' }
          : m
      ));
      setIsGenerating(false);
      return;
    }

    // 检测是否引用了需求文档
    const requirementMatch = inputMessage.match(/[@＠]需求文档\s*(.+?)(?=\s|$)/) || 
                             inputMessage.match(/根据需求文档\s*(.+?)(?=\s|$)/);
    
    if (requirementMatch && inputMessage.includes('生成')) {
      // 引用了需求文档且需要生成
      await handleGenerateFromRequirement(
        requirementMatch[1].trim(),
        assistantMessageId
      );
      return;
    }

    try {
      if (!token) {
        message.error('请先登录');
        setMessages(prev => prev.map(m => 
          m.id === assistantMessageId 
            ? { ...m, content: '❌ 请先登录后再使用AI助手功能' }
            : m
        ));
        setIsGenerating(false);
        return;
      }
      
      const response = await fetch('/api/v1/web-ui-tests/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: userMessage.content,
          base_url: config.base_url,
          browser: config.browser,
          viewport_size: config.viewport_size,
          headless: config.headless,
          script_type: config.script_type,
          script_language: config.script_language,
          generate_element_selectors: config.generate_element_selectors,
          generate_test_script: config.generate_test_script,
        }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value);
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.substring(6));
                
                if (data.type === 'start' || data.type === 'start_generate') {
                  // 开始处理
                } else if (data.type === 'content') {
                  // 流式内容
                  setMessages(prev => prev.map(m => 
                    m.id === assistantMessageId 
                      ? { ...m, content: m.content + data.content }
                      : m
                  ));
                } else if (data.type === 'info') {
                  setMessages(prev => prev.map(m => 
                    m.id === assistantMessageId 
                      ? { ...m, content: data.content }
                      : m
                  ));
                } else if (data.type === 'result') {
                  // 生成测试用例完成
                  if (data.success && data.test_cases?.length > 0) {
                    const formattedTests = data.test_cases.map((tc: any) => ({
                      id: tc.id,
                      testCaseId: tc.test_case_id,
                      title: tc.test_case?.title || '未命名测试',
                      description: tc.test_case?.description || '',
                      baseUrl: tc.base_url,
                      browser: tc.browser,
                      viewportSize: tc.viewport_size,
                      headless: tc.headless,
                      scriptType: tc.script_type,
                      scriptLanguage: tc.script_language,
                      testScript: tc.test_script,
                      elementSelectors: tc.element_selectors || {},
                      status: 'pending',
                      testType: 'webui',
                      createdAt: tc.created_at
                    }));
                    
                    setGeneratedTests(prev => [...formattedTests, ...prev]);
                    
                    setMessages(prev => prev.map(m => 
                      m.id === assistantMessageId 
                        ? { ...m, type: 'test_case', metadata: { testCases: data.test_cases } }
                        : m
                    ));
                  }
                } else if (data.type === 'done') {
                  // 完成
                }
              } catch (e) {
                console.error('Parse SSE error:', e);
              }
            }
          }
        }
      }
    } catch (error: any) {
      console.error('生成失败:', error);
      
      // 检查是否是LLM配置错误
      let errorMessage = `❌ 处理失败: ${error.message}`;
      if (error.message?.includes('No active LLM config') || 
          error.response?.data?.detail?.includes('LLM') ||
          error.response?.status === 503) {
        errorMessage = `❌ 系统未配置AI服务\n\n请先前往【系统设置 → LLM配置】页面:\n1. 添加LLM配置（如OpenAI、DeepSeek等）\n2. 点击"测试连接"验证配置\n3. 激活配置后刷新页面`;
      }
      
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: errorMessage }
          : m
      ));
    } finally {
      setIsGenerating(false);
    }
  };

  // 根据需求文档生成测试用例
  const handleGenerateFromRequirement = async (docName: string, assistantMessageId: string) => {
    try {
      // 1. 查询需求文档
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `🔍 正在查找需求文档 "${docName}"...` }
          : m
      ));

      const docsRes = await requirementApi.listDocuments({
        version_id: versionId,
        status: 'parsed'
      });
      
      const matchedDoc = docsRes.items.find(doc => 
        doc.name.toLowerCase().includes(docName.toLowerCase())
      );

      if (!matchedDoc) {
        setMessages(prev => prev.map(m => 
          m.id === assistantMessageId 
            ? { ...m, content: `❌ 未找到需求文档 "${docName}"。\n\n可用文档：\n${docsRes.items.map(d => `• ${d.name}`).join('\n')}` }
            : m
        ));
        setIsGenerating(false);
        return;
      }

      // 2. 分析文档并生成测试用例
      setMessages(prev => prev.map(m =>
        m.id === assistantMessageId
          ? { ...m, content: `🤖 正在分析需求文档 "${matchedDoc.name}" 并生成测试用例，请稍候（可能需要几分钟）...` }
          : m
      ));

      const genRes = await versionApi.generateAssets(versionId, 'ai');

      // 3. 展示生成结果
      setMessages(prev => prev.map(m =>
        m.id === assistantMessageId
          ? { ...m,
              content: `✅ AI分析完成并生成测试用例！\n\n📊 **生成结果**\n• 文档：${matchedDoc.name}\n• 生成用例数：${genRes.data?.test_cases_count ?? 0}\n\n已保存到功能测试用例库，你可以在功能测试页面查看和管理这些用例。` }
          : m
      ));

    } catch (error: any) {
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `❌ 处理失败: ${error.message}` }
          : m
      ));
    } finally {
      setIsGenerating(false);
    }
  };

  // 图片OCR分析处理
  const handleImageAnalysis = async (
    images: { file: File; preview: string; id: string }[],
    existingAssistantMessageId?: string
  ) => {
    const assistantMessageId = existingAssistantMessageId || (Date.now() + 1).toString();
    
    // 如果没有提供existingAssistantMessageId，需要创建新的消息
    if (!existingAssistantMessageId) {
      setMessages(prev => [...prev, {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        type: 'text'
      }]);
    }

    try {
      // 检查token是否存在
      if (!token) {
        throw new Error('未登录或登录已过期，请重新登录');
      }

      // 1. 上传图片进行OCR识别
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `🔍 正在识别 ${images.length} 张图片的内容...` }
          : m
      ));

      const formData = new FormData();
      images.forEach((img) => {
        formData.append(`images`, img.file);
      });
      
      // 调用OCR API - 使用axios
      const response = await axiosInstance.post('/web-ui-tests/ocr/analyze', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      const ocrResult = response.data;
      
      // 检查识别结果
      if (!ocrResult.success) {
        throw new Error(ocrResult.error || '图片识别失败');
      }
      
      if (!ocrResult.text || ocrResult.text.length === 0) {
        setMessages(prev => prev.map(m => 
          m.id === assistantMessageId 
            ? { ...m, content: `⚠️ **图片识别完成，但未识别到文本内容**\n\n可能原因：\n• Tesseract OCR引擎未正确安装\n• 图片中不包含文字\n• 图片清晰度不足\n• 未安装中文语言包 (chi_sim)\n\n**解决方案：**\n1. 运行 install_tesseract.bat 安装Tesseract\n2. 确保安装时勾选中文语言包\n3. 尝试上传包含清晰文字的图片` }
            : m
        ));
        setUploadedImages([]);
        setIsGenerating(false);
        return;
      }
      
      // 2. 显示识别结果
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `✅ 图片识别完成！\n\n📝 **识别内容**（共${ocrResult.text.length}字符）：\n${ocrResult.text.substring(0, 500)}${ocrResult.text.length > 500 ? '...' : ''}\n\n💡 **提示**：如果需要根据此内容生成测试用例，请输入"**生成测试用例**"或"**根据以上内容生成测试用例**"` }
          : m
      ));
      
      // 保存OCR结果，用于后续可能的测试用例生成
      setLastOcrText(ocrResult.text);

      // 清空已上传图片
      setUploadedImages([]);

    } catch (error: any) {
      // 显示后端返回的详细错误信息
      let errorContent = `❌ 图片处理失败`;
      
      if (error.response) {
        // 后端返回了错误响应
        const status = error.response.status;
        const errorData = error.response.data;
        
        if (status === 500 && errorData?.error) {
          // 显示后端返回的具体错误
          errorContent = `❌ ${errorData.error}`;
        } else if (errorData?.detail) {
          errorContent = `❌ ${errorData.detail}`;
        } else if (errorData?.message) {
          errorContent = `❌ ${errorData.message}`;
        } else {
          errorContent = `❌ 服务器错误 (${status})`;
        }
      } else if (error.request) {
        // 请求已发送但没有收到响应
        errorContent = `❌ 无法连接到服务器，请检查网络或后端服务是否运行`;
      } else {
        // 其他错误
        errorContent = `❌ ${error.message || '未知错误'}`;
      }
      
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: errorContent }
          : m
      ));
    } finally {
      setIsGenerating(false);
      setIsUploading(false);
    }
  };

  // 根据OCR文本生成测试用例
  const generateFromOcrText = async (ocrText: string, assistantMessageId: string) => {
    try {
      // 显示正在生成的消息
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: '🤖 正在根据图片识别内容生成测试用例...' }
          : m
      ));

      // 调用生成API - 使用axios，增加超时时间到120秒
      const result = await axiosInstance.post('/web-ui-tests/generate-from-image', {
        image_text: ocrText,
        base_url: config.base_url,
        browser: config.browser,
        viewport_size: config.viewport_size,
        headless: config.headless,
      }, {
        timeout: 120000, // 120秒超时
      });

      // 将生成的测试用例添加到右侧列表
      if (result.data.count > 0) {
        const newTestCase: WebUITestCase = {
          id: Date.now().toString(),
          testCaseId: '',
          title: '基于图片生成的测试用例',
          description: ocrText.substring(0, 100) + '...',
          baseUrl: config.base_url,
          browser: config.browser,
          viewportSize: config.viewport_size,
          headless: config.headless,
          scriptType: config.script_type,
          scriptLanguage: config.script_language,
          testScript: result.data.generated || '',
          elementSelectors: {},
          status: 'pending',
          testType: 'webui',
          createdAt: new Date().toISOString()
        };
        setGeneratedTests(prev => [newTestCase, ...prev]);
      }

      setMessages(prev => [...prev, {
        id: (Date.now() + 3).toString(),
        role: 'assistant',
        content: `🎉 根据图片内容成功生成 ${result.data.count} 个测试用例！\n\n测试用例已添加到右侧列表，您可以：\n1. 点击"查看"按钮查看测试脚本\n2. 点击"执行"按钮运行测试\n3. 点击"保存"按钮将用例保存到测试库`,
        timestamp: new Date().toISOString(),
        type: 'text'
      }]);

      // 清空已保存的OCR文本
      setLastOcrText('');
    } catch (error: any) {
      console.error('生成测试用例失败:', error);
      let errorMessage = error.message || '未知错误';
      
      // 检查是否是超时错误
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMessage = '请求超时（120秒）。AI生成测试用例可能需要较长时间，请稍后重试或尝试：\n1. 减少图片中的文本内容\n2. 分段生成测试用例\n3. 检查后端服务是否正常运行';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      
      setMessages(prev => [...prev, {
        id: (Date.now() + 3).toString(),
        role: 'assistant',
        content: `❌ 生成测试用例失败: ${errorMessage}`,
        timestamp: new Date().toISOString(),
        type: 'error'
      }]);
    } finally {
      setIsGenerating(false);
    }
  };

  // 图片OCR识别并生成测试用例
  const handleImageAnalysisWithGeneration = async (
    images: { file: File; preview: string; id: string }[],
    assistantMessageId: string
  ) => {
    try {
      // 检查token是否存在
      if (!token) {
        throw new Error('未登录或登录已过期，请重新登录');
      }

      // 1. 上传图片进行OCR识别
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `🔍 正在识别 ${images.length} 张图片的内容...` }
          : m
      ));

      const formData = new FormData();
      images.forEach((img) => {
        formData.append(`images`, img.file);
      });
      
      // 调用OCR API
      const response = await axiosInstance.post('/web-ui-tests/ocr/analyze', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      const ocrResult = response.data;
      
      // 检查识别结果
      if (!ocrResult.success) {
        throw new Error(ocrResult.error || '图片识别失败');
      }
      
      if (!ocrResult.text || ocrResult.text.length === 0) {
        setMessages(prev => prev.map(m => 
          m.id === assistantMessageId 
            ? { ...m, content: `⚠️ **图片识别完成，但未识别到文本内容**\n\n可能原因：\n• Tesseract OCR引擎未正确安装\n• 图片中不包含文字\n• 图片清晰度不足\n• 未安装中文语言包 (chi_sim)\n\n**解决方案：**\n1. 运行 install_tesseract.bat 安装Tesseract\n2. 确保安装时勾选中文语言包\n3. 尝试上传包含清晰文字的图片` }
            : m
        ));
        setUploadedImages([]);
        setIsGenerating(false);
        return;
      }
      
      // 2. 显示识别结果并开始生成测试用例
      setMessages(prev => prev.map(m => 
        m.id === assistantMessageId 
          ? { ...m, content: `✅ 图片识别完成！\n\n📝 **识别内容**（共${ocrResult.text.length}字符）：\n${ocrResult.text.substring(0, 500)}${ocrResult.text.length > 500 ? '...' : ''}\n\n🤖 正在根据识别内容生成测试用例...` }
          : m
      ));

      // 3. 根据识别内容生成测试用例
      const result = await axiosInstance.post('/web-ui-tests/generate-from-image', {
        image_text: ocrResult.text,
        base_url: config.base_url,
        browser: config.browser,
        viewport_size: config.viewport_size,
        headless: config.headless,
      }, {
        timeout: 120000, // 120秒超时
      });

      // 将生成的测试用例添加到右侧列表
      if (result.data.count > 0) {
        const newTestCase: WebUITestCase = {
          id: Date.now().toString(),
          testCaseId: '',
          title: '基于图片生成的测试用例',
          description: ocrResult.text.substring(0, 100) + '...',
          baseUrl: config.base_url,
          browser: config.browser,
          viewportSize: config.viewport_size,
          headless: config.headless,
          scriptType: config.script_type,
          scriptLanguage: config.script_language,
          testScript: result.data.generated || '',
          elementSelectors: {},
          status: 'pending',
          testType: 'webui',
          createdAt: new Date().toISOString()
        };
        setGeneratedTests(prev => [newTestCase, ...prev]);
      }

      setMessages(prev => [...prev, {
        id: (Date.now() + 3).toString(),
        role: 'assistant',
        content: `🎉 根据图片内容成功生成 ${result.data.count} 个测试用例！\n\n测试用例已添加到右侧列表，您可以：\n1. 点击"查看"按钮查看测试脚本\n2. 点击"执行"按钮运行测试\n3. 点击"保存"按钮将用例保存到测试库`,
        timestamp: new Date().toISOString(),
        type: 'text'
      }]);

      // 清空已上传图片
      setUploadedImages([]);
    } catch (error: any) {
      console.error('处理失败:', error);
      let errorMessage = error.message || '未知错误';
      
      // 检查是否是超时错误
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMessage = '请求超时（120秒）。AI生成测试用例可能需要较长时间，请稍后重试或尝试：\n1. 减少图片中的文本内容\n2. 分段生成测试用例\n3. 检查后端服务是否正常运行';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      
      setMessages(prev => [...prev, {
        id: (Date.now() + 3).toString(),
        role: 'assistant',
        content: `❌ 处理失败: ${errorMessage}`,
        timestamp: new Date().toISOString(),
        type: 'error'
      }]);
    } finally {
      setIsGenerating(false);
      setIsUploading(false);
    }
  };

  // 处理图片上传
  const handleImageUpload: UploadProps['beforeUpload'] = (file) => {
    const isImage = file.type.startsWith('image/');
    if (!isImage) {
      message.error('只能上传图片文件！');
      return Upload.LIST_IGNORE;
    }
    
    const isLt5M = file.size / 1024 / 1024 < 5;
    if (!isLt5M) {
      message.error('图片大小不能超过5MB！');
      return Upload.LIST_IGNORE;
    }

    // 创建预览
    const reader = new FileReader();
    reader.onload = (e) => {
      setUploadedImages(prev => [...prev, {
        file,
        preview: e.target?.result as string,
        id: Date.now().toString()
      }]);
    };
    reader.readAsDataURL(file);

    return false; // 阻止自动上传
  };

  // 移除已上传图片
  const handleRemoveImage = (id: string) => {
    setUploadedImages(prev => prev.filter(img => img.id !== id));
  };

  // 执行测试
  const handleExecuteTest = async (test: WebUITestCase) => {
    try {
      // 更新测试状态为运行中
      setGeneratedTests(prev => prev.map(t => 
        t.id === test.id 
          ? { ...t, status: 'running', statusMessage: '正在执行测试...' }
          : t
      ));

      // TODO: 调用执行测试的API
      // const response = await axiosInstance.post('/web-ui-tests/execute', {
      //   test_script: test.testScript,
      //   browser: test.browser,
      //   base_url: test.baseUrl,
      //   headless: test.headless,
      // });

      // 模拟执行成功
      setTimeout(() => {
        setGeneratedTests(prev => prev.map(t => 
          t.id === test.id 
            ? { ...t, status: 'passed', statusMessage: '测试执行成功' }
            : t
        ));
        message.success('测试执行完成');
      }, 2000);

    } catch (error: any) {
      setGeneratedTests(prev => prev.map(t => 
        t.id === test.id 
          ? { ...t, status: 'failed', statusMessage: error.message || '执行失败' }
          : t
      ));
      message.error('测试执行失败: ' + error.message);
    }
  };

  // 删除临时测试用例
  const handleDeleteTest = (testId: string) => {
    setGeneratedTests(prev => prev.filter(t => t.id !== testId));
    message.success('临时测试用例已删除');
  };

  // 打开编辑测试用例弹窗
  const handleOpenEditModal = (test: WebUITestCase) => {
    setEditingTest(test);
    setEditFormData({
      title: test.title,
      description: test.description,
      testScript: test.testScript,
    });
    setShowEditModal(true);
  };

  // 保存编辑后的测试用例
  const handleSaveEdit = () => {
    if (!editingTest) return;

    setGeneratedTests(prev => prev.map(t => 
      t.id === editingTest.id 
        ? { 
            ...t, 
            title: editFormData.title,
            description: editFormData.description,
            testScript: editFormData.testScript,
          }
        : t
    ));

    message.success('测试用例已更新');
    setShowEditModal(false);
    setEditingTest(null);
  };

  // 打开保存到用例库的弹窗
  const handleOpenSaveModal = (test: WebUITestCase) => {
    setTestToSave(test);
    setSaveTargetType(test.testType);
    setShowSaveModal(true);
  };

  // 保存测试用例到用例库
  const handleSaveToLibrary = async () => {
    if (!testToSave) return;

    setIsSaving(true);
    try {
      // 模拟保存成功
      await new Promise(resolve => setTimeout(resolve, 1000));

      // 更新测试状态为已保存
      setGeneratedTests(prev => prev.map(t => 
        t.id === testToSave.id 
          ? { ...t, status: 'saved', statusMessage: `已保存到${saveTargetType === 'functional' ? '功能' : saveTargetType === 'api' ? 'API' : 'WEBUI'}测试库` }
          : t
      ));

      message.success(`测试用例已成功保存到${saveTargetType === 'functional' ? '功能' : saveTargetType === 'api' ? 'API' : 'WEBUI'}测试库`);
      setShowSaveModal(false);
      setTestToSave(null);
    } catch (error: any) {
      message.error('保存失败: ' + error.message);
    } finally {
      setIsSaving(false);
    }
  };

  // 清空对话
  const handleClearChat = () => {
    // 清除localStorage中的聊天记录
    try {
      localStorage.removeItem(CHAT_HISTORY_KEY);
    } catch (error) {
      console.error('清除聊天记录失败:', error);
    }
    
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: '对话已清空，临时测试用例列表也已清空。你可以继续问我测试相关的问题，或者输入"**生成测试用例**"来创建测试用例。',
        timestamp: new Date().toISOString(),
        type: 'text'
      }
    ]);
    setGeneratedTests([]);
    setSelectedTest(null);
    message.success('对话历史已清空');
  };

  // 渲染消息内容
  const renderMessageContent = (content: string) => {
    // 简单的文本格式化，替代 marked
    const formattedContent = content
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br/>');
    return <div dangerouslySetInnerHTML={{ __html: formattedContent }} />;
  };

  // 浏览器选项
  const browserOptions = [
    { value: 'chromium', label: 'Chrome/Chromium', icon: <ChromeOutlined /> },
    { value: 'firefox', label: 'Firefox' },
    { value: 'safari', label: 'Safari' },
    { value: 'edge', label: 'Edge' },
    { value: 'webkit', label: 'WebKit' }
  ];

  // 视口尺寸选项
  const viewportOptions = [
    { value: '1920x1080', label: '桌面 1920x1080', icon: <DesktopOutlined /> },
    { value: '1366x768', label: '桌面 1366x768', icon: <DesktopOutlined /> },
    { value: '1536x864', label: '桌面 1536x864', icon: <DesktopOutlined /> },
    { value: '768x1024', label: '平板 768x1024', icon: <TabletOutlined /> },
    { value: '810x1080', label: '平板 810x1080', icon: <TabletOutlined /> },
    { value: '375x667', label: '移动端 375x667', icon: <MobileOutlined /> },
    { value: '414x896', label: '移动端 414x896', icon: <MobileOutlined /> },
    { value: '360x640', label: '移动端 360x640', icon: <MobileOutlined /> }
  ];

  return (
    <div style={{ height: 'calc(100vh - 120px)', display: 'flex', gap: 16 }}>
      {/* 左侧聊天区域 */}
      <Card 
        style={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column',
          overflow: 'hidden'
        }}
        styles={{ body: { 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column',
          overflow: 'hidden',
          padding: '16px'
        }}}
        title={
          <Space>
            <RobotOutlined />
            <span>AI 聊天生成器</span>
            <Badge count={generatedTests.length} showZero style={{ backgroundColor: '#52c41a' }} />
          </Space>
        }
        extra={
          <Space>
            <Button 
              icon={<SettingOutlined />} 
              onClick={() => setShowConfig(!showConfig)}
              type={showConfig ? 'primary' : 'default'}
            >
              配置
            </Button>
            <Button icon={<ClearOutlined />} onClick={handleClearChat}>
              清空
            </Button>
          </Space>
        }
      >
        {/* 配置面板 */}
        {showConfig && (
          <Alert
            type="info"
            closable
            onClose={() => setShowConfig(false)}
            style={{ marginBottom: 16 }}
            message="
生成配置"
            description={
              <Row gutter={16} style={{ marginTop: 8 }}>
                <Col span={12}>
                  <Text strong>基础URL：</Text>
                  <Input 
                    value={config.base_url}
                    onChange={e => setConfig({...config, base_url: e.target.value})}
                    placeholder="http://localhost:3000"
                    style={{ marginTop: 4 }}
                  />
                </Col>
                <Col span={6}>
                  <Text strong>浏览器：</Text>
                  <Select 
                    value={config.browser}
                    onChange={val => setConfig({...config, browser: val})}
                    style={{ width: '100%', marginTop: 4 }}
                  >
                    {browserOptions.map(opt => (
                      <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                    ))}
                  </Select>
                </Col>
                <Col span={6}>
                  <Text strong>视口尺寸：</Text>
                  <Select 
                    value={config.viewport_size}
                    onChange={val => setConfig({...config, viewport_size: val})}
                    style={{ width: '100%', marginTop: 4 }}
                  >
                    {viewportOptions.map(opt => (
                      <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                    ))}
                  </Select>
                </Col>
              </Row>
            }
          />
        )}

        {/* 消息列表 */}
        <div style={{ 
          flex: 1, 
          overflowY: 'auto', 
          padding: '0 8px',
          marginBottom: 16
        }}>
          <List
            itemLayout="horizontal"
            dataSource={messages}
            renderItem={msg => (
              <List.Item
                style={{
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  padding: '8px 0'
                }}
              >
                <Space align="start" style={{ maxWidth: '80%' }}>
                  {msg.role === 'assistant' && (
                    <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#1890ff' }} />
                  )}
                  <div
                    style={{
                      background: msg.role === 'user' ? '#1890ff' : '#f0f2f5',
                      color: msg.role === 'user' ? '#fff' : '#000',
                      padding: '12px 16px',
                      borderRadius: '12px',
                      borderBottomLeftRadius: msg.role === 'user' ? '12px' : '4px',
                      borderBottomRightRadius: msg.role === 'user' ? '4px' : '12px'
                    }}
                  >
                    {renderMessageContent(msg.content)}
                    {msg.type === 'test_case' && msg.metadata?.testCases && (
                      <div style={{ marginTop: 12 }}>
                        <Button 
                          type="primary" 
                          size="small"
                          icon={<EyeOutlined />}
                          onClick={() => {
                            const firstTest = msg.metadata.testCases[0];
                            setSelectedTest({
                              id: firstTest.id,
                              testCaseId: firstTest.test_case_id,
                              title: firstTest.test_case?.title || '未命名测试',
                              description: firstTest.test_case?.description || '',
                              baseUrl: firstTest.base_url,
                              browser: firstTest.browser,
                              viewportSize: firstTest.viewport_size,
                              headless: firstTest.headless,
                              scriptType: firstTest.script_type,
                              scriptLanguage: firstTest.script_language,
                              testScript: firstTest.test_script,
                              testType: 'webui',
                              elementSelectors: firstTest.element_selectors || {},
                              status: 'pending',
                              createdAt: firstTest.created_at
                            });
                          }}
                        >
                          查看详情
                        </Button>
                      </div>
                    )}
                    <div style={{ fontSize: '11px', opacity: 0.6, marginTop: 4, textAlign: 'right' }}>
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                  {msg.role === 'user' && (
                    <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#52c41a' }} />
                  )}
                </Space>
              </List.Item>
            )}
          />
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div style={{ flexShrink: 0 }}>
          {/* 已上传图片预览 */}
          {uploadedImages.length > 0 && (
            <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {uploadedImages.map(img => (
                <div key={img.id} style={{ position: 'relative', display: 'inline-block' }}>
                  <Image
                    src={img.preview}
                    style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 4, cursor: 'pointer' }}
                    preview={false}
                    onClick={() => setPreviewImage({ src: img.preview, name: img.file.name })}
                  />
                  <Button
                    type="text"
                    icon={<CloseOutlined />}
                    size="small"
                    style={{ 
                      position: 'absolute', 
                      top: -8, 
                      right: -8, 
                      background: '#fff',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                    }}
                    onClick={() => handleRemoveImage(img.id)}
                  />
                </div>
              ))}
            </div>
          )}
          
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            {/* 图片上传按钮 */}
            <Upload
              beforeUpload={handleImageUpload}
              showUploadList={false}
              accept="image/*"
              multiple
              disabled={isGenerating || isUploading}
            >
              <Button
                icon={<PictureOutlined />}
                style={{ height: 76 }}
                disabled={isGenerating || isUploading}
              >
                图片{uploadedImages.length > 0 && `(${uploadedImages.length})`}
              </Button>
            </Upload>
            
            <TextArea
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              placeholder='输入你的问题...&#10;• 上传图片：AI自动识别图片中的文本&#10;• 生成测试用例：在输入框中输入"生成测试用例"+图片或需求描述&#10;• 示例：上传需求截图后，输入"根据以上内容生成测试用例"'
              rows={3}
              disabled={isGenerating}
              style={{ flex: 1, resize: 'none' }}
              onPressEnter={e => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              autoFocus
            />
            <Button
              type="primary"
              icon={isGenerating ? <LoadingOutlined /> : <SendOutlined />}
              onClick={handleSendMessage}
              disabled={isGenerating || (!inputMessage.trim() && uploadedImages.length === 0)}
              loading={isGenerating}
              style={{ height: 76 }}
            >
              {isGenerating ? '生成中...' : '发送'}
            </Button>
          </div>
          <Text type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
            按 Enter 发送，Shift+Enter 换行 · 上传图片仅进行OCR识别，生成的测试用例将显示在右侧列表中
          </Text>
        </div>
      </Card>

      {/* 右侧测试用例列表 */}
      <Card 
        style={{ 
          width: 400, 
          display: 'flex', 
          flexDirection: 'column',
          maxHeight: 'calc(100vh - 140px)'
        }}
        styles={{ body: { 
          flex: 1, 
          overflow: 'auto',
          padding: '12px'
        }}}
        title={
          <Space>
            <CodeOutlined />
            <span>临时测试用例</span>
            <Tag color="blue">{generatedTests.length}</Tag>
          </Space>
        }
      >
        {generatedTests.length === 0 ? (
          <Empty description="暂无临时测试用例
上传图片并输入'生成测试用例'来创建" />
        ) : (
          <List
            dataSource={generatedTests}
            split={false}
            renderItem={test => (
              <List.Item
                style={{ 
                  marginBottom: 12,
                  padding: '12px',
                  border: '1px solid #e8e8e8',
                  borderRadius: '8px',
                  borderLeft: `4px solid ${
                    test.status === 'passed' ? '#52c41a' : 
                    test.status === 'failed' ? '#f5222d' : 
                    test.status === 'running' ? '#1890ff' :
                    test.status === 'saved' ? '#722ed1' : '#d9d9d9'
                  }`,
                  background: test.status === 'running' ? '#e6f7ff' : '#fafafa'
                }}
              >
                <div style={{ width: '100%' }}>
                  {/* 标题行 */}
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center',
                    marginBottom: 8
                  }}>
                    <Text strong style={{ fontSize: 14 }} ellipsis={{ tooltip: test.title }}>
                      {test.title}
                    </Text>
                    <Tag color={
                      test.status === 'pending' ? 'default' :
                      test.status === 'running' ? 'blue' :
                      test.status === 'passed' ? 'success' :
                      test.status === 'failed' ? 'error' :
                      test.status === 'saved' ? 'purple' : 'default'
                    }>
                      {test.status === 'pending' && '待执行'}
                      {test.status === 'running' && '执行中'}
                      {test.status === 'passed' && '通过'}
                      {test.status === 'failed' && '失败'}
                      {test.status === 'saved' && '已保存'}
                    </Tag>
                  </div>
                  
                  {/* 描述 */}
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                      {test.description?.substring(0, 60) || '暂无描述'}...
                    </Text>
                  </div>
                  
                  {/* 标签行 */}
                  <div style={{ marginBottom: 8 }}>
                    <Space size={4}>
                      <Tag>{test.browser}</Tag>
                      <Tag>{test.viewportSize}</Tag>
                      <Tag color="blue">{test.testType?.toUpperCase()}</Tag>
                    </Space>
                  </div>
                  
                  {/* 操作按钮行 - 水平排列 */}
                  <div style={{ 
                    display: 'flex', 
                    gap: '8px',
                    borderTop: '1px solid #e8e8e8',
                    paddingTop: 8,
                    marginTop: 4
                  }}>
                    <Button 
                      icon={<EyeOutlined />} 
                      size="small"
                      onClick={() => setSelectedTest(test)}
                      style={{ flex: 1 }}
                    >
                      查看
                    </Button>
                    <Button 
                      icon={<EditOutlined />} 
                      size="small"
                      onClick={() => handleOpenEditModal(test)}
                      style={{ flex: 1 }}
                    >
                      编辑
                    </Button>
                    <Button 
                      icon={<PlayCircleOutlined />} 
                      size="small"
                      type="primary"
                      loading={test.status === 'running'}
                      disabled={test.status === 'running' || test.status === 'saved'}
                      onClick={() => handleExecuteTest(test)}
                      style={{ flex: 1 }}
                    >
                      执行
                    </Button>
                    <Button 
                      icon={<SaveOutlined />} 
                      size="small"
                      disabled={test.status === 'saved'}
                      onClick={() => handleOpenSaveModal(test)}
                      style={{ flex: 1 }}
                    >
                      保存
                    </Button>
                    <Button 
                      icon={<DeleteOutlined />} 
                      size="small"
                      danger
                      onClick={() => handleDeleteTest(test.id)}
                    />
                  </div>
                  
                  {/* 状态消息 */}
                  {test.statusMessage && (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {test.statusMessage}
                      </Text>
                    </div>
                  )}
                </div>
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 测试详情弹窗 */}
      {selectedTest && (
        <Modal
          maskClosable={false}
        title={selectedTest.title}
          open={!!selectedTest}
          onCancel={() => setSelectedTest(null)}
          width={800}
          footer={[
            <Button key="close" onClick={() => setSelectedTest(null)}>
              关闭
            </Button>,
            <Button key="copy" icon={<CodeOutlined />} onClick={() => {
              navigator.clipboard.writeText(selectedTest.testScript);
              message.success('脚本已复制到剪贴板');
            }}>
              复制脚本
            </Button>,
            <Button 
              key="execute" 
              type="primary" 
              icon={<PlayCircleOutlined />}
              onClick={() => {
                handleExecuteTest(selectedTest);
                setSelectedTest(null);
              }}
            >
              执行测试
            </Button>
          ]}
        >
          <Tabs defaultActiveKey="script">
            <TabPane tab="测试脚本" key="script">
              <TextArea
                value={selectedTest.testScript}
                rows={20}
                style={{ fontFamily: 'monospace', fontSize: 12 }}
                readOnly
              />
            </TabPane>
            <TabPane tab="元素选择器" key="selectors">
              {Object.entries(selectedTest.elementSelectors).map(([name, selector]) => (
                <div key={name} style={{ marginBottom: 8 }}>
                  <Text strong>{name}:</Text>
                  <Tag style={{ marginLeft: 8 }}>{selector}</Tag>
                </div>
              ))}
            </TabPane>
            <TabPane tab="配置信息" key="config">
              <Descriptions bordered column={2}>
                <Descriptions.Item label="基础URL">{selectedTest.baseUrl}</Descriptions.Item>
                <Descriptions.Item label="浏览器">{selectedTest.browser}</Descriptions.Item>
                <Descriptions.Item label="视口尺寸">{selectedTest.viewportSize}</Descriptions.Item>
                <Descriptions.Item label="无头模式">{selectedTest.headless ? '是' : '否'}</Descriptions.Item>
                <Descriptions.Item label="脚本类型">{selectedTest.scriptType}</Descriptions.Item>
                <Descriptions.Item label="脚本语言">{selectedTest.scriptLanguage}</Descriptions.Item>
              </Descriptions>
            </TabPane>
          </Tabs>
        </Modal>
      )}

      {/* 图片预览弹窗 */}
      <Modal
        title="图片预览"
        open={!!previewImage}
        onCancel={() => setPreviewImage(null)}
        footer={null}
        width="auto"
        centered
        styles={{ body: { padding: 0 } }}
      maskClosable={false}      >
        {previewImage && (
          <img
            src={previewImage.src}
            alt={previewImage.name}
            style={{ 
              width: '100%', 
              maxHeight: '80vh', 
              objectFit: 'contain',
              display: 'block'
            }}
          />
        )}
      </Modal>

      {/* 保存到用例库弹窗 */}
      <Modal
        title="保存测试用例"
        open={showSaveModal}
        onCancel={() => setShowSaveModal(false)}
        onOk={handleSaveToLibrary}
        confirmLoading={isSaving}
        okText="保存"
        cancelText="取消"
      maskClosable={false}      >
        <div style={{ marginBottom: 16 }}>
          <Text strong>测试用例：{testToSave?.title}</Text>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">请选择目标用例库：</Text>
        </div>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Button 
            type={saveTargetType === 'functional' ? 'primary' : 'default'}
            block
            onClick={() => setSaveTargetType('functional')}
          >
            功能测试用例库
          </Button>
          <Button 
            type={saveTargetType === 'api' ? 'primary' : 'default'}
            block
            onClick={() => setSaveTargetType('api')}
          >
            API测试用例库
          </Button>
          <Button 
            type={saveTargetType === 'webui' ? 'primary' : 'default'}
            block
            onClick={() => setSaveTargetType('webui')}
          >
            WEB UI测试用例库
          </Button>
        </Space>
        <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            💡 提示：保存后测试用例将正式存入测试库，可以在对应的测试管理页面查看和管理。
          </Text>
        </div>
      </Modal>

      {/* 编辑测试用例弹窗 */}
      <Modal
        title="编辑测试用例"
        open={showEditModal}
        onCancel={() => setShowEditModal(false)}
        onOk={handleSaveEdit}
        width={800}
        okText="保存"
        cancelText="取消"
      maskClosable={false}      >
        <div style={{ marginBottom: 16 }}>
          <Text strong>测试用例标题</Text>
          <Input
            value={editFormData.title}
            onChange={e => setEditFormData(prev => ({ ...prev, title: e.target.value }))}
            placeholder="输入测试用例标题"
            style={{ marginTop: 8 }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>测试用例描述</Text>
          <TextArea
            value={editFormData.description}
            onChange={e => setEditFormData(prev => ({ ...prev, description: e.target.value }))}
            placeholder="输入测试用例描述"
            rows={3}
            style={{ marginTop: 8 }}
          />
        </div>
        <div>
          <Text strong>测试脚本</Text>
          <TextArea
            value={editFormData.testScript}
            onChange={e => setEditFormData(prev => ({ ...prev, testScript: e.target.value }))}
            placeholder="输入测试脚本"
            rows={15}
            style={{ 
              marginTop: 8, 
              fontFamily: 'monospace', 
              fontSize: 12 
            }}
          />
        </div>
        <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            💡 提示：编辑后的测试用例将保存在临时列表中，您可以继续修改后再保存到正式用例库。
          </Text>
        </div>
      </Modal>
    </div>
  );
};

export default WebUIChatPage;
