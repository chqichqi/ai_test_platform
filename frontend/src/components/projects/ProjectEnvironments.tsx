import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Switch, message, Tag, Space,
  Popconfirm, Typography, Tabs, Badge
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined,
  GlobalOutlined, StarOutlined
} from '@ant-design/icons';
import { projectEnvironmentApi, ProjectEnvironment } from '../../api/projectExtApi';

const { Text } = Typography;
const { TextArea } = Input;
const { TabPane } = Tabs;

interface ProjectEnvironmentsProps {
  projectId: number;
}

const ProjectEnvironments: React.FC<ProjectEnvironmentsProps> = ({ projectId }) => {
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingEnv, setEditingEnv] = useState<ProjectEnvironment | null>(null);
  const [form] = Form.useForm();
  const [activeTab, setActiveTab] = useState('list');

  useEffect(() => {
    fetchEnvironments();
  }, [projectId]);

  const fetchEnvironments = async () => {
    setLoading(true);
    try {
      const data = await projectEnvironmentApi.list(projectId, true);
      setEnvironments(data.items);
    } catch (error) {
      message.error('获取环境列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values: any) => {
    try {
      await projectEnvironmentApi.create(projectId, {
        name: values.name,
        code: values.code,
        base_url: values.base_url,
        headers: values.headers ? JSON.parse(values.headers) : undefined,
        variables: values.variables ? JSON.parse(values.variables) : undefined,
        db_config: values.db_config ? JSON.parse(values.db_config) : undefined,
        is_default: values.is_default,
        description: values.description,
      });
      message.success('创建环境成功');
      setModalVisible(false);
      form.resetFields();
      fetchEnvironments();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建环境失败');
    }
  };

  const handleUpdate = async (values: any) => {
    if (!editingEnv) return;
    try {
      await projectEnvironmentApi.update(projectId, editingEnv.id, {
        name: values.name,
        base_url: values.base_url,
        headers: values.headers ? JSON.parse(values.headers) : undefined,
        variables: values.variables ? JSON.parse(values.variables) : undefined,
        db_config: values.db_config ? JSON.parse(values.db_config) : undefined,
        is_default: values.is_default,
        is_active: values.is_active,
        description: values.description,
      });
      message.success('更新环境成功');
      setModalVisible(false);
      setEditingEnv(null);
      form.resetFields();
      fetchEnvironments();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新环境失败');
    }
  };

  const handleDelete = async (envId: number) => {
    try {
      await projectEnvironmentApi.delete(projectId, envId);
      message.success('删除环境成功');
      fetchEnvironments();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除环境失败');
    }
  };

  const handleSetDefault = async (envId: number) => {
    try {
      await projectEnvironmentApi.setDefault(projectId, envId);
      message.success('默认环境设置成功');
      fetchEnvironments();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '设置默认环境失败');
    }
  };

  const openEditModal = (env: ProjectEnvironment) => {
    setEditingEnv(env);
    form.setFieldsValue({
      name: env.name,
      code: env.code,
      base_url: env.base_url,
      headers: env.headers ? JSON.stringify(env.headers, null, 2) : '',
      variables: env.variables ? JSON.stringify(env.variables, null, 2) : '',
      db_config: env.db_config ? JSON.stringify(env.db_config, null, 2) : '',
      is_default: env.is_default,
      is_active: env.is_active,
      description: env.description,
    });
    setModalVisible(true);
  };

  const openCreateModal = () => {
    setEditingEnv(null);
    form.resetFields();
    setModalVisible(true);
  };

  const columns = [
    {
      title: '环境名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: ProjectEnvironment) => (
        <Space>
          <Text strong>{text}</Text>
          {record.is_default && (
            <Tag color="gold" icon={<StarOutlined />}>默认</Tag>
          )}
          {!record.is_active && <Tag color="red">已禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '编码',
      dataIndex: 'code',
      key: 'code',
    },
    {
      title: '基础URL',
      dataIndex: 'base_url',
      key: 'base_url',
      render: (url: string | null) => url || '-',
    },
    {
      title: '环境变量',
      key: 'variables',
      render: (_: any, record: ProjectEnvironment) => (
        record.variables ? (
          <Badge count={Object.keys(record.variables).length} style={{ backgroundColor: '#52c41a' }} />
        ) : (
          <Badge count={0} style={{ backgroundColor: '#d9d9d9' }} />
        )
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 250,
      render: (_: any, record: ProjectEnvironment) => (
        <Space>
          {!record.is_default && record.is_active && (
            <Button
              type="link"
              size="small"
              icon={<StarOutlined />}
              onClick={() => handleSetDefault(record.id)}
            >
              设为默认
            </Button>
          )}
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            编辑
          </Button>
          {!record.is_default && (
            <Popconfirm
              title="确定删除此环境？"
              onConfirm={() => handleDelete(record.id)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const renderEnvironmentCard = (env: ProjectEnvironment) => (
    <Card
      key={env.id}
      size="small"
      title={
        <Space>
          <GlobalOutlined />
          <Text strong>{env.name}</Text>
          {env.is_default && <Tag color="gold">默认</Tag>}
          {!env.is_active && <Tag color="red">已禁用</Tag>}
        </Space>
      }
      extra={
        <Space>
          {!env.is_default && env.is_active && (
            <Button
              type="link"
              size="small"
              onClick={() => handleSetDefault(env.id)}
            >
              设为默认
            </Button>
          )}
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(env)}
          >
            编辑
          </Button>
        </Space>
      }
      style={{ marginBottom: 16 }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <Text type="secondary">编码: </Text>
          <Text code>{env.code}</Text>
        </div>
        {env.base_url && (
          <div>
            <Text type="secondary">基础URL: </Text>
            <Text>{env.base_url}</Text>
          </div>
        )}
        {env.description && (
          <div>
            <Text type="secondary">描述: </Text>
            <Text>{env.description}</Text>
          </div>
        )}
        {env.variables && Object.keys(env.variables).length > 0 && (
          <div>
            <Text type="secondary">环境变量: </Text>
            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
              {JSON.stringify(env.variables, null, 2)}
            </pre>
          </div>
        )}
        {env.db_config && (
          <div>
            <Text type="secondary">数据库配置: </Text>
            <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
              {JSON.stringify(env.db_config, null, 2)}
            </pre>
          </div>
        )}
      </Space>
    </Card>
  );

  return (
    <Card
      title="环境配置"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
          创建环境
        </Button>
      }
    >
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="列表视图" key="list">
          <Table
            columns={columns}
            dataSource={environments}
            rowKey="id"
            loading={loading}
            pagination={false}
          />
        </TabPane>
        <TabPane tab="卡片视图" key="card">
          {environments.map(renderEnvironmentCard)}
        </TabPane>
      </Tabs>

      <Modal
        title={editingEnv ? '编辑环境' : '创建环境'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setEditingEnv(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        width={700}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={editingEnv ? handleUpdate : handleCreate}
        >
          <Form.Item
            name="name"
            label="环境名称"
            rules={[{ required: true, message: '请输入环境名称' }]}
          >
            <Input placeholder="如：测试环境" maxLength={100} />
          </Form.Item>

          {!editingEnv && (
            <Form.Item
              name="code"
              label="环境编码"
              rules={[{ required: true, message: '请输入环境编码' }]}
            >
              <Input placeholder="如：test、staging、production" maxLength={50} />
            </Form.Item>
          )}

          <Form.Item name="base_url" label="基础URL">
            <Input placeholder="如：https://api.example.com" />
          </Form.Item>

          <Form.Item name="description" label="环境描述">
            <TextArea rows={2} placeholder="环境描述信息" />
          </Form.Item>

          <Tabs defaultActiveKey="headers">
            <TabPane tab="请求头配置" key="headers">
              <Form.Item name="headers">
                <TextArea
                  rows={6}
                  placeholder={`请求头配置（JSON格式）
例如：
{
  "Authorization": "Bearer token",
  "X-API-Key": "your-api-key"
}`}
                />
              </Form.Item>
            </TabPane>
            <TabPane tab="环境变量" key="variables">
              <Form.Item name="variables">
                <TextArea
                  rows={6}
                  placeholder={`环境变量（JSON格式）
例如：
{
  "BASE_URL": "https://api.example.com",
  "TIMEOUT": "30"
}`}
                />
              </Form.Item>
            </TabPane>
            <TabPane tab="数据库配置" key="db">
              <Form.Item name="db_config">
                <TextArea
                  rows={6}
                  placeholder={`数据库配置（JSON格式）
例如：
{
  "host": "localhost",
  "port": 3306,
  "database": "test_db",
  "username": "root"
}`}
                />
              </Form.Item>
            </TabPane>
          </Tabs>

          <Space>
            <Form.Item name="is_default" valuePropName="checked">
              <Switch checkedChildren="默认" unCheckedChildren="非默认" />
            </Form.Item>
            {editingEnv && (
              <Form.Item name="is_active" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="禁用" />
              </Form.Item>
            )}
          </Space>
        </Form>
      </Modal>
    </Card>
  );
};

export default ProjectEnvironments;
