import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Input, Space, Tag, Modal, Form, message,
  Popconfirm, Select, Typography, Row, Col, DatePicker, Tooltip
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  EyeOutlined, CalendarOutlined, HistoryOutlined
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { versionApi } from '../../api/projectApi';
import type { Version, VersionCreate, VersionUpdate } from '../../api/projectApi';

const { Title } = Typography;
const { Search } = Input;
const { RangePicker } = DatePicker;

const VersionListPage: React.FC = () => {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingVersion, setEditingVersion] = useState<Version | null>(null);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0
  });

  const statusColors: Record<string, string> = {
    planning: 'blue',
    developing: 'orange',
    testing: 'purple',
    frozen: 'cyan',
    released: 'green',
    archived: 'default'
  };

  const statusLabels: Record<string, string> = {
    planning: '规划中',
    developing: '开发中',
    testing: '测试中',
    frozen: '冻结',
    released: '已发布',
    archived: '已归档'
  };

  useEffect(() => {
    fetchVersions();
  }, [projectId, pagination.current, pagination.pageSize, searchText, statusFilter]);

  const fetchVersions = async () => {
    setLoading(true);
    try {
      let response;
      if (projectId) {
        response = await versionApi.listByProject(Number(projectId), {
          page: pagination.current,
          page_size: pagination.pageSize,
          status_filter: statusFilter || undefined
        });
      } else {
        response = await versionApi.list({
          page: pagination.current,
          page_size: pagination.pageSize,
          search: searchText || undefined,
          status_filter: statusFilter || undefined
        });
      }
      setVersions(response.items);
      setPagination(prev => ({ ...prev, total: response.total }));
    } catch (error: any) {
      message.error('获取版本列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values: VersionCreate) => {
    try {
      await versionApi.create(values);
      message.success('创建版本成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchVersions();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建版本失败');
    }
  };

  const handleUpdate = async (values: VersionUpdate) => {
    if (!editingVersion) return;
    try {
      await versionApi.update(editingVersion.id, values);
      message.success('更新版本成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingVersion(null);
      fetchVersions();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新版本失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await versionApi.delete(id);
      message.success('删除版本成功');
      fetchVersions();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除版本失败');
    }
  };

  const openEditModal = (version: Version) => {
    setEditingVersion(version);
    editForm.setFieldsValue({
      version_name: version.version_name,
      description: version.description,
      plan_start_date: version.plan_start_date ? new Date(version.plan_start_date) : null,
      plan_end_date: version.plan_end_date ? new Date(version.plan_end_date) : null,
    });
    setEditModalVisible(true);
  };

  const columns = [
    {
      title: '版本号',
      dataIndex: 'version_number',
      key: 'version_number',
      render: (text: string, record: Version) => (
        <Space>
          <span style={{ fontWeight: 500 }}>{text}</span>
          {record.version_name && (
            <span style={{ color: '#666', fontSize: 12 }}>({record.version_name})</span>
          )}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusColors[status] || 'default'}>
          {statusLabels[status] || status}
        </Tag>
      ),
    },
    {
      title: '计划时间',
      key: 'plan_time',
      render: (_: any, record: Version) => (
        <Space>
          <CalendarOutlined />
          <span>
            {record.plan_start_date ? new Date(record.plan_start_date).toLocaleDateString() : '-'}
            {' ~ '}
            {record.plan_end_date ? new Date(record.plan_end_date).toLocaleDateString() : '-'}
          </span>
        </Space>
      ),
    },
    {
      title: '实际时间',
      key: 'actual_time',
      render: (_: any, record: Version) => (
        <Space>
          <HistoryOutlined />
          <span>
            {record.actual_start_date ? new Date(record.actual_start_date).toLocaleDateString() : '-'}
            {' ~ '}
            {record.actual_end_date ? new Date(record.actual_end_date).toLocaleDateString() : '-'}
          </span>
        </Space>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: Version) => (
        <Space>
          <Tooltip title="查看详情">
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/versions/${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description={`确定要删除版本 "${record.version_number}" 吗？`}
            onConfirm={() => handleDelete(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button type="text" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '6px' }}>
      <Card>
        <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
          <Col>
            <Title level={4}>版本管理</Title>
          </Col>
          <Col>
            <Space>
              <Select
                placeholder="状态筛选"
                allowClear
                style={{ width: 120 }}
                value={statusFilter}
                onChange={setStatusFilter}
              >
                <Select.Option value="planning">规划中</Select.Option>
                <Select.Option value="developing">开发中</Select.Option>
                <Select.Option value="testing">测试中</Select.Option>
                <Select.Option value="frozen">冻结</Select.Option>
                <Select.Option value="released">已发布</Select.Option>
                <Select.Option value="archived">已归档</Select.Option>
              </Select>
              <Search
                placeholder="搜索版本号/名称"
                allowClear
                onSearch={setSearchText}
                style={{ width: 250 }}
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalVisible(true)}
              >
                创建版本
              </Button>
            </Space>
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={versions}
          rowKey="id"
          loading={loading}
          pagination={{
            ...pagination,
            onChange: (page, pageSize) => {
              setPagination({ current: page, pageSize: pageSize || 10, total: pagination.total });
            },
          }}
        />
      </Card>

      {/* 创建版本弹窗 */}
      <Modal
        title="创建版本"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form 
          form={form} 
          layout="vertical" 
          onFinish={handleCreate}
          initialValues={{ project_id: projectId ? Number(projectId) : undefined }}
        >
          {!projectId && (
            <Form.Item
              name="project_id"
              label="项目"
              rules={[{ required: true, message: '请选择项目' }]}
            >
              <Select placeholder="请选择项目">
                {/* 这里需要从项目列表获取 */}
              </Select>
            </Form.Item>
          )}
          <Form.Item
            name="version_number"
            label="版本号"
            rules={[
              { required: true, message: '请输入版本号' },
              { pattern: /^v?\d+(\.\d+)*(-[a-zA-Z0-9]+)?$/, message: '版本号格式无效，如: 1.0.0, v1.0.0' }
            ]}
          >
            <Input placeholder="如: 1.0.0 或 v1.0.0" />
          </Form.Item>
          <Form.Item name="version_name" label="版本名称">
            <Input placeholder="请输入版本名称" />
          </Form.Item>
          <Form.Item name="description" label="版本描述">
            <Input.TextArea placeholder="请输入版本描述" rows={3} />
          </Form.Item>
          <Form.Item label="计划时间">
            <RangePicker
              style={{ width: '100%' }}
              onChange={(dates) => {
                if (dates) {
                  form.setFieldsValue({
                    plan_start_date: dates[0]?.toDate(),
                    plan_end_date: dates[1]?.toDate()
                  });
                }
              }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑版本弹窗 */}
      <Modal
        title="编辑版本"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          editForm.resetFields();
          setEditingVersion(null);
        }}
        onOk={() => editForm.submit()}
        width={600}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="version_name" label="版本名称">
            <Input placeholder="请输入版本名称" />
          </Form.Item>
          <Form.Item name="description" label="版本描述">
            <Input.TextArea placeholder="请输入版本描述" rows={3} />
          </Form.Item>
          <Form.Item label="计划时间">
            <RangePicker
              style={{ width: '100%' }}
              onChange={(dates) => {
                if (dates) {
                  editForm.setFieldsValue({
                    plan_start_date: dates[0]?.toDate(),
                    plan_end_date: dates[1]?.toDate()
                  });
                }
              }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default VersionListPage;
