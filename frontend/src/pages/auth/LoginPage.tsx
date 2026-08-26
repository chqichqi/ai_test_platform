import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message, Checkbox } from 'antd';
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { setCredentials } from '../../store/slices/authSlice';
import { login } from '../../api/authApi';

const { Title, Text } = Typography;

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const dispatch = useDispatch();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const response = await login(values.username, values.password);
      dispatch(setCredentials({
        user: response.user,
        token: response.token,
        refreshToken: response.refreshToken,
      }));
      message.success('登录成功！');
      navigate('/dashboard');
    } catch (error: any) {
      message.error(error.message || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #f0f4ff 0%, #e8f0fe 50%, #f5f3ff 100%)',
      padding: 24,
    }}>
      <Card 
        style={{ 
          width: '100%',
          maxWidth: 380,
          borderRadius: 12,
          border: 'none',
          boxShadow: '0 4px 24px rgba(0, 0, 0, 0.06)',
        }}
        styles={{ body: { padding: 32 } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 56,
            height: 56,
            borderRadius: 14,
            background: 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 16px',
            boxShadow: '0 4px 12px rgba(129, 140, 248, 0.25)',
          }}>
            <RobotOutlined style={{ fontSize: 26, color: '#fff' }} />
          </div>
          
          <Title level={4} style={{ marginBottom: 4, fontWeight: 600, color: '#1f2937' }}>
            AI Agent 测试平台
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            登录您的账户
          </Text>
        </div>
        
        <Form
          name="login"
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: '#9ca3af' }} />}
              placeholder="用户名"
              style={{ height: 42, borderRadius: 8 }}
            />
          </Form.Item>
          
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#9ca3af' }} />}
              placeholder="密码"
              style={{ height: 42, borderRadius: 8 }}
            />
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Checkbox style={{ fontSize: 13 }}>记住我</Checkbox>
              <Link to="/auth/forgot-password" style={{ fontSize: 13, color: '#818cf8' }}>
                忘记密码？
              </Link>
            </div>
          </Form.Item>
          
          <Form.Item style={{ marginBottom: 16 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              style={{
                height: 42,
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                background: 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
                border: 'none',
              }}
            >
              登录
            </Button>
          </Form.Item>
          
          <div style={{ textAlign: 'center' }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              还没有账户？{' '}
              <Link to="/auth/register" style={{ color: '#818cf8', fontWeight: 500 }}>
                立即注册
              </Link>
            </Text>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default LoginPage;