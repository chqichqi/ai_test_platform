import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Select, message, Tag, Avatar, Space,
  Popconfirm, Typography, Tooltip, Input
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, UserOutlined, CrownOutlined,
  TeamOutlined, CodeOutlined, EyeOutlined
} from '@ant-design/icons';
import { projectMemberApi, ProjectMember, ProjectRole } from '../../api/projectExtApi';

const { Text } = Typography;

interface ProjectMembersProps {
  projectId: number;
  isOwner: boolean;
}

const roleIcons: Record<string, React.ReactNode> = {
  owner: <CrownOutlined style={{ color: '#faad14' }} />,
  test_lead: <TeamOutlined style={{ color: '#52c41a' }} />,
  tester: <CodeOutlined style={{ color: '#1890ff' }} />,
  developer: <CodeOutlined style={{ color: '#722ed1' }} />,
  viewer: <EyeOutlined style={{ color: '#8c8c8c' }} />,
};

const roleColors: Record<string, string> = {
  owner: 'gold',
  test_lead: 'green',
  tester: 'blue',
  developer: 'purple',
  viewer: 'default',
};

const roleNames: Record<string, string> = {
  owner: '所有者',
  test_lead: '测试负责人',
  tester: '测试人员',
  developer: '开发人员',
  viewer: '观察者',
};

const ProjectMembers: React.FC<ProjectMembersProps> = ({ projectId, isOwner }) => {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [transferModalVisible, setTransferModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [transferForm] = Form.useForm();

  useEffect(() => {
    fetchMembers();
    fetchRoles();
  }, [projectId]);

  const fetchMembers = async () => {
    setLoading(true);
    try {
      const data = await projectMemberApi.list(projectId);
      setMembers(data.items);
    } catch (error: any) {
      message.error('获取成员列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchRoles = async () => {
    try {
      const data = await projectMemberApi.getRoles();
      setRoles(data);
    } catch (error) {
      console.error('获取角色列表失败', error);
    }
  };

  const handleAddMember = async (values: any) => {
    try {
      await projectMemberApi.create(projectId, {
        user_id: values.user_id,
        role: values.role,
      });
      message.success('添加成员成功');
      setModalVisible(false);
      form.resetFields();
      fetchMembers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '添加成员失败');
    }
  };

  const handleUpdateRole = async (memberId: number, newRole: string) => {
    try {
      await projectMemberApi.update(projectId, memberId, { role: newRole });
      message.success('更新角色成功');
      fetchMembers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新角色失败');
    }
  };

  const handleRemoveMember = async (memberId: number) => {
    try {
      await projectMemberApi.delete(projectId, memberId);
      message.success('移除成员成功');
      fetchMembers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '移除成员失败');
    }
  };

  const handleTransferOwnership = async (values: any) => {
    try {
      await projectMemberApi.transferOwnership(projectId, values.new_owner_id);
      message.success('项目所有权转移成功');
      setTransferModalVisible(false);
      transferForm.resetFields();
      fetchMembers();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '转移所有权失败');
    }
  };

  const columns = [
    {
      title: '用户',
      key: 'user',
      render: (_: any, record: ProjectMember) => (
        <Space>
          <Avatar
            src={record.user.avatar}
            icon={<UserOutlined />}
            size="small"
          />
          <div>
            <Text strong>{record.user.full_name || record.user.username}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>{record.user.email}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string, record: ProjectMember) => {
        if (isOwner && record.role !== 'owner') {
          return (
            <Select
              value={role}
              style={{ width: 120 }}
              onChange={(value) => handleUpdateRole(record.id, value)}
              size="small"
            >
              {roles.map((r) => (
                <Select.Option key={r.code} value={r.code}>
                  {roleIcons[r.code]} {r.name}
                </Select.Option>
              ))}
            </Select>
          );
        }
        return (
          <Tag color={roleColors[role]} icon={roleIcons[role]}>
            {roleNames[role] || role}
          </Tag>
        );
      },
    },
    {
      title: '加入时间',
      dataIndex: 'joined_at',
      key: 'joined_at',
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '邀请人',
      key: 'inviter',
      render: (_: any, record: ProjectMember) => (
        record.inviter ? (
          <Tooltip title={record.inviter.email}>
            <span>{record.inviter.full_name || record.inviter.username}</span>
          </Tooltip>
        ) : '-'
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: ProjectMember) => (
        <Space>
          {isOwner && record.role !== 'owner' && (
            <Popconfirm
              title="确定移除此成员？"
              onConfirm={() => handleRemoveMember(record.id)}
            >
              <Button type="link" danger icon={<DeleteOutlined />} size="small">
                移除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="项目成员"
      extra={
        isOwner && (
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setModalVisible(true)}
            >
              添加成员
            </Button>
            <Button
              onClick={() => setTransferModalVisible(true)}
            >
              转移所有权
            </Button>
          </Space>
        )
      }
    >
      <Table
        columns={columns}
        dataSource={members}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      {/* 添加成员模态框 */}
      <Modal
        title="添加项目成员"
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleAddMember}>
          <Form.Item
            name="user_id"
            label="用户ID"
            rules={[{ required: true, message: '请输入用户ID' }]}
          >
            <Input placeholder="请输入要添加的用户ID" />
          </Form.Item>
          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true, message: '请选择角色' }]}
            initialValue="viewer"
          >
            <Select placeholder="选择角色">
              {roles.filter(r => r.code !== 'owner').map((role) => (
                <Select.Option key={role.code} value={role.code}>
                  <Space>
                    {roleIcons[role.code]}
                    <span>{role.name}</span>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      - {role.description}
                    </Text>
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 转移所有权模态框 */}
      <Modal
        title="转移项目所有权"
        open={transferModalVisible}
        onCancel={() => {
          setTransferModalVisible(false);
          transferForm.resetFields();
        }}
        onOk={() => transferForm.submit()}
      >
        <Form form={transferForm} layout="vertical" onFinish={handleTransferOwnership}>
          <Form.Item>
            <Text type="warning">
              警告：转移所有权后，您将失去项目所有者权限。此操作不可撤销。
            </Text>
          </Form.Item>
          <Form.Item
            name="new_owner_id"
            label="新所有者用户ID"
            rules={[{ required: true, message: '请输入新所有者用户ID' }]}
          >
            <Input placeholder="请输入新所有者的用户ID" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ProjectMembers;
