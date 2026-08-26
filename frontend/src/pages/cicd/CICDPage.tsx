import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  message, Popconfirm, Tabs, Row, Col, Typography
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined,
  CheckCircleOutlined, CloseCircleOutlined, PlayCircleOutlined, FolderOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import {
  cicdApi, CICDConfig, PipelineDefinition, PipelineExecution,
  PLATFORM_OPTIONS, TRIGGER_OPTIONS, STATUS_OPTIONS
} from '../../api/cicdApi';
import { projectApi } from '../../api/projectApi';

const { Option } = Select;
const { TabPane } = Tabs;
const { Title } = Typography;

const CICDPage: React.FC = () => {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = projectIdParam ? Number(projectIdParam) : null;
  const navigate = useNavigate();
  
  const [configs, setConfigs] = useState<CICDConfig[]>([]);
  const [pipelines, setPipelines] = useState<PipelineDefinition[]>([]);
  const [executions, setExecutions] = useState<PipelineExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);
  const [pipelineModalVisible, setPipelineModalVisible] = useState(false);
  const [testingConfig, setTestingConfig] = useState<number | null>(null);
  const [configForm] = Form.useForm();
  const [pipelineForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState('configs');
  
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
      const [configRes, pipelineRes, executionRes] = await Promise.all([
        cicdApi.listConfigs(projectId),
        cicdApi.listPipelines(projectId),
        cicdApi.listExecutions(projectId)
      ]);
      setConfigs(configRes.items || []);
      setPipelines(pipelineRes.items || []);
      setExecutions(executionRes.items || []);
    } catch (error) {
      message.error('加载CI/CD数据失败');
    } finally {
      setLoading(false);
    }
  };

  const handleProjectSelect = (pId: number) => {
    navigate(`/cicd/project/${pId}`);
  };

  const handleCreateConfig = async (values: any) => {
    if (!projectId) return;
    try {
      await cicdApi.createConfig({ ...values, project_id: projectId });
      message.success('创建配置成功');
      setConfigModalVisible(false);
      configForm.resetFields();
      fetchData();
    } catch (error) {
      message.error('创建配置失败');
    }
  };

  const handleDeleteConfig = async (id: number) => {
    try {
      await cicdApi.deleteConfig(id);
      message.success('删除成功');
      fetchData();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleTestConfig = async (id: number) => {
    setTestingConfig(id);
    try {
      const result = await cicdApi.testConfig(id);
      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('测试连接失败');
    } finally {
      setTestingConfig(null);
    }
  };

  const handleCreatePipeline = async (values: any) => {
    if (!projectId) return;
    try {
      await cicdApi.createPipeline({ ...values, project_id: projectId });
      message.success('创建Pipeline成功');
      setPipelineModalVisible(false);
      pipelineForm.resetFields();
      fetchData();
    } catch (error) {
      message.error('创建Pipeline失败');
    }
  };

  const handleTriggerPipeline = async (pipelineId: number) => {
    try {
      const result = await cicdApi.triggerPipeline(pipelineId);
      if (result.success) {
        message.success('Pipeline已触发');
        fetchData();
      } else {
        message.error(result.message);
      }
    } catch (error) {
      message.error('触发Pipeline失败');
    }
  };

  const getStatusTag = (status: string) => {
    const option = STATUS_OPTIONS.find(o => o.value === status);
    return <Tag color={option?.color}>{option?.label || status}</Tag>;
  };

  const configColumns: ColumnsType<CICDConfig> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '配置名称', dataIndex: 'name', key: 'name' },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (platform) => {
        const opt = PLATFORM_OPTIONS.find(o => o.value === platform);
        return <span>{opt?.icon} {opt?.label}</span>;
      }
    },
    { title: '平台URL', dataIndex: 'platform_url', key: 'platform_url', ellipsis: true },
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
      title: '同步状态',
      dataIndex: 'sync_status',
      key: 'sync_status',
      render: (status) => status === 'success' 
        ? <CheckCircleOutlined style={{ color: '#52c41a' }} />
        : status === 'failed' 
          ? <CloseCircleOutlined style={{ color: '#f5222d' }} />
          : '-'
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (date) => dayjs(date).format('YYYY-MM-DD HH:mm')
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            onClick={() => handleTestConfig(record.id)}
            loading={testingConfig === record.id}
          >
            测试连接
          </Button>
          <Popconfirm
            title="确定删除此配置？"
            onConfirm={() => handleDeleteConfig(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  const pipelineColumns: ColumnsType<PipelineDefinition> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: 'Pipeline名称', dataIndex: 'name', key: 'name' },
    { title: '外部ID', dataIndex: 'external_id', key: 'external_id', ellipsis: true },
    {
      title: '触发类型',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      render: (type) => {
        const opt = TRIGGER_OPTIONS.find(o => o.value === type);
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
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => handleTriggerPipeline(record.id)}
            disabled={!record.enabled}
          >
            触发
          </Button>
          <Popconfirm
            title="确定删除此Pipeline？"
            onConfirm={async () => {
              await cicdApi.deletePipeline(record.id);
              message.success('删除成功');
              fetchData();
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  const executionColumns: ColumnsType<PipelineExecution> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: 'Pipeline ID', dataIndex: 'pipeline_id', key: 'pipeline_id', width: 100 },
    { title: '构建号', dataIndex: 'build_number', key: 'build_number', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => getStatusTag(status)
    },
    { title: '触发人', dataIndex: 'trigger_by', key: 'trigger_by', width: 100 },
    { title: '分支', dataIndex: 'trigger_ref', key: 'trigger_ref', width: 100 },
    {
      title: '通过率',
      dataIndex: 'pass_rate',
      key: 'pass_rate',
      render: (rate) => `${rate}%`
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : '-'
    },
    {
      title: '执行时长',
      dataIndex: 'duration',
      key: 'duration',
      render: (duration) => duration ? `${Math.floor(duration / 60)}分${duration % 60}秒` : '-'
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
          <TabPane tab="配置管理" key="configs">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button onClick={() => navigate('/cicd')}>
                  切换项目
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setConfigModalVisible(true)}>
                  新建配置
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              </Space>
            </div>
            <Table
              columns={configColumns}
              dataSource={configs}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="Pipeline管理" key="pipelines">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button onClick={() => navigate('/cicd')}>
                  切换项目
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setPipelineModalVisible(true)}>
                  新建Pipeline
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              </Space>
            </div>
            <Table
              columns={pipelineColumns}
              dataSource={pipelines}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>

          <TabPane tab="执行记录" key="executions">
            <Table
              columns={executionColumns}
              dataSource={executions}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title="新建CI/CD配置"
        open={configModalVisible}
        onCancel={() => {
          setConfigModalVisible(false);
          configForm.resetFields();
        }}
        onOk={() => configForm.submit()}
        width={600}
      >
        <Form form={configForm} layout="vertical" onFinish={handleCreateConfig}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="请输入配置名称" />
          </Form.Item>
          <Form.Item name="platform" label="平台类型" rules={[{ required: true }]}>
            <Select placeholder="选择平台">
              {PLATFORM_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>
                  {opt.icon} {opt.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="platform_url" label="平台URL">
            <Input placeholder="如: http://jenkins.example.com:8080" />
          </Form.Item>
          <Form.Item name="username" label="用户名">
            <Input placeholder="API用户名" />
          </Form.Item>
          <Form.Item name="api_token" label="API Token">
            <Input.Password placeholder="API密钥" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="新建Pipeline"
        open={pipelineModalVisible}
        onCancel={() => {
          setPipelineModalVisible(false);
          pipelineForm.resetFields();
        }}
        onOk={() => pipelineForm.submit()}
        width={600}
      >
        <Form form={pipelineForm} layout="vertical" onFinish={handleCreatePipeline}>
          <Form.Item name="config_id" label="CI/CD配置" rules={[{ required: true }]}>
            <Select placeholder="选择配置">
              {configs.map(c => (
                <Option key={c.id} value={c.id}>{c.name}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="name" label="Pipeline名称" rules={[{ required: true }]}>
            <Input placeholder="请输入Pipeline名称" />
          </Form.Item>
          <Form.Item name="external_id" label="外部ID">
            <Input placeholder="Job名称/Pipeline ID/Workflow文件名" />
          </Form.Item>
          <Form.Item name="trigger_type" label="触发类型" initialValue="manual">
            <Select>
              {TRIGGER_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="environment" label="执行环境">
            <Input placeholder="如: staging, production" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CICDPage;