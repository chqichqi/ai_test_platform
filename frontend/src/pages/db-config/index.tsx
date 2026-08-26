import React, { useState, useEffect } from 'react';
import {
  Card, Steps, Button, message, Typography, Row, Col,
  Form, Input, Space, Alert, Tag
} from 'antd';
import {
  DatabaseOutlined, CheckCircleOutlined, LoadingOutlined,
  SettingOutlined, ThunderboltOutlined, ArrowRightOutlined,
  ArrowLeftOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import dbConfigApi, { MySQLConfig, TestConnectionResult, InitStep } from '../../api/dbConfigApi';

const { Title, Text, Paragraph } = Typography;

interface WizardStep {
  title: string;
  icon: React.ReactNode;
}

const steps: WizardStep[] = [
  { title: '选择数据库', icon: <DatabaseOutlined /> },
  { title: '配置连接', icon: <SettingOutlined /> },
  { title: '初始化', icon: <ThunderboltOutlined /> },
];

const DatabaseConfigWizard: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [dbType, setDbType] = useState<string>('mysql');
  const [form] = Form.useForm();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [initSteps, setInitSteps] = useState<InitStep[]>([]);
  const [initSuccess, setInitSuccess] = useState(false);

  // 检查是否已经配置
  useEffect(() => {
    checkConfigStatus();
  }, []);

  const checkConfigStatus = async () => {
    try {
      const status = await dbConfigApi.checkStatus();
      if (status.configured) {
        message.info('数据库已配置，即将跳转到登录页面');
        setTimeout(() => navigate('/login'), 1500);
      }
    } catch (error) {
      // 未配置，正常显示向导
    }
  };

  // 步骤1：选择数据库类型
  const renderStep1 = () => (
    <div style={{ padding: '40px 0' }}>
      <Row gutter={[32, 32]} justify="center">
        <Col xs={24} md={10}>
          <Card
            hoverable
            className={dbType === 'mysql' ? 'selected-card' : ''}
            style={{
              borderRadius: 16,
              border: dbType === 'mysql' ? '2px solid #818cf8' : '1px solid #e5e7eb',
              background: dbType === 'mysql' ? 'linear-gradient(135deg, #f0f4ff 0%, #f5f3ff 100%)' : '#fff',
              cursor: 'pointer',
              transition: 'all 0.3s ease',
            }}
            onClick={() => setDbType('mysql')}
          >
            <div style={{ textAlign: 'center', padding: 24 }}>
              <div style={{
                width: 72,
                height: 72,
                borderRadius: 16,
                background: 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 20px',
              }}>
                <DatabaseOutlined style={{ fontSize: 32, color: '#fff' }} />
              </div>
              <Title level={4} style={{ marginBottom: 12 }}>MySQL 数据库</Title>
              <Paragraph type="secondary" style={{ marginBottom: 16 }}>
                生产环境推荐，支持高并发和大数据量
              </Paragraph>
              <Tag color="blue">推荐</Tag>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card
            hoverable
            className={dbType === 'sqlite' ? 'selected-card' : ''}
            style={{
              borderRadius: 16,
              border: dbType === 'sqlite' ? '2px solid #34d399' : '1px solid #e5e7eb',
              background: dbType === 'sqlite' ? 'linear-gradient(135deg, #f0fdf4 0%, #f5f3ff 100%)' : '#fff',
              cursor: 'pointer',
              transition: 'all 0.3s ease',
            }}
            onClick={() => setDbType('sqlite')}
          >
            <div style={{ textAlign: 'center', padding: 24 }}>
              <div style={{
                width: 72,
                height: 72,
                borderRadius: 16,
                background: 'linear-gradient(135deg, #6ee7b7 0%, #34d399 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 20px',
              }}>
                <DatabaseOutlined style={{ fontSize: 32, color: '#fff' }} />
              </div>
              <Title level={4} style={{ marginBottom: 12 }}>SQLite 数据库</Title>
              <Paragraph type="secondary" style={{ marginBottom: 16 }}>
                本地测试使用，零配置快速启动
              </Paragraph>
              <Tag color="green">简单</Tag>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );

  // 步骤2：配置连接
  const renderStep2 = () => {
    if (dbType === 'sqlite') {
      return (
        <div style={{ padding: '40px 0', textAlign: 'center' }}>
          <CheckCircleOutlined style={{ fontSize: 64, color: '#34d399', marginBottom: 24 }} />
          <Title level={4}>SQLite 配置简单</Title>
          <Paragraph type="secondary" style={{ maxWidth: 400, margin: '0 auto' }}>
            SQLite 无需额外配置，系统将自动创建数据库文件。
            适合本地测试和开发环境使用。
          </Paragraph>
        </div>
      );
    }

    return (
      <div style={{ padding: '20px 0' }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            host: 'localhost',
            port: 3306,
            database: 'ai_test_platform',
            username: 'root',
          }}
        >
          <Row gutter={24}>
            <Col span={12}>
              <Form.Item
                label="主机地址"
                name="host"
                rules={[{ required: true, message: '请输入主机地址' }]}
              >
                <Input placeholder="localhost" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="端口"
                name="port"
                rules={[{ required: true, message: '请输入端口' }]}
              >
                <Input type="number" placeholder="3306" size="large" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            label="数据库名"
            name="database"
            rules={[{ required: true, message: '请输入数据库名' }]}
          >
            <Input placeholder="ai_test_platform" size="large" />
          </Form.Item>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="root" size="large" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入密码" size="large" />
          </Form.Item>
        </Form>

        {testResult && (
          <Alert
            style={{ marginTop: 16 }}
            type={testResult.success ? 'success' : 'error'}
            message={testResult.success ? '连接成功' : '连接失败'}
            description={
              testResult.success ? (
                <Space direction="vertical">
                  <Text>MySQL版本: {testResult.version}</Text>
                  <Text>
                    数据库状态: {testResult.db_exists ? '已存在' : '不存在（将自动创建）'}
                  </Text>
                  {testResult.existing_tables && testResult.existing_tables.length > 0 && (
                    <Text>已存在表: {testResult.existing_tables.length} 个</Text>
                  )}
                </Space>
              ) : (
                testResult.message
              )
            }
            showIcon
          />
        )}

        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <Button
            type="primary"
            size="large"
            icon={testing ? <LoadingOutlined /> : <CheckCircleOutlined />}
            onClick={handleTestConnection}
            loading={testing}
          >
            {testing ? '测试中...' : '测试连接'}
          </Button>
        </div>
      </div>
    );
  };

  // 测试连接
  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields();
      setTesting(true);
      setTestResult(null);
      
      const result = await dbConfigApi.testMySQLConnection(values as MySQLConfig);
      setTestResult(result);
      
      if (result.success) {
        message.success('连接测试成功');
      } else {
        message.error(result.message);
      }
    } catch (error: any) {
      message.error(error.message || '测试失败');
    } finally {
      setTesting(false);
    }
  };

  // 步骤3：初始化
  const renderStep3 = () => (
    <div style={{ padding: '40px 0', textAlign: 'center' }}>
      {initializing ? (
        <>
          <LoadingOutlined style={{ fontSize: 48, color: '#818cf8', marginBottom: 24 }} spin />
          <Title level={4}>正在初始化数据库...</Title>
          <div style={{ maxWidth: 500, margin: '24px auto' }}>
            {initSteps.map((step, index) => (
              <div key={index} style={{ 
                display: 'flex', 
                alignItems: 'center', 
                marginBottom: 16,
                padding: 12,
                background: '#f9fafb',
                borderRadius: 8
              }}>
                {step.status === 'running' && <LoadingOutlined style={{ color: '#818cf8', marginRight: 12 }} spin />}
                {step.status === 'success' && <CheckCircleOutlined style={{ color: '#34d399', marginRight: 12 }} />}
                {step.status === 'error' && <CheckCircleOutlined style={{ color: '#ef4444', marginRight: 12 }} />}
                <Text>{step.name}</Text>
                {step.status === 'success' && (
                  <Tag color="success" style={{ marginLeft: 'auto' }}>完成</Tag>
                )}
                {step.status === 'error' && (
                  <Tag color="error" style={{ marginLeft: 'auto' }}>失败</Tag>
                )}
              </div>
            ))}
          </div>
        </>
      ) : initSuccess ? (
        <>
          <CheckCircleOutlined style={{ fontSize: 64, color: '#34d399', marginBottom: 24 }} />
          <Title level={4}>数据库初始化成功</Title>
          <Paragraph type="secondary" style={{ marginBottom: 24 }}>
            系统已创建数据库、数据表和基础数据。<br />
            默认管理员账号: admin / 123456
          </Paragraph>
          <Button 
            type="primary" 
            size="large" 
            onClick={() => navigate('/login')}
            icon={<ArrowRightOutlined />}
          >
            进入登录页面
          </Button>
        </>
      ) : (
        <>
          <SettingOutlined style={{ fontSize: 64, color: '#818cf8', marginBottom: 24 }} />
          <Title level={4}>准备初始化</Title>
          <Paragraph type="secondary" style={{ maxWidth: 400, margin: '0 auto 24px' }}>
            即将创建数据库、数据表和基础数据。<br />
            此过程可能需要几分钟时间。
          </Paragraph>
          <Button 
            type="primary" 
            size="large" 
            onClick={handleInitialize}
            icon={<ThunderboltOutlined />}
          >
            开始初始化
          </Button>
        </>
      )}
    </div>
  );

  // 初始化数据库
  const handleInitialize = async () => {
    try {
      setInitializing(true);
      setInitSteps([
        { name: '创建数据库', status: 'running' },
        { name: '创建数据表', status: 'pending' as any },
        { name: '初始化基础数据', status: 'pending' as any },
        { name: '保存配置', status: 'pending' as any },
      ]);

      let params: any = { db_type: dbType, init_data: true };
      
      if (dbType === 'mysql') {
        const values = form.getFieldsValue();
        params = { ...params, ...values };
      } else {
        params.database = './data/app.db';
      }

      // 模拟步骤更新（实际应该根据后端返回更新）
      const result = await dbConfigApi.initDatabase(params);
      
      if (result.success) {
        setInitSteps(prev => prev.map(s => ({ ...s, status: 'success' })));
        setInitSuccess(true);
        message.success('数据库初始化成功');
      } else {
        setInitSteps(prev => 
          prev.map((s, i) => i === prev.length - 1 ? { ...s, status: 'error', error: result.message } : s)
        );
        message.error(result.message);
      }
    } catch (error: any) {
      message.error(error.message || '初始化失败');
      setInitSteps(prev => 
        prev.map((s, i) => i === prev.length - 1 ? { ...s, status: 'error', error: error.message } : s)
      );
    } finally {
      setInitializing(false);
    }
  };

  // 下一步
  const nextStep = async () => {
    if (currentStep === 0) {
      setCurrentStep(1);
    } else if (currentStep === 1) {
      if (dbType === 'mysql') {
        if (!testResult?.success) {
          message.warning('请先测试数据库连接');
          return;
        }
      }
      setCurrentStep(2);
    }
  };

  // 上一步
  const prevStep = () => {
    setCurrentStep(currentStep - 1);
    setTestResult(null);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #f0f4ff 0%, #e8f0fe 50%, #f5f3ff 100%)',
      padding: '40px 20px',
    }}>
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <Card
          style={{
            borderRadius: 16,
            border: 'none',
            boxShadow: '0 4px 24px rgba(0, 0, 0, 0.08)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: 40 }}>
            <div style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              background: 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              <DatabaseOutlined style={{ fontSize: 28, color: '#fff' }} />
            </div>
            <Title level={3} style={{ marginBottom: 8 }}>数据库配置向导</Title>
            <Text type="secondary">首次使用，请先配置数据库连接</Text>
          </div>

          <Steps
            current={currentStep}
            items={steps.map((s, i) => ({
              title: s.title,
              icon: i === currentStep ? <LoadingOutlined /> : s.icon,
            }))}
            style={{ marginBottom: 40 }}
          />

          <div style={{ minHeight: 300 }}>
            {currentStep === 0 && renderStep1()}
            {currentStep === 1 && renderStep2()}
            {currentStep === 2 && renderStep3()}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 40 }}>
            <Button
              size="large"
              onClick={prevStep}
              disabled={currentStep === 0 || initializing || initSuccess}
              icon={<ArrowLeftOutlined />}
            >
              上一步
            </Button>
            
            {currentStep < 2 && (
              <Button
                type="primary"
                size="large"
                onClick={nextStep}
                disabled={initializing}
                icon={<ArrowRightOutlined />}
              >
                下一步
              </Button>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DatabaseConfigWizard;
