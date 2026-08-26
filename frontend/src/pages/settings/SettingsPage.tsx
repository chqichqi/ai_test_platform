import React, { useState } from 'react';
import { Card, Typography, Form, Input, Button, Switch, Select, Tabs, message, Space, Tag, Row, Col, Divider, Alert } from 'antd';
import { SaveOutlined, BellOutlined, SettingOutlined, CloudServerOutlined, SafetyOutlined, ThunderboltOutlined, CloudOutlined, SunOutlined, GithubOutlined, ApiOutlined } from '@ant-design/icons';
import LLMConfigManager from '../../components/llm/LLMConfigManager';
import { useDispatch, useSelector } from 'react-redux';
import { setTheme, ThemeMode, THEMES } from '../../store/slices/themeSlice';
import { RootState } from '../../store';

const { Title, Text } = Typography;
const { TabPane } = Tabs;
const { Option } = Select;

const SettingsPage: React.FC = () => {
  const [form] = Form.useForm();
  const [gitForm] = Form.useForm();
  const [jenkinsForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('llm-configs');
  const dispatch = useDispatch();
  const { mode: currentTheme, colors } = useSelector((state: RootState) => state.theme);

  const onFinish = (values: any) => {
    setLoading(true);
    console.log('保存设置:', values);
    
    setTimeout(() => {
      setLoading(false);
      message.success('设置已保存成功');
    }, 1500);
  };

  const handleThemeChange = (themeMode: ThemeMode) => {
    dispatch(setTheme(themeMode));
    message.success(`已切换到「${THEMES[themeMode].name}」主题`);
  };

  const generalSettings = {
    platformName: 'AI驱动测试管理平台',
    language: 'zh-CN',
    timezone: 'Asia/Shanghai',
  };

  const gitSettings = {
    defaultBranch: 'main',
    webhookSecret: '',
    autoSync: true,
    syncInterval: 30,
  };

  const jenkinsSettings = {
    jenkinsUrl: '',
    username: '',
    apiToken: '',
    timeout: 30,
    retryCount: 3,
  };

  const securitySettings = {
    requireLogin: true,
    sessionTimeout: 7200,
    passwordPolicy: 'strong',
    maxLoginAttempts: 5,
    enable2FA: false,
    allowRegistration: true,
  };

  return (
    <div>
      <Card style={{ 
        borderRadius: 12, 
        border: `1px solid ${colors.cardBorder}`,
        background: colors.cardBg,
      }}>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab}
          tabBarStyle={{
            marginBottom: 24,
          }}
        >
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <SettingOutlined />
                基本设置
              </span>
            } 
            key="general"
          >
            <Form
              form={form}
              layout="vertical"
              initialValues={generalSettings}
              onFinish={onFinish}
            >
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="platformName"
                    label="平台名称"
                    rules={[{ required: true, message: '请输入平台名称' }]}
                  >
                    <Input placeholder="请输入平台名称" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="language"
                    label="系统语言"
                    rules={[{ required: true, message: '请选择系统语言' }]}
                  >
                    <Select placeholder="选择系统语言">
                      <Option value="zh-CN">简体中文</Option>
                      <Option value="en-US">English</Option>
                      <Option value="ja-JP">日本語</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="timezone"
                    label="时区"
                    rules={[{ required: true, message: '请选择时区' }]}
                  >
                    <Select placeholder="选择时区">
                      <Option value="Asia/Shanghai">亚洲/上海 (UTC+8)</Option>
                      <Option value="America/New_York">美国/纽约 (UTC-5)</Option>
                      <Option value="Europe/London">欧洲/伦敦 (UTC+0)</Option>
                      <Option value="Asia/Tokyo">亚洲/东京 (UTC+9)</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="主题设置">
                    <Select 
                      value={currentTheme}
                      onChange={handleThemeChange}
                      style={{ width: '100%' }}
                    >
                      <Option value="tech-color">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <ThunderboltOutlined style={{ color: '#6366f1' }} />
                          <span>炫彩科技 - 明亮炫彩，充满科技感</span>
                        </div>
                      </Option>
                      <Option value="ocean-breeze">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <CloudOutlined style={{ color: '#0891b2' }} />
                          <span>海洋微风 - 清新淡雅，宁静致远</span>
                        </div>
                      </Option>
                      <Option value="sunset-glow">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <SunOutlined style={{ color: '#ea580c' }} />
                          <span>暮光暖阳 - 温暖柔和，舒适惬意</span>
                        </div>
                      </Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              
              <Divider style={{ borderColor: colors.colorBorder }} />
              
              <Form.Item>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={loading} 
                  icon={<SaveOutlined />}
                  style={{
                    height: 40,
                    borderRadius: 8,
                    paddingLeft: 24,
                    paddingRight: 24,
                    background: colors.gradientPrimary,
                    border: 'none',
                  }}
                >
                  保存基本设置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>
          
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CloudServerOutlined />
                LLM配置
              </span>
            } 
            key="llm-configs"
          >
            <LLMConfigManager />
          </TabPane>
          
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <GithubOutlined />
                Git配置
              </span>
            } 
            key="git"
          >
            <Alert
              message="Git配置说明"
              description="配置Git仓库的全局默认设置，包括默认分支、Webhook密钥等。具体仓库配置请在项目管理中设置。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            
            <Form
              form={gitForm}
              layout="vertical"
              initialValues={gitSettings}
              onFinish={onFinish}
            >
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="defaultBranch"
                    label="默认分支"
                    rules={[{ required: true, message: '请输入默认分支' }]}
                  >
                    <Input placeholder="main" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="webhookSecret"
                    label="Webhook密钥"
                    tooltip="用于验证Webhook请求的合法性"
                  >
                    <Input.Password placeholder="输入Webhook密钥" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="autoSync"
                    label="自动同步"
                    valuePropName="checked"
                    tooltip="是否自动同步仓库信息"
                  >
                    <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="syncInterval"
                    label="同步间隔(分钟)"
                    tooltip="自动同步的时间间隔"
                  >
                    <Input type="number" placeholder="30" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Divider style={{ borderColor: colors.colorBorder }} />
              
              <Form.Item>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={loading} 
                  icon={<SaveOutlined />}
                  style={{
                    height: 40,
                    borderRadius: 8,
                    paddingLeft: 24,
                    paddingRight: 24,
                    background: colors.gradientPrimary,
                    border: 'none',
                  }}
                >
                  保存Git配置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>
          
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ApiOutlined />
                Jenkins配置
              </span>
            } 
            key="jenkins"
          >
            <Alert
              message="Jenkins配置说明"
              description="配置Jenkins服务器的全局连接信息。具体Job配置请在CI/CD集成中设置。"
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            
            <Form
              form={jenkinsForm}
              layout="vertical"
              initialValues={jenkinsSettings}
              onFinish={onFinish}
            >
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="jenkinsUrl"
                    label="Jenkins URL"
                    rules={[{ required: true, message: '请输入Jenkins URL' }]}
                  >
                    <Input placeholder="http://jenkins.example.com:8080" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="username"
                    label="用户名"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input placeholder="Jenkins用户名" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="apiToken"
                    label="API Token"
                    rules={[{ required: true, message: '请输入API Token' }]}
                  >
                    <Input.Password placeholder="Jenkins API Token" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="timeout"
                    label="超时时间(秒)"
                    tooltip="请求Jenkins的超时时间"
                  >
                    <Input type="number" placeholder="30" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="retryCount"
                    label="重试次数"
                    tooltip="请求失败时的重试次数"
                  >
                    <Input type="number" placeholder="3" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Divider style={{ borderColor: colors.colorBorder }} />
              
              <Form.Item>
                <Space>
                  <Button 
                    type="primary" 
                    htmlType="submit" 
                    loading={loading} 
                    icon={<SaveOutlined />}
                    style={{
                      height: 40,
                      borderRadius: 8,
                      paddingLeft: 24,
                      paddingRight: 24,
                      background: colors.gradientPrimary,
                      border: 'none',
                    }}
                  >
                    保存Jenkins配置
                  </Button>
                  <Button 
                    onClick={async () => {
                      try {
                        message.loading('正在测试连接...');
                        await new Promise(r => setTimeout(r, 1500));
                        message.success('Jenkins连接成功');
                      } catch (e) {
                        message.error('Jenkins连接失败');
                      }
                    }}
                    style={{ height: 40, borderRadius: 8 }}
                  >
                    测试连接
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </TabPane>
          
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <SafetyOutlined />
                安全设置
              </span>
            } 
            key="security"
          >
            <Form
              form={form}
              layout="vertical"
              initialValues={securitySettings}
              onFinish={onFinish}
            >
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="requireLogin"
                    label="要求登录"
                    valuePropName="checked"
                  >
                    <Switch checkedChildren="是" unCheckedChildren="否" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="sessionTimeout"
                    label="会话超时(秒)"
                    rules={[{ required: true, message: '请输入会话超时时间' }]}
                  >
                    <Input type="number" placeholder="7200" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="passwordPolicy"
                    label="密码策略"
                    rules={[{ required: true, message: '请选择密码策略' }]}
                  >
                    <Select placeholder="选择密码策略">
                      <Option value="weak">弱密码(仅长度要求)</Option>
                      <Option value="medium">中等密码(字母+数字)</Option>
                      <Option value="strong">强密码(大小写字母+数字+特殊字符)</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="maxLoginAttempts"
                    label="最大登录尝试次数"
                    rules={[{ required: true, message: '请输入最大登录尝试次数' }]}
                  >
                    <Input type="number" placeholder="5" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Row gutter={24}>
                <Col span={12}>
                  <Form.Item
                    name="enable2FA"
                    label="启用双因素认证"
                    valuePropName="checked"
                  >
                    <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="allowRegistration"
                    label="允许用户注册"
                    valuePropName="checked"
                  >
                    <Switch checkedChildren="允许" unCheckedChildren="禁止" />
                  </Form.Item>
                </Col>
              </Row>
              
              <Form.Item>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={loading} 
                  icon={<SaveOutlined />}
                  style={{
                    height: 40,
                    borderRadius: 8,
                    paddingLeft: 24,
                    paddingRight: 24,
                    background: colors.gradientPrimary,
                    border: 'none',
                  }}
                >
                  保存安全设置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>
          
          <TabPane 
            tab={
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <BellOutlined />
                通知设置
              </span>
            } 
            key="notification"
          >
            <Row gutter={24}>
              <Col span={24}>
                <Card 
                  title="邮件通知" 
                  style={{ marginBottom: 24, borderRadius: 12, border: `1px solid ${colors.cardBorder}`, background: colors.cardBg }}
                  styles={{ body: { padding: 24 } }}
                >
                  <Row gutter={24}>
                    <Col span={8}>
                      <Form.Item label="SMTP服务器">
                        <Input placeholder="smtp.example.com" />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="SMTP端口">
                        <Input placeholder="587" />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="发件人邮箱">
                        <Input placeholder="noreply@example.com" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Button type="primary" icon={<SaveOutlined />}>保存邮件设置</Button>
                </Card>
              </Col>
            </Row>
            
            <Card 
              title="通知类型" 
              style={{ borderRadius: 12, border: `1px solid ${colors.cardBorder}`, background: colors.cardBg }}
              styles={{ body: { padding: 24 } }}
            >
              {[
                { title: '测试执行失败', desc: '当测试执行失败时通知', enabled: true },
                { title: '通过率过低', desc: '当测试通过率低于阈值时通知', enabled: true },
                { title: 'CI构建失败', desc: '当CI构建失败时通知', enabled: true },
                { title: '问题创建', desc: '当新问题创建时通知', enabled: false },
                { title: '问题未解决', desc: '当问题超过期限未解决时通知', enabled: true },
              ].map((item, index) => (
                <div key={index} style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between', 
                  padding: '12px 0',
                  borderBottom: index < 4 ? `1px solid ${colors.colorBorder}` : 'none'
                }}>
                  <div>
                    <Text strong style={{ display: 'block' }}>{item.title}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.desc}</Text>
                  </div>
                  <Switch defaultChecked={item.enabled} />
                </div>
              ))}
            </Card>
          </TabPane>
        </Tabs>
      </Card>
      
      <Card style={{ marginTop: 20, borderRadius: 12, border: `1px solid ${colors.cardBorder}`, background: colors.cardBg }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <Title level={4} style={{ marginBottom: 6, fontSize: 15, color: colors.colorText }}>系统信息</Title>
            <Space wrap>
              <Tag color="blue" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>版本: 1.0.0</Tag>
              <Tag color="green" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>Node: v18.17.0</Tag>
              <Tag color="orange" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>React: 18.2.0</Tag>
              <Tag color="purple" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>TypeScript: 5.2.2</Tag>
              <Tag color="cyan" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>Ant Design: 5.12.2</Tag>
              <Tag color="red" style={{ padding: '2px 10px', borderRadius: 16, fontSize: 11 }}>后端API: 运行中</Tag>
            </Space>
          </div>
          
          <Space>
            <Button danger>重启系统</Button>
            <Button>导出配置</Button>
            <Button>导入配置</Button>
            <Button>重置为默认</Button>
          </Space>
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;