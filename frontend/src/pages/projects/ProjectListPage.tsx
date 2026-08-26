import React, { useState, useEffect } from 'react';
import {
  Card, Button, Input, Space, Tag, Modal, Form, message,
  Popconfirm, Select, Typography, Row, Col, Avatar, Spin, Radio,
  Table,
  DatePicker, Empty, Tooltip, Divider, Alert
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined,
  FolderOutlined, UserOutlined, BranchesOutlined, ApartmentOutlined,
  MobileOutlined, GlobalOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import dayjs from 'dayjs';
import { projectApi, versionApi } from '../../api/projectApi';
import {
  knowledgeGraphApi,
  type KnowledgeGraphResponse,
  type KnowledgeGraphGenerateRequest,
} from '../../api/knowledgeGraphApi';
import axiosInstance from '../../api/axiosConfig';
import type { Project, ProjectCreate, ProjectUpdate } from '../../types/project';
import type { Version } from '../../api/projectApi';
import { selectUser } from '../../store/slices/authSlice';
import GenerateKnowledgeGraphModal from '../../components/knowledgeGraph/GenerateKnowledgeGraphModal';

const { Text } = Typography;

const ProjectListPage: React.FC = () => {
  const navigate = useNavigate();
  const user = useSelector(selectUser);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [versionForm] = Form.useForm();

  // 项目状态
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);

  // 版本状态：按项目ID分组
  const [versionsMap, setVersionsMap] = useState<Record<number, Version[]>>({});
  const [loadingVersions, setLoadingVersions] = useState(false);

  // 知识图谱状态：按项目ID（入口在项目卡片，不再经项目详情页）
  const [kgMap, setKgMap] = useState<Record<number, KnowledgeGraphResponse | null>>({});
  // 生成弹窗当前项目（null=关闭）
  const [kgModalProjectId, setKgModalProjectId] = useState<number | null>(null);

  // 项目弹窗
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);

  // 项目配置弹窗
  const [exploreConfigVisible, setExploreConfigVisible] = useState(false);
  const [exploreConfigProject, setExploreConfigProject] = useState<Project | null>(null);
  const [exploreConfigForm] = Form.useForm();
  const [exploreConfigInit, setExploreConfigInit] = useState<Record<string, any>>({});
  // 环境管理
  const [environments, setEnvironments] = useState<{name: string; url: string}[]>([]);
  const [activeEnv, setActiveEnv] = useState('');
  const [envModalVisible, setEnvModalVisible] = useState(false);
  const [editingEnv, setEditingEnv] = useState<{name: string; url: string} | null>(null);
  const [envForm] = Form.useForm();

  // 版本弹窗
  const [versionModalVisible, setVersionModalVisible] = useState(false);
  const [editingVersion, setEditingVersion] = useState<Version | null>(null);

  useEffect(() => { fetchProjects(); }, []);

  // 项目列表加载后，获取所有项目的版本 + 知识图谱状态
  useEffect(() => {
    if (projects.length > 0) {
      fetchAllVersions();
      fetchAllKg();
    }
  }, [projects]);

  // ===== 项目相关 =====
  const fetchProjects = async () => {
    setLoading(true);
    try {
      const response = await projectApi.list({ page: 1, page_size: 100 });
      setProjects(response.items);
    } catch { message.error('获取项目列表失败'); }
    finally { setLoading(false); }
  };

  const handleCreate = async (values: ProjectCreate) => {
    try {
      console.log('[创建项目] 提交数据:', JSON.stringify(values));
      await projectApi.create(values);
      message.success('创建项目成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchProjects();
    } catch (error: any) {
      const detail = error.response?.data?.detail || error.message || '';
      console.error('[创建项目] 失败:', detail, error);
      message.error(detail || '创建项目失败，请检查后端日志');
    }
  };

  const handleUpdate = async (values: ProjectUpdate) => {
    if (!editingProject) return;
    try {
      await projectApi.update(editingProject.id, values);
      message.success('更新项目成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingProject(null);
      fetchProjects();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新项目失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await projectApi.delete(id);
      message.success('删除项目成功');
      if (selectedProjectId === id) setSelectedProjectId(null);
      fetchProjects();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除项目失败');
    }
  };

  const openEditModal = (project: Project) => {
    setEditingProject(project);
    editForm.setFieldsValue({
      name: project.name,
      description: project.description,
      status: project.status,
      owner_id: project.owner_id,
      project_type: project.project_type || 'web',
      app_platform: project.app_platform,
      app_package_name: project.app_package_name,
      app_launch_activity: project.app_launch_activity,
      app_bundle_id: project.app_bundle_id,
      app_device_type: project.app_device_type,
      app_device_udid: project.app_device_udid,
      app_simulator_name: project.app_simulator_name,
      app_automation_name: project.app_automation_name,
    });
    setEditModalVisible(true);
  };

  // ===== 版本相关 =====
  const fetchAllVersions = async () => {
    setLoadingVersions(true);
    const map: Record<number, Version[]> = {};
    try {
      for (const p of projects) {
        try {
          const response = await versionApi.listByProject(p.id, { page_size: 100 });
          map[p.id] = response.items;
        } catch { map[p.id] = []; }
      }
    } catch { /* ignore */ }
    setVersionsMap(map);
    setLoadingVersions(false);
  };

  const refreshProjectVersions = async (projectId: number) => {
    try {
      const response = await versionApi.listByProject(projectId, { page_size: 100 });
      setVersionsMap(prev => ({ ...prev, [projectId]: response.items }));
    } catch { /* ignore */ }
  };

  // ===== 知识图谱（入口在项目卡片） =====
  const fetchAllKg = async () => {
    const map: Record<number, KnowledgeGraphResponse | null> = {};
    await Promise.all(
      projects.map(async (p) => {
        try {
          const list = await knowledgeGraphApi.listByProject(p.id);
          map[p.id] = Array.isArray(list) && list.length > 0 ? list[0] : null;
        } catch {
          map[p.id] = null;
        }
      }),
    );
    setKgMap(map);
  };

  const handleOpenKg = (record: Project) => {
    const kg = kgMap[record.id] || null;
    // 已完成 → 直接进可视化
    if (kg && kg.exploration_status === 'completed') {
      navigate(`/knowledge-graph/${kg.id}`);
      return;
    }
    // 生成中 → 提示稍后再看
    if (kg && (kg.exploration_status === 'running' || kg.exploration_status === 'pending')) {
      message.info('知识图谱正在生成中，请稍后再查看');
      return;
    }
    // 失败 → 提示原因后重新生成
    if (kg && kg.exploration_status === 'failed' && kg.error_message) {
      message.warning(`上次生成失败：${kg.error_message}`);
    }
    // 未生成/失败 → 打开生成弹窗
    setKgModalProjectId(record.id);
  };

  const handleGenerateKg = async (request: KnowledgeGraphGenerateRequest) => {
    const res: any = await knowledgeGraphApi.generate(request);
    if (request.mode === 'crawl') {
      // 后台爬取任务已启动（由生成进度轮询跟踪）
      if (!res?.success) throw new Error(res?.message || '爬取任务启动失败');
      setKgModalProjectId(null);
      return;
    }
    // existing：同步秒级完成，直接进可视化
    if (res?.success && res?.data?.graph_id) {
      setKgModalProjectId(null);
      navigate(`/knowledge-graph/${res.data.graph_id}`);
      return;
    }
    if (res?.data?.needs_exploration) {
      // 暂无探索结果：不关弹窗，引导先探索或展开高级爬取
      message.warning(res.message || '暂无探索结果，请先导入登录模块或转化功能用例');
      throw new Error(res.message);
    }
    message.error(res.message || '知识图谱生成失败');
    throw new Error(res.message);
  };

  const handleCreateVersion = async (values: any) => {
    const pid = values._project_id || selectedProjectId;
    if (!pid) { message.error('请先选择项目'); return; }
    try {
      await versionApi.create({
        project_id: pid,
        version_number: values.version_number,
        version_name: values.version_name,
        description: values.description,
        plan_start_date: values.plan_start_date?.toISOString(),
        plan_end_date: values.plan_end_date?.toISOString(),
      }, false, false);
      message.success('创建版本成功');
      setVersionModalVisible(false);
      versionForm.resetFields();
      refreshProjectVersions(pid);
    } catch (error: any) {
      const detail = error.response?.data?.message || error.response?.data?.error
        || error.response?.data?.detail || error.message || '创建版本失败';
      message.error(detail);
    }
  };

  const handleUpdateVersion = async (values: any) => {
    if (!editingVersion) return;
    try {
      await versionApi.update(editingVersion.id, {
        version_name: values.version_name,
        description: values.description,
        plan_start_date: values.plan_start_date?.toISOString(),
        plan_end_date: values.plan_end_date?.toISOString(),
      });
      message.success('更新版本成功');
      setVersionModalVisible(false);
      versionForm.resetFields();
      setEditingVersion(null);
      refreshProjectVersions(selectedProjectId!);
    } catch (error: any) {
      const detail = error.response?.data?.message || error.response?.data?.error
        || error.response?.data?.detail || '更新版本失败';
      message.error(detail);
    }
  };

  const handleDeleteVersion = async (projectId: number, versionId: number) => {
    try {
      await versionApi.delete(versionId);
      message.success('删除版本成功');
      refreshProjectVersions(projectId);
    } catch (error: any) {
      const detail = error.response?.data?.message || error.response?.data?.error
        || error.response?.data?.detail || '删除版本失败';
      message.error(detail);
    }
  };

  const openVersionModal = (ver?: Version) => {
    if (ver) {
      setEditingVersion(ver);
      versionForm.setFieldsValue({
        version_number: ver.version_number,
        version_name: ver.version_name,
        description: ver.description,
        plan_start_date: ver.plan_start_date ? dayjs(ver.plan_start_date) : null,
        plan_end_date: ver.plan_end_date ? dayjs(ver.plan_end_date) : null,
      });
    } else {
      setEditingVersion(null);
      // 保存 _project_id 再 reset
      const savedPid = versionForm.getFieldValue('_project_id');
      versionForm.resetFields();
      if (savedPid) versionForm.setFieldsValue({ _project_id: savedPid });
    }
    setVersionModalVisible(true);
  };

  const openExploreConfig = async (project: Project) => {
    setExploreConfigProject(project);
    setExploreConfigInit({});  // 先清空触发 Form 重建
    setExploreConfigVisible(true);
    try {
      const res = await axiosInstance.get(`/projects/${project.id}/settings?_t=${Date.now()}`);
      const web = (res.data?.exploration_config || {}).web || {};
      const envs = web.environments || [];
      // 兼容旧格式：base_url 转为单环境
      if (!envs.length && web.base_url) {
        envs.push({name: '默认环境', url: web.base_url});
      }
      setEnvironments(envs);
      setActiveEnv(web.active_environment || (envs[0]?.name || ''));
      setExploreConfigInit({
        base_url: web.active_environment ? (envs.find((e: any) => e.name === web.active_environment)?.url || '') : (web.base_url || ''),
        web_username: web.username || '',
        web_password: web.password || '',
      });
    } catch { /* ignore */ }
  };

  const saveExploreConfig = async () => {
    const values = exploreConfigForm.getFieldsValue();
    const existing = await axiosInstance.get(`/projects/${exploreConfigProject?.id}/settings?_t=${Date.now()}`);
    const oldWeb = (existing.data?.exploration_config || {}).web || {};
    // 从当前 active environment 同步 base_url
    const activeEnvUrl = activeEnv ? (environments.find((e: any) => e.name === activeEnv)?.url || '') : '';
    const config = {
      web: {
        ...oldWeb,  // 保留 environments 等已即时保存的字段
        base_url: activeEnvUrl || values.base_url || oldWeb.base_url || '',
        username: values.web_username,
        password: values.web_password,
      },
    };
    try {
      await axiosInstance.patch(`/projects/${exploreConfigProject?.id}/settings/exploration`, config);
      message.success('项目配置已保存');
      setExploreConfigVisible(false);
    } catch (e: any) { message.error('保存失败'); }
  };

  const saveEnvToServer = async (envs: {name: string; url: string}[], active: string) => {
    const existing = await axiosInstance.get(`/projects/${exploreConfigProject?.id}/settings?_t=${Date.now()}`);
    const oldCfg = existing.data?.exploration_config || {};
    const oldWeb = oldCfg.web || {};
    await axiosInstance.patch(`/projects/${exploreConfigProject?.id}/settings/exploration`, {
      web: { ...oldWeb, environments: envs, active_environment: active },
    });
  };

  const handleDeleteEnv = async (name: string) => {
    const updated = environments.filter(e => e.name !== name);
    const newActive = activeEnv === name ? (updated[0]?.name || '') : activeEnv;
    setEnvironments(updated);
    setActiveEnv(newActive);
    await saveEnvToServer(updated, newActive);
    message.success('环境已删除');
  };

  const handleEnvSave = async () => {
    const vals = envForm.getFieldsValue();
    if (!vals.env_name?.trim() || !vals.env_url?.trim()) return;
    const newEnv = {name: vals.env_name.trim(), url: vals.env_url.trim()};
    let updated: {name: string; url: string}[];
    if (editingEnv) {
      updated = environments.map(e => e.name === editingEnv.name ? newEnv : e);
    } else {
      updated = [...environments, newEnv];
    }
    const newActive = editingEnv ? (activeEnv === editingEnv.name ? newEnv.name : activeEnv) : (activeEnv || newEnv.name);
    setEnvironments(updated);
    setActiveEnv(newActive);
    await saveEnvToServer(updated, newActive);
    setEnvModalVisible(false);
    setEditingEnv(null);
    envForm.resetFields();
    message.success(editingEnv ? '环境已更新' : '环境已添加');
  };
  const handleEnvChange = (name: string) => {
    setActiveEnv(name);
    const env = environments.find(e => e.name === name);
    if (env) exploreConfigForm.setFieldsValue({ base_url: env.url });
  };

  return (
    <div style={{ padding: 6, height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      <Card
        title={<Space><FolderOutlined /> 项目及版本 ({projects.length})</Space>}
        extra={
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
            创建项目
          </Button>
        }
        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        bodyStyle={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}
      >
            <Spin spinning={loading}>
              {projects.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Empty description="暂无项目" />
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignContent: 'flex-start' }}>
                  {projects.map((record) => {
                    const isActive = record.status === 'active';
                    const isSelected = record.id === selectedProjectId;
                    const projectVersions = versionsMap[record.id] || [];
                    const kg = kgMap[record.id] || null;
                    return (
                      <Card
                        key={record.id}
                        size="small"
                        hoverable
                        style={{
                          width: 520,
                          minHeight: 190,
                          borderLeft: `4px solid ${isActive ? '#52c41a' : '#d9d9d9'}`,
                          background: isSelected ? '#fafafa' : undefined,
                        }}
                        bodyStyle={{ padding: '12px 14px', display: 'flex', flexDirection: 'column' }}
                        onClick={() => setSelectedProjectId(record.id)}
                      >
                        {/* 项目头部 */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                          <div style={{ display: 'flex', gap: 8, minWidth: 0, flex: 1 }}>
                            <FolderOutlined style={{ color: isActive ? '#1890ff' : '#999', marginTop: 4, flexShrink: 0 }} />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <Text strong style={{ fontSize: 14, wordBreak: 'break-all' }}>{record.name}</Text>
                              <div style={{ marginTop: 2, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                {record.project_type === 'app' ? (
                                  <MobileOutlined style={{ fontSize: 18, color: '#52c41a' }} />
                                ) : (
                                  <GlobalOutlined style={{ fontSize: 18, color: '#1890ff' }} />
                                )}
                                <Tag color={isActive ? 'green' : 'default'} style={{ fontSize: 11 }}>
                                  {isActive ? '活跃' : '已归档'}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: 11 }}>{record.code}</Text>
                                {kg && kg.exploration_status === 'completed' && (
                                  <Tag color="purple" style={{ fontSize: 11 }}>图谱{kg.page_count}页</Tag>
                                )}
                                {kg && kg.exploration_status === 'running' && (
                                  <Tag color="processing" style={{ fontSize: 11 }}>图谱生成中</Tag>
                                )}
                                {kg && kg.exploration_status === 'failed' && (
                                  <Tag color="red" style={{ fontSize: 11 }}>图谱失败</Tag>
                                )}
                              </div>
                            </div>
                          </div>
                          <Space size={2} style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                            <Tooltip title="知识图谱（基于已探索结果生成）"><Button size="small" icon={<ApartmentOutlined />}
                              onClick={() => handleOpenKg(record)} /></Tooltip>
                            <Tooltip title="项目配置"><Button size="small" icon={<SettingOutlined />}
                              onClick={() => openExploreConfig(record)} /></Tooltip>
                            <Tooltip title="编辑项目"><Button size="small" icon={<EditOutlined />}
                              onClick={() => openEditModal(record)} /></Tooltip>
                            <Popconfirm title="确定删除此项目？" onConfirm={() => handleDelete(record.id)}>
                              <Tooltip title="删除项目"><Button size="small" danger icon={<DeleteOutlined />} /></Tooltip>
                            </Popconfirm>
                          </Space>
                        </div>

                        {/* 版本列表（始终可见） */}
                        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px dashed #e8e8e8', flex: 1, overflow: 'auto' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {loadingVersions ? '加载中...' : `版本 (${projectVersions.length})`}
                            </Text>
                            <Tooltip title="添加版本">
                              <Button size="small" type="dashed" icon={<PlusOutlined />}
                                onClick={(e) => { e.stopPropagation(); setSelectedProjectId(record.id); versionForm.setFieldsValue({ _project_id: record.id }); openVersionModal(); }} />
                            </Tooltip>
                          </div>
                          {loadingVersions ? (
                            <Spin size="small" />
                          ) : projectVersions.length === 0 ? (
                            <Text type="secondary" style={{ fontSize: 12 }}>暂无版本</Text>
                          ) : (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                              {projectVersions.map((ver) => {
                                return (
                                  <Tooltip key={ver.id} title={`${ver.version_number} — 点击进入版本详情`}>
                                    <div
                                      style={{
                                        display: 'inline-flex', alignItems: 'center', gap: 3,
                                        padding: '3px 5px', cursor: 'pointer',
                                        borderRadius: 4, border: '1px solid #e8e8e8',
                                        background: '#fff', fontSize: 12,
                                        transition: 'box-shadow 0.2s, border-color 0.2s',
                                        maxWidth: 155,
                                      }}
                                      onMouseEnter={(e) => {
                                        e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.1)';
                                        e.currentTarget.style.borderColor = '#1890ff';
                                      }}
                                      onMouseLeave={(e) => {
                                        e.currentTarget.style.boxShadow = 'none';
                                        e.currentTarget.style.borderColor = '#e8e8e8';
                                      }}
                                      onClick={(e) => { e.stopPropagation(); navigate(`/projects/${record.id}/versions/${ver.id}`); }}
                                    >
                                      <BranchesOutlined style={{ color: '#1677ff', fontSize: 12 }} />
                                      <span style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {ver.version_number}
                                      </span>
                                      <Space size={0} onClick={(e) => e.stopPropagation()}>
                                        <Tooltip title="编辑版本"><Button type="text" size="small" icon={<EditOutlined />}
                                          style={{ fontSize: 11, height: 18, padding: '0 1px', minWidth: 18 }} onClick={() => openVersionModal(ver)} /></Tooltip>
                                        <Popconfirm title="确定删除？" onConfirm={() => handleDeleteVersion(record.id, ver.id)}>
                                          <Tooltip title="删除版本"><Button type="text" size="small" danger icon={<DeleteOutlined />}
                                            style={{ fontSize: 11, height: 18, padding: '0 1px', minWidth: 18 }} /></Tooltip>
                                        </Popconfirm>
                                      </Space>
                                    </div>
                                  </Tooltip>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}
            </Spin>
        </Card>

      {/* ===== 创建项目弹窗 ===== */}
      <Modal
        title="创建项目"
        open={createModalVisible}
        onCancel={() => { setCreateModalVisible(false); form.resetFields(); }}
        onOk={() => form.submit()}
        width={600}
        maskClosable={false}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}
          initialValues={{ project_type: 'web', owner_id: user?.id || 1 }}>
          <Form.Item name="project_type" label="项目类型" rules={[{ required: true }]}>
            <Radio.Group optionType="button" buttonStyle="solid" defaultValue="web" style={{ width: '100%' }}>
              <Radio.Button value="web" style={{ width: '50%', textAlign: 'center', height: 48, lineHeight: '48px' }}>
                <GlobalOutlined style={{ fontSize: 20, marginRight: 8 }} />Web 端
              </Radio.Button>
              <Radio.Button value="app" style={{ width: '50%', textAlign: 'center', height: 48, lineHeight: '48px' }}>
                <MobileOutlined style={{ fontSize: 20, marginRight: 8 }} />APP 端
              </Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="请输入项目名称" maxLength={100} />
          </Form.Item>
          <Form.Item name="code" label="项目编码" rules={[
            { required: true, message: '请输入项目编码' },
            { pattern: /^[a-zA-Z][a-zA-Z0-9_-]*$/, message: '编码必须以字母开头' },
          ]}>
            <Input placeholder="如: my-project" maxLength={50} />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea placeholder="请输入项目描述" rows={2} />
          </Form.Item>
          <Form.Item name="owner_id" label="项目负责人" rules={[{ required: true, message: '请选择负责人' }]}>
            <Select placeholder="请选择" showSearch optionFilterProp="label">
              {user && (
                <Select.Option value={user.id} label={user.username}>
                  <Space><Avatar size="small" icon={<UserOutlined />} /><span>{user.username}</span><Tag color="blue">当前用户</Tag></Space>
                </Select.Option>
              )}
            </Select>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(pv, cv) => pv.project_type !== cv.project_type || pv.app_platform !== cv.app_platform}>
            {({ getFieldValue }) => {
              const pt = getFieldValue('project_type');
              if (pt !== 'app') return null;
              const platform = getFieldValue('app_platform');
              return (
                <>
                  <Form.Item name="app_platform" label="📱 APP 平台类型" rules={[{ required: true, message: '请选择平台类型' }]}>
                    <Radio.Group optionType="button" buttonStyle="solid" style={{ width: '100%' }}>
                      <Radio.Button value="android" style={{ width: '50%', textAlign: 'center' }}>
                        🤖 Android
                      </Radio.Button>
                      <Radio.Button value="ios" style={{ width: '50%', textAlign: 'center' }}>
                        🍎 iOS
                      </Radio.Button>
                    </Radio.Group>
                  </Form.Item>

                  {platform === 'android' ? (
                    <>
                      <Alert type="info" showIcon style={{ marginBottom: 12, fontSize: 12 }}
                        message="Android 配置说明：Appium 使用 UiAutomator2 驱动，需要提供包名和启动 Activity" />
                      <Form.Item name="app_package_name" label="📦 应用包名 (appPackage)" rules={[{ required: true, message: '请输入应用包名' }]}>
                        <Input placeholder="如: com.example.app" maxLength={200} />
                      </Form.Item>
                      <Form.Item name="app_launch_activity" label="🚀 启动 Activity (appActivity)" rules={[{ required: true, message: '请输入启动Activity' }]}>
                        <Input placeholder="如: .MainActivity 或 com.example.app.MainActivity" maxLength={500} />
                      </Form.Item>
                      <Form.Item name="app_automation_name" label="⚙️ 自动化引擎">
                        <Select placeholder="默认 UiAutomator2">
                          <Select.Option value="UiAutomator2">UiAutomator2（推荐）</Select.Option>
                          <Select.Option value="Espresso">Espresso</Select.Option>
                        </Select>
                      </Form.Item>
                    </>
                  ) : platform === 'ios' ? (
                    <>
                      <Alert type="info" showIcon style={{ marginBottom: 12, fontSize: 12 }}
                        message="iOS 配置说明：Appium 使用 XCUITest 驱动，需要提供 Bundle ID 和设备信息" />
                      <Form.Item name="app_bundle_id" label="📦 Bundle ID" rules={[{ required: true, message: '请输入 Bundle ID' }]}>
                        <Input placeholder="如: com.example.app" maxLength={200} />
                      </Form.Item>
                      <Form.Item name="app_device_type" label="📱 设备类型">
                        <Select placeholder="请选择设备类型">
                          <Select.Option value="simulator">模拟器 (Simulator)</Select.Option>
                          <Select.Option value="real">真机 (Real Device)</Select.Option>
                        </Select>
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate={(pv, cv) => pv.app_device_type !== cv.app_device_type}>
                        {({ getFieldValue: getNested }) => {
                          const deviceType = getNested('app_device_type');
                          return deviceType === 'real' ? (
                            <Form.Item name="app_device_udid" label="🔢 设备 UDID" rules={[{ required: true, message: '真机需要填写UDID' }]}>
                              <Input placeholder="真机UDID（通过 Xcode → Window → Devices 获取）" maxLength={100} />
                            </Form.Item>
                          ) : deviceType === 'simulator' ? (
                            <Form.Item name="app_simulator_name" label="📱 模拟器名称">
                              <Input placeholder="如: iPhone 15 Pro（默认最新型号）" maxLength={100} />
                            </Form.Item>
                          ) : null;
                        }}
                      </Form.Item>
                      <Form.Item name="app_automation_name" label="⚙️ 自动化引擎">
                        <Select placeholder="默认 XCUITest">
                          <Select.Option value="XCUITest">XCUITest（推荐）</Select.Option>
                        </Select>
                      </Form.Item>
                    </>
                  ) : null}
                </>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>

      {/* ===== 编辑项目弹窗 ===== */}
      <Modal
        title="编辑项目"
        open={editModalVisible}
        onCancel={() => { setEditModalVisible(false); editForm.resetFields(); setEditingProject(null); }}
        onOk={() => editForm.submit()}
        width={600}
        maskClosable={false}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input placeholder="请输入项目名称" maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea placeholder="请输入项目描述" rows={3} />
          </Form.Item>
          <Form.Item name="owner_id" label="项目负责人">
            <Select placeholder="请选择" showSearch disabled={!user}>
              {user && <Select.Option value={user.id} label={user.username}><Space><Avatar size="small" icon={<UserOutlined />} /><span>{user.username}</span></Space></Select.Option>}
            </Select>
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select><Select.Option value="active">活跃</Select.Option><Select.Option value="archived">已归档</Select.Option></Select>
          </Form.Item>
          <Form.Item name="project_type" label="项目类型">
            <Radio.Group optionType="button" buttonStyle="solid" defaultValue="web">
              <Radio.Button value="web"><GlobalOutlined /> Web</Radio.Button>
              <Radio.Button value="app"><MobileOutlined /> APP</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(pv, cv) => pv.project_type !== cv.project_type || pv.app_platform !== cv.app_platform}>
            {({ getFieldValue }) => {
              const pt = getFieldValue('project_type');
              if (pt !== 'app') return null;
              const platform = getFieldValue('app_platform');
              return (
                <>
                  <Form.Item name="app_platform" label="📱 APP 平台类型">
                    <Radio.Group optionType="button" buttonStyle="solid" style={{ width: '100%' }}>
                      <Radio.Button value="android" style={{ width: '50%', textAlign: 'center' }}>🤖 Android</Radio.Button>
                      <Radio.Button value="ios" style={{ width: '50%', textAlign: 'center' }}>🍎 iOS</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                  {platform === 'android' ? (
                    <>
                      <Form.Item name="app_package_name" label="📦 应用包名"><Input maxLength={200} /></Form.Item>
                      <Form.Item name="app_launch_activity" label="🚀 启动Activity"><Input maxLength={500} /></Form.Item>
                      <Form.Item name="app_automation_name" label="⚙️ 自动化引擎">
                        <Select><Select.Option value="UiAutomator2">UiAutomator2</Select.Option><Select.Option value="Espresso">Espresso</Select.Option></Select>
                      </Form.Item>
                    </>
                  ) : platform === 'ios' ? (
                    <>
                      <Form.Item name="app_bundle_id" label="📦 Bundle ID"><Input maxLength={200} /></Form.Item>
                      <Form.Item name="app_device_type" label="📱 设备类型">
                        <Select><Select.Option value="simulator">模拟器</Select.Option><Select.Option value="real">真机</Select.Option></Select>
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate={(pv2, cv2) => pv2.app_device_type !== cv2.app_device_type}>
                        {({ getFieldValue: getNested }) => getNested('app_device_type') === 'real'
                          ? <Form.Item name="app_device_udid" label="🔢 设备 UDID"><Input maxLength={100} /></Form.Item>
                          : <Form.Item name="app_simulator_name" label="📱 模拟器名称"><Input maxLength={100} /></Form.Item>
                        }
                      </Form.Item>
                      <Form.Item name="app_automation_name" label="⚙️ 自动化引擎">
                        <Select><Select.Option value="XCUITest">XCUITest</Select.Option></Select>
                      </Form.Item>
                    </>
                  ) : null}
                </>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>

      {/* ===== 项目配置弹窗 ===== */}
      <Modal title={`项目配置 - ${exploreConfigProject?.name || ''}`} open={exploreConfigVisible}
        onCancel={() => setExploreConfigVisible(false)} onOk={saveExploreConfig} width={560} okText="保存" maskClosable={false}>
        <Form form={exploreConfigForm} layout="vertical"
          key={JSON.stringify(exploreConfigInit)}
          initialValues={exploreConfigInit}>
          <Form.Item label="目标环境" required>
            <div style={{ display: 'flex', gap: 8 }}>
              <Select
                value={activeEnv || undefined}
                onChange={handleEnvChange}
                placeholder="选择环境"
                style={{ flex: 1 }}
              >
                {environments.map(env => (
                  <Select.Option key={env.name} value={env.name}>{env.name} — {env.url}</Select.Option>
                ))}
              </Select>
              <Button icon={<SettingOutlined />} onClick={() => { setEditingEnv(null); envForm.resetFields(); setEnvModalVisible(true); }}>管理环境</Button>
            </div>
          </Form.Item>
          <Form.Item name="base_url" hidden><Input /></Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="web_username" label="登录用户名">
                <Input placeholder="手机号 / 用户名" autoComplete="new-password" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="web_password" label="登录密码">
                <Input.Password placeholder="密码" autoComplete="new-password" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* ===== 环境管理弹窗 ===== */}
      <Modal title="管理环境" open={envModalVisible}
        onCancel={() => setEnvModalVisible(false)} footer={null} width={560}>
        {/* 已有环境列表 */}
        {environments.length > 0 && (
          <Table dataSource={environments.map((e, i) => ({...e, key: i}))} pagination={false} size="small"
            style={{ marginBottom: 16 }}
            columns={[
              { title: '名称', dataIndex: 'name', width: 120 },
              { title: 'URL', dataIndex: 'url', ellipsis: true },
              { title: '', width: 100, render: (_: any, r: any) => (
                <Space size={2}>
                  <Button type="link" size="small" onClick={() => { setEditingEnv(r); envForm.setFieldsValue(r); }}>编辑</Button>
                  <Button type="link" size="small" danger onClick={() => handleDeleteEnv(r.name)}>删除</Button>
                </Space>
              )},
            ]}
          />
        )}
        {/* 添加/编辑表单 */}
        <Divider>{editingEnv ? '编辑环境' : '添加环境'}</Divider>
        <Form form={envForm} layout="vertical">
          <Row gutter={12} align="middle">
            <Col span={6}>
              <Form.Item name="env_name" label="名称" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                <Input placeholder="环境名称" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="env_url" label="URL" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                <Input placeholder="https://..." />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item label=" " style={{ marginBottom: 0 }}>
                <Space>
                  <Button type="primary" onClick={handleEnvSave}>{editingEnv ? '保存' : '添加'}</Button>
                  {editingEnv && <Button onClick={() => { setEditingEnv(null); envForm.resetFields(); }}>取消编辑</Button>}
                </Space>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* ===== 创建/编辑版本弹窗 ===== */}
      <Modal
        title={editingVersion ? '编辑版本' : '创建版本'}
        open={versionModalVisible}
        onCancel={() => { setVersionModalVisible(false); versionForm.resetFields(); setEditingVersion(null); }}
        onOk={() => versionForm.submit()}
        width={600}
        maskClosable={false}
      >
        <Form form={versionForm} layout="vertical" onFinish={editingVersion ? handleUpdateVersion : handleCreateVersion}>
          <Form.Item name="_project_id" hidden><Input /></Form.Item>
          {!editingVersion && (
            <Form.Item name="version_number" label="版本号" rules={[{ required: true, message: '请输入版本号' }]}>
              <Input placeholder="如: v1.0.0" maxLength={50} />
            </Form.Item>
          )}
          <Form.Item name="version_name" label="版本名称">
            <Input placeholder="如: 第一版" maxLength={100} />
          </Form.Item>
          <Form.Item name="description" label="版本描述">
            <Input.TextArea placeholder="请输入版本描述" rows={3} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="plan_start_date" label="计划开始日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="plan_end_date" label="计划结束日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* ===== 知识图谱生成弹窗 ===== */}
      <GenerateKnowledgeGraphModal
        visible={kgModalProjectId !== null}
        projectId={kgModalProjectId ?? 0}
        onCancel={() => setKgModalProjectId(null)}
        onGenerate={handleGenerateKg}
      />
    </div>
  );
};

export default ProjectListPage;
