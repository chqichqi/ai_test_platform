/**
 * 执行中心 — 场景编排与执行
 * 左侧场景列表，右侧场景详情（拖拽排序、启用/跳过、执行）
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Button, Space, Tag, Modal, Form, Input, Select, message, Empty,
  Typography, Popconfirm, Switch, Tooltip, Spin, Row, Col
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, PlayCircleOutlined,
  EditOutlined, HolderOutlined,
  ThunderboltOutlined, ApiOutlined, MobileOutlined,
  BranchesOutlined, ReloadOutlined
} from '@ant-design/icons';
import { Table } from 'antd';
import { sceneApi, projectApi, versionApi } from '../../api/projectApi';
import { testCaseApi, type TestCase } from '../../api/requirementApi';
import type { SceneInfo } from '../../api/projectApi';

const { Text } = Typography;
const { TextArea } = Input;

const SCENE_TYPE_OPTIONS = [
  { value: 'ui', label: 'UI 测试', icon: <MobileOutlined />, color: 'blue' },
  { value: 'api', label: 'API 测试', icon: <ApiOutlined />, color: 'green' },
  { value: 'performance', label: '压力测试', icon: <ThunderboltOutlined />, color: 'orange' },
];

const ExecutionCenterPage: React.FC = () => {
  const [sceneType, setSceneType] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('type') || 'ui';
  });
  const [scenes, setScenes] = useState<SceneInfo[]>([]);
  const [selectedScene, setSelectedScene] = useState<SceneInfo | null>(null);
  const [loading, setLoading] = useState(false);

  // 弹窗
  const [modalVisible, setModalVisible] = useState(false);
  const [editingScene, setEditingScene] = useState<SceneInfo | null>(null);
  const [form] = Form.useForm();

  // 项目/版本
  const [projects, setProjects] = useState<any[]>([]);
  const [versions, setVersions] = useState<any[]>([]);

  // 执行状态
  const [executing, setExecuting] = useState(false);
  const [execResults, setExecResults] = useState<any>(null);

  // 添加用例弹窗（方案B：按生效功能用例选入，add_items 绑定最新 WUI）
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [addProjectId, setAddProjectId] = useState<number | null>(null);
  const [addVersionId, setAddVersionId] = useState<number | null>(null);
  const [addVersions, setAddVersions] = useState<any[]>([]);
  const [addCases, setAddCases] = useState<TestCase[]>([]);
  const [addLoading, setAddLoading] = useState(false);
  const [selectedCaseIds, setSelectedCaseIds] = useState<React.Key[]>([]);
  const [adding, setAdding] = useState(false);

  // 执行配置
  const [execHeadless, setExecHeadless] = useState(true);
  const [execBrowserMode, setExecBrowserMode] = useState<'isolated' | 'reuse'>('reuse');
  const [execSlowMo] = useState(0);

  useEffect(() => { loadProjects(); }, []);
  useEffect(() => { loadScenes(); }, [sceneType]);

  const loadProjects = async () => {
    try {
      const res = await projectApi.list({ page_size: 100 });
      setProjects(res.items || []);
    } catch { /* ignore */ }
  };

  const loadScenes = async () => {
    setLoading(true);
    try {
      const res = await sceneApi.list({ scene_type: sceneType });
      setScenes(res.items || []);
      if (!selectedScene || !res.items?.find(s => s.id === selectedScene.id)) {
        setSelectedScene(res.items?.[0] || null);
      }
    } catch { setScenes([]); }
    finally { setLoading(false); }
  };

  const loadSceneDetail = async (id: number) => {
    try {
      const detail = await sceneApi.get(id);
      setSelectedScene(detail);
    } catch { /* ignore */ }
  };

  const loadVersions = async (projectId: number) => {
    try {
      const res = await versionApi.listByProject(projectId, { page_size: 100 });
      setVersions(res.items || []);
    } catch { setVersions([]); }
  };

  // 创建/编辑场景
  const handleSaveScene = async (values: any) => {
    try {
      if (editingScene) {
        await sceneApi.update(editingScene.id, values);
      } else {
        await sceneApi.create({ ...values, scene_type: sceneType });
      }
      message.success(editingScene ? '场景已更新' : '场景已创建');
      setModalVisible(false);
      form.resetFields();
      loadScenes();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '保存失败');
    }
  };

  const openCreateModal = () => {
    setEditingScene(null);
    form.resetFields();
    form.setFieldsValue({ scene_type: sceneType });
    setModalVisible(true);
  };

  const openEditModal = (scene: SceneInfo) => {
    setEditingScene(scene);
    form.setFieldsValue({
      name: scene.name,
      description: scene.description,
      project_id: scene.project_id,
    });
    if (scene.project_id) loadVersions(scene.project_id);
    setModalVisible(true);
  };

  const handleDeleteScene = async (id: number) => {
    await sceneApi.delete(id);
    message.success('已删除');
    if (selectedScene?.id === id) setSelectedScene(null);
    loadScenes();
  };

  // 拖拽重排（简化版：上移/下移按钮）
  const moveItem = async (itemId: number, direction: 'up' | 'down') => {
    if (!selectedScene?.items) return;
    const items = [...selectedScene.items].sort((a, b) => a.sort_order - b.sort_order);
    const idx = items.findIndex(i => i.id === itemId);
    if (idx < 0) return;
    if (direction === 'up' && idx === 0) return;
    if (direction === 'down' && idx === items.length - 1) return;
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
    [items[idx], items[targetIdx]] = [items[targetIdx], items[idx]];
    const orderedIds = items.map(i => i.id);
    await sceneApi.reorder(selectedScene.id, orderedIds);
    loadSceneDetail(selectedScene.id);
  };

  // 启用/禁用
  const toggleItem = async (itemId: number, enabled: boolean) => {
    if (!selectedScene) return;
    await sceneApi.toggleItem(selectedScene.id, itemId, enabled);
    loadSceneDetail(selectedScene.id);
  };

  // 移除
  const removeItem = async (itemId: number) => {
    if (!selectedScene) return;
    await sceneApi.removeItem(selectedScene.id, itemId);
    message.success('已移除');
    loadSceneDetail(selectedScene.id);
  };

  // 执行
  const handleExecute = async () => {
    if (!selectedScene) return;
    setExecuting(true);
    setExecResults(null);
    try {
      const res = await sceneApi.execute(selectedScene.id, {
        version_id: selectedScene.version_id,
        headless: execHeadless,
        browser_mode: execBrowserMode,
        slow_mo: execSlowMo,
      });
      setExecResults(res);
      const cfg = res.config || {};
      message.info(
        `执行完成：${res.passed ?? '-'}/${res.total} 通过`
        + (cfg.browser_mode ? ` | 模式: ${cfg.browser_mode}` : '')
        + (cfg.headless ? ' | 无头' : ' | 有头'),
        5
      );
    } catch (e: any) {
      message.error(e.response?.data?.detail || '执行失败');
    } finally { setExecuting(false); }
  };

  const typeCfg = SCENE_TYPE_OPTIONS.find(t => t.value === sceneType)!;
  const sortedItems = selectedScene?.items
    ? [...selectedScene.items].sort((a, b) => a.sort_order - b.sort_order)
    : [];

  // ── 添加生效功能用例到场景（方案B 最小入口）──
  const openAddCasesModal = () => {
    setSelectedCaseIds([]);
    setAddCases([]);
    setAddProjectId(selectedScene?.project_id ?? null);
    setAddVersionId(selectedScene?.version_id ?? null);
    setAddVersions([]);
    if (selectedScene?.project_id) {
      loadVersions(selectedScene.project_id);
      loadAddCases(selectedScene.project_id, selectedScene?.version_id);
    }
    setAddModalVisible(true);
  };

  const loadAddCases = async (projectId: number, versionId?: number) => {
    setAddLoading(true);
    try {
      const res = await testCaseApi.list({
        project_id: projectId,
        version_id: versionId || undefined,
        page_size: 100,
      });
      // 只列可用的生效用例（排除废弃/归档冻结行）
      setAddCases((res.items || []).filter(
        (tc: TestCase) => !['deprecated', 'archived'].includes(tc.status)
      ));
    } catch { setAddCases([]); }
    finally { setAddLoading(false); }
  };

  const handleAddCases = async () => {
    if (!selectedScene || selectedCaseIds.length === 0) return;
    setAdding(true);
    try {
      await sceneApi.addItems(selectedScene.id, selectedCaseIds as number[], 'ui');
      message.success(`已添加 ${selectedCaseIds.length} 条用例`);
      setAddModalVisible(false);
      loadSceneDetail(selectedScene.id);
    } catch (e: any) {
      message.error(e.response?.data?.detail || '添加失败');
    } finally { setAdding(false); }
  };

  return (
    <div style={{ padding: 6, height: 'calc(100vh - 120px)' }}>
      <Row gutter={12} style={{ height: '100%' }}>
        {/* ===== 左侧：场景列表 ===== */}
        <Col span={6} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Card
            size="small"
            title={<Space>{typeCfg.icon} {typeCfg.label} 场景</Space>}
            extra={
              <Select value={sceneType} onChange={setSceneType} size="small" style={{ width: 100 }}>
                {SCENE_TYPE_OPTIONS.map(o => (
                  <Select.Option key={o.value} value={o.value}>{o.label}</Select.Option>
                ))}
              </Select>
            }
            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
            bodyStyle={{ flex: 1, overflow: 'auto', padding: 0 }}
          >
            <div style={{ padding: 8 }}>
              <Button type="dashed" block icon={<PlusOutlined />} onClick={openCreateModal}>
                新建场景
              </Button>
            </div>
            <Spin spinning={loading}>
              {scenes.length === 0 ? (
                <Empty description="暂无场景" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                scenes.map(s => (
                  <div
                    key={s.id}
                    onClick={() => loadSceneDetail(s.id)}
                    style={{
                      padding: '8px 12px', cursor: 'pointer',
                      borderBottom: '1px solid #f0f0f0',
                      background: selectedScene?.id === s.id ? '#e6f7ff' : undefined,
                      borderLeft: selectedScene?.id === s.id ? '3px solid #1890ff' : '3px solid transparent',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong style={{ fontSize: 13 }} ellipsis>{s.name}</Text>
                      <Space size={2} onClick={e => e.stopPropagation()}>
                        <Button type="text" size="small" icon={<EditOutlined />}
                          onClick={() => openEditModal(s)} />
                        <Popconfirm title="删除场景？" onConfirm={() => handleDeleteScene(s.id)}>
                          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>
                    <div>
                      <Tag style={{ fontSize: 10 }}>{s.item_count} 条用例</Tag>
                      <Tag color={s.status === 'ready' ? 'green' : 'default'} style={{ fontSize: 10 }}>
                        {s.status === 'draft' ? '草稿' : s.status === 'ready' ? '就绪' : s.status}
                      </Tag>
                    </div>
                  </div>
                ))
              )}
            </Spin>
          </Card>
        </Col>

        {/* ===== 右侧：场景详情 ===== */}
        <Col span={18} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Card
            size="small"
            title={
              selectedScene ? (
                <Space>
                  <BranchesOutlined />
                  <Text strong>{selectedScene.name}</Text>
                  <Tag color={typeCfg.color}>{typeCfg.label}</Tag>
                </Space>
              ) : '场景详情'
            }
            extra={
              selectedScene && (
                <Space>
                  <Tooltip title={execHeadless ? '无头模式（后台运行）' : '有头模式（显示浏览器）'}>
                    <Switch
                      checkedChildren="无头" unCheckedChildren="有头"
                      checked={execHeadless} onChange={setExecHeadless}
                      size="small"
                    />
                  </Tooltip>
                  <Select
                    value={execBrowserMode} onChange={setExecBrowserMode}
                    size="small" style={{ width: 128 }}
                  >
                    <Select.Option value="reuse">浏览器复用</Select.Option>
                    <Select.Option value="isolated">浏览器隔离</Select.Option>
                  </Select>
                  <Button type="primary" icon={<PlayCircleOutlined />}
                    loading={executing} onClick={handleExecute}>
                    执行
                  </Button>
                  <Button icon={<EditOutlined />} onClick={() => openEditModal(selectedScene)}>
                    编辑
                  </Button>
                  {sceneType === 'ui' && (
                    <Button icon={<PlusOutlined />} onClick={openAddCasesModal}>
                      添加用例
                    </Button>
                  )}
                </Space>
              )
            }
            style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
            bodyStyle={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}
          >
            {!selectedScene ? (
              <Empty description="请选择一个场景" />
            ) : sortedItems.length === 0 ? (
              <Empty description={sceneType === 'ui' ? '暂无用例，点击右上角「添加用例」选择生效功能用例' : '暂无用例'}>
                {sceneType === 'ui' && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={openAddCasesModal}>
                    添加用例
                  </Button>
                )}
              </Empty>
            ) : (
              <div>
                <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', color: '#999', fontSize: 12 }}>
                  <span>共 {sortedItems.length} 条（已启用 {sortedItems.filter(i => i.enabled).length} 条）</span>
                </div>
                {sortedItems.map((item, idx) => (
                  <div
                    key={item.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 10px', marginBottom: 4,
                      borderRadius: 6, border: '1px solid #f0f0f0',
                      background: item.enabled ? '#fff' : '#fafafa',
                      opacity: item.enabled ? 1 : 0.6,
                    }}
                  >
                    <HolderOutlined style={{ color: '#bbb', cursor: 'grab' }} />
                    <Text strong style={{ width: 32, textAlign: 'center', color: '#999' }}>{idx + 1}</Text>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        {item.case_module ? (
                          <Tag color="cyan" style={{ marginRight: 0, fontSize: 10 }}>
                            {item.case_module}
                          </Tag>
                        ) : (
                          <Tag color="default" style={{ marginRight: 0, fontSize: 10 }}>-</Tag>
                        )}
                        <Tag color={item.case_type === 'ui' ? 'blue' : 'purple'} style={{ marginRight: 0, fontSize: 10 }}>
                          {item.case_type.toUpperCase()}
                        </Tag>
                      </div>
                      <Text style={{ fontSize: 13 }} ellipsis>
                        {item.case_name || `用例 #${item.case_id}`}
                      </Text>
                    </div>
                    <Switch size="small" checked={item.enabled}
                      onChange={(v) => toggleItem(item.id, v)} />
                    <Tooltip title="上移"><Button type="text" size="small" disabled={idx === 0}
                      onClick={() => moveItem(item.id, 'up')}>↑</Button></Tooltip>
                    <Tooltip title="下移"><Button type="text" size="small" disabled={idx === sortedItems.length - 1}
                      onClick={() => moveItem(item.id, 'down')}>↓</Button></Tooltip>
                    <Popconfirm title="移除此条？" onConfirm={() => removeItem(item.id)}>
                      <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </div>
                ))}
              </div>
            )}

            {/* 执行结果 */}
            {execResults && (
              <div style={{ marginTop: 16, padding: 12, background: '#f6ffed', borderRadius: 6 }}>
                <Text strong style={{ color: '#52c41a' }}>执行结果</Text>
                <div style={{ marginTop: 8 }}>
                  {execResults.results?.map((r: any, i: number) => (
                    <div key={i} style={{ fontSize: 12, padding: '2px 0' }}>
                      {i + 1}. 用例 #{r.case_id} — <Tag color={r.status === 'passed' ? 'green' : 'default'}>{r.status}</Tag>
                      {r.re_resolved && (
                        <Tooltip title="该用例已被新版本取代，本次执行已自动切换到最新版本">
                          <Tag color="orange" style={{ marginLeft: 4 }}>已自动更新至最新版本</Tag>
                        </Tooltip>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 创建/编辑场景弹窗 */}
      <Modal
        title={editingScene ? '编辑场景' : '新建场景'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); }}
        onOk={() => form.submit()}
        width={500}
      maskClosable={false}      >
        <Form form={form} layout="vertical" onFinish={handleSaveScene}>
          <Form.Item name="name" label="场景名称" rules={[{ required: true }]}>
            <Input placeholder="如：登录流程验证" maxLength={100} />
          </Form.Item>
          <Form.Item name="project_id" label="所属项目" rules={[{ required: true }]}>
            <Select placeholder="选择项目" onChange={(v) => loadVersions(v)}>
              {projects.map((p: any) => (
                <Select.Option key={p.id} value={p.id}>{p.name}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="version_id" label="默认版本">
            <Select placeholder="选择版本" allowClear>
              {versions.map((v: any) => (
                <Select.Option key={v.id} value={v.id}>{v.version_number}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加生效功能用例（方案B：add_items 按逻辑 id 绑定最新 WUI） */}
      <Modal
        title="添加功能用例到场景"
        open={addModalVisible}
        onCancel={() => setAddModalVisible(false)}
        onOk={handleAddCases}
        okText={`添加 ${selectedCaseIds.length} 条`}
        confirmLoading={adding}
        width={640}
      >
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            placeholder="选择项目" style={{ width: 180 }} size="small"
            value={addProjectId} onChange={(v: number) => { setAddProjectId(v); setAddVersionId(null); setAddVersions([]); loadVersions(v); loadAddCases(v); }}
          >
            {projects.map((p: any) => (
              <Select.Option key={p.id} value={p.id}>{p.name}</Select.Option>
            ))}
          </Select>
          <Select
            placeholder="版本（默认全部生效）" style={{ width: 200 }} size="small" allowClear
            value={addVersionId} onChange={(v?: number) => { setAddVersionId(v ?? null); if (addProjectId) loadAddCases(addProjectId, v ?? undefined); }}
          >
            {addVersions.map((v: any) => (
              <Select.Option key={v.id} value={v.id}>{v.version_number}</Select.Option>
            ))}
          </Select>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => addProjectId && loadAddCases(addProjectId, addVersionId ?? undefined)}>
            刷新
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>仅列出生效功能用例（不含已废弃/已归档），已转化 UI 的用例自动绑定最新版本</Text>
        </Space>
        <Table
          size="small"
          rowKey="id"
          loading={addLoading}
          dataSource={addCases}
          rowSelection={{
            selectedRowKeys: selectedCaseIds,
            onChange: setSelectedCaseIds,
          }}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          scroll={{ y: 280 }}
          columns={[
            { title: '用例名称', dataIndex: 'name', ellipsis: true },
            {
              title: '模块', dataIndex: 'module', width: 110, ellipsis: true,
              render: (m: string | null) => m || '-',
            },
            {
              title: '版本', dataIndex: 'revision_no', width: 70,
              render: (rev: number | null | undefined) => (rev ? <Tag>v{rev}</Tag> : '-'),
            },
            {
              title: '状态', dataIndex: 'status', width: 80,
              render: (s: string) => {
                const cfg: Record<string, { color: string; label: string }> = {
                  draft: { color: 'default', label: '草稿' },
                  pending_review: { color: 'processing', label: '待审批' },
                  approved: { color: 'success', label: '已通过' },
                  published: { color: 'success', label: '已发布' },
                };
                const c = cfg[s] || { color: 'default', label: s };
                return <Tag color={c.color}>{c.label}</Tag>;
              },
            },
          ]}
        />
      </Modal>
    </div>
  );
};

export default ExecutionCenterPage;
