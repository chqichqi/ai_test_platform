import React, { useState, useEffect } from 'react';
import {
  Card,
  Typography,
  Button,
  Table,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  message,
  Row,
  Col,
  Divider,
  Tabs,
  Popconfirm,
  Tooltip,
  Progress,
  Alert,
  Statistic
} from 'antd';
import {
  PlayCircleOutlined,
  PlusOutlined,
  SearchOutlined,
  EyeOutlined,
  DownloadOutlined,
  CodeOutlined,
  RobotOutlined,
  ChromeOutlined,
  ReloadOutlined,
  DeleteOutlined,
  CopyOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import axiosInstance from '../../api/axiosConfig';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;

const API_BASE_URL = '/web-ui-tests';

interface WebUITestCase {
  id: string;
  test_case_id: string;
  base_url: string;
  browser: string;
  viewport_size: string;
  viewport_width?: number;
  viewport_height?: number;
  headless: boolean;
  script_type: string;
  script_language: string;
  test_script?: string;
  element_selectors?: Record<string, string>;
  generation_mode?: 'linear' | 'pom_data_driven';
  test_data?: any;
  test_case?: { name: string; module: string };
  created_at?: string;
  updated_at?: string;
  // 后端无对应列，历史遗留兼容（渲染时兜底 '-')
  description?: string;
  title?: string;
  status?: string;
  lastExecuted?: string;
  precondition_plan?: any;
}

interface FunctionalTestCase {
  id: string;
  title: string;
  description: string;
  testType: string;
  testSteps: any[];
  priority: string;
  createdAt: string;
}

interface ConversionRequest {
  functional_test_case_id: string;
  base_url: string;
  browser: string;
  viewport_size: string;
  headless: boolean;
  generate_element_selectors: boolean;
  generate_test_script: boolean;
  script_type: string;
  script_language: string;
}

const WebUITestPage: React.FC = () => {
  const [webUiTestCases, setWebUiTestCases] = useState<WebUITestCase[]>([]);
  const [functionalTestCases, setFunctionalTestCases] = useState<FunctionalTestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversionLoading, setConversionLoading] = useState(false);
  const [executionLoading, setExecutionLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [selectedTests, setSelectedTests] = useState<React.Key[]>([]);
  const [conversionModalVisible, setConversionModalVisible] = useState(false);
  const [scriptModalVisible, setScriptModalVisible] = useState(false);
  const [scriptContent, setScriptContent] = useState('');
  const [conversionForm] = Form.useForm();
  // 批量执行结果反馈（成功/失败汇总 + 失败明细）
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [execResultVisible, setExecResultVisible] = useState(false);
  const [execResult, setExecResult] = useState<{
    total: number; ok: number; skipped: number; fail: number; results: any[];
  } | null>(null);

  // 浏览器选项
  const browserOptions = [
    { value: 'chrome', label: 'Chrome' },
    { value: 'firefox', label: 'Firefox' },
    { value: 'safari', label: 'Safari' },
    { value: 'edge', label: 'Edge' },
    { value: 'webkit', label: 'WebKit' }
  ];

  // 视口尺寸选项
  const viewportOptions = [
    { value: '1920x1080', label: '桌面 1920x1080' },
    { value: '1366x768', label: '桌面 1366x768' },
    { value: '1536x864', label: '桌面 1536x864' },
    { value: '768x1024', label: '平板 768x1024' },
    { value: '810x1080', label: '平板 810x1080' },
    { value: '375x667', label: '移动端 375x667' },
    { value: '414x896', label: '移动端 414x896' },
    { value: '360x640', label: '移动端 360x640' }
  ];

  // 脚本类型选项
  const scriptTypeOptions = [
    { value: 'playwright', label: 'Playwright' },
    { value: 'selenium', label: 'Selenium' },
    { value: 'puppeteer', label: 'Puppeteer' }
  ];

  // 脚本语言选项
  const scriptLanguageOptions = [
    { value: 'python', label: 'Python' },
    { value: 'javascript', label: 'JavaScript' },
    { value: 'typescript', label: 'TypeScript' },
    { value: 'java', label: 'Java' }
  ];

  // 加载WEB UI测试用例
  const loadWebUITestCases = async () => {
    setLoading(true);
    try {
      const response = await axiosInstance.get(`${API_BASE_URL}/test-cases`);
      setWebUiTestCases(response.data.items || []);
    } catch (error) {
      console.error('加载WEB UI测试用例失败:', error);
      message.error('加载WEB UI测试用例失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载可转换的功能测试用例
  const loadFunctionalTestCases = async () => {
    try {
      const response = await axiosInstance.get(`${API_BASE_URL}/convertible-functional-tests`);
      setFunctionalTestCases(response.data.items || []);
    } catch (error) {
      console.error('加载功能测试用例失败:', error);
      // 模拟数据
      setFunctionalTestCases([
        {
          id: '1',
          title: '用户登录功能测试',
          description: '测试用户登录流程',
          testType: 'FUNCTIONAL',
          testSteps: [
            { step: 1, action: '访问登录页面', expected: '页面正常加载' },
            { step: 2, action: '输入用户名和密码', expected: '输入框可正常输入' },
            { step: 3, action: '点击登录按钮', expected: '登录成功，跳转到首页' }
          ],
          priority: 'high',
          createdAt: '2025-03-22'
        },
        {
          id: '2',
          title: '商品搜索功能测试',
          description: '测试商品搜索功能',
          testType: 'FUNCTIONAL',
          testSteps: [
            { step: 1, action: '访问商品列表页面', expected: '页面正常加载' },
            { step: 2, action: '在搜索框输入关键词', expected: '输入框可正常输入' },
            { step: 3, action: '点击搜索按钮', expected: '显示相关商品列表' }
          ],
          priority: 'medium',
          createdAt: '2025-03-21'
        }
      ]);
    }
  };

  // 初始化加载
  useEffect(() => {
    loadWebUITestCases();
    loadFunctionalTestCases();
  }, []);

  // 转换功能测试为WEB UI测试
  const handleConvert = async (values: any) => {
    setConversionLoading(true);
    try {
      const conversionRequest: ConversionRequest = {
        functional_test_case_id: values.functional_test_case_id,
        base_url: values.base_url,
        browser: values.browser,
        viewport_size: values.viewport_size,
        headless: values.headless,
        generate_element_selectors: values.generate_element_selectors,
        generate_test_script: values.generate_test_script,
        script_type: values.script_type,
        script_language: values.script_language
      };

      const response = await axiosInstance.post(`${API_BASE_URL}/convert-from-functional`, conversionRequest);
      
      if (response.data.success) {
        message.success('转换成功！');
        setConversionModalVisible(false);
        conversionForm.resetFields();
        loadWebUITestCases();
        
        // 显示生成结果
        Modal.success({
          title: '转换成功',
          content: (
            <div>
              <p>已成功生成WEB UI测试用例</p>
              {response.data.test_script && (
                <Button
                  type="link"
                  icon={<CodeOutlined />}
                  onClick={() => {
                    setScriptContent(response.data.test_script);
                    setScriptModalVisible(true);
                  }}
                >
                  查看生成的脚本
                </Button>
              )}
            </div>
          )
        });
      } else {
        message.error(`转换失败: ${response.data.errors?.join(', ')}`);
      }
    } catch (error: any) {
      console.error('转换失败:', error);
      message.error(`转换失败: ${error.response?.data?.detail || error.message}`);
    } finally {
      setConversionLoading(false);
    }
  };

  // 执行WEB UI测试
  const handleExecute = async (testCaseId: string) => {
    setExecutionLoading(true);
    try {
      const response = await axiosInstance.post(`${API_BASE_URL}/execute`, {
        web_ui_test_case_id: testCaseId,
        environment: 'development'
      });
      
      if (response.data.status === 'completed') {
        message.success('测试执行成功！');
        loadWebUITestCases();
      } else {
        message.error(response.data.error || '测试执行失败');
      }
    } catch (error: any) {
      console.error('执行失败:', error);
      message.error(`执行失败: ${error.response?.data?.detail || error.message}`);
    } finally {
      setExecutionLoading(false);
    }
  };

  // 批量执行选中用例（有头+复用：浏览器开一次、登录一次、依次执行）
  // 执行完成后弹出结果反馈：成功/失败汇总 + 失败明细
  const handleBatchExecute = async () => {
    if (selectedTests.length === 0) {
      message.warning('请先勾选要执行的测试用例');
      return;
    }
    Modal.confirm({
      title: '批量执行（有头 + 复用）',
      content: `浏览器打开一次，登录后依次执行 ${selectedTests.length} 条用例。`,
      okText: '开始执行',
      onOk: async () => {
        setBatchExecuting(true);
        try {
          const response = await axiosInstance.post(
            `${API_BASE_URL}/execute-batch`,
            { ids: selectedTests as string[] },
            { params: { headless: false }, timeout: 7200000 }
          );
          setExecResult(response.data);
          setExecResultVisible(true);
          message.success(`执行完成: ${response.data.ok} 成功, ${response.data.skipped || 0} 跳过, ${response.data.fail} 失败`);
        } catch (error: any) {
          message.error(`执行失败: ${error.response?.data?.detail || error.message}`);
        } finally {
          setBatchExecuting(false);
          loadWebUITestCases();
        }
      },
    });
  };

  // 删除WEB UI测试用例
  const handleDelete = async (testCaseId: string) => {
    try {
      await axiosInstance.delete(`${API_BASE_URL}/test-cases/${testCaseId}`);
      message.success('删除成功');
      loadWebUITestCases();
    } catch (error: any) {
      const detail = error.response?.data?.detail || '';
      if (error.response?.status === 409) {
        message.warning(detail || '该UI用例已添加到执行中心，请先从执行中心移除');
      } else {
        message.error(`删除失败: ${detail || error.message}`);
      }
    }
  };

  // 表格列定义
  const columns: ColumnsType<WebUITestCase> = [
    {
      title: '测试用例',
      dataIndex: 'test_case',
      key: 'test_case',
      render: (_, record) => (
        <Space direction="vertical" size={2}>
          <Text strong>{record.test_case?.name || record.test_data?.title || '-'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.description}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <ChromeOutlined /> {record.browser} | {record.viewport_size}
          </Text>
        </Space>
      ),
    },
    {
      title: '浏览器/视口',
      dataIndex: 'browser',
      key: 'browser',
      render: (browser, record) => (
        <Space direction="vertical" size={2}>
          <Tag color="blue">{browser}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.viewport_size}</Text>
        </Space>
      ),
    },
    {
      title: '脚本类型',
      dataIndex: 'script_type',
      key: 'script_type',
      render: (scriptType) => (
        <Tag color="purple">{scriptType}</Tag>
      ),
    },
    {
      title: '前置条件',
      dataIndex: 'test_data',
      key: 'test_data',
      render: (testData) => {
        const text = testData?.preconditions || '';
        const plan = testData?.precondition_plan;
        const dynamic = plan?.conditions?.find((c: any) => c?.type === 'dynamic_data');
        return text ? (
          <Space direction="vertical" size={2}>
            <Text type="secondary" ellipsis={{ tooltip: text }} style={{ maxWidth: 200 }}>{text.replace(/\n/g, ' / ')}</Text>
            {dynamic && <Tag color="orange">动态数据为空时跳过</Tag>}
          </Space>
        ) : <Text type="secondary">-</Text>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const statusMap = {
          generated: { color: 'blue', text: '已生成', icon: <CodeOutlined /> },
          executed: { color: 'green', text: '已执行', icon: <CheckCircleOutlined /> },
          failed: { color: 'red', text: '执行失败', icon: <ExclamationCircleOutlined /> },
          pending: { color: 'gray', text: '待执行', icon: <ClockCircleOutlined /> }
        };
        const config = statusMap[status as keyof typeof statusMap] || { color: 'default', text: status || '-' };
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        );
      },
    },
    {
      title: '最后执行',
      dataIndex: 'lastExecuted',
      key: 'lastExecuted',
      render: (lastExecuted) => lastExecuted || '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="执行测试">
            <Button
              type="link"
              icon={<PlayCircleOutlined />}
              size="small"
              onClick={() => handleExecute(record.id)}
              loading={executionLoading}
            />
          </Tooltip>
          <Tooltip title="查看脚本">
            <Button
              type="link"
              icon={<EyeOutlined />}
              size="small"
              onClick={() => {
                if (record.generation_mode === 'pom_data_driven' && record.test_data) {
                  setScriptContent(JSON.stringify(record.test_data, null, 2));
                } else {
                  setScriptContent(record.test_script || '// 无脚本内容');
                }
                setScriptModalVisible(true);
              }}
            />
          </Tooltip>
          <Tooltip title="下载脚本">
            <Button
              type="link"
              icon={<DownloadOutlined />}
              size="small"
              onClick={() => {
                const blob = new Blob([record.test_script || ''], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.download = `${record.test_case?.name || record.test_case_id}_${record.script_type}.${record.script_language}`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此测试用例吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button type="link" icon={<DeleteOutlined />} size="small" danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 过滤后的测试用例
  const filteredTestCases = webUiTestCases.filter(testCase =>
    (testCase.test_case?.name || '').toLowerCase().includes(searchText.toLowerCase()) ||
    (testCase.description || '').toLowerCase().includes(searchText.toLowerCase()) ||
    (testCase.browser || '').toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div>
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              <RobotOutlined /> WEB UI自动化测试
            </Title>
            <Paragraph type="secondary">
              将功能测试用例自动转换为WEB UI自动化测试用例，支持Playwright、Selenium等框架
            </Paragraph>
          </div>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setConversionModalVisible(true)}
            >
              功能用例AI转化为UI用例
            </Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleBatchExecute}
              loading={batchExecuting}
              disabled={selectedTests.length === 0}
              style={{ background: '#f9f0ff', borderColor: '#d3adf7', color: '#722ed1' }}
            >
              批量执行
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadWebUITestCases}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        </Space>

        <Alert
          message="WEB UI自动化测试模块"
          description="此模块可以自动将功能测试用例转换为可执行的WEB UI自动化测试脚本。系统会分析功能测试步骤，生成对应的元素选择器和测试脚本。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Tabs defaultActiveKey="list">
          <TabPane tab="测试用例列表" key="list">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Input
                    placeholder="搜索测试用例（标题、描述、浏览器）"
                    prefix={<SearchOutlined />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    allowClear
                  />
                </Col>
                <Col span={4}>
                  <Select
                    placeholder="脚本类型"
                    style={{ width: '100%' }}
                    allowClear
                  >
                    {scriptTypeOptions.map(opt => (
                      <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                    ))}
                  </Select>
                </Col>
                <Col span={4}>
                  <Select
                    placeholder="浏览器"
                    style={{ width: '100%' }}
                    allowClear
                  >
                    {browserOptions.map(opt => (
                      <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                    ))}
                  </Select>
                </Col>
                <Col span={4}>
                  <Select
                    placeholder="状态"
                    style={{ width: '100%' }}
                    allowClear
                  >
                    <Option value="generated">已生成</Option>
                    <Option value="executed">已执行</Option>
                    <Option value="failed">执行失败</Option>
                    <Option value="pending">待执行</Option>
                  </Select>
                </Col>
              </Row>

              <Table
                columns={columns}
                dataSource={filteredTestCases}
                rowKey="id"
                loading={loading}
                pagination={{ pageSize: 10 }}
                rowSelection={{
                  selectedRowKeys: selectedTests,
                  onChange: (keys) => setSelectedTests(keys),
                }}
              />
            </Space>
          </TabPane>
          <TabPane tab="转换统计" key="stats">
            <Row gutter={16}>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="总测试用例"
                    value={webUiTestCases.length}
                    prefix={<CodeOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="已执行"
                    value={webUiTestCases.filter(t => t.status === 'executed').length}
                    prefix={<CheckCircleOutlined />}
                    valueStyle={{ color: '#3f8600' }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="成功率"
                    value={webUiTestCases.length > 0 
                      ? (webUiTestCases.filter(t => t.status === 'executed').length / webUiTestCases.length * 100).toFixed(1)
                      : 0
                    }
                    suffix="%"
                    prefix={<RobotOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="脚本类型分布"
                    value="Playwright"
                    prefix={<ChromeOutlined />}
                  />
                  <Progress
                    percent={webUiTestCases.length > 0
                      ? (webUiTestCases.filter(t => t.script_type === 'playwright').length / webUiTestCases.length * 100)
                      : 0
                    }
                    size="small"
                  />
                </Card>
              </Col>
            </Row>
          </TabPane>
        </Tabs>
      </Card>

      {/* 转换功能测试弹窗 */}
      <Modal
        maskClosable={false}
        title="功能用例AI转化为UI用例"
        open={conversionModalVisible}
        onCancel={() => setConversionModalVisible(false)}
        footer={null}
        width={800}
      >
        <Form
          form={conversionForm}
          layout="vertical"
          onFinish={handleConvert}
          initialValues={{
            browser: 'chrome',
            viewport_size: '1920x1080',
            headless: true,
            generate_element_selectors: true,
            generate_test_script: true,
            script_type: 'playwright',
            script_language: 'python'
          }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="functional_test_case_id"
                label="选择功能测试用例"
                rules={[{ required: true, message: '请选择功能测试用例' }]}
              >
                <Select placeholder="选择要转换的功能测试用例" showSearch>
                  {functionalTestCases.map(testCase => (
                    <Option key={testCase.id} value={testCase.id}>
                      {testCase.title} ({testCase.priority})
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="base_url"
                label="基础URL"
                rules={[
                  { required: true, message: '请输入基础URL' },
                  { pattern: /^https?:\/\/.+/, message: '请输入有效的URL（以http://或https://开头）' }
                ]}
              >
                <Input placeholder="例如：https://example.com" />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left">浏览器配置</Divider>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="browser" label="浏览器类型">
                <Select>
                  {browserOptions.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="viewport_size" label="视口尺寸">
                <Select>
                  {viewportOptions.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="headless" label="无头模式" valuePropName="checked">
                <Switch checkedChildren="开启" unCheckedChildren="关闭" defaultChecked />
              </Form.Item>
            </Col>
          </Row>

          <Divider orientation="left">脚本生成配置</Divider>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="script_type" label="脚本类型">
                <Select>
                  {scriptTypeOptions.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="script_language" label="脚本语言">
                <Select>
                  {scriptLanguageOptions.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="generate_element_selectors" label="生成元素选择器" valuePropName="checked">
                <Switch checkedChildren="生成" unCheckedChildren="不生成" defaultChecked />
              </Form.Item>
              <Text type="secondary">自动从测试步骤中提取元素并生成选择器</Text>
            </Col>
            <Col span={12}>
              <Form.Item name="generate_test_script" label="生成测试脚本" valuePropName="checked">
                <Switch checkedChildren="生成" unCheckedChildren="不生成" defaultChecked />
              </Form.Item>
              <Text type="secondary">生成可执行的测试脚本（Playwright/Selenium）</Text>
            </Col>
          </Row>

          <Divider />
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setConversionModalVisible(false)}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={conversionLoading}>
                开始转换
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 脚本查看弹窗 */}
      <Modal
        maskClosable={false}
        title="测试脚本"
        open={scriptModalVisible}
        onCancel={() => setScriptModalVisible(false)}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={() => {
            navigator.clipboard.writeText(scriptContent);
            message.success('脚本已复制到剪贴板');
          }}>
            复制
          </Button>,
          <Button key="download" icon={<DownloadOutlined />} onClick={() => {
            const blob = new Blob([scriptContent], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `web_ui_test_script.${scriptContent.includes('def ') ? 'py' : 'js'}`;
            a.click();
            URL.revokeObjectURL(url);
          }}>
            下载
          </Button>,
          <Button key="close" onClick={() => setScriptModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={900}
      >
        <TextArea
          value={scriptContent}
          rows={20}
          style={{ fontFamily: 'monospace', fontSize: 12 }}
          readOnly
        />
      </Modal>

      {/* 批量执行结果反馈弹窗：成功/失败汇总 + 失败明细 */}
      <Modal
        title="批量执行结果"
        open={execResultVisible}
        onCancel={() => setExecResultVisible(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setExecResultVisible(false)}>
            关闭
          </Button>
        ]}
        width={760}
      >
        {execResult && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Row gutter={16}>
              <Col span={6}>
                <Card>
                  <Statistic title="用例总数" value={execResult.total} />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="成功"
                    value={execResult.ok}
                    valueStyle={{ color: '#3f8600' }}
                    prefix={<CheckCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic title="跳过" value={execResult.skipped || 0} />
                </Card>
              </Col>
              <Col span={6}>
                <Card>
                  <Statistic
                    title="失败"
                    value={execResult.fail}
                    valueStyle={{ color: '#cf1322' }}
                    prefix={<ExclamationCircleOutlined />}
                  />
                </Card>
              </Col>
            </Row>
            {execResult.fail > 0 && (
              <>
                <Divider orientation="left">失败明细</Divider>
                <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                  {(execResult.results || [])
                    .filter(r => r.status !== 'completed')
                    .map((r, i) => {
                      const tc = webUiTestCases.find(c => c.id === r.test_case_id);
                      return (
                        <Alert
                          key={i}
                          type="error"
                          showIcon
                          message={tc ? tc.title : `用例 ${r.test_case_id}`}
                          description={r.error ? String(r.error).slice(0, 300) : '未知错误'}
                          style={{ marginBottom: 8 }}
                        />
                      );
                    })}
                </div>
              </>
            )}
            {execResult.fail === 0 && (
              <Alert type="success" showIcon message={`执行完成：${execResult.ok} 成功，${execResult.skipped || 0} 跳过`} />
            )}
          </Space>
        )}
      </Modal>
    </div>
  );
};



export default WebUITestPage;