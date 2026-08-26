import React, { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Space,
  Tag,
  message,
  Popconfirm,
  Tooltip,
  Badge,
  Typography,
  Row,
  Col,
  Empty,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ThunderboltOutlined,
  CloudServerOutlined,
  RobotOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import llmConfigApi, { LLMConfig, LLMConfigCreate, LLMConfigUpdate } from '../../api/llmConfigApi';

const { Option } = Select;
const { Text, Title } = Typography;

const OPENAI_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
];

const DEEPSEEK_MODELS = [
  { value: 'deepseek-chat', label: 'DeepSeek Chat' },
  { value: 'deepseek-coder', label: 'DeepSeek Coder' },
  { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner' },
  { value: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
  { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
];

const ZHIPUAI_MODELS = [
  { value: 'glm-4', label: 'GLM-4' },
  { value: 'glm-4-plus', label: 'GLM-4-Plus' },
  { value: 'glm-4-flash', label: 'GLM-4-Flash' },
  { value: 'glm-3-turbo', label: 'GLM-3-Turbo' },
];

const MOONSHOT_MODELS = [
  { value: 'moonshot-v1-8k', label: 'Moonshot-v1-8k' },
  { value: 'moonshot-v1-32k', label: 'Moonshot-v1-32k' },
  { value: 'moonshot-v1-128k', label: 'Moonshot-v1-128k' },
];

const QWEN_MODELS = [
  { value: 'qwen-turbo', label: 'Qwen Turbo' },
  { value: 'qwen-plus', label: 'Qwen Plus' },
  { value: 'qwen-max', label: 'Qwen Max' },
  { value: 'qwen-long', label: 'Qwen Long' },
];

const PROVIDER_CONFIG: Record<string, { models: { value: string; label: string }[]; defaultBaseUrl: string; defaultModel: string; color: string; gradient: string }> = {
  openai: { 
    models: OPENAI_MODELS, 
    defaultBaseUrl: 'https://api.openai.com/v1', 
    defaultModel: 'gpt-4o',
    color: '#6ee7b7',
    gradient: 'linear-gradient(135deg, #6ee7b7 0%, #34d399 100%)',
  },
  deepseek: { 
    models: DEEPSEEK_MODELS, 
    defaultBaseUrl: 'https://api.deepseek.com/v1', 
    defaultModel: 'deepseek-chat',
    color: '#93c5fd',
    gradient: 'linear-gradient(135deg, #93c5fd 0%, #60a5fa 100%)',
  },
  zhipuai: { 
    models: ZHIPUAI_MODELS, 
    defaultBaseUrl: 'https://open.bigmodel.cn/api/paas/v4', 
    defaultModel: 'glm-4',
    color: '#a5b4fc',
    gradient: 'linear-gradient(135deg, #a5b4fc 0%, #818cf8 100%)',
  },
  moonshot: { 
    models: MOONSHOT_MODELS, 
    defaultBaseUrl: 'https://api.moonshot.cn/v1', 
    defaultModel: 'moonshot-v1-8k',
    color: '#fcd34d',
    gradient: 'linear-gradient(135deg, #fcd34d 0%, #fbbf24 100%)',
  },
  qwen: { 
    models: QWEN_MODELS, 
    defaultBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', 
    defaultModel: 'qwen-turbo',
    color: '#c4b5fd',
    gradient: 'linear-gradient(135deg, #c4b5fd 0%, #a78bfa 100%)',
  },
  custom: { 
    models: [], 
    defaultBaseUrl: '', 
    defaultModel: '',
    color: '#9ca3af',
    gradient: 'linear-gradient(135deg, #9ca3af 0%, #6b7280 100%)',
  },
};

const LLMConfigManager: React.FC = () => {
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<string>('openai');
  const [form] = Form.useForm();

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const data = await llmConfigApi.list();
      setConfigs(data);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '获取LLM配置列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider);
    const config = PROVIDER_CONFIG[provider];
    if (config) {
      form.setFieldsValue({
        base_url: config.defaultBaseUrl,
        model: config.defaultModel,
      });
    }
  };

  const handleAdd = () => {
    setEditingConfig(null);
    setSelectedProvider('openai');
    form.resetFields();
    form.setFieldsValue({
      provider: 'openai',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4o',
      temperature: 0.7,
      max_tokens: 4000,
    });
    setModalVisible(true);
  };

  const handleEdit = (record: LLMConfig) => {
    setEditingConfig(record);
    setSelectedProvider(record.provider);
    form.setFieldsValue({
      name: record.name,
      provider: record.provider,
      api_key: '******',
      base_url: record.base_url,
      model: record.model,
      temperature: record.temperature,
      max_tokens: record.max_tokens,
    });
    setModalVisible(true);
  };

  const handleDelete = async (id: string) => {
    try {
      await llmConfigApi.delete(id);
      message.success('删除成功');
      fetchConfigs();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败');
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const result = await llmConfigApi.test(id);
      if (result.success) {
        message.success('连接测试成功');
      } else {
        message.error(result.message || '连接测试失败');
      }
      fetchConfigs();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '连接测试失败');
      fetchConfigs();
    } finally {
      setTestingId(null);
    }
  };

  const handleActivate = async (id: string) => {
    try {
      const result = await llmConfigApi.activate(id);
      if (result.success) {
        message.success(result.message || '切换成功');
        fetchConfigs();
      } else {
        message.error(result.message || '切换失败');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '切换失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      if (editingConfig) {
        const updateData: LLMConfigUpdate = {};
        if (values.name) updateData.name = values.name;
        if (values.base_url) updateData.base_url = values.base_url;
        if (values.model) updateData.model = values.model;
        if (values.temperature !== undefined) updateData.temperature = values.temperature;
        if (values.max_tokens !== undefined) updateData.max_tokens = values.max_tokens;
        if (values.api_key && values.api_key !== '******') {
          updateData.api_key = values.api_key;
        }
        
        await llmConfigApi.update(editingConfig.id, updateData);
        message.success('更新成功');
      } else {
        const createData: LLMConfigCreate = {
          name: values.name,
          provider: values.provider || 'openai',
          api_key: values.api_key,
          base_url: values.base_url,
          model: values.model,
          temperature: values.temperature,
          max_tokens: values.max_tokens,
        };
        await llmConfigApi.create(createData);
        message.success('创建成功');
      }
      
      setModalVisible(false);
      fetchConfigs();
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || '操作失败';
      message.error(errorMsg);
    }
  };

  const renderStatusTag = (status: string) => {
    switch (status) {
      case 'success':
        return (
          <Tag 
            icon={<CheckCircleOutlined />} 
            style={{ 
              background: 'rgba(52, 211, 153, 0.1)', 
              color: '#059669',
              border: 'none',
              borderRadius: 16,
              padding: '2px 10px',
              fontSize: 11,
            }}
          >
            已验证
          </Tag>
        );
      case 'failed':
        return (
          <Tag 
            icon={<CloseCircleOutlined />} 
            style={{ 
              background: 'rgba(248, 113, 113, 0.1)', 
              color: '#dc2626',
              border: 'none',
              borderRadius: 16,
              padding: '2px 10px',
              fontSize: 11,
            }}
          >
            验证失败
          </Tag>
        );
      default:
        return (
          <Tag 
            icon={<ExclamationCircleOutlined />} 
            style={{ 
              background: 'rgba(251, 191, 36, 0.1)', 
              color: '#d97706',
              border: 'none',
              borderRadius: 16,
              padding: '2px 10px',
              fontSize: 11,
            }}
          >
            待验证
          </Tag>
        );
    }
  };

  const columns = [
    {
      title: '配置名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: LLMConfig) => (
        <Space>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: PROVIDER_CONFIG[record.provider]?.gradient || 'linear-gradient(135deg, #9ca3af 0%, #6b7280 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: `0 2px 8px ${PROVIDER_CONFIG[record.provider]?.color || '#9ca3af'}20`,
          }}>
            <CloudServerOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          <div>
            <Text strong style={{ display: 'block', fontSize: 13 }}>{text}</Text>
            {record.is_active && (
              <Badge status="processing" text={<Text type="secondary" style={{ fontSize: 11 }}>当前使用</Text>} />
            )}
          </div>
        </Space>
      ),
    },
    {
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
      render: (text: string) => {
        const providerNames: Record<string, string> = {
          openai: 'OpenAI',
          deepseek: 'DeepSeek',
          zhipuai: '智谱AI',
          moonshot: 'Moonshot',
          qwen: '通义千问',
          custom: '自定义',
        };
        return (
          <Tag style={{ 
            background: `${PROVIDER_CONFIG[text]?.color || '#9ca3af'}12`,
            color: PROVIDER_CONFIG[text]?.color || '#6b7280',
            border: 'none',
            borderRadius: 16,
            fontSize: 11,
          }}>
            {providerNames[text] || text}
          </Tag>
        );
      },
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
      render: (text: string) => <Text code style={{ borderRadius: 6 }}>{text}</Text>,
    },
    {
      title: 'API地址',
      dataIndex: 'base_url',
      key: 'base_url',
      ellipsis: true,
      render: (text: string) => (
        <Tooltip title={text}>
          <Text type="secondary" style={{ fontSize: 12 }}>{text}</Text>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => renderStatusTag(status),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: LLMConfig) => (
        <Space size="small">
          <Tooltip title="测试连接">
            <Button
              type="text"
              size="small"
              icon={testingId === record.id ? <SyncOutlined spin /> : <ApiOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTest(record.id)}
              style={{ color: '#818cf8' }}
            />
          </Tooltip>
          {!record.is_active && record.status === 'success' && (
            <Tooltip title="切换使用">
              <Button
                type="text"
                size="small"
                icon={<ThunderboltOutlined />}
                onClick={() => handleActivate(record.id)}
                style={{ color: '#059669' }}
              />
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
              style={{ color: '#818cf8' }}
            />
          </Tooltip>
          <Popconfirm
            title="确定要删除这个配置吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <Title level={4} style={{ margin: 0, marginBottom: 4, fontSize: 15 }}>
            <RobotOutlined style={{ marginRight: 6, color: '#818cf8', fontSize: 14 }} />
            LLM 模型配置
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            管理和切换不同的 AI 模型配置
          </Text>
        </div>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={handleAdd}
          style={{
            height: 40,
            borderRadius: 8,
            paddingLeft: 16,
            paddingRight: 16,
            background: 'linear-gradient(135deg, #818cf8 0%, #a78bfa 100%)',
            border: 'none',
            boxShadow: '0 2px 8px rgba(129, 140, 248, 0.25)',
          }}
        >
          添加配置
        </Button>
      </div>
      
      {configs.length === 0 && !loading ? (
        <div style={{
          padding: 48,
          textAlign: 'center',
          background: 'linear-gradient(135deg, rgba(129, 140, 248, 0.04) 0%, rgba(167, 139, 250, 0.04) 100%)',
          borderRadius: 12,
        }}>
          <Empty
            image={<CloudServerOutlined style={{ fontSize: 48, color: '#a5b4fc' }} />}
            description={
              <div>
                <Text style={{ display: 'block', marginBottom: 6, color: '#374151', fontWeight: 500, fontSize: 14 }}>
                  暂无LLM配置
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  点击上方"添加配置"按钮创建您的第一个LLM配置
                </Text>
              </div>
            }
          />
        </div>
      ) : (
        <Table
          dataSource={configs}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ 
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (total) => <Text type="secondary">共 {total} 条配置</Text>,
          }}
        />
      )}

      <Modal
        maskClosable={false}
        title={editingConfig ? '编辑LLM配置' : '添加LLM配置'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText={editingConfig ? '更新' : '创建'}
        cancelText="取消"
        width={520}
        centered
        styles={{
          body: { padding: 24 },
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：我的GPT-4配置" style={{ height: 40, borderRadius: 8 }} />
          </Form.Item>
          
          <Form.Item
            name="provider"
            label="LLM提供商"
            rules={[{ required: true, message: '请选择提供商' }]}
          >
            <Select 
              disabled={!!editingConfig}
              onChange={handleProviderChange}
              placeholder="选择LLM提供商"
              style={{ height: 40 }}
            >
              <Option value="openai">OpenAI</Option>
              <Option value="deepseek">DeepSeek</Option>
              <Option value="zhipuai">智谱AI (GLM)</Option>
              <Option value="moonshot">Moonshot (Kimi)</Option>
              <Option value="qwen">通义千问 (Qwen)</Option>
              <Option value="custom">自定义</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="api_key"
            label="API密钥"
            rules={editingConfig ? [] : [{ required: true, message: '请输入API密钥' }]}
          >
            <Input.Password placeholder="请输入API密钥" style={{ height: 40, borderRadius: 8 }} />
          </Form.Item>
          
          <Form.Item
            name="base_url"
            label="API地址"
            rules={[{ required: true, message: '请输入API地址' }]}
          >
            <Input placeholder="请输入API地址" style={{ height: 40, borderRadius: 8 }} />
          </Form.Item>
          
          <Form.Item
            name="model"
            label="模型"
            rules={[{ required: true, message: '请选择或输入模型' }]}
          >
            {selectedProvider === 'custom' ? (
              <Input placeholder="模型名称" style={{ height: 40, borderRadius: 8 }} />
            ) : (
              <Select placeholder="选择模型" style={{ height: 40 }}>
                {(PROVIDER_CONFIG[selectedProvider]?.models || []).map(model => (
                  <Option key={model.value} value={model.value}>{model.label}</Option>
                ))}
              </Select>
            )}
          </Form.Item>
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="temperature"
                label="温度参数"
                rules={[{ required: true, message: '请输入温度参数' }]}
              >
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%', height: 40, borderRadius: 8 }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="max_tokens"
                label="最大Token数"
                rules={[{ required: true, message: '请输入最大Token数' }]}
              >
                <InputNumber min={100} max={200000} step={100} style={{ width: '100%', height: 40, borderRadius: 8 }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
};

export default LLMConfigManager;