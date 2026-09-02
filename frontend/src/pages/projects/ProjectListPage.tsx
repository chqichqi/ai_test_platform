import React, { useState, useEffect } from 'react';
import {
  Card, Button, Input, Space, Tag, Modal, Form, message,
  Popconfirm, Select, Typography, Row, Col, Avatar, Spin, Radio,
  DatePicker, Empty, Tooltip, Alert
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
import ProjectSettings from '../../components/projects/ProjectSettings';

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

  // 项目前置配置状态：按项目ID（项目级，{login: 登录模块已导入, web: 项目配置已填 URL}）
  const [configStatusMap, setConfigStatusMap] = useState<Record<number, {login: boolean; web: boolean}>>({});
  // 项目配置弹窗（唯一入口：内含项目配置/登录模块/测试/执行/通知全部页签）
  const [settingsModalProject, setSettingsModalProject] = useState<Project | null>(null);

  // 项目弹窗
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);

  // 版本弹窗
  const [versionModalVisible, setVersionModalVisible] = useState(false);
  const [editingVersion, setEditingVersion] = useState<Version | null>(null);

  useEffect(() => { fetchProjects(); }, []);

  // 项目列表加载后，获取所有项目的版本 + 知识图谱状态 + 项目前置配置状态
  useEffect(() => {
    if (projects.length > 0) {
      fetchAllVersions();
      fetchAllKg();
      fetchAllConfigStatus();
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

  // ===== 项目前置配置状态（项目级：项目配置 + 登录模块，创建版本双前置） =====
  const fetchAllConfigStatus = async () => {
    const map: Record<number, {login: boolean; web: boolean}> = {};
    await Promise.all(
      projects.map(async (p) => {
        try {
          const res = await axiosInstance.get('/web-ui-tests/check-login-module', {
            params: { project_id: p.id },
          });
          map[p.id] = {
            login: !!res.data?.has_login_module,
            web: !!res.data?.has_web_config,
          };
        } catch {
          map[p.id] = { login: false, web: false };
        }
      }),
    );
    setConfigStatusMap(map);
  };

  const refreshConfigStatus = async (projectId: number) => {
    try {
      const res = await axiosInstance.get('/web-ui-tests/check-login-module', {
        params: { project_id: projectId },
      });
      setConfigStatusMap(prev => ({
        ...prev,
        [projectId]: {
          login: !!res.data?.has_login_module,
          web: !!res.data?.has_web_config,
        },
      }));
    } catch (e) {
      // 不静默：状态刷新失败留日志（2026-09-01 根因=后端判定源对 dict test_data 抛异常 → 500 被吞 → 卡片恒「待配置」）
      console.error(`[ProjectListPage] refreshConfigStatus(project ${projectId}) failed:`, e);
    }
  };

  const handleAddVersionClick = (record: Project) => {
    setSelectedProjectId(record.id);
    // 创建版本门控的前端引导：项目配置（URL）+ 登录模块两项都齐才能创建（后端 400 兜底）
    const cfg = configStatusMap[record.id] || { login: false, web: false };
    if (!cfg.web) {
      message.warning('创建版本前必须先完成项目配置：请先点击卡片「项目配置」填写目标系统 URL');
      return;
    }
    if (!cfg.login) {
      message.warning('创建版本前必须先配置登录鉴权：请先点击卡片「项目配置」，在「登录模块」页签导入并验证登录流程');
      return;
    }
    versionForm.setFieldsValue({ _project_id: record.id });
    openVersionModal();
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
                                {(() => {
                                  const cfg = configStatusMap[record.id] || { login: false, web: false };
                                  const cfgReady = cfg.login && cfg.web;
                                  return (
                                    <Tooltip title={cfgReady ? '项目配置与登录模块均已完成' : (cfg.web ? '待导入登录模块（项目配置 → 登录模块）' : '待完成项目配置（项目配置 → 目标系统 URL）')}>
                                      <Tag color={cfgReady ? 'blue' : 'orange'} style={{ fontSize: 11 }}>
                                        {cfgReady ? '已配置' : '待配置'}
                                      </Tag>
                                    </Tooltip>
                                  );
                                })()}
                              </div>
                            </div>
                          </div>
                          <Space size={2} style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
                            <Tooltip title="知识图谱（基于已探索结果生成）"><Button size="small" icon={<ApartmentOutlined />}
                              onClick={() => handleOpenKg(record)} /></Tooltip>
                            <Tooltip title="项目配置（项目配置/登录模块/测试/执行/通知）"><Button size="small" icon={<SettingOutlined />}
                              onClick={() => setSettingsModalProject(record)} /></Tooltip>
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
                            <Tooltip title="添加版本（创建版本前必须先完成项目配置与登录模块）">
                              <Button size="small" type="dashed" icon={<PlusOutlined />}
                                onClick={(e) => { e.stopPropagation(); handleAddVersionClick(record); }} />
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

      {/* ===== 项目配置弹窗（唯一入口：项目配置/登录模块/测试/执行/通知全部页签） ===== */}
      <Modal
        title={`项目配置 - ${settingsModalProject?.name || ''}`}
        open={settingsModalProject !== null}
        onCancel={() => {
          // 关闭项目配置弹窗时刷新卡片状态（配置可能刚保存/登录刚导入，保证返回后立即看到最新 Tag）
          if (settingsModalProject) {
            refreshConfigStatus(settingsModalProject.id);
          }
          setSettingsModalProject(null);
        }}
        footer={null}
        width={760}
        maskClosable={false}
      >
        {settingsModalProject && (
          <ProjectSettings
            projectId={settingsModalProject.id}
            onLoginImported={() => refreshConfigStatus(settingsModalProject.id)}
            onWebConfigSaved={() => refreshConfigStatus(settingsModalProject.id)}
          />
        )}
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
