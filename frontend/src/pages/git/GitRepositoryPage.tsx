import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Input, Space, Tag, Modal, Form, message,
  Popconfirm, Select, Typography, Row, Col, Tooltip, Tabs, Spin
} from 'antd';
import {
  PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined,
  ApiOutlined, SyncOutlined,
  BranchesOutlined
} from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import { gitApi } from '../../api/gitApi';
import type { GitRepository, GitRepositoryCreate, GitRepositoryUpdate, GitBranch, GitCommit } from '../../api/gitApi';

const { Text } = Typography;
const { Search } = Input;

const GitRepositoryPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();

  const [loading, setLoading] = useState(false);
  const [repositories, setRepositories] = useState<GitRepository[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [search, setSearch] = useState('');

  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingRepo, setEditingRepo] = useState<GitRepository | null>(null);

  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<GitRepository | null>(null);
  const [branches, setBranches] = useState<GitBranch[]>([]);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    fetchRepositories();
  }, [page, pageSize, projectId]);

  const fetchRepositories = async () => {
    setLoading(true);
    try {
      const response = await gitApi.listRepositories({
        page,
        page_size: pageSize,
        project_id: projectId ? Number(projectId) : undefined,
        search: search || undefined,
      });
      setRepositories(response.items);
      setTotal(response.total);
    } catch (error) {
      message.error('获取仓库列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (values: GitRepositoryCreate) => {
    try {
      await gitApi.createRepository(values);
      message.success('创建仓库成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchRepositories();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建仓库失败');
    }
  };

  const handleUpdate = async (values: GitRepositoryUpdate) => {
    if (!editingRepo) return;
    try {
      await gitApi.updateRepository(editingRepo.id, values);
      message.success('更新仓库成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingRepo(null);
      fetchRepositories();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新仓库失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await gitApi.deleteRepository(id);
      message.success('删除仓库成功');
      fetchRepositories();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除仓库失败');
    }
  };

  const handleTestConnection = async (id: number) => {
    setTesting(true);
    try {
      const result = await gitApi.testConnection(id);
      if (result.success) {
        message.success(`连接成功！发现 ${result.branch_count || 0} 个分支`);
      } else {
        message.error(result.message);
      }
      fetchRepositories();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '连接测试失败');
    } finally {
      setTesting(false);
    }
  };

  const handleSync = async (id: number) => {
    try {
      const result = await gitApi.syncRepository(id);
      if (result.success) {
        message.success(`同步成功！分支: ${result.branches_synced}, 提交: ${result.commits_synced}`);
        fetchRepositories();
      } else {
        message.error(result.message);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '同步失败');
    }
  };

  const openEditModal = (repo: GitRepository) => {
    setEditingRepo(repo);
    editForm.setFieldsValue({
      name: repo.name,
      auth_type: repo.auth_type,
      default_branch: repo.default_branch,
      status: repo.status,
    });
    setEditModalVisible(true);
  };

  const openDetailModal = async (repo: GitRepository) => {
    setSelectedRepo(repo);
    setDetailModalVisible(true);
    setDetailLoading(true);
    
    try {
      const [branchesRes, commitsRes] = await Promise.all([
        gitApi.listBranches(repo.id),
        gitApi.listCommits(repo.id, { page_size: 10 }),
      ]);
      setBranches(branchesRes.items);
      setCommits(commitsRes.items);
    } catch (error) {
      message.error('获取详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'active':
        return <Tag color="green">活跃</Tag>;
      case 'inactive':
        return <Tag color="orange">未激活</Tag>;
      case 'error':
        return <Tag color="red">错误</Tag>;
      default:
        return <Tag>{status}</Tag>;
    }
  };

  const getSyncStatusTag = (status: string | null) => {
    if (!status) return <Tag>未同步</Tag>;
    return status === 'success' 
      ? <Tag color="green">同步成功</Tag>
      : <Tag color="red">同步失败</Tag>;
  };

  const columns = [
    {
      title: '仓库名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: GitRepository) => (
        <Space>
          <BranchesOutlined />
          <a onClick={() => openDetailModal(record)}>{text}</a>
        </Space>
      ),
    },
    {
      title: '仓库URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (text: string) => (
        <Tooltip title={text}>
          <Text code style={{ maxWidth: 300, display: 'inline-block' }} ellipsis>
            {text}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '默认分支',
      dataIndex: 'default_branch',
      key: 'default_branch',
      render: (text: string) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: '认证类型',
      dataIndex: 'auth_type',
      key: 'auth_type',
      render: (text: string) => {
        const types: Record<string, string> = {
          none: '无',
          token: 'Token',
          ssh: 'SSH密钥',
          password: '用户名密码',
        };
        return types[text] || text;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '同步状态',
      key: 'sync_status',
      render: (_: any, record: GitRepository) => (
        <Space direction="vertical" size="small">
          {getSyncStatusTag(record.last_sync_status)}
          {record.last_sync_at && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(record.last_sync_at).toLocaleString('zh-CN')}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: GitRepository) => (
        <Space>
          <Tooltip title="连接测试">
            <Button
              type="link"
              icon={<ApiOutlined />}
              onClick={() => handleTestConnection(record.id)}
              loading={testing}
            />
          </Tooltip>
          <Tooltip title="同步">
            <Button
              type="link"
              icon={<SyncOutlined />}
              onClick={() => handleSync(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="link"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此仓库？"
            description="删除后历史数据将保留"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const branchColumns = [
    { title: '分支名称', dataIndex: 'name', key: 'name' },
    {
      title: '最后提交',
      dataIndex: 'last_commit_hash',
      key: 'last_commit_hash',
      render: (hash: string) => hash ? <Text code>{hash.substring(0, 7)}</Text> : '-',
    },
    {
      title: '提交者',
      dataIndex: 'last_commit_author',
      key: 'last_commit_author',
    },
    {
      title: '是否默认',
      dataIndex: 'is_default',
      key: 'is_default',
      render: (v: number) => v ? <Tag color="blue">默认</Tag> : null,
    },
  ];

  const commitColumns = [
    {
      title: '提交哈希',
      dataIndex: 'short_hash',
      key: 'short_hash',
      render: (hash: string) => <Text code>{hash}</Text>,
    },
    {
      title: '分支',
      dataIndex: 'branch',
      key: 'branch',
      render: (branch: string) => branch ? <Tag>{branch}</Tag> : '-',
    },
    {
      title: '提交信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '提交者',
      dataIndex: 'author',
      key: 'author',
    },
    {
      title: '时间',
      dataIndex: 'committed_at',
      key: 'committed_at',
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
  ];

  return (
    <div style={{ padding: 6 }}>
      <Card>
        <div style={{ marginBottom: 16 }}>
          <Row gutter={16} align="middle">
            <Col span={8}>
              <Search
                placeholder="搜索仓库名称或URL"
                allowClear
                onSearch={(value) => {
                  setSearch(value);
                  setPage(1);
                  fetchRepositories();
                }}
                enterButton={<SearchOutlined />}
              />
            </Col>
            <Col span={16} style={{ textAlign: 'right' }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalVisible(true)}
              >
                添加仓库
              </Button>
            </Col>
          </Row>
        </div>

        <Table
          columns={columns}
          dataSource={repositories}
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
            },
          }}
        />
      </Card>

      <Modal
        title="添加仓库"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          {projectId && (
            <Form.Item name="project_id" initialValue={Number(projectId)} hidden>
              <Input />
            </Form.Item>
          )}
          <Form.Item
            name="name"
            label="仓库名称"
            rules={[{ required: true, message: '请输入仓库名称' }]}
          >
            <Input placeholder="如: my-project" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="url"
            label="仓库URL"
            rules={[{ required: true, message: '请输入仓库URL' }]}
          >
            <Input placeholder="如: git@github.com:user/repo.git" />
          </Form.Item>
          <Form.Item name="auth_type" label="认证类型" initialValue="none">
            <Select>
              <Select.Option value="none">无</Select.Option>
              <Select.Option value="token">Token</Select.Option>
              <Select.Option value="ssh">SSH密钥</Select.Option>
              <Select.Option value="password">用户名密码</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, curr) => prev.auth_type !== curr.auth_type}
          >
            {({ getFieldValue }) => {
              const authType = getFieldValue('auth_type');
              if (authType === 'token') {
                return (
                  <Form.Item name="auth_token" label="Token">
                    <Input.TextArea rows={3} placeholder="请输入访问Token" />
                  </Form.Item>
                );
              }
              if (authType === 'ssh') {
                return (
                  <Form.Item name="ssh_key" label="SSH私钥">
                    <Input.TextArea rows={5} placeholder="请输入SSH私钥内容" />
                  </Form.Item>
                );
              }
              if (authType === 'password') {
                return (
                  <>
                    <Form.Item name="username" label="用户名">
                      <Input placeholder="Git用户名" />
                    </Form.Item>
                    <Form.Item name="password" label="密码">
                      <Input.Password placeholder="Git密码" />
                    </Form.Item>
                  </>
                );
              }
              return null;
            }}
          </Form.Item>
          <Form.Item name="default_branch" label="默认分支" initialValue="main">
            <Input placeholder="默认: main" maxLength={50} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑仓库"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          editForm.resetFields();
          setEditingRepo(null);
        }}
        onOk={() => editForm.submit()}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="name" label="仓库名称" rules={[{ required: true }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="default_branch" label="默认分支">
            <Input maxLength={50} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              <Select.Option value="active">活跃</Select.Option>
              <Select.Option value="inactive">未激活</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={selectedRepo?.name || '仓库详情'}
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedRepo(null);
          setBranches([]);
          setCommits([]);
        }}
        footer={null}
        width={900}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
          </div>
        ) : (
          <Tabs defaultActiveKey="branches">
            <Tabs.TabPane tab={`分支 (${branches.length})`} key="branches">
              <Table
                columns={branchColumns}
                dataSource={branches}
                rowKey="id"
                pagination={false}
                size="small"
              />
            </Tabs.TabPane>
            <Tabs.TabPane tab="最近提交" key="commits">
              <Table
                columns={commitColumns}
                dataSource={commits}
                rowKey="id"
                pagination={false}
                size="small"
              />
            </Tabs.TabPane>
          </Tabs>
        )}
      </Modal>
    </div>
  );
};

export default GitRepositoryPage;