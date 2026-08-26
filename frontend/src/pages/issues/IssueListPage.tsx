import React, { useState, useEffect } from 'react';
import {
  Table, Card, Button, Tag, Space, Input, Select, Modal,
  Form, message, Popconfirm, Drawer, Descriptions,
  Row, Col, Dropdown, Menu, Typography
} from 'antd';
import {
  PlusOutlined, SearchOutlined, ReloadOutlined, DeleteOutlined,
  ExportOutlined, FolderOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import {
  issueApi, Issue, SEVERITY_OPTIONS, PRIORITY_OPTIONS,
  STATUS_OPTIONS, FAILURE_TYPE_OPTIONS
} from '../../api/issueApi';
import { projectApi } from '../../api/projectApi';

const { Option } = Select;
const { TextArea } = Input;
const { Title } = Typography;

const IssueListPage: React.FC = () => {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = projectIdParam ? Number(projectIdParam) : null;
  const navigate = useNavigate();
  
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [severityFilter, setSeverityFilter] = useState<string | undefined>();
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [form] = Form.useForm();
  
  const [projects, setProjects] = useState<any[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  useEffect(() => {
    if (!projectId) {
      fetchProjects();
    }
  }, [projectId]);

  useEffect(() => {
    if (projectId) {
      fetchIssues();
    }
  }, [projectId, page, pageSize, statusFilter, severityFilter]);

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

  const fetchIssues = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const response = await issueApi.list({
        project_id: projectId,
        page,
        page_size: pageSize,
        search: searchText || undefined,
        status: statusFilter,
        severity: severityFilter
      });
      setIssues(response.items);
      setTotal(response.total);
    } catch (error) {
      message.error('加载问题列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleProjectSelect = (pId: number) => {
    navigate(`/issues/project/${pId}`);
  };

  const handleCreate = async (values: any) => {
    if (!projectId) return;
    try {
      await issueApi.create({
        project_id: projectId,
        ...values
      });
      message.success('创建问题成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchIssues();
    } catch (error) {
      message.error('创建问题失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await issueApi.delete(id);
      message.success('删除成功');
      fetchIssues();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleStatusChange = async (id: number, action: string) => {
    try {
      switch (action) {
        case 'resolve':
          await issueApi.resolve(id);
          message.success('已解决');
          break;
        case 'close':
          await issueApi.close(id);
          message.success('已关闭');
          break;
        case 'reopen':
          await issueApi.reopen(id);
          message.success('已重新打开');
          break;
      }
      fetchIssues();
    } catch (error) {
      message.error('操作失败');
    }
  };

  const handleExport = async (format: 'excel' | 'csv' | 'json') => {
    if (!projectId) return;
    try {
      const blob = await issueApi.export({
        project_id: projectId,
        format,
        status: statusFilter,
        severity: severityFilter
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `issues_${projectId}.${format === 'excel' ? 'xlsx' : format}`;
      a.click();
      window.URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
    }
  };

  const getStatusTag = (status: string) => {
    const option = STATUS_OPTIONS.find(o => o.value === status);
    return <Tag color={option?.color}>{option?.label || status}</Tag>;
  };

  const getSeverityTag = (severity: string) => {
    const option = SEVERITY_OPTIONS.find(o => o.value === severity);
    return (
      <Tag color={option?.color}>
        {option?.label || severity}
      </Tag>
    );
  };

  const getPriorityTag = (priority: string) => {
    const option = PRIORITY_OPTIONS.find(o => o.value === priority);
    return <Tag color={option?.color}>{option?.label || priority}</Tag>;
  };

  const columns: ColumnsType<Issue> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text, record) => (
        <a onClick={() => {
          setSelectedIssue(record);
          setDetailDrawerVisible(true);
        }}>
          {text}
        </a>
      )
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity) => getSeverityTag(severity)
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 100,
      render: (priority) => getPriorityTag(priority)
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => getStatusTag(status)
    },
    {
      title: '失败类型',
      dataIndex: 'failure_type',
      key: 'failure_type',
      width: 120,
      render: (type) => {
        const option = FAILURE_TYPE_OPTIONS.find(o => o.value === type);
        return type ? <Tag>{option?.label || type}</Tag> : '-';
      }
    },
    {
      title: 'AI置信度',
      dataIndex: 'ai_confidence',
      key: 'ai_confidence',
      width: 100,
      render: (confidence) => confidence ? `${confidence}%` : '-'
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
        <Space size="small">
          <Dropdown
            menu={{
              items: [
                { key: 'resolve', label: '标记为已解决' },
                { key: 'close', label: '关闭问题' },
                { key: 'reopen', label: '重新打开' }
              ],
              onClick: ({ key }) => handleStatusChange(record.id, key)
            }}
          >
            <Button size="small">状态变更</Button>
          </Dropdown>
          <Popconfirm
            title="确定删除此问题？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )
    }
  ];

  const exportMenu = (
    <Menu>
      <Menu.Item key="excel" onClick={() => handleExport('excel')}>
        导出为 Excel
      </Menu.Item>
      <Menu.Item key="csv" onClick={() => handleExport('csv')}>
        导出为 CSV
      </Menu.Item>
      <Menu.Item key="json" onClick={() => handleExport('json')}>
        导出为 JSON
      </Menu.Item>
    </Menu>
  );

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
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <Input
              placeholder="搜索问题标题或描述"
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              onPressEnter={fetchIssues}
              allowClear
            />
          </Col>
          <Col span={4}>
            <Select
              placeholder="状态筛选"
              style={{ width: '100%' }}
              allowClear
              value={statusFilter}
              onChange={setStatusFilter}
            >
              {STATUS_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Col>
          <Col span={4}>
            <Select
              placeholder="严重程度筛选"
              style={{ width: '100%' }}
              allowClear
              value={severityFilter}
              onChange={setSeverityFilter}
            >
              {SEVERITY_OPTIONS.map(opt => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Col>
          <Col span={8} style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => navigate('/issues')}>
                切换项目
              </Button>
              <Button icon={<ReloadOutlined />} onClick={fetchIssues}>
                刷新
              </Button>
              <Dropdown overlay={exportMenu}>
                <Button icon={<ExportOutlined />}>导出</Button>
              </Dropdown>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalVisible(true)}
              >
                新建问题
              </Button>
            </Space>
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={issues}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            }
          }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[])
          }}
        />
      </Card>

      <Modal
        title="新建问题"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="title"
            label="问题标题"
            rules={[{ required: true, message: '请输入问题标题' }]}
          >
            <Input placeholder="请输入问题标题" maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label="问题描述">
            <TextArea rows={4} placeholder="请详细描述问题" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="severity" label="严重程度" initialValue="medium">
                <Select>
                  {SEVERITY_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="priority" label="优先级" initialValue="P2">
                <Select>
                  {PRIORITY_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="failure_type" label="失败类型">
                <Select allowClear>
                  {FAILURE_TYPE_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>{opt.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Drawer
        title="问题详情"
        placement="right"
        width={700}
        open={detailDrawerVisible}
        onClose={() => setDetailDrawerVisible(false)}
      >
        {selectedIssue && (
          <div>
            <Descriptions column={2} bordered>
              <Descriptions.Item label="问题ID">{selectedIssue.id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                {getStatusTag(selectedIssue.status)}
              </Descriptions.Item>
              <Descriptions.Item label="严重程度">
                {getSeverityTag(selectedIssue.severity)}
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                {getPriorityTag(selectedIssue.priority)}
              </Descriptions.Item>
              <Descriptions.Item label="失败类型">
                {selectedIssue.failure_type || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="根本原因">
                {selectedIssue.root_cause || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {dayjs(selectedIssue.created_at).format('YYYY-MM-DD HH:mm:ss')}
              </Descriptions.Item>
              <Descriptions.Item label="标题" span={2}>
                {selectedIssue.title}
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedIssue.description || '-'}
                </div>
              </Descriptions.Item>
            </Descriptions>

            {selectedIssue.ai_analysis && (
              <Card title="AI分析结果" style={{ marginTop: 16 }}>
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedIssue.ai_analysis}
                </div>
                {selectedIssue.ai_confidence && (
                  <div style={{ marginTop: 8 }}>
                    <Tag color="blue">置信度: {selectedIssue.ai_confidence}%</Tag>
                  </div>
                )}
              </Card>
            )}

            {selectedIssue.ai_suggestion && (
              <Card title="AI建议" style={{ marginTop: 16 }}>
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedIssue.ai_suggestion}
                </div>
              </Card>
            )}

            <div style={{ marginTop: 16 }}>
              <Space>
                <Button
                  type="primary"
                  onClick={() => handleStatusChange(selectedIssue.id, 'resolve')}
                  disabled={selectedIssue.status === 'resolved'}
                >
                  标记为已解决
                </Button>
                <Button
                  onClick={() => handleStatusChange(selectedIssue.id, 'close')}
                  disabled={selectedIssue.status === 'closed'}
                >
                  关闭问题
                </Button>
                <Button
                  onClick={() => handleStatusChange(selectedIssue.id, 'reopen')}
                  disabled={selectedIssue.status === 'open' || selectedIssue.status === 'in_progress'}
                >
                  重新打开
                </Button>
              </Space>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default IssueListPage;