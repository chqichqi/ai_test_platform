import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  message, Popconfirm, Tabs, Switch, InputNumber, Typography, Row, Col
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SendOutlined, FolderOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import {
  notificationApi, NotificationChannel,
  AlertRule, NotificationHistory,
  CHANNEL_TYPE_OPTIONS, CONDITION_TYPE_OPTIONS, STATUS_OPTIONS
} from '../../api/notificationApi';
import { projectApi } from '../../api/projectApi';

const { Option } = Select;
const { TabPane } = Tabs;
const { TextArea } = Input;
const { Title } = Typography;

const NotificationPage: React.FC = () => {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = projectIdParam ? Number(projectIdParam) : null;
  const navigate = useNavigate();
  
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [history, setHistory] = useState<NotificationHistory[]>([]);
  const [loading, setLoading] = useState(false);
  const [channelModalVisible, setChannelModalVisible] = useState(false);
  const [ruleModalVisible, setRuleModalVisible] = useState(false);
  const [sendModalVisible, setSendModalVisible] = useState(false);
  const [testingChannel, setTestingChannel] = useState<number | null>(null);
  const [channelForm] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [sendForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('channels');
  
  const [projects, setProjects] = useState<any[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  useEffect(() => {
    if (!projectId) {
      fetchProjects();
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) {
      fetchData();
    }
  }, [projectId]);

  const fetchProjects = async () => {
    setProjectsLoading(true);
    try {
      const response = await projectApi.list({ page: 1, page_size: 100 });
      setProjects(response.items || []);
    } catch (error) {
      message.error('加载项目列表失败');
    } finally {
      setProjectsLoading(false);
    }
  };

  const fetchData = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [channelRes, ruleRes, historyRes] = await Promise.all([
        notificationApi.listChannels(projectId),
        notificationApi.listRules(projectId),
        notificationApi.listHistory(projectId)
      ]);
      setChannels(channelRes.items || []);
      setRules(ruleRes.items || []);
      setHistory(historyRes.items || []);
    } catch (error) {
      message.error('加载通知数据失败');
    } finally {
      setLoading(false);
    }
  };

  const handleProjectSelect = (pId: number) => {
    navigate(`/notifications/project/${pId}`);
  };

  const handleCreateChannel = async (values: any) => {
    if (!projectId) return;
    try {
      await notificationApi.createChannel({ ...values, project_id: projectId });
      message.success('创建渠道成功');
      setChannelModalVisible(false);
      channelForm.resetFields();
      fetchData();
    } catch (error) {
      message.error('创建渠道失败');
    }
  };

  const handleDeleteChannel = async (id: number) => {
    try {
      await notificationApi.deleteChannel(id);
      message.success('删除成功');
      fetchData();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleTestChannel = async (id: number) => {
    setTestingChannel(id);
    try {
      const result = await notificationApi.testChannel(id);
      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('测试渠道失败');
    } finally {
      setTestingChannel(null);
    }
  };

  const handleCreateRule = async (values: any) => {
    if (!projectId) return;
    try {
      await notificationApi.createRule({ ...values, project_id: projectId });
      message.success('创建规则成功');
      setRuleModalVisible(false);
      ruleForm.resetFields();
      fetchData();
    } catch (error) {
      message.error('创建规则失败');
    }
  };

  const handleDeleteRule = async (id: number) => {
    try {
      await notificationApi.deleteRule(id);
      message.success('删除成功');
      fetchData();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleSendNotification = async (values: any) => {
    try {
      const result = await notificationApi.sendNotification(values);
      if (result.success) {
        message.success('发送成功');
        setSendModalVisible(false);
        sendForm.resetFields();
        fetchData();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('发送失败');
    }
  };

  const getChannelTypeTag = (type: string) => {
    const opt = CHANNEL_TYPE_OPTIONS.find(o => o.value === type);
    return <span>{opt?.icon} {opt?.label}</span>;
  };

  const getTestStatusTag = (status?: string) => {
    if (!status) return '-';
    if (status === 'success') {
      return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    }
    return <CloseCircleOutlined style={{ color: '#f5222d' }} />;
  };

  const getHistoryStatusTag = (status: string) => {
    const opt = STATUS_OPTIONS.find(o => o.value === status);
    return <Tag color={opt?.color}>{opt?.label || status}</Tag>;
  };

  const channelColumns: ColumnsType<NotificationChannel> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '渠道名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type) => getChannelTypeTag(type)
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled) => (
        <Tag color={enabled ? 'green' : 'red'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      )
    },
    {
      title: '测试状态',
      dataIndex: 'test_status',
      key: 'test_status',
      render: (status) => getTestStatusTag(status)
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            onClick={() => handleTestChannel(record.id)}
            loading={testingChannel === record.id}
          >
            测试
          </Button>
          <Popconfirm
            title="确定删除此渠道？"
            onConfirm={() => handleDeleteChannel(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  const ruleColumns: ColumnsType<AlertRule> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '规则名称', dataIndex: 'name', key: 'name' },
    {
      title: '条件类型',
      dataIndex: 'condition_type',
      key: 'condition_type',
      render: (type) => {
        const opt = CONDITION_TYPE_OPTIONS.find(o => o.value === type);
        return opt?.label || type;
      }
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled) => (
        <Tag color={enabled ? 'green' : 'red'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      )
    },
    { title: '触发次数', dataIndex: 'trigger_count', key: 'trigger_count', width: 100 },
    {
      title: '最后触发',
      dataIndex: 'last_triggered_at',
      key: 'last_triggered_at',
      width: 160,
      render: (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Popconfirm
          title="确定删除此规则？"
          onConfirm={() => handleDeleteRule(record.id)}
        >
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      )
    }
  ];

  const historyColumns: ColumnsType<NotificationHistory> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '渠道ID', dataIndex: 'channel_id', key: 'channel_id', width: 80 },
    { title: '收件人', dataIndex: 'recipient', key: 'recipient', ellipsis: true },
    { title: '主题', dataIndex: 'subject', key: 'subject', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => getHistoryStatusTag(status)
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      render: (msg) => msg || '-'
    },
    {
      title: '发送时间',
      dataIndex: 'sent_at',
      key: 'sent_at',
      width: 160,
      render: (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
    }
  ];

  if (!projectId) {
    return (
      <div>
        <Title level={4} style={{ marginBottom: 16 }}>请选择项目</Title>
        <Row gutter={[16, 16]}>
          {projectsLoading ? (
            <Col span={24} style={{ textAlign: 'center', padding: 40 }}>
              加载中...
            </Col>
          ) : projects.length === 0 ? (
            <Col span={24} style={{ textAlign: 'center', padding: 40 }}>
              暂无项目，请先创建项目
            </Col>
          ) : (
            projects.map(p => (
              <Col key={p.id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  onClick={() => handleProjectSelect(p.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <Card.Meta
                    avatar={<FolderOutlined style={{ fontSize: 32, color: '#1890ff' }} />}
                    title={p.name}
                    description={p.code}
                  />
                </Card>
              </Col>
            ))
          )}
        </Row>
      </div>
    );
  }

  return (
    <div>
      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="通知渠道" key="channels">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button onClick={() => navigate('/notifications')}>
                  切换项目
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setChannelModalVisible(true)}>
                  新建渠道
                </Button>
                <Button icon={<SendOutlined />} onClick={() => setSendModalVisible(true)}>
                  发送通知
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              </Space>
            </div>
            <Table
              columns={channelColumns}
              dataSource={channels}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="告警规则" key="rules">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button onClick={() => navigate('/notifications')}>
                  切换项目
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRuleModalVisible(true)}>
                  新建规则
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              </Space>
            </div>
            <Table
              columns={ruleColumns}
              dataSource={rules}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="通知历史" key="history">
            <Table
              columns={historyColumns}
              dataSource={history}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title="新建通知渠道"
        open={channelModalVisible}
        onCancel={() => {
          setChannelModalVisible(false);
          channelForm.resetFields();
        }}
        onOk={() => channelForm.submit()}
        width={600}
      >
        <Form form={channelForm} layout="vertical" onFinish={handleCreateChannel}>
          <Form.Item name="name" label="渠道名称" rules={[{ required: true }]}>
            <Input placeholder="请输入渠道名称" />
          </Form.Item>
          <Form.Item name="type" label="渠道类型" rules={[{ required: true }]}>
            <Select placeholder="选择渠道类型">
              {CHANNEL_TYPE_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>
                  {opt.icon} {opt.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item 
            noStyle
            shouldUpdate={(prev, curr) => prev.type !== curr.type}
          >
            {({ getFieldValue }) => {
              const type = getFieldValue('type');
              if (type === 'email') {
                return (
                  <>
                    <Form.Item name={['email_config', 'smtp_server']} label="SMTP服务器" rules={[{ required: true }]}>
                      <Input placeholder="如: smtp.example.com" />
                    </Form.Item>
                    <Form.Item name={['email_config', 'smtp_port']} label="SMTP端口" initialValue={465}>
                      <InputNumber min={1} max={65535} />
                    </Form.Item>
                    <Form.Item name={['email_config', 'username']} label="用户名" rules={[{ required: true }]}>
                      <Input placeholder="SMTP用户名" />
                    </Form.Item>
                    <Form.Item name={['email_config', 'password']} label="密码" rules={[{ required: true }]}>
                      <Input.Password placeholder="SMTP密码" />
                    </Form.Item>
                    <Form.Item name={['email_config', 'from_addr']} label="发件人地址">
                      <Input placeholder="默认使用用户名" />
                    </Form.Item>
                  </>
                );
              }
              return (
                <>
                  <Form.Item name="webhook_url" label="Webhook URL" rules={[{ required: true }]}>
                    <Input placeholder="Webhook地址" />
                  </Form.Item>
                  {type === 'dingtalk' && (
                    <Form.Item name="secret" label="签名密钥">
                      <Input.Password placeholder="钉钉加签密钥（可选）" />
                    </Form.Item>
                  )}
                </>
              );
            }}
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" initialValue={true} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建告警规则"
        open={ruleModalVisible}
        onCancel={() => {
          setRuleModalVisible(false);
          ruleForm.resetFields();
        }}
        onOk={() => ruleForm.submit()}
        width={600}
      >
        <Form form={ruleForm} layout="vertical" onFinish={handleCreateRule}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
            <Input placeholder="请输入规则名称" />
          </Form.Item>
          <Form.Item name="condition_type" label="触发条件" rules={[{ required: true }]}>
            <Select placeholder="选择触发条件">
              {CONDITION_TYPE_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="规则描述" />
          </Form.Item>
          <Form.Item name="channel_ids" label="通知渠道">
            <Select mode="multiple" placeholder="选择通知渠道">
              {channels.map(c => (
                <Option key={c.id} value={c.id}>{c.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="receivers" label="接收人">
            <Select mode="tags" placeholder="输入接收人（邮件地址或用户ID）" />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" initialValue={true} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="发送通知"
        open={sendModalVisible}
        onCancel={() => {
          setSendModalVisible(false);
          sendForm.resetFields();
        }}
        onOk={() => sendForm.submit()}
        width={600}
      >
        <Form form={sendForm} layout="vertical" onFinish={handleSendNotification}>
          <Form.Item name="channel_id" label="通知渠道" rules={[{ required: true }]}>
            <Select placeholder="选择通知渠道">
              {channels.filter(c => c.enabled).map(c => (
                <Option key={c.id} value={c.id}>{c.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="通知标题" />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true }]}>
            <TextArea rows={4} placeholder="通知内容" />
          </Form.Item>
          <Form.Item 
            noStyle
            shouldUpdate={(prev, curr) => prev.channel_id !== curr.channel_id}
          >
            {({ getFieldValue }) => {
              const channelId = getFieldValue('channel_id');
              const channel = channels.find(c => c.id === channelId);
              if (channel?.type === 'email') {
                return (
                  <Form.Item name="recipients" label="收件人" rules={[{ required: true }]}>
                    <Select mode="tags" placeholder="输入收件人邮箱地址" />
                  </Form.Item>
                );
              }
              return null;
            }}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default NotificationPage;