import React, { useState, useEffect } from 'react';
import {
  Card, Form, Input, Switch, Button, message, Divider, Typography,
  Space, Tag, InputNumber, Select, Row, Col, Tabs
} from 'antd';
import {
  SaveOutlined, BellOutlined, PlayCircleOutlined,
  ExperimentOutlined, DesktopOutlined, GlobalOutlined
} from '@ant-design/icons';
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
}

const ProjectSettings: React.FC<ProjectSettingsProps> = ({ projectId }) => {
  const [setting, setSetting] = useState<ProjectSetting | null>(null);
  const [loading, setLoading] = useState(false);
  const [explorationLoading, setExplorationLoading] = useState(false);
  const [notificationForm] = Form.useForm();
  const [executionForm] = Form.useForm();
  const [testForm] = Form.useForm();
  const [explorationForm] = Form.useForm();

  useEffect(() => {
    fetchSettings();
  }, [projectId]);

  const fetchSettings = async () => {
    try {
      const data = await projectSettingApi.get(projectId);
      setSetting(data);

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
      // 初始化项目配置
      const webCfg = data.exploration_config?.web || {};
      explorationForm.setFieldsValue({
        web_base_url: webCfg.base_url || '',
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
      const loginRules = webCfg.login_rules || {};

      const config: Record<string, any> = {
        web: {
          base_url: values.web_base_url || '',
          username: values.web_username || '',
          password: values.web_password || '',
          login_rules: loginRules,  // 保留已有鉴权规则不动
        },
      };
      await projectSettingApi.updateExplorationConfig(projectId, config);
      message.success('项目配置保存成功');
      fetchSettings();
    } catch (error) {
      message.error('保存失败');
    } finally {
      setExplorationLoading(false);
    }
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

  return (
    <Card title="项目设置">
      <Tabs defaultActiveKey="notification" type="card">
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
              <GlobalOutlined /> 项目配置
            </span>
          }
          key="exploration"
        >
          <Form
            form={explorationForm}
            layout="vertical"
            onFinish={handleSaveExploration}
          >
            <Title level={5}><DesktopOutlined style={{ marginRight: 6 }} />WEB 端</Title>
            <Row gutter={24}>
              <Col span={12}>
                <Form.Item name="web_base_url" label="目标系统 URL" rules={[{ required: true, message: '请输入目标系统URL' }]}>
                  <Input placeholder="https://你的系统地址" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="web_username" label="登录用户名">
                  <Input placeholder="手机号 / 用户名" autoComplete="new-password" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="web_password" label="登录密码">
                  <Input.Password placeholder="密码" autoComplete="new-password" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item>
              <Button type="primary" htmlType="submit" loading={explorationLoading} icon={<SaveOutlined />}>
                保存探索配置
              </Button>
            </Form.Item>
          </Form>
        </TabPane>
      </Tabs>
    </Card>
  );
};

export default ProjectSettings;
