import React, { useState, useEffect } from 'react';
import {
  Card, Form, Input, Switch, Button, message, Divider, Typography,
  Space, Tag, InputNumber, Select, Row, Col, Tabs, Alert, Table, Modal
} from 'antd';
import {
  SaveOutlined, BellOutlined, PlayCircleOutlined,
  ExperimentOutlined, DesktopOutlined, GlobalOutlined, LoginOutlined, ThunderboltOutlined,
  SettingOutlined
} from '@ant-design/icons';
import axiosInstance from '../../api/axiosConfig';
import {
  projectSettingApi,
  ProjectSetting,
  NotificationConfig,
  ExecutionDefaults,
  TestDefaults
} from '../../api/projectExtApi';

const { Title, Text } = Typography;
const { TabPane } = Tabs;
interface ProjectSettingsProps {
  projectId: number;
  /** 初始激活的 Tab（默认 'exploration' 项目配置第一）。旧版登录入口的直达参数保留兼容 */
  initialTab?: string;
  /** 登录模块导入并验证成功后的回调（项目卡片入口用它刷新状态 Tag） */
  onLoginImported?: () => void;
  /** 项目配置保存成功后的回调（项目卡片入口用它刷新状态 Tag） */
  onWebConfigSaved?: () => void;
}

const ProjectSettings: React.FC<ProjectSettingsProps> = ({ projectId, initialTab, onLoginImported, onWebConfigSaved }) => {
  const [setting, setSetting] = useState<ProjectSetting | null>(null);
  const [loading, setLoading] = useState(false);
  const [explorationLoading, setExplorationLoading] = useState(false);
  const [notificationForm] = Form.useForm();
  const [executionForm] = Form.useForm();
  const [testForm] = Form.useForm();
  const [explorationForm] = Form.useForm();

  // ===== 环境管理（项目配置 Tab 内）=====
  const [environments, setEnvironments] = useState<{name: string; url: string}[]>([]);
  const [activeEnv, setActiveEnv] = useState('');
  const [envModalVisible, setEnvModalVisible] = useState(false);
  const [editingEnv, setEditingEnv] = useState<{name: string; url: string} | null>(null);
  const [envForm] = Form.useForm();

  // ===== 登录模块（项目级：同一项目同一套登录逻辑，跨版本共享）=====
  const [loginModuleContent, setLoginModuleContent] = useState('');
  const [hasLoginModule, setHasLoginModule] = useState(false);
  const [hasWebConfig, setHasWebConfig] = useState(false);
  const [loginImporting, setLoginImporting] = useState(false);
  const [loginImportError, setLoginImportError] = useState('');
  const [loginAuthLinkMsg, setLoginAuthLinkMsg] = useState(''); // API 鉴权自动联动结果文案
  // API 鉴权联动状态（登录模块导入时自动生成；持久展示，不依赖一次性提示）
  const [apiAuthInfo, setApiAuthInfo] = useState<any>(null);

  useEffect(() => {
    fetchSettings();
    checkLoginModule();
    loadApiAuthInfo();
  }, [projectId]);

  // 读取项目级 API 鉴权（联动产物），登录 Tab 展示状态
  const loadApiAuthInfo = async () => {
    try {
      const res = await projectSettingApi.getApiAuth(projectId);
      setApiAuthInfo(res?.api_auth || null);
    } catch { /* 后端不可达时保持现状 */ }
  };

  const checkLoginModule = async () => {
    try {
      const res = await axiosInstance.get('/web-ui-tests/check-login-module', {
        params: { project_id: projectId },
      });
      setHasLoginModule(!!res.data?.has_login_module);
      setHasWebConfig(!!res.data?.has_web_config);
    } catch { /* 后端不可达时保持现状 */ }
  };

  const fetchSettings = async () => {
    try {
      const data = await projectSettingApi.get(projectId);
      setSetting(data);

      // 加载已保存的登录模块业务流内容（项目级配置）
      const savedLogin = data.exploration_config?.login_module_content?.trim();
      if (savedLogin) setLoginModuleContent(savedLogin);

      // 初始化表单
      if (data.notification_config) {
        notificationForm.setFieldsValue(data.notification_config);
      }
      if (data.execution_defaults) {
        executionForm.setFieldsValue(data.execution_defaults);
      }
      if (data.test_defaults) {
        testForm.setFieldsValue({
          ...data.test_defaults,
          viewport_width: data.test_defaults.viewport?.width,
          viewport_height: data.test_defaults.viewport?.height,
        });
      }
      // 初始化项目配置（环境列表 + 表单字段）
      const webCfg = data.exploration_config?.web || {};
      const envs = (webCfg.environments || []).slice();
      if (!envs.length && webCfg.base_url) {
        envs.push({name: '默认环境', url: webCfg.base_url});
      }
      setEnvironments(envs);
      // active_environment 校验存在性（配置残留指向已删环境时回退首个环境）
      setActiveEnv(webCfg.active_environment && envs.some(e => e.name === webCfg.active_environment)
        ? webCfg.active_environment : (envs[0]?.name || ''));
      explorationForm.setFieldsValue({
        web_base_url: webCfg.active_environment
          ? (envs.find((e: any) => e.name === webCfg.active_environment)?.url || '')
          : (webCfg.base_url || ''),
        web_username: webCfg.username || '',
        web_password: webCfg.password || '',
      });
    } catch (error) {
      message.error('获取项目设置失败');
    }
  };

  const handleSaveNotification = async (values: any) => {
    setLoading(true);
    try {
      const config: NotificationConfig = {
        execution_completed: values.execution_completed,
        execution_failed: values.execution_failed,
        issue_created: values.issue_created,
        channels: values.channels,
      };
      await projectSettingApi.updateNotification(projectId, config);
      message.success('通知设置保存成功');
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveExecution = async (values: any) => {
    setLoading(true);
    try {
      const defaults: ExecutionDefaults = {
        parallel: values.parallel,
        retry: values.retry,
        timeout: values.timeout,
      };
      await projectSettingApi.updateExecutionDefaults(projectId, defaults);
      message.success('执行默认设置保存成功');
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveExploration = async (values: any) => {
    setExplorationLoading(true);
    try {
      const webCfg = setting?.exploration_config?.web || {};
      // 从当前 active environment 同步 base_url（环境管理模式下 base_url 由环境 URL 驱动）
      const activeEnvUrl = activeEnv ? (environments.find((e: any) => e.name === activeEnv)?.url || '') : '';
      const baseUrl = activeEnvUrl || values.web_base_url || webCfg.base_url || '';
      const config: Record<string, any> = {
        web: {
          ...webCfg,  // 保留 login_rules/convert_batch_size 等已保存字段
          base_url: baseUrl,
          username: values.web_username || '',
          password: values.web_password || '',
          // environments/active_environment 以本地实时 state 为准（环境管理即时落库，勿用旧 setting 快照覆盖）
          environments: environments.slice(),
          active_environment: activeEnv,
        },
      };
      await projectSettingApi.updateExplorationConfig(projectId, config);
      message.success('项目配置保存成功');
      fetchSettings();
      setHasWebConfig(Boolean(baseUrl.trim()));
      onWebConfigSaved?.();
    } catch (error) {
      message.error('保存失败');
    } finally {
      setExplorationLoading(false);
    }
  };

  // ===== 环境管理（保存 environments/active_environment 即时落库）=====
  const saveEnvToServer = async (envs: {name: string; url: string}[], active: string) => {
    const webCfg = setting?.exploration_config?.web || {};
    // base_url 同步（创建版本门控读 web.base_url：切换/删除环境后立即生效，无需再点「保存项目配置」）
    const activeUrl = active ? (envs.find(e => e.name === active)?.url || '') : '';
    await projectSettingApi.updateExplorationConfig(projectId, {
      web: { ...webCfg, environments: envs, active_environment: active, base_url: activeUrl || webCfg.base_url || '' },
    });
    // 同步登录 Tab 的「已完成项目配置」提示与项目卡片状态 Tag
    checkLoginModule();
    onWebConfigSaved?.();
  };

  const handleDeleteEnv = async (name: string) => {
    const updated = environments.filter(e => e.name !== name);
    const newActive = activeEnv === name ? (updated[0]?.name || '') : activeEnv;
    setEnvironments(updated);
    setActiveEnv(newActive);
    await saveEnvToServer(updated, newActive);
    message.success('环境已删除');
  };

  const handleEnvSave = async () => {
    const vals = envForm.getFieldsValue();
    if (!vals.env_name?.trim() || !vals.env_url?.trim()) return;
    const newEnv = {name: vals.env_name.trim(), url: vals.env_url.trim()};
    let updated: {name: string; url: string}[];
    if (editingEnv) {
      updated = environments.map(e => e.name === editingEnv.name ? newEnv : e);
    } else {
      updated = [...environments, newEnv];
    }
    const newActive = editingEnv ? (activeEnv === editingEnv.name ? newEnv.name : activeEnv) : (activeEnv || newEnv.name);
    setEnvironments(updated);
    setActiveEnv(newActive);
    await saveEnvToServer(updated, newActive);
    setEnvModalVisible(false);
    setEditingEnv(null);
    envForm.resetFields();
    message.success(editingEnv ? '环境已更新' : '环境已添加');
  };

  const handleEnvChange = (name: string) => {
    setActiveEnv(name);
    const env = environments.find(e => e.name === name);
    if (env) explorationForm.setFieldsValue({ web_base_url: env.url });
  };

  const handleSaveTest = async (values: any) => {
    setLoading(true);
    try {
      const defaults: TestDefaults = {
        browser: values.browser,
        viewport: {
          width: values.viewport_width,
          height: values.viewport_height,
        },
        headless: values.headless,
      };
      await projectSettingApi.updateTestDefaults(projectId, defaults);
      message.success('测试默认设置保存成功');
    } catch (error) {
      message.error('保存失败');
    } finally {
      setLoading(false);
    }
  };

  // ===== 登录模块：导入并验证（项目级入口）=====
  const handleImportLoginModule = async () => {
    setLoginImportError('');
    setLoginAuthLinkMsg('');
    if (!loginModuleContent.trim()) {
      message.warning('请先填写登录模块的业务流描述');
      return;
    }
    setLoginImporting(true);
    // 导入含真实浏览器探索+登录验证（约1-2分钟），axios 默认 120s 超时接近耗时上限，专用 600s
    message.info('正在导入登录模块并验证登录流程（含浏览器探索，约 1-2 分钟），请勿关闭页面…', 6);
    try {
      const { data } = await axiosInstance.post('/business-flow/import-login-module', {
        project_id: projectId,
        login_content: loginModuleContent.trim(),
      }, { timeout: 600000 });
      if (data.success) {
        // API 鉴权自动联动结果（登录模块导入成功后自动检测/验证 Swagger 登录接口）
        const authStatus = data.api_auth_auto?.status;
        const authMsg = authStatus === 'success'
          ? `；API 鉴权已自动联动验证通过（${data.api_auth_auto.login_url} → ${data.api_auth_auto.token_path}）`
          : authStatus === 'partial'
            ? `；API 鉴权已自动填充配置但验证未通过（${data.api_auth_auto.reason}），可到 Swagger Tab 手动测试`
            : authStatus === 'failed'
              ? `；API 鉴权自动联动失败（${data.api_auth_auto.reason}），可到 Swagger Tab 手动配置`
              : authStatus === 'skipped'
                ? `；API 鉴权自动联动跳过（${data.api_auth_auto.reason}）`
                : '';
        message.success(`登录模块验证成功！已固化业务流文档 + 生成UI用例 + 执行通过${authMsg}`, 8);
        setHasLoginModule(true);
        setLoginAuthLinkMsg(authMsg || '');
        loadApiAuthInfo(); // 联动产物已落库，刷新状态展示
        onLoginImported?.();
      } else {
        const errMsg = data.execution_result?.error || data.error || '验证未通过';
        message.warning(`登录模块验证失败：${errMsg}。请修改业务流描述后重试。`);
      }
    } catch (e: any) {
      const errDetail = e.response?.data?.message || e.response?.data?.detail || '登录模块导入失败，请修改后重试';
      setLoginImportError(errDetail);
      message.error(errDetail);
    } finally {
      setLoginImporting(false);
    }
  };

  return (
    <Card title="项目设置">
      <Tabs defaultActiveKey={initialTab || 'exploration'} type="card">
        <TabPane
          tab={
            <span>
              <GlobalOutlined /> 项目配置
            </span>
          }
          key="exploration"
        >
          <Alert type="info" showIcon style={{ marginBottom: 12 }}
            message="项目配置是创建版本的前置条件：请先配置目标环境 URL 与登录账号，再到「登录模块」页签导入并验证登录流程。" />
          <Form
            form={explorationForm}
            layout="vertical"
            onFinish={handleSaveExploration}
          >
            <Form.Item label="目标环境" required>
              <div style={{ display: 'flex', gap: 8 }}>
                <Select
                  value={activeEnv || undefined}
                  onChange={handleEnvChange}
                  placeholder="选择环境"
                  style={{ flex: 1 }}
                >
                  {environments.map(env => (
                    <Select.Option key={env.name} value={env.name}>{env.name} — {env.url}</Select.Option>
                  ))}
                </Select>
                <Button icon={<SettingOutlined />} onClick={() => { setEditingEnv(null); envForm.resetFields(); setEnvModalVisible(true); }}>管理环境</Button>
              </div>
            </Form.Item>
            <Form.Item name="web_base_url" hidden><Input /></Form.Item>
            <Title level={5}><DesktopOutlined style={{ marginRight: 6 }} />WEB 端</Title>
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="web_username" label="登录用户名" rules={[{ required: true, message: '请输入登录用户名' }]}>
                  <Input placeholder="手机号 / 用户名" autoComplete="new-password" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="web_password" label="登录密码" rules={[{ required: true, message: '请输入登录密码' }]}>
                  <Input.Password placeholder="密码" autoComplete="new-password" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={explorationLoading} icon={<SaveOutlined />}>
                保存项目配置
              </Button>
            </Form.Item>
          </Form>

          {/* ===== 环境管理弹窗（项目配置 Tab 内）===== */}
          <Modal title="管理环境" open={envModalVisible}
            onCancel={() => setEnvModalVisible(false)} footer={null} width={560}>
            {environments.length > 0 && (
              <Table dataSource={environments.map((e, i) => ({...e, key: i}))} pagination={false} size="small"
                style={{ marginBottom: 16 }}
                columns={[
                  { title: '名称', dataIndex: 'name', width: 120 },
                  { title: 'URL', dataIndex: 'url', ellipsis: true },
                  { title: '', width: 100, render: (_: any, r: any) => (
                    <Space size={2}>
                      <Button type="link" size="small" onClick={() => { setEditingEnv(r); envForm.setFieldsValue(r); }}>编辑</Button>
                      <Button type="link" size="small" danger onClick={() => handleDeleteEnv(r.name)}>删除</Button>
                    </Space>
                  )},
                ]}
              />
            )}
            <Divider>{editingEnv ? '编辑环境' : '添加环境'}</Divider>
            <Form form={envForm} layout="vertical">
              <Row gutter={12} align="middle">
                <Col span={6}>
                  <Form.Item name="env_name" label="名称" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                    <Input placeholder="环境名称" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="env_url" label="URL" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                    <Input placeholder="https://..." />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label=" " style={{ marginBottom: 0 }}>
                    <Space>
                      <Button type="primary" onClick={handleEnvSave}>{editingEnv ? '保存' : '添加'}</Button>
                      {editingEnv && <Button onClick={() => { setEditingEnv(null); envForm.resetFields(); }}>取消编辑</Button>}
                    </Space>
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          </Modal>
        </TabPane>

        <TabPane
          tab={
            <span>
              <LoginOutlined /> 登录模块
            </span>
          }
          key="login_module"
        >
          <Space style={{ marginBottom: 8 }}>
            <Tag color="gold">🔑 前置</Tag>
            <Text strong style={{ fontSize: 13 }}>登录模块（项目级）</Text>
            {hasLoginModule ? <Tag color="success">已导入验证</Tag> : <Tag color="warning">待导入验证</Tag>}
            {hasLoginModule && <Text type="success" style={{ fontSize: 12 }}>✅ 登录验证已通过</Text>}
          </Space>

          <Alert type="info" showIcon style={{ marginBottom: 12 }}
            message="登录模块是项目级资产：同一项目下所有版本共享同一套登录逻辑（UI 用例执行与 API 用例鉴权均复用）。根据实际系统登录流程修改以下描述，点击「导入并验证」确认登录可用，验证通过后才会固化保存。" />

          {!hasWebConfig && (
            <Alert type="warning" showIcon style={{ marginBottom: 8 }}
              message="尚未完成项目配置（目标系统 URL）。请先在「项目配置」页签填写目标环境 URL 与登录账号，再进行登录模块导入。" />
          )}
          {!hasLoginModule && (
            <Alert type="warning" showIcon style={{ marginBottom: 8 }}
              message="未检测到已验证的登录模块。导入并验证通过前，无法创建版本，版本页面的「导入 业务流/需求」等功能也将被拦截。" />
          )}
          {loginImportError && (
            <Alert type="error" showIcon closable style={{ marginBottom: 8 }}
              message="导入失败"
              description={loginImportError}
              onClose={() => setLoginImportError('')} />
          )}
          {loginAuthLinkMsg && (
            <Alert type="success" showIcon style={{ marginBottom: 8 }} message={`API 鉴权自动联动：${loginAuthLinkMsg.replace(/^；/, '')}`} />
          )}

          {/* ===== API 鉴权联动状态（登录模块导入时自动生成，可随时查看） ===== */}
          {apiAuthInfo ? (
            <Alert type={apiAuthInfo.verified ? 'success' : 'warning'} showIcon style={{ marginBottom: 8 }}
              message={<span>
                {apiAuthInfo.verified
                  ? <>✅ <Text strong>API 鉴权已配置并验证通过</Text></>
                  : <>⚠️ <Text strong>API 鉴权待验证</Text></>}
                {apiAuthInfo.capture_source === 'browser_login' && (
                  <Tag color="geekblue" style={{ marginLeft: 8 }}>由登录模块联动生成</Tag>
                )}
                <div style={{ marginTop: 4, fontSize: 12 }}>
                  登录接口：<Text code>{apiAuthInfo.login_method || 'POST'} {apiAuthInfo.login_url || '（未配置）'}</Text>
                  {apiAuthInfo.token_path && <>　Token 路径：<Text code>{apiAuthInfo.token_path}</Text></>}
                </div>
                {!apiAuthInfo.verified && (
                  <div style={{ marginTop: 4, fontSize: 12 }}>可在版本页 Swagger 导入页签手动补位：点击「测试鉴权」验证，或修改配置后保存。</div>
                )}
              </span>} />
          ) : hasLoginModule ? (
            <Alert type="warning" showIcon style={{ marginBottom: 8 }}
              message="登录模块已导入，但未联动生成 API 鉴权（未捕获到登录接口且无 Swagger 候选）。可到版本页 Swagger 导入页签手动配置，或重新导入登录模块。" />
          ) : null}

          <Input.TextArea
            rows={8}
            value={loginModuleContent}
            onChange={e => { setLoginModuleContent(e.target.value); setLoginImportError(''); }}
            placeholder="请描述系统登录流程（每步一行）..."
            style={{ fontFamily: 'monospace', fontSize: 12, marginBottom: 12 }}
          />

          <Button type="primary" icon={<ThunderboltOutlined />} loading={loginImporting}
            onClick={handleImportLoginModule}>
            导入并验证
          </Button>
        </TabPane>

        <TabPane
          tab={
            <span>
              <ExperimentOutlined /> 测试默认配置
            </span>
          }
          key="test"
        >
          <Form
            form={testForm}
            layout="vertical"
            onFinish={handleSaveTest}
            initialValues={{
              browser: 'chromium',
              viewport_width: 1920,
              viewport_height: 1080,
              headless: true,
            }}
          >
            <Title level={5}>浏览器配置</Title>

            <Form.Item
              name="browser"
              label="默认浏览器"
              rules={[{ required: true }]}
            >
              <Select placeholder="选择浏览器">
                <Select.Option value="chromium">
                  <Space>
                    <DesktopOutlined /> Chromium
                  </Space>
                </Select.Option>
                <Select.Option value="firefox">
                  <Space>
                    <DesktopOutlined /> Firefox
                  </Space>
                </Select.Option>
                <Select.Option value="webkit">
                  <Space>
                    <DesktopOutlined /> WebKit
                  </Space>
                </Select.Option>
                <Select.Option value="chrome">
                  <Space>
                    <DesktopOutlined /> Chrome
                  </Space>
                </Select.Option>
                <Select.Option value="edge">
                  <Space>
                    <DesktopOutlined /> Edge
                  </Space>
                </Select.Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="headless"
              valuePropName="checked"
              label="无头模式"
            >
              <Switch checkedChildren="启用" unCheckedChildren="禁用" />
            </Form.Item>

            <Divider />

            <Title level={5}>视口配置</Title>

            <Row gutter={24}>
              <Col span={12}>
                <Form.Item
                  name="viewport_width"
                  label="宽度(px)"
                  rules={[{ required: true }, { type: 'number', min: 320, max: 3840 }]}
                >
                  <InputNumber style={{ width: '100%' }} min={320} max={3840} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="viewport_height"
                  label="高度(px)"
                  rules={[{ required: true }, { type: 'number', min: 240, max: 2160 }]}
                >
                  <InputNumber style={{ width: '100%' }} min={240} max={2160} />
                </Form.Item>
              </Col>
            </Row>

            <Space style={{ marginBottom: 16 }}>
              <Tag color="blue" onClick={() => testForm.setFieldsValue({ viewport_width: 1920, viewport_height: 1080 })}>
                1920x1080 (桌面)
              </Tag>
              <Tag color="blue" onClick={() => testForm.setFieldsValue({ viewport_width: 1366, viewport_height: 768 })}>
                1366x768 (笔记本)
              </Tag>
              <Tag color="blue" onClick={() => testForm.setFieldsValue({ viewport_width: 390, viewport_height: 844 })}>
                390x844 (iPhone)
              </Tag>
              <Tag color="blue" onClick={() => testForm.setFieldsValue({ viewport_width: 768, viewport_height: 1024 })}>
                768x1024 (iPad)
              </Tag>
            </Space>

            <Text type="secondary">
              这些设置将作为项目下所有WebUI测试的默认值。
            </Text>

            <Form.Item style={{ marginTop: 16 }}>
              <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
                保存测试配置
              </Button>
            </Form.Item>
          </Form>
        </TabPane>

        <TabPane
          tab={
            <span>
              <PlayCircleOutlined /> 执行默认配置
            </span>
          }
          key="execution"
        >
          <Form
            form={executionForm}
            layout="vertical"
            onFinish={handleSaveExecution}
            initialValues={{
              parallel: 4,
              retry: 1,
              timeout: 3600,
            }}
          >
            <Row gutter={24}>
              <Col span={8}>
                <Form.Item
                  name="parallel"
                  label="并行执行数"
                  rules={[{ required: true }, { type: 'number', min: 1, max: 20 }]}
                >
                  <InputNumber style={{ width: '100%' }} min={1} max={20} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="retry"
                  label="重试次数"
                  rules={[{ required: true }, { type: 'number', min: 0, max: 5 }]}
                >
                  <InputNumber style={{ width: '100%' }} min={0} max={5} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="timeout"
                  label="超时时间(秒)"
                  rules={[{ required: true }, { type: 'number', min: 60, max: 86400 }]}
                >
                  <InputNumber style={{ width: '100%' }} min={60} max={86400} />
                </Form.Item>
              </Col>
            </Row>

            <Text type="secondary">
              这些设置将作为项目下所有测试执行的默认值，创建执行时可覆盖。
            </Text>

            <Form.Item style={{ marginTop: 16 }}>
              <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
                保存执行配置
              </Button>
            </Form.Item>
          </Form>
        </TabPane>

        <TabPane
          tab={
            <span>
              <BellOutlined /> 通知设置
            </span>
          }
          key="notification"
        >
          <Form
            form={notificationForm}
            layout="vertical"
            onFinish={handleSaveNotification}
            initialValues={{
              execution_completed: true,
              execution_failed: true,
              issue_created: true,
              channels: ['email'],
            }}
          >
            <Title level={5}>通知触发条件</Title>

            <Form.Item
              name="execution_completed"
              valuePropName="checked"
              label="测试执行完成"
            >
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>

            <Form.Item
              name="execution_failed"
              valuePropName="checked"
              label="测试执行失败"
            >
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>

            <Form.Item
              name="issue_created"
              valuePropName="checked"
              label="问题创建"
            >
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>

            <Divider />

            <Title level={5}>通知渠道</Title>

            <Form.Item
              name="channels"
              label="启用渠道"
              rules={[{ required: true, message: '请至少选择一个通知渠道' }]}
            >
              <Select mode="multiple" placeholder="选择通知渠道">
                <Select.Option value="email">邮件</Select.Option>
                <Select.Option value="feishu">飞书</Select.Option>
                <Select.Option value="dingtalk">钉钉</Select.Option>
                <Select.Option value="wecom">企业微信</Select.Option>
              </Select>
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
                保存通知设置
              </Button>
            </Form.Item>
          </Form>
        </TabPane>
      </Tabs>
    </Card>
  );
};

export default ProjectSettings;
