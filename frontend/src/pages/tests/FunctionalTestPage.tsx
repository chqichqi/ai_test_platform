import React, { useState, useEffect, useRef } from 'react';
import { Card, Typography, Button, Table, Space, Tag, Select, Input, Modal, message, Empty, Descriptions, Tree, Layout, Spin, Tooltip, Radio, Form, Divider, Checkbox, Alert, Upload, Row, Col, Switch, Progress } from 'antd';
const { Dragger } = Upload;
import { PlusOutlined, EyeOutlined, PlayCircleOutlined, DeleteOutlined, LeftOutlined, RightOutlined, FolderOutlined, FileTextOutlined, ExportOutlined, ThunderboltOutlined, ImportOutlined, InboxOutlined, EditOutlined, SaveOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { testCaseApi } from '../../api/requirementApi';
import axiosInstance from '../../api/axiosConfig';
import { projectApi, versionApi } from '../../api/projectApi';

const { Title, Text } = Typography;
const { Option } = Select;
const { Sider, Content } = Layout;
const { Search } = Input;

function formatDateTime(dateStr: string): string {
  if (!dateStr) return '-';
  
  try {
    let date: Date;
    
    if (dateStr.endsWith('Z')) {
      date = new Date(dateStr);
    } else {
      date = new Date(dateStr + 'Z');
    }
    
    const offset = date.getTimezoneOffset() / 60000;
    const localTime = new Date(date.getTime() + offset * 60000);
    
    return localTime.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch {
    return dateStr;
  }
}

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_review: { color: 'processing', label: '待审批' },
  approved: { color: 'success', label: '已通过' },
  published: { color: 'success', label: '已发布' },
  rejected: { color: 'error', label: '已驳回' },
  deprecated: { color: 'default', label: '已废弃' },
  archived: { color: 'default', label: '已归档' },
};

type TestStep = string | { action: string; expected?: string };

interface TestCase {
  id: string;
  name: string;
  description: string;
  module: string;
  status: string;  // 审核状态: draft / pending_review / approved / rejected / deprecated / archived
  lastRun: string;
  duration: number;
  priority: string;
  preconditions?: string;
  test_steps?: TestStep[];
  expected_result?: string;
  project_id?: number;
  version_id?: number;
  project_name?: string;
  version_number?: string;
  // 方案B 版本化：修订号 / 派生来源（列表 v 徽标 + 派生提示）
  logical_case_id?: number | null;
  revision_no?: number | null;
  derived_from_id?: number | null;
}

interface ProjectInfo {
  id: number;
  name: string;
  code: string;
  project_type?: 'web' | 'app';
}

interface VersionInfo {
  id: number;
  version_number: string;
  version_name: string | null;
  status: string;
  test_cases_count?: number;
}

const FunctionalTestPage: React.FC = () => {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [versionsMap, setVersionsMap] = useState<Record<number, VersionInfo[]>>({});
  const versions = selectedProjectId ? (versionsMap[selectedProjectId] || []) : [];
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [treeData, setTreeData] = useState<any[]>([]);
  const [loadingTree] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [selectedTests, setSelectedTests] = useState<string[]>([]);
  const [searchText, setSearchText] = useState('');
  const [filterModule, setFilterModule] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [modules, setModules] = useState<string[]>([]);
  
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20, total: 0 });
  
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [exportTemplate, setExportTemplate] = useState<string>('zentao_csv');
  const [exporting, setExporting] = useState(false);
  // 根据路由判断页面类型
  const isFunctionalPage = window.location.pathname.includes('/functional');
  const isUIPage = window.location.pathname.includes('/web-ui') || window.location.pathname.includes('/app');
  const isAPIPage = window.location.pathname.includes('/api') && !window.location.pathname.includes('/web-ui');

  // 当前选中项目是否为APP端
  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const isAppProject = selectedProject?.project_type === 'app';

  const [selectAllMode, setSelectAllMode] = useState(false);
  const navFetchRef = useRef(false);  // 标记是否为跨页导航触发的加载
  // 用例编辑状态
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [editSteps, setEditStepsLocal] = useState<any[]>([]);
  const [editFormLocal, setEditFormLocal] = useState({ name: '', module: '', priority: 'P2', preconditions: '', expected_result: '', description: '' });
  const [savingDetail, setSavingDetail] = useState(false);
  // 登录模块检查
  const [hasLoginModule, setHasLoginModule] = useState(true); // 默认true避免闪烁
  // 用例导入（仅功能用例页）
  const [showImp, setShowImp] = useState(false);
  const [impFile, setImpFile] = useState<File | null>(null);

  // AI转化为UI用例
  const [convertModalVisible, setConvertModalVisible] = useState(false);
  const [batchConvertModalVisible, setBatchConvertModalVisible] = useState(false);
  const [convertingCase, setConvertingCase] = useState<TestCase | null>(null);
  const [convertBrowser, setConvertBrowser] = useState('chromium');
  const [convertViewport, setConvertViewport] = useState('1920x1080');
  const [convertHeadless, setConvertHeadless] = useState(true);
  const [convertForceExplore, setConvertForceExplore] = useState(false);
  const [converting, setConverting] = useState(false);
  const [batchConverting, setBatchConverting] = useState(false);
  // 转化进度（已完成/总数，用于进度条展示）
  const [convertProgress, setConvertProgress] = useState<{ done: number; total: number } | null>(null);
  // 批量转化阶段进度（后端 _BATCH_TASKS.phase 事件：exploring/pom/converting；2026-08-25 用户要求进度条从点击转化即开始移动）
  const [convertPhaseInfo, setConvertPhaseInfo] = useState<{
    phase: string; phaseDetail: string;
    exploredDone: number; exploredTotal: number;
    stepDone: number; stepTotal: number;
  } | null>(null);
  const startTimeRef = useRef<number>(0);

  // 审核弹窗
  const [reviewVisible, setReviewVisible] = useState(false);
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject'>('approve');
  const [reviewComment, setReviewComment] = useState('');
  const [reviewCaseId, setReviewCaseId] = useState<string | null>(null);
  const [reviewBatch, setReviewBatch] = useState(false);

  // ===== 探索功能已移除 =====
  // 探索现在集成在"转化为UI"流程中——测试用例步骤驱动探索。
  // 不再需要独立的模块探索入口。

  // 从 URL 读取预设的项目/版本
  const urlParams = new URLSearchParams(window.location.search);
  const presetProjectId = urlParams.get('projectId') ? Number(urlParams.get('projectId')) : null;
  const presetVersionId = urlParams.get('versionId') ? Number(urlParams.get('versionId')) : null;

  useEffect(() => {
    loadProjects();
    // 检查登录模块是否已导入
    const _pid2 = urlParams.get('projectId') ? Number(urlParams.get('projectId')) : null;
    axiosInstance.get('/web-ui-tests/check-login-module', {
      params: _pid2 ? { project_id: _pid2 } : {}
    }).then(
      (res: any) => setHasLoginModule(!!res.data?.has_login_module)
    ).catch(() => setHasLoginModule(true)); // 失败时不禁用
  }, []);

  // 页面类型切换时全面重置状态，避免数据残留
  const pageTypeRef = useRef(isFunctionalPage ? 'func' : isAPIPage ? 'api' : isUIPage ? 'ui' : 'func');
  useEffect(() => {
    const currentType = isFunctionalPage ? 'func' : isAPIPage ? 'api' : isUIPage ? 'ui' : 'func';
    if (pageTypeRef.current !== currentType) {
      pageTypeRef.current = currentType;
      // 重置所有页面相关状态
      setTestCases([]);
      setLoadingCases(true);  // 显示加载中，避免空白闪烁
      setPagination(prev => ({ ...prev, page: 1 }));
      setSelectedTests([]);
      setSelectAllMode(false);
      setSearchText('');
      setFilterModule('all');
      setFilterStatus('all');
    }
  }, [isFunctionalPage, isAPIPage, isUIPage]);

  useEffect(() => {
    if (projects.length > 0) {
      loadAllVersions();
    }
  }, [projects]);

  const loadAllVersions = async () => {
    const map: Record<number, VersionInfo[]> = {};
    for (const p of projects) {
      try {
        const response = await versionApi.listByProject(p.id, { page_size: 100 });
        map[p.id] = response.items || [];
      } catch { map[p.id] = []; }
    }
    setVersionsMap(map);
  };

  // 版本加载完成后自动选中
  const autoSelectApplied = useRef(false);
  useEffect(() => {
    if (autoSelectApplied.current) return;
    if (Object.keys(versionsMap).length === 0) return;

    // 优先使用 URL preset
    if (presetVersionId) {
      for (const [pid, vers] of Object.entries(versionsMap)) {
        if (vers.some(v => v.id === presetVersionId)) {
          autoSelectApplied.current = true;
          setSelectedProjectId(Number(pid));
          setSelectedVersionId(presetVersionId);
          setExpandedKeys([`project-${pid}`]);
          return;
        }
      }
    }

    // 自动选：当前已选项目 → 第一个版本
    if (selectedProjectId && !selectedVersionId) {
      const vers = versionsMap[selectedProjectId] || [];
      if (vers.length > 0) {
        autoSelectApplied.current = true;
        setSelectedVersionId(vers[0].id);
        return;
      }
    }

    // 兜底：第一个项目 → 第一个版本
    if (!selectedVersionId) {
      const firstProjectId = Object.keys(versionsMap)[0];
      if (firstProjectId) {
        const vers = versionsMap[Number(firstProjectId)] || [];
        if (vers.length > 0) {
          autoSelectApplied.current = true;
          setSelectedProjectId(Number(firstProjectId));
          setSelectedVersionId(vers[0].id);
          setExpandedKeys([`project-${firstProjectId}`]);
        }
      }
    }
  }, [versionsMap, presetVersionId, selectedProjectId]);

  useEffect(() => {
    buildTree();
  }, [projects, versionsMap, selectedProjectId, selectedVersionId, expandedKeys]);

  // 数据获取 — 用 ref 防止页面切换时的重复请求竞态
  const fetchingRef = useRef(false);
  // 跟踪当前活跃的页面类型，用于在切换子菜单时强制重取
  const activePageType = isFunctionalPage ? 'func' : isAPIPage ? 'api' : isUIPage ? 'ui' : 'func';
  useEffect(() => {
    if (!selectedVersionId) return;
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    fetchTestCases().finally(() => { fetchingRef.current = false; });
    axiosInstance.get('/web-ui-tests/converted-ids').then(r => {
      setConvertedIds(new Set(r.data.converted_ids || []));
    }).catch(() => {});
  }, [selectedVersionId, pagination.page, pagination.pageSize, searchText, filterModule, filterStatus, activePageType]);

  const loadProjects = async () => {
    try {
      const response = await projectApi.list({ page_size: 100 });
      setProjects(response.items || []);
      if (response.items?.length > 0) {
        // 如果 URL 指定了 projectId，优先使用
        if (presetProjectId && response.items.some(p => p.id === presetProjectId)) {
          setSelectedProjectId(presetProjectId);
          setExpandedKeys([`project-${presetProjectId}`]);
        } else if (!presetVersionId) {
          setSelectedProjectId(response.items[0].id);
          setExpandedKeys([`project-${response.items[0].id}`]);
        }
        // 如果有 presetVersionId，等待版本加载后再设置 selectedProjectId
      }
    } catch (error) {
      message.error('加载项目列表失败');
    }
  };

  const buildTree = () => {
    const truncateName = (name: string, maxLen: number = 12) => {
      if (name.length <= maxLen) return name;
      return name.slice(0, maxLen) + '...';
    };
    
    const tree: any[] = projects.map(project => {
      const projectKey = `project-${project.id}`;
      const isExpanded = expandedKeys.includes(projectKey);
      
      return {
        key: projectKey,
        title: (
          <div 
            className={project.id === selectedProjectId ? 'tree-node-selected-project' : ''}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              cursor: 'pointer', 
              paddingLeft: 8,
              borderRadius: 4,
              padding: '4px 8px',
              ...(project.id === selectedProjectId ? { background: 'rgba(24, 144, 255, 0.1)' } : {})
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (isExpanded) {
                setExpandedKeys(prev => prev.filter(k => k !== projectKey));
              } else {
                setExpandedKeys(prev => [...prev, projectKey]);
              }
            }}
          >
            <FolderOutlined style={{ fontSize: 16 }} />
            <Tooltip title={project.name}>
              <span style={{ 
                marginLeft: 4,
                whiteSpace: 'nowrap', 
                overflow: 'hidden',
                display: 'inline-block',
                maxWidth: '140px',
                lineHeight: '16px'
              }}>
                {truncateName(project.name)}
              </span>
            </Tooltip>
          </div>
        ),
        children: (versionsMap[project.id] || []).map(version => ({
             key: `version-${version.id}`,
 title: (
                <div 
                  className={version.id === selectedVersionId ? 'tree-node-selected-version' : ''}
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between', 
                    width: '100%',
                    marginLeft: -8,
                    paddingLeft: 8,
                    paddingRight: 8,
                    borderRadius: 4,
                    paddingTop: 4,
                    paddingBottom: 4,
                    ...(version.id === selectedVersionId ? { background: 'rgba(82, 196, 26, 0.15)' } : {})
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <FileTextOutlined style={{ fontSize: 16 }} />
                    <span style={{ marginLeft: 4 }}>{version.version_number}</span>
                    <Tag color="green" style={{ marginLeft: 8 }}>{version.test_cases_count}用例</Tag>
                  </div>
                </div>
              ),
             isLeaf: true,
           })),
      };
    });
    setTreeData(tree);
  };

  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    const key = selectedKeys[0] as string;
    if (key?.startsWith('project-')) {
      const projectId = Number(key.replace('project-', ''));
      setSelectedProjectId(projectId);
      setSelectedVersionId(null);
      setTestCases([]);
      setSelectedTests([]);
      setSelectAllMode(false);
    } else if (key?.startsWith('version-')) {
      const versionId = Number(key.replace('version-', ''));
      setSelectedVersionId(versionId);
      setSelectedTests([]);
      setSelectAllMode(false);
    }
  };

  const fetchTestCases = async () => {
    if (!selectedVersionId) {
      setLoadingCases(false);
      return;
    }

    setLoadingCases(true);
    try {
      // 按页面类型走不同数据源
      const apiUrl = isAPIPage ? `/api-tests/cases/version/${selectedVersionId}`
        : isUIPage ? '/web-ui-tests/test-cases'
        : '/test-cases/';
      const params: any = {
        page: pagination.page, page_size: pagination.pageSize,
        search: searchText || undefined,
      };
      if (isUIPage && selectedProjectId) {
        params.project_id = selectedProjectId;
      }
      if (!isUIPage) {
        params.version_id = selectedVersionId;
        params.status = filterStatus !== 'all' ? filterStatus : undefined;
      }
      const { data } = await axiosInstance.get(apiUrl, { params });
      
      const items = data.items || [];
      setPagination(prev => ({ ...prev, total: data.total || 0 }));

      const project = projects.find(p => p.id === selectedProjectId);
      const version = versions.find(v => v.id === selectedVersionId);

      const transformedCases: TestCase[] = items.map((item: any) => {
        // UI 页面：数据来自 WebUITestCase，通过 test_case 字段获取关联信息
        const tc = isUIPage ? (item.test_case || {}) : item;
        return {
          id: String(item.id),
          test_case_id: item.test_case_id || '',
          name: tc.title || tc.name || item.name || '未命名',
          description: tc.description || item.description || '',
          module: tc.module || item.module || '通用模块',
          preconditions: tc.preconditions || item.preconditions || '',
          test_steps: Array.isArray(tc.test_steps || item.test_steps) ? (tc.test_steps || item.test_steps) : [],
          expected_result: tc.expected_result || item.expected_result || '',
          lastRun: item.created_at ? formatDateTime(item.created_at) : '-',
          priority: (tc.priority === 'P0' || item.priority === 'P0' ? 'high' :
                     tc.priority === 'P1' || item.priority === 'P1' ? 'medium' : 'low') as 'high' | 'medium' | 'low',
          duration: 0,
          status: tc.status || item.status || 'draft',
          project_id: tc.project_id || item.project_id,
          version_id: tc.version_id || item.version_id,
          project_name: project?.name,
          version_number: version?.version_number,
        };
      });
      
      setTestCases(transformedCases);
      
      const mods = [...new Set(transformedCases.map(t => t.module))];
      setModules(mods);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载测试用例失败');
    } finally {
      setLoadingCases(false);
    }
  };

  const handleDeleteCase = (id: string) => {
    Modal.confirm({
      title: '确认删除',
      content: isUIPage
        ? '确定要删除此UI测试用例吗？仅删除UI脚本，不影响原始功能用例。'
        : '确定要删除这个测试用例吗？此操作不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          if (isUIPage) {
            await axiosInstance.delete(`/web-ui-tests/test-cases/${id}`);
          } else {
            await testCaseApi.delete(Number(id));
          }
          setTestCases(prev => prev.filter(test => test.id !== id));
          setSelectedTests(prev => prev.filter(testId => testId !== id));
          setConvertedIds(prev => { const next = new Set(prev); next.delete(id); return next; });
          message.success('删除成功');
        } catch (error: any) {
          const detail = error.response?.data?.detail || '';
          if (error.response?.status === 409) {
            message.warning(detail || '该用例已转化为UI用例，请先从UI用例页面删除');
          } else {
            message.error(detail || '删除失败');
          }
        }
      },
    });
  };

  // 打开AI转化弹窗（前提：功能用例审核通过 approved/active，与后端守卫一致）
  const handleOpenConvert = (record: TestCase) => {
    const st = record.status || 'draft';
    if (st !== 'approved' && st !== 'active') {
      const label = STATUS_MAP[st]?.label || st;
      message.warning(`功能用例「${record.name || record.id}」未审核通过（当前状态: ${label}），请先审核通过后再转化为UI用例`);
      return;
    }
    setConvertingCase(record);
    setConvertModalVisible(true);
  };

  // 执行AI转化为UI用例
  const handleConvertToUI = async () => {
    if (!convertingCase) return;
    setConverting(true);
    try {
      const axiosInstance = (await import('../../api/axiosConfig')).default;
      const response = await axiosInstance.post('/web-ui-tests/convert-from-functional', {
        functional_test_case_id: convertingCase.id,
        browser: convertBrowser,
        viewport_size: convertViewport,
        headless: convertHeadless,
        script_type: 'playwright',
        script_language: 'python',
        generate_element_selectors: true,
        generate_test_script: true,
        force_explore: convertForceExplore,
      });
      if (response.data?.success) {
        message.success('AI转化成功！可在"功能用例AI转化为UI用例"页面查看生成的脚本');
      } else {
        message.success('转化完成');
      }
      setConvertModalVisible(false);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '转化失败，请检查后端服务');
    } finally {
      setConverting(false);
    }
  };

  // 解析本次待转化用例并分类（入口预检 / 开始转化共用同一口径，保证提示时机一致）
  const resolveConvertibleCases = async () => {
    const axiosInstance = (await import('../../api/axiosConfig')).default;
    let allCases: { id: string; status: string; module?: string }[] = [];
    if (selectAllMode) {
      // 跨页全选：分页拉取全部 ID 和状态
      let p = 1;
      while (true) {
        const { data } = await axiosInstance.get('/test-cases/', {
          params: {
            page: p, page_size: 100,
            version_id: selectedVersionId,
            search: searchText || undefined,
            status: filterStatus !== 'all' ? filterStatus : undefined,
          }
        });
        const items = data.items || [];
        allCases.push(...items.map((c: any) => ({ id: String(c.id), status: c.status || 'draft', module: c.module || '' })));
        if (allCases.length >= data.total || items.length === 0) break;
        p++;
      }
    } else {
      // 手动勾选：从当前页数据获取状态和模块
      const statusMap = new Map(testCases.map(c => [c.id, c.status]));
      const moduleMap = new Map(testCases.map(c => [c.id, c.module || '']));
      allCases = selectedTests.map(id => ({ id, status: statusMap.get(id) || 'draft', module: moduleMap.get(id) || '' }));
    }
    // 排除登录模块（平台内部约定名）：登录模块用例由业务流导入自动生成/发布(published)，
    // 不参与普通用例的「审核→转化」预检，避免其 published 状态被误判为「未审核」。
    const nonLoginCases = allCases.filter(c => c.module !== '登录模块');
    // 只转换已通过(approved/active，与后端守卫同源) + 未转化的用例
    const approvedCases = nonLoginCases.filter(c => c.status === 'approved' || c.status === 'active');
    const notApprovedSkipped = nonLoginCases.length - approvedCases.length;
    const toConvert = approvedCases.filter(c => !convertedIds.has(String(c.id)));
    const alreadyConvertedSkipped = approvedCases.length - toConvert.length;
    return { approvedCases, notApprovedSkipped, alreadyConvertedSkipped, toConvert };
  };

  // 批量转化为UI用例（入口预检：未审核/已转化/无可转化用例在点击时就提示，不等到设置页）
  const handleBatchConvertToUI = async () => {
    if (selectedTests.length === 0 && !selectAllMode) {
      message.warning('请先选择要转化的用例');
      return;
    }
    try {
      const { toConvert, notApprovedSkipped, alreadyConvertedSkipped } = await resolveConvertibleCases();
      if (toConvert.length === 0) {
        message.warning(notApprovedSkipped === 0
          ? '所选已审核用例均已转化，无需重复转化'
          : '所选用例中没有已通过审核的用例，请先审核通过后再转化');
        return;  // 无可转化用例 → 不打开设置弹窗
      }
      if (notApprovedSkipped > 0 || alreadyConvertedSkipped > 0) {
        const skipReasons: string[] = [];
        if (notApprovedSkipped > 0) skipReasons.push(`${notApprovedSkipped} 条未审核`);
        if (alreadyConvertedSkipped > 0) skipReasons.push(`${alreadyConvertedSkipped} 条已转化`);
        message.warning(`待转化用例中存在${skipReasons.join('、')}，本次转化将跳过它们，实际转化 ${toConvert.length} 条`, 5);
      }
    } catch { /* 预检失败不阻塞，进入设置页后由开始转化兜底检查 */ }
    setBatchConvertModalVisible(true);
  };

  // 转化进度文本
  const [convertProgressText, setConvertProgressText] = useState('');
  // 调试状态
  const [debugResult, setDebugResult] = useState<any>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [convertedIds, setConvertedIds] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const batchTaskIdRef = useRef<string | null>(null);  // 当前批量转化 task_id（「取消转化」时通知后端停止探索关浏览器）

  // 执行批量转化
  const doBatchConvert = async () => {
    let batchSucceeded = false;  // 成功路径才自动关闭弹窗（失败保留弹窗+错误详情，用户手动关闭）
    setBatchConverting(true);
    setConvertProgressText('正在准备转化...');
    setConvertPhaseInfo(null);
    startTimeRef.current = Date.now();
    abortRef.current = new AbortController();
    try {
      const axiosInstance = (await import('../../api/axiosConfig')).default;

      // 获取所有要处理的用例 ID 及其状态（与入口预检同源；Modal 打开期间选择可能变化，故此处再查）
      const { approvedCases, notApprovedSkipped, alreadyConvertedSkipped, toConvert } = await resolveConvertibleCases();

      if (toConvert.length === 0) {
        message.warning(approvedCases.length === 0
          ? '所选用例中没有已通过审核的用例，请先审核通过后再转化'
          : '所选已审核用例均已转化，无需重复转化');
        setBatchConverting(false);
        setConvertProgressText('');
        return;
      }

      // 用户要求：存在未审核/已转化用例时，转化前先提示将跳过它们
      if (notApprovedSkipped > 0 || alreadyConvertedSkipped > 0) {
        const skipReasons: string[] = [];
        if (notApprovedSkipped > 0) skipReasons.push(`${notApprovedSkipped} 条未审核`);
        if (alreadyConvertedSkipped > 0) skipReasons.push(`${alreadyConvertedSkipped} 条已转化`);
        message.warning(`待转化用例中存在${skipReasons.join('、')}，本次转化将跳过它们`, 5);
      }

      const skipParts: string[] = [];
      if (notApprovedSkipped > 0) skipParts.push(`跳过 ${notApprovedSkipped} 个未审核`);
      if (alreadyConvertedSkipped > 0) skipParts.push(`跳过 ${alreadyConvertedSkipped} 个已转化`);
      skipParts.push(`开始转化 ${toConvert.length} 个用例...`);
      setConvertProgressText(skipParts.join('，'));
      setConvertProgress({ done: 0, total: toConvert.length });

      // === 调用批量转化端点 ===
      setConvertProgressText(prev => prev + '\n正在打开浏览器探索目标系统，提取页面交互元素...');

      const approvedIds = toConvert.map(c => c.id);
      const { data: batchResult } = await axiosInstance.post(
        '/web-ui-tests/convert-batch-from-functional',
        {
          test_case_ids: approvedIds,
          browser: convertBrowser,
          viewport_size: convertViewport,
          headless: convertHeadless,
          script_type: 'playwright',
          script_language: 'python',
          generate_element_selectors: true,
          generate_test_script: true,
          force_explore: convertForceExplore,
        },
        {
          signal: abortRef.current?.signal,
          timeout: 900000,  // 15分钟超时（axios config 参数）
        }
      );

      // ── 异步模式：检测 task_id → 轮询等待结果 ──
      if (batchResult.task_id) {
        const taskId = batchResult.task_id;
        batchTaskIdRef.current = taskId;  // 供「取消转化」按钮通知后端停止探索并关闭浏览器
        setConvertProgressText(prev => prev + `\n\n⏳ 后台处理中... 已完成 0/${batchResult.total}`);
        setConvertProgress({ done: 0, total: batchResult.total ?? toConvert.length });

        const pollResult = await new Promise<any>((resolve, reject) => {
          let stopped = false;
          let consecutiveErrors = 0;
          const timer = setInterval(async () => {
            if (stopped) return;
            try {
              const { data: task } = await axiosInstance.get(
                `/web-ui-tests/convert-batch-async-status/${taskId}`,
                { timeout: 30000 }  // 轮询是短请求；后端事件循环已不再被 LLM 占死（线程化），30s 足够
              );
              if (stopped) return;
              consecutiveErrors = 0;
              if (task.status === 'completed' || task.status === 'partial' || task.status === 'failed'
                  || task.status === 'cancelled') {
                stopped = true;
                clearInterval(timer);
                resolve(task);
              } else {
                try {
                  const done = task.completed ?? task.results?.length ?? 0;
                  setConvertProgress({ done, total: task.total ?? toConvert.length });
                  // 阶段进度事件：探索模块/步骤 + POM + 转化（进度条从点击转化即开始移动）
                  if (task.phase) {
                    setConvertPhaseInfo({
                      phase: task.phase,
                      phaseDetail: task.phase_detail || '',
                      exploredDone: task.explored_done ?? 0,
                      exploredTotal: task.explored_total ?? 0,
                      stepDone: task.step_done ?? 0,
                      stepTotal: task.step_total ?? 0,
                    });
                  }
                  // 已运行时间（每次轮询刷新）
                  const secs = Math.floor((Date.now() - startTimeRef.current) / 1000);
                  const elapsedStr = `${Math.floor(secs / 60)}分${secs % 60}秒`;
                  setConvertProgressText(prev => {
                    const base = prev || '';
                    const lines = base.split('\n');
                    lines[lines.length - 1] = task.phase_detail
                      ? `⏳ ${task.phase_detail}（已完成 ${done}/${task.total || '?'}，已运行 ${elapsedStr}）`
                      : `⏳ 后台处理中... 已完成 ${done}/${task.total || '?'}，已运行 ${elapsedStr}`;
                    return lines.join('\n');
                  });
                } catch (_) {}
              }
            } catch (e) {
              // 单次轮询失败（后端瞬时忙/重启中）不立即放弃——连续 3 次失败才判死
              // （此前单次失败即 reject → catch → 弹窗自动消失，用户看到的是「转化失败」而非真实结果）
              consecutiveErrors += 1;
              if (!stopped && consecutiveErrors >= 3) {
                stopped = true; clearInterval(timer); reject(e);
              }
            }
          }, 2000);

          // 安全阀：2 小时后强制停止轮询
          setTimeout(() => { if (!stopped) { stopped = true; clearInterval(timer); reject(new Error('轮询超时')); } }, 7200000);
        });

        setConvertProgressText(prev => prev + '\n\n✅ 转化请求完成，正在生成测试项目文件...');
        // 用户取消（「取消转化」按钮）：后端已停止探索并关闭浏览器，流程真正结束——
        // 不展示误导性的失败/成功弹窗，仅提示已取消
        if (pollResult.status === 'cancelled') {
          batchTaskIdRef.current = null;
          message.info('已取消转化，探索浏览器已关闭', 3);
          return;
        }
        // 用轮询结果覆盖 batchResult
        batchResult.success_count = pollResult.success_count || 0;
        batchResult.total_count = pollResult.total_count || batchResult.total;
        batchResult.results = pollResult.results || [];
        batchResult.summary = pollResult.summary || {};
        batchResult.skipped_cases = pollResult.skipped_cases || [];
        batchResult.api_cases_generated = pollResult.api_cases_generated || {};
        // 后台任务整体失败（status=failed，异常中断）时透传错误信息，否则全部失败场景看不到原因
        if (pollResult.error) batchResult.error = pollResult.error;
      }

      const {
        success_count = 0,
        explored_modules = [], cached_modules = [],
        summary = {}, results = [],
        exploration_failures = null,
        api_cases_generated = {},
      } = batchResult;

      const {
        exploration_insufficient = 0,
        exploration_failed = 0,
        conversion_failed = 0,
        steps_missing = 0,
      } = summary || {};

      // 构建详细的结果提示
      const parts: string[] = [];
      if (batchResult.error) parts.push(`❌ ${batchResult.error}`);
      if (success_count > 0) parts.push(`✅ 成功 ${success_count} 个`);
      if (steps_missing > 0) parts.push(`🔶 部分步骤未定位 ${steps_missing} 个`);
      if (conversion_failed > 0) parts.push(`⚠️ LLM转化失败 ${conversion_failed} 个`);
      if (exploration_insufficient > 0) parts.push(`🔍 探索数据不足 ${exploration_insufficient} 个`);
      if (exploration_failed > 0) parts.push(`❌ 探索失败 ${exploration_failed} 个`);
      if (explored_modules.length > 0) parts.push(`📡 探索模块: ${explored_modules.join(', ')}`);
      if (cached_modules.length > 0) parts.push(`💾 缓存命中: ${cached_modules.join(', ')}`);
      if ((api_cases_generated as any).generated > 0) {
        parts.push(`🔧 探索生成API用例 ${(api_cases_generated as any).generated} 条`);
      }

      const resultMsg = parts.join(' | ');

      // 跳过用例列表：与失败详情合并进同一个弹窗展示，避免多弹窗叠加（2026-08-17）
      const skippedCases: any[] = batchResult.skipped_cases || [];
      const renderSkippedBlock = (skips: any[]) => {
        if (!skips || skips.length === 0) return null;
        return (
          <div style={{ maxHeight: 360, overflow: 'auto', marginTop: 12 }}>
            <strong>本次转化跳过 {skips.length} 条用例：</strong>
            <ul style={{ marginTop: 4, paddingLeft: 20 }}>
              {skips.map((s: any, i: number) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  <strong>{s.name || s.id}</strong>{' '}
                  <span style={{ color: '#999', fontSize: 12 }}>
                    {s.reason ? `（${s.reason}）` : ''}
                    （状态: {STATUS_MAP[s.status || '']?.label || s.status || '未知'}）
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      };

      // 对完全失败的用例，用 Modal 展示详情
      const failedCases = results.filter((r: any) => r.status !== 'success');
      const hasFailures = failedCases.length > 0;
      const allFailed = success_count === 0;

      if (allFailed) {
        // 全部失败：用 error 弹窗 + Modal 展示详情
        Modal.error({
          title: '批量转化失败',
          width: 600,
          content: (
            <div>
              <p style={{ marginBottom: 12 }}>{resultMsg}</p>
              {exploration_failures && Object.keys(exploration_failures).length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <strong>探索失败详情：</strong>
                  <ul style={{ marginTop: 4, paddingLeft: 20 }}>
                    {Object.entries(exploration_failures).map(([mod, reason]) => (
                      <li key={mod}><strong>{mod}</strong>: {String(reason)}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <strong>失败用例列表：</strong>
                <ul style={{ marginTop: 4, paddingLeft: 20, maxHeight: 300, overflow: 'auto' }}>
                  {failedCases.map((c: any) => (
                    <li key={c.test_case_id} style={{ marginBottom: 8 }}>
                      <strong>{c.case_name}</strong> [{c.module}] — {c.error}
                      {c.diagnostics?.step_details && c.diagnostics.step_details.length > 0 && (
                        <ul style={{ marginTop: 2, paddingLeft: 16, fontSize: 12 }}>
                          {c.diagnostics.step_details.map((sd: any) => (
                            <li key={sd.seq} style={{
                              color: sd.status === 'success' ? '#52c41a' :
                                     sd.status === 'not_found' ? '#ff4d4f' : '#999'
                            }}>
                              {sd.message || `步骤 ${sd.seq}: ${sd.target || '?'}`}
                            </li>
                          ))}
                        </ul>
                      )}
                      {c.diagnostics?.warning && (
                        <div style={{ color: '#faad14', fontSize: 11, marginTop: 2 }}>
                          ⚠ {c.diagnostics.warning}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
              {renderSkippedBlock(skippedCases)}
            </div>
          ),
        });
      } else if (hasFailures) {
        // 部分失败：单个 Modal 展示统计 + 失败详情 + 跳过列表（不再重复 toast）
        const hasRealFailure = conversion_failed > 0 || exploration_failed > 0 || exploration_insufficient > 0;
        Modal.info({
          title: hasRealFailure ? '部分用例转化失败' : '部分用例步骤未定位',
          width: 600,
          content: (
            <div>
              <p style={{ marginBottom: 12 }}>{resultMsg}</p>
              <div>
                <strong>失败详情：</strong>
                <ul style={{ marginTop: 4, paddingLeft: 20, maxHeight: 300, overflow: 'auto' }}>
                  {failedCases.map((c: any) => (
                    <li key={c.test_case_id} style={{ marginBottom: 8 }}>
                      <strong>{c.case_name}</strong> [{c.module}]
                      <br /><span style={{ fontSize: 12 }}>
                        状态: <span style={{
                          color: c.status === 'steps_missing' ? '#faad14' :
                                 c.status === 'exploration_insufficient' ? '#fa8c16' :
                                 c.status === 'exploration_failed' ? '#ff4d4f' : '#722ed1'
                        }}>{c.status}</span>
                      </span>
                      <br /><span style={{ color: '#999', fontSize: 12 }}>{c.error || c.diagnostics?.warning}</span>
                      {c.diagnostics?.step_details && c.diagnostics.step_details.some((s: any) => s.status === 'not_found') && (
                        <ul style={{ marginTop: 2, paddingLeft: 16, fontSize: 11 }}>
                          {c.diagnostics.step_details.filter((s: any) => s.status === 'not_found').map((sd: any) => (
                            <li key={sd.seq} style={{ color: '#ff4d4f' }}>
                              ✗ 步骤 {sd.seq}: {sd.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
              {renderSkippedBlock(skippedCases)}
            </div>
          ),
        });
      } else {
        // 全部成功（含 steps_missing 警告）
        const withWarnings = results.filter((r: any) => r.diagnostics?.warning);
        if (withWarnings.length > 0) {
          message.success(resultMsg + ' | 部分用例存在步骤未定位，已用橙色标记', 8);
        } else {
          message.success(resultMsg, 8);
        }
      }

      // 全成功且有跳过时，跳过列表独立展示（失败场景已合并进失败弹窗，避免叠加）
      if (skippedCases.length > 0 && !allFailed && !hasFailures) {
        Modal.info({
          title: `本次转化跳过 ${skippedCases.length} 条用例`,
          width: 520,
          content: renderSkippedBlock(skippedCases),
        });
      }
      batchSucceeded = true;
    } catch (error: any) {
      const detail = error.response?.data?.detail || error.message || '批量转化失败';
      setConvertProgressText(prev => prev + `\n\n❌ 转化失败: ${detail}`);
      message.error(detail);
    } finally {
      setBatchConverting(false);
      if (batchSucceeded) {
        // 成功路径：清空进度 + 延迟关闭弹窗，让用户看到结果
        setConvertProgressText('');
        setConvertProgress(null);
        setConvertPhaseInfo(null);
        setTimeout(() => setBatchConvertModalVisible(false), 2000);
      }
      // 失败路径：保留弹窗与错误详情，用户看到原因后手动关闭（不再自动消失——2026-08-25 用户反馈「转化页面又自动消失了」）
    }
  };

  // 批量转化进度条百分比：按阶段加权——探索 0-60%（模块+当前模块步骤双进度）、POM 62%、转化 65-100%。
  // 无阶段信息时（后端旧逻辑/首次轮询前）退化为用例完成度。
  const convertPercent = (() => {
    if (!convertProgress) return 0;
    if (!convertPhaseInfo) {
      return convertProgress.total > 0
        ? Math.min(100, Math.round((convertProgress.done / convertProgress.total) * 100))
        : 0;
    }
    const { phase, exploredDone, exploredTotal, stepDone, stepTotal } = convertPhaseInfo;
    if (phase === 'exploring') {
      if (exploredTotal > 0) {
        const modFrac = exploredDone + (stepTotal > 0 ? Math.min(1, stepDone / stepTotal) : 0);
        return Math.min(60, Math.round((modFrac / exploredTotal) * 60));
      }
      return 3; // 模块数未知时保底微动，避免进度条静止
    }
    if (phase === 'pom') return 62;
    if (phase === 'converting') {
      const conv = convertProgress.total > 0
        ? Math.min(1, convertProgress.done / convertProgress.total) * 35
        : 0;
      return Math.min(99, Math.round(65 + conv));
    }
    if (phase === 'done') return 100;
    if (phase === 'failed') return 0;
    return 2;
  })();

  // ===== 探索功能已集成到"转化为UI"流程 =====
  // 不再需要独立的模块探索入口和统计弹窗。
  // 测试用例步骤现在驱动探索引擎，在转化过程中自动完成探索。

  // 打开单个审核
  const openReview = (caseId: string) => {
    setReviewCaseId(caseId); setReviewBatch(false);
    setReviewAction('approve'); setReviewComment(''); setReviewVisible(true);
  };

  // 可审核状态集（与后端 batch-review 守卫同源）：draft/pending_review/rejected 可审，
  // 已通过/已发布/终态跳过——全选批量审核时已审核记录不再被带入重复审核
  const REVIEWABLE_STATUSES = ['draft', 'pending_review', 'rejected'];

  // 解析本次待审核用例并分类（入口预检 / 执行审核共用同一口径，保证提示时机一致）
  const resolveReviewableCases = async () => {
    const axiosInstance = (await import('../../api/axiosConfig')).default;
    let allCases: { id: string; status: string }[] = [];
    if (selectAllMode) {
      // 跨页全选：分页拉取全部 ID 和状态
      let p = 1;
      while (true) {
        const { data } = await axiosInstance.get('/test-cases/', {
          params: {
            page: p, page_size: 100,
            version_id: selectedVersionId,
            search: searchText || undefined,
            status: filterStatus !== 'all' ? filterStatus : undefined,
          }
        });
        const items = data.items || [];
        allCases.push(...items.map((c: any) => ({ id: String(c.id), status: c.status || 'draft' })));
        if (allCases.length >= data.total || items.length === 0) break;
        p++;
      }
    } else {
      // 手动勾选：从当前页数据获取状态
      const statusMap = new Map(testCases.map(c => [c.id, c.status]));
      allCases = selectedTests.map(id => ({ id, status: statusMap.get(id) || 'draft' }));
    }
    const reviewable = allCases.filter(c => REVIEWABLE_STATUSES.includes(c.status));
    const skippedCount = allCases.length - reviewable.length;
    return { reviewable, skippedCount };
  };

  // 打开批量审核（入口预检：已审核记录全选时在点击时就提示，不等到提交）
  const openBatchReview = async () => {
    const { reviewable, skippedCount } = await resolveReviewableCases();
    if (reviewable.length === 0) {
      message.warning(skippedCount > 0 ? '所选记录均已审核，无需重复审核' : '请先选择要审核的用例');
      return;
    }
    if (skippedCount > 0) {
      message.warning(`所选记录中 ${skippedCount} 条已审核，本次将跳过，实际审核 ${reviewable.length} 条`);
    }
    setReviewBatch(true); setReviewAction('approve');
    setReviewComment(''); setReviewVisible(true);
  };

  // 执行审核
  const handleReview = async () => {
    if (!reviewCaseId && !reviewBatch) return;
    try {
      if (reviewBatch) {
        // 提交时重算一次可审核集（与预检同口径），已审核记录不提交给后端
        const { reviewable, skippedCount } = await resolveReviewableCases();
        if (reviewable.length === 0) {
          setReviewVisible(false);
          message.warning(skippedCount > 0 ? '所选记录均已审核，无需重复审核' : '没有可审核的用例');
          return;
        }
        await axiosInstance.post('/test-cases/batch-review', {
          case_ids: reviewable.map(c => Number(c.id)), action: reviewAction, comment: reviewComment,
        });
        const count = reviewable.length;
        setReviewVisible(false); setReviewComment('');
        if (reviewAction === 'approve' && count > 0) {
          Modal.confirm({
            title: `已通过 ${count} 条用例`,
            content: '是否立即将这些已通过的用例转化为 UI 自动化用例？',
            okText: '立即转化',
            cancelText: '稍后再说',
            onOk: () => handleBatchConvertToUI(),
          });
        } else {
          message.success(`${reviewAction === 'approve' ? '已通过' : '已驳回'} ${count} 条`);
        }
        setSelectedTests([]);
      } else {
        await axiosInstance.post(`/test-cases/${reviewCaseId}/review`, {
          action: reviewAction, comment: reviewComment,
        });
        setReviewVisible(false); setReviewComment('');
        if (reviewAction === 'approve') {
          message.success('已通过');
          // 刷新列表以更新状态
          fetchTestCases();
        } else {
          message.success('已驳回');
          fetchTestCases();
        }
      }
      fetchTestCases();
    } catch (e: any) { message.error(e.response?.data?.detail || '审核失败'); }
  };

  const loadDetailPage = async (targetPage: number, selectLast: boolean) => {
    const { data } = await axiosInstance.get('/test-cases/', {
      params: { page: targetPage, page_size: pagination.pageSize, version_id: selectedVersionId, search: searchText || undefined }
    });
    const items = data.items || [];
    if (items.length > 0) {
      const transformed = items.map((item: any) => ({
        id: String(item.id), name: item.name || '未命名', description: item.description || '',
        module: item.module || '通用模块', preconditions: item.preconditions || '',
        test_steps: Array.isArray(item.test_steps) ? item.test_steps : [],
        expected_result: item.expected_result || '', lastRun: item.created_at ? formatDateTime(item.created_at) : '-',
        priority: (item.priority === 'P0' ? 'high' : item.priority === 'P1' ? 'medium' : 'low') as 'high' | 'medium' | 'low',
        duration: 0, status: item.status || 'draft', project_id: item.project_id, version_id: item.version_id,
        project_name: selectedProject?.name, version_number: versions.find(v => v.id === selectedVersionId)?.version_number,
      }));
      const idx = selectLast ? transformed.length - 1 : 0;
      setTestCases(transformed);
      setCurrentIndex(idx);
      setSelectedTestCase(transformed[idx]);
      navFetchRef.current = true;  // 阻止 useEffect 重复加载
      setPagination(prev => ({ ...prev, page: targetPage, total: data.total || 0 }));
    }
  };

  const handlePrevTestCase = async () => {
    if (currentIndex > 0) {
      const i = currentIndex - 1;
      setCurrentIndex(i);
      setSelectedTestCase(testCases[i]);
    } else if (pagination.page > 1) {
      await loadDetailPage(pagination.page - 1, true);
    } else {
      message.info('已是第一条');
    }
  };

  const handleNextTestCase = async () => {
    if (currentIndex < testCases.length - 1) {
      const i = currentIndex + 1;
      setCurrentIndex(i);
      setSelectedTestCase(testCases[i]);
    } else if (pagination.page * pagination.pageSize < pagination.total) {
      await loadDetailPage(pagination.page + 1, false);
    } else {
      message.info('已是最后一条');
    }
  };

  const handleExport = async () => {
    if (!selectedVersionId) {
      message.error('请先选择版本');
      return;
    }

    if (!selectAllMode && selectedTests.length === 0) {
      message.warning('请先选择要导出的用例');
      return;
    }

    setExporting(true);
    try {
      let cases: any[] = [];

      const totalToExport = selectAllMode ? pagination.total : selectedTests.length;
      const pageSize = 100;
      const totalPages = Math.ceil(totalToExport / pageSize);

      // 按页面类型使用不同的数据源
      const listUrl = isAPIPage ? `/api-tests/cases/version/${selectedVersionId}`
        : isUIPage ? '/web-ui-tests/test-cases'
        : '/test-cases/';

      for (let page = 1; page <= totalPages; page++) {
        const params: any = { page, page_size: pageSize };
        if (isUIPage && selectedProjectId) params.project_id = selectedProjectId;
        if (!isUIPage) params.version_id = selectedVersionId;
        const { data: listData } = await axiosInstance.get(listUrl, { params });
        const response = { items: listData.items || [], total: listData.total || 0 };
        
        if (selectAllMode) {
          cases = cases.concat(response.items || []);
        } else {
          const filtered = response.items?.filter((c: any) => selectedTests.includes(String(c.id))) || [];
          cases = cases.concat(filtered);
        }
        
        if (cases.length >= totalToExport) break;
      }
      
      if (selectAllMode) {
        cases = cases.slice(0, pagination.total);
      }
      
      if (cases.length === 0) {
        message.warning('没有可导出的测试用例');
        setExporting(false);
        return;
      }
      
      const project = projects.find(p => p.id === selectedProjectId);
      const version = versions.find(v => v.id === selectedVersionId);
      
      let content: string = '';
      let filename: string = '';
      let mimeType: string = '';
      
      if (exportTemplate === 'zentao_csv') {
        const headers = ['用例名称', '所属模块', '优先级', '前置条件', '测试步骤', '预期结果', '关键词'];
        const rows = cases.map((c: any) => [
          c.name || '',
          c.module || '',
          c.priority || 'P2',
          c.preconditions || '',
          formatTestSteps(c.test_steps),
          c.expected_result || '',
          ''
        ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
        content = [headers.join(','), ...rows].join('\n');
        filename = `${project?.name}_${version?.version_number}_测试用例_禅道.csv`;
        mimeType = 'text/csv;charset=utf-8';
      } else if (exportTemplate === 'zentao_xml') {
        content = generateZentaoXML(cases, project, version);
        filename = `${project?.name}_${version?.version_number}_测试用例_禅道.xml`;
        mimeType = 'application/xml;charset=utf-8';
      } else if (exportTemplate === 'jira_csv') {
        const headers = ['Summary', 'Issue Type', 'Priority', 'Description', 'Test Steps', 'Expected Result'];
        const rows = cases.map((c: any) => [
          c.name || '',
          'Test',
          mapPriorityToJira(c.priority),
          c.description || '',
          formatTestSteps(c.test_steps),
          c.expected_result || ''
        ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
        content = [headers.join(','), ...rows].join('\n');
        filename = `${project?.name}_${version?.version_number}_测试用例_Jira.csv`;
        mimeType = 'text/csv;charset=utf-8';
      } else if (exportTemplate === 'json') {
        content = JSON.stringify({
          project: project?.name,
          version: version?.version_number,
          export_time: new Date().toISOString(),
          total: cases.length,
          test_cases: cases.map((c: any) => ({
            id: c.id,
            name: c.name,
            module: c.module,
            priority: c.priority,
            description: c.description,
            preconditions: c.preconditions,
            test_steps: c.test_steps,
            expected_result: c.expected_result
          }))
        }, null, 2);
        filename = `${project?.name}_${version?.version_number}_测试用例.json`;
        mimeType = 'application/json;charset=utf-8';
      } else if (exportTemplate === 'excel') {
        const headers = ['用例ID', '用例名称', '所属模块', '优先级', '描述', '前置条件', '测试步骤', '预期结果'];
        const rows = cases.map((c: any) => [
          c.id,
          c.name || '',
          c.module || '',
          c.priority || 'P2',
          c.description || '',
          c.preconditions || '',
          formatTestSteps(c.test_steps),
          c.expected_result || ''
        ]);
        const csvContent = [headers.join('\t'), ...rows.map(r => r.join('\t'))].join('\n');
        content = csvContent;
        filename = `${project?.name}_${version?.version_number}_测试用例.csv`;
        mimeType = 'text/csv;charset=utf-8';
      }
      
      const blob = new Blob(['\ufeff' + content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      message.success(`成功导出 ${cases.length} 条测试用例`);
      setExportModalVisible(false);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '导出失败');
    } finally {
      setExporting(false);
    }
  };

  const formatTestSteps = (steps: any): string => {
    if (!steps || !Array.isArray(steps) || steps.length === 0) return '';
    return steps.map((s: any, i: number) => {
      const action = typeof s === 'string' ? s : s.action || '';
      const expected = typeof s === 'string' ? '' : s.expected || '';
      return `${i + 1}. ${action}${expected ? ' (预期: ' + expected + ')' : ''}`;
    }).join('\n');
  };

  const mapPriorityToJira = (priority: string): string => {
    const map: Record<string, string> = {
      'P0': 'Highest',
      'P1': 'High',
      'P2': 'Medium',
      'P3': 'Low'
    };
    return map[priority] || 'Medium';
  };

  const generateZentaoXML = (cases: any[], project: any, version: any): string => {
    let xml = '<?xml version="1.0" encoding="UTF-8"?>\n';
    xml += '<testcases>\n';
    xml += `  <project name="${project?.name || ''}" version="${version?.version_number || ''}">\n`;
    cases.forEach((c: any) => {
      xml += '    <testcase>\n';
      xml += `      <name>${escapeXml(c.name || '')}</name>\n`;
      xml += `      <module>${escapeXml(c.module || '')}</module>\n`;
      xml += `      <priority>${c.priority || 'P2'}</priority>\n`;
      xml += `      <preconditions>${escapeXml(c.preconditions || '')}</preconditions>\n`;
      xml += '      <steps>\n';
      if (c.test_steps && Array.isArray(c.test_steps)) {
        c.test_steps.forEach((s: any, i: number) => {
          const action = typeof s === 'string' ? s : s.action || '';
          const expected = typeof s === 'string' ? '' : s.expected || '';
          xml += `        <step order="${i + 1}">\n`;
          xml += `          <actions>${escapeXml(action)}</actions>\n`;
          xml += `          <expected>${escapeXml(expected)}</expected>\n`;
          xml += '        </step>\n';
        });
      }
      xml += '      </steps>\n';
      xml += `      <expectedresult>${escapeXml(c.expected_result || '')}</expectedresult>\n`;
      xml += '    </testcase>\n';
    });
    xml += '  </project>\n';
    xml += '</testcases>';
    return xml;
  };

  const escapeXml = (str: string): string => {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  };

  const filteredCases = testCases.filter(caseItem => {
    const matchesSearch = searchText === '' || 
      caseItem.name.toLowerCase().includes(searchText.toLowerCase()) ||
      caseItem.description.toLowerCase().includes(searchText.toLowerCase());
    const matchesModule = filterModule === 'all' || caseItem.module === filterModule;
    const matchesStatus = filterStatus === 'all' || caseItem.status === filterStatus;
    return matchesSearch && matchesModule && matchesStatus;
  });

  const columns: ColumnsType<TestCase> = [
    {
      title: '用例名称',
      dataIndex: 'name',
      key: 'name',
      width: isAPIPage || isUIPage ? 280 : 200,
      ellipsis: true,
      render: (text, record) => (
        <Space>
          {text}
          {record.priority === 'high' && <Tag color="red">P0</Tag>}
          {record.revision_no ? (
            record.derived_from_id ? (
              <Tooltip title={`变更派生修订 v${record.revision_no}（自 v${record.revision_no - 1} 派生，需审核后发布）`}>
                <Tag color="orange">v{record.revision_no}</Tag>
              </Tooltip>
            ) : (
              <Tag>v{record.revision_no}</Tag>
            )
          ) : null}
        </Space>
      ),
    },
    {
      title: '所属模块',
      dataIndex: 'module',
      key: 'module',
      width: 100,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      render: (priority: string) => (
        <Tag color={
          priority === 'high' ? 'red' :
          priority === 'medium' ? 'orange' : 'green'
        }>
          {priority === 'high' ? 'P0' :
           priority === 'medium' ? 'P1' : 'P2'}
        </Tag>
      ),
    },
    // UI 用例没有状态概念（无审核流），仅功能用例/API用例页显示状态列
    ...(isUIPage ? [] : [{
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s: string) => {
        const c = STATUS_MAP[s] || { color: 'default', label: s || '未知' };
        return <Tag color={c.color}>{c.label}</Tag>;
      },
    }]),
    {
      title: '创建时间',
      dataIndex: 'lastRun',
      key: 'lastRun',
      width: 150,
    },
    {
      title: '操作',
      key: 'action',
      width: isAPIPage || isUIPage ? 180 : 260,
      render: (_, record) => (
        // UI 用例操作列均为图标按钮，间距加大避免图标重叠
        <Space size={isUIPage ? 'middle' : 'small'}>
          {!isUIPage && (record.status === 'draft' || record.status === 'pending_review') && (
            <Button
              type="link"
              size="small"
              onClick={() => openReview(record.id)}
            >
              审核
            </Button>
          )}
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => {
              const index = testCases.findIndex(t => t.id === record.id);
              setCurrentIndex(index);
              setSelectedTestCase(record);
              setDetailVisible(true);
            }}
          >
            查看
          </Button>
          {isUIPage && (
            <Tooltip title="执行UI自动化测试">
              <Button
                type="link" size="small"
                icon={<PlayCircleOutlined />}
                onClick={() => {
                  Modal.confirm({
                    title: '确认执行',
                    content: '将在服务器上执行此UI自动化测试，可能需要几分钟。',
                    onOk: async () => {
                      try {
                        const r = await axiosInstance.post('/web-ui-tests/execute', { web_ui_test_case_id: record.id, environment: 'development' }, { params: { headless: false } });
                        if (r.data?.status === 'completed') {
                          message.success('测试执行完成');
                        } else {
                          message.error('执行失败: ' + (r.data?.error || r.data?.status || '未知'));
                        }
                      } catch (e: any) {
                        message.error('执行失败: ' + (e.response?.data?.detail || e.message));
                      }
                    },
                  });
                }}
              />
            </Tooltip>
          )}
          {!isAPIPage && !isUIPage && (
          <Tooltip title={
            convertedIds.has(String(record.id)) ? '已转化为UI用例' :
            (record.status !== 'approved' && record.status !== 'active') ? '请先审核通过该用例' :
            'AI将功能测试步骤转化为Playwright UI自动化脚本'
          }>
            <Button
              type="link"
              size="small"
              icon={<ThunderboltOutlined />}
              style={{ color: ((record.status === 'approved' || record.status === 'active') && !convertedIds.has(String(record.id))) ? '#722ed1' : '#bbb' }}
              disabled={(record.status !== 'approved' && record.status !== 'active') || convertedIds.has(String(record.id))}
              onClick={() => handleOpenConvert(record)}
            >
              转化为UI
            </Button>
          </Tooltip>
          )}
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            style={isUIPage ? { marginLeft: 6 } : undefined}
            onClick={() => {
              const tid = (record as any).test_case_id || (record as any).testCaseId || '';
              if (tid === '__login__' || record.id === '__login__') {
                message.warning('系统登录用例是所有用例的前置条件，不可删除');
                return;
              }
              handleDeleteCase(record.id);
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      <Sider width={210} style={{ background: '#fff', borderRight: '1px solid #e8e8e8' }}>
        <Card 
          title={<Space><FolderOutlined /> 项目/版本选择</Space>} 
          style={{ height: '100%', borderRadius: 0 }}
          bodyStyle={{ padding: '12px 4px', height: 'calc(100% - 57px)', overflow: 'auto' }}
        >
          {loadingTree ? (
            <Spin />
          ) : (
            <Tree
              showIcon
              treeData={treeData}
              onSelect={handleTreeSelect}
              expandedKeys={expandedKeys}
              onExpand={(keys) => setExpandedKeys(keys as string[])}
              blockNode
              className="functional-test-tree"
              selectedKeys={[]}
            />
          )}
        </Card>
      </Sider>
      
      <Content style={{ padding: '6px' }}>
        <Card>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Title level={4} style={{ margin: 0 }}>
                  {selectedProjectId ? (
                    <Space>
                      <Tag color="blue">{projects.find(p => p.id === selectedProjectId)?.name}</Tag>
                      {selectedVersionId ? (
                        <>
                          <Tag color="green">{versions.find(v => v.id === selectedVersionId)?.version_number}</Tag>
                          测试用例
                        </>
                      ) : (
                        <Text type="secondary">请选择版本</Text>
                      )}
                    </Space>
                  ) : '请先选择项目'}
                </Title>
              </Space>
            </div>

            {selectedVersionId && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space>
                    <Search
                      placeholder="搜索用例名称或描述"
                      allowClear
                      onSearch={setSearchText}
                      style={{ width: 250 }}
                    />
                    <Select
                      value={filterModule}
                      onChange={setFilterModule}
                      style={{ width: 150 }}
                    >
                      <Option value="all">所有模块</Option>
                      {modules.map(mod => (
                        <Option key={mod} value={mod}>{mod}</Option>
                      ))}
                    </Select>
                    {/* UI 用例无审核状态，不显示状态过滤 */}
                    {!isUIPage && (
                    <Select
                      value={filterStatus}
                      onChange={setFilterStatus}
                      style={{ width: 120 }}
                    >
                      <Option value="all">所有状态</Option>
                      <Option value="draft">草稿</Option>
                      <Option value="pending_review">待审批</Option>
                      <Option value="approved">已通过</Option>
                      <Option value="rejected">已驳回</Option>
                    </Select>
                    )}
                  </Space>
                  {/* 批量导出/删除 — 功能用例+API用例页显示，UI用例页隐藏 */}
                  {!isUIPage && (
                  <Space>
                    <Button
                      icon={<ExportOutlined />}
                      onClick={() => setExportModalVisible(true)}
                      disabled={selectedTests.length === 0 && !selectAllMode}
                      size="small"
                    >
                      批量导出
                    </Button>
                    <Button
                      icon={<DeleteOutlined />}
                      onClick={() => {
                        const count = selectAllMode ? pagination.total : selectedTests.length;
                        if (!count) return;
                        Modal.confirm({
                          title: `确定删除选中的 ${count} 条用例？`,
                          content: '此操作不可恢复',
                          okText: '删除', okType: 'danger',
                          onOk: async () => {
                            try {
                              let ids: string[] = [];
                              if (selectAllMode) {
                                const listUrl = isAPIPage ? `/api-tests/cases/version/${selectedVersionId}`
                                  : '/test-cases/';
                                let p = 1;
                                while (true) {
                                  const { data } = await axiosInstance.get(listUrl, {
                                    params: { page: p, page_size: 100, version_id: selectedVersionId }
                                  });
                                  ids.push(...(data.items || []).map((c: any) => String(c.id)));
                                  if (ids.length >= data.total) break;
                                  p++;
                                }
                              } else {
                                ids = selectedTests;
                              }
                              const deleteUrl = isAPIPage ? '/api-tests/cases/batch-delete'
                                : '/test-cases/batch-delete';
                              const resp = await axiosInstance.post(deleteUrl, {
                                case_ids: ids.map(id => Number(id)),
                              });
                              if (resp.data?.blocked?.length > 0) {
                                message.warning(resp.data.message);
                              } else {
                                message.success(resp.data?.message || '删除成功');
                              }
                              setSelectedTests([]); setSelectAllMode(false);
                              fetchTestCases();
                            } catch (e: any) {
                              message.error(e.response?.data?.detail || '批量删除失败');
                            }
                          },
                        });
                      }}
                      disabled={selectedTests.length === 0 && !selectAllMode}
                      size="small"
                      danger
                    >
                      批量删除
                    </Button>
                  </Space>
                  )}
                </div>
                
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingLeft: 12, marginTop: 12 }}>
                   <Space size={0}>
                     <Checkbox
                       checked={selectAllMode}
                       onChange={(e) => {
                         setSelectAllMode(e.target.checked);
                         if (e.target.checked) {
                           setSelectedTests([]);
                         }
                       }}
                     >
                       全选所有用例（共 {pagination.total} 条）
                     </Checkbox>
                     {selectedTests.length > 0 && !selectAllMode && (
                       <Button
                         type="link"
                         size="small"
                         onClick={() => setSelectedTests([])}
                       >
                         清除选中
                       </Button>
                     )}
</Space>
                    <Space style={{ alignSelf: 'flex-start', marginTop: -12 }}>
                      {!hasLoginModule && (
                        <Alert
                          type="warning" showIcon
                          style={{ marginBottom: 0, padding: '4px 12px' }}
                          message={<>⚠️ 尚未导入登录模块，无法导入业务流/需求/用例。请先在「项目配置」中设置登录流程。</>}
                        />
                      )}
                      {selectedTests.length > 0 && (
                        <Text type="secondary">已选中 {selectAllMode ? pagination.total : selectedTests.length} 条</Text>
                      )}
                      {/* 导入已评审用例 — 仅功能用例页显示 */}
                      {!window.location.pathname.includes('/web-ui') && !window.location.pathname.includes('/api') && (
                        <Button
                          icon={<ImportOutlined />}
                          onClick={() => setShowImp(true)}
                          disabled={!hasLoginModule}
                          style={{ background: '#e6fffb', color: '#13c2c2', borderColor: '#87e8de' }}
                          title={!hasLoginModule ? '请先导入登录模块' : ''}
                        >
                          导入已评审用例
                        </Button>
                      )}
                      {/* 批量审核 — 仅功能用例页显示 */}
                      {!window.location.pathname.includes('/web-ui') && !window.location.pathname.includes('/api') && (
                        <Button
                          icon={<CheckCircleOutlined />}
                          onClick={openBatchReview}
                          disabled={selectedTests.length === 0 && !selectAllMode}
                          style={{ background: '#fff7e6', color: '#fa8c16', borderColor: '#ffd591' }}
                        >
                          批量审核
                        </Button>
                      )}
                      {/* 批量转化为UI — 仅功能用例页显示，APP端禁用 */}
                      {!window.location.pathname.includes('/web-ui') && !window.location.pathname.includes('/api') && (
                        <Tooltip title={isAppProject ? 'APP端暂不支持转为WebUI脚本' : '将功能用例转为Playwright UI自动化脚本'}>
                          <Button
                            icon={<ThunderboltOutlined />}
                            onClick={handleBatchConvertToUI}
                            loading={batchConverting}
                            disabled={!hasLoginModule || isAppProject || (selectedTests.length === 0 && !selectAllMode)}
                            style={{ background: (!hasLoginModule || isAppProject) ? '#f5f5f5' : '#f9f0ff', color: (!hasLoginModule || isAppProject) ? '#bbb' : '#722ed1', borderColor: (!hasLoginModule || isAppProject) ? '#d9d9d9' : '#d3adf7' }}
                          >
                            批量转化为UI
                          </Button>
                        </Tooltip>
                      )}
                      {/* 批量执行 + 批量删除 — 仅UI用例页显示 */}
                      {window.location.pathname.includes('/web-ui') && (
                        <>
                          <Button
                            icon={<PlayCircleOutlined />}
                            type="primary"
                            disabled={selectedTests.length === 0 && !selectAllMode}
                            onClick={async () => {
                              let ids: string[];
                              if (selectAllMode) {
                                const allResp = await axiosInstance.get('/web-ui-tests/all-ids');
                                ids = allResp.data.ids || [];
                              } else {
                                ids = selectedTests as string[];
                              }
                              Modal.confirm({
                                title: '批量执行（有头+复用）',
                                content: `浏览器打开一次，登录后依次执行 ${ids.length} 条用例。`,
                                onOk: async () => {
                                  try {
                                    const r = await axiosInstance.post('/web-ui-tests/execute-batch',
                                      { ids },
                                      { params: { headless: false }, timeout: 7200000 }
                                    );
                                    message.success(`完成: ${r.data.ok} 成功, ${r.data.fail} 失败`);
                                  } catch (e: any) {
                                    message.error('执行失败: ' + (e.response?.data?.detail || e.message));
                                  }
                                },
                              });
                            }}
                          >
                            批量执行
                          </Button>
                          <Button
                            icon={<DeleteOutlined />}
                            danger
                            disabled={selectedTests.length === 0 && !selectAllMode}
                            onClick={async () => {
                              let ids: string[];
                              if (selectAllMode) {
                                const allResp = await axiosInstance.get('/web-ui-tests/all-ids');
                                ids = allResp.data.ids || [];
                              } else {
                                ids = selectedTests as string[];
                              }
                              Modal.confirm({
                                title: '批量删除UI用例',
                                content: `确定删除 ${ids.length} 条UI用例吗？仅删除UI脚本，不影响功能用例。`,
                                okText: '删除', okType: 'danger',
                                onOk: async () => {
                                  let ok = 0;
                                  for (const id of ids) {
                                    try { await axiosInstance.delete(`/web-ui-tests/test-cases/${id}`); ok++; }
                                    catch (e) {}
                                  }
                                  setTestCases(prev => prev.filter(t => !ids.includes(t.id)));
                                  setSelectedTests([]);
                                  setSelectAllMode(false);
                                  message.success(`已删除 ${ok} 条`);
                                },
                              });
                            }}
                          >
                            批量删除
                          </Button>
                        </>
                      )}
                    </Space>
                  </div>
                 
                 <Table
                   columns={columns}
                   dataSource={filteredCases}
                   rowKey="id"
                   loading={loadingCases}
                   style={{ marginTop: -16 }}
                   rowSelection={{
                    selectedRowKeys: selectAllMode ? filteredCases.map(c => c.id) : selectedTests,
                    onChange: (keys) => {
                      setSelectedTests(keys as string[]);
                      setSelectAllMode(false);
                    },
                    getCheckboxProps: () => ({
                      disabled: selectAllMode,
                    }),
                  }}
                  pagination={{
                    current: pagination.page,
                    pageSize: pagination.pageSize,
                    total: pagination.total,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条`,
                    onChange: (page, pageSize) => setPagination(prev => ({ ...prev, page, pageSize })),
                  }}
                  scroll={{ x: 800 }}
                />
              </>
            )}
            
            {!selectedVersionId && (
              <Empty 
                description="请在左侧选择项目下的版本查看测试用例" 
                style={{ padding: '60px 0' }}
              />
            )}
          </Space>
        </Card>
      </Content>
      
      <Modal
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: 40 }}>
            <Space>
              <span>测试用例详情</span>
              {selectedTestCase && (
                <Space>
                  <Tag color="blue">{selectedTestCase.project_name}</Tag>
                  <Tag color="green">{selectedTestCase.version_number}</Tag>
                </Space>
              )}
            </Space>
            {selectedTestCase && editingCaseId !== selectedTestCase.id
              && (selectedTestCase as any).test_case_id !== '__login__' && (selectedTestCase as any).id !== '__login__' && (
              <Button size="small" type="primary" icon={<EditOutlined />} onClick={() => {
                  if (selectedTestCase) {
                    const steps = (selectedTestCase.test_steps && Array.isArray(selectedTestCase.test_steps))
                      ? selectedTestCase.test_steps.map((s: any, i: number) => {
                          if (typeof s === 'string') return { step: i + 1, action: s, expected: '' };
                          return { step: s.step || i + 1, action: s.action || '', expected: s.expected || s.expected_result || '' };
                        })
                      : [];
                    setEditingCaseId(selectedTestCase.id);
                    setEditStepsLocal(steps);
                    setEditFormLocal({ name: selectedTestCase.name, module: selectedTestCase.module, priority: selectedTestCase.priority, preconditions: selectedTestCase.preconditions || '', expected_result: selectedTestCase.expected_result || '', description: selectedTestCase.description || '' });
                  }
                }}>编辑</Button>
            )}
          </div>
        }
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={(() => {
          const isFirst = currentIndex <= 0;
          const isLast = currentIndex >= testCases.length - 1;
          const hasPrevPage = pagination.page > 1;
          const hasNextPage = pagination.page * pagination.pageSize < pagination.total;
          const atFirstDisabled = isFirst && !hasPrevPage;
          const atLastDisabled = isLast && !hasNextPage;
          const prevLabel = (isFirst && hasPrevPage) ? '上一页' : '上一个';
          const nextLabel = (isLast && hasNextPage) ? '下一页' : '下一个';
          return [
            <Button key="prev" icon={<LeftOutlined />} onClick={handlePrevTestCase} disabled={atFirstDisabled}>
              {prevLabel}
            </Button>,
            <Button key="next" icon={<RightOutlined />} onClick={handleNextTestCase} disabled={atLastDisabled}>
              {nextLabel}
            </Button>,
            <Button key="close" onClick={() => setDetailVisible(false)}>
              关闭
            </Button>,
          ];
        })()}
        width={700}
      maskClosable={false}
      >
        {selectedTestCase && (() => {
          const isEditing = editingCaseId === selectedTestCase.id;
          const initSteps = (selectedTestCase.test_steps && Array.isArray(selectedTestCase.test_steps))
            ? selectedTestCase.test_steps.map((s: any, i: number) => {
                if (typeof s === 'string') return { step: i + 1, action: s, expected: '' };
                return { step: s.step || i + 1, action: s.action || '', expected: s.expected || s.expected_result || '' };
              })
            : [];
          const cancelEdit = () => { setEditingCaseId(null); };

          const handleAddStep = () => setEditStepsLocal([...editSteps, { step: editSteps.length + 1, action: '', expected: '' }]);
          const handleInsertStep = (idx: number) => {
            const u = [...editSteps]; u.splice(idx + 1, 0, { step: 0, action: '', expected: '' });
            setEditStepsLocal(u.map((s, i) => ({ ...s, step: i + 1 })));
          };
          const handleRemoveStep = (idx: number) => {
            if (editSteps.length <= 1) return;
            setEditStepsLocal(editSteps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step: i + 1 })));
          };
          const handleUpdateStep = (idx: number, field: string, value: string) => {
            const u = [...editSteps]; u[idx] = { ...u[idx], [field]: value }; setEditStepsLocal(u);
          };
          const handleSave = async () => {
            setSavingDetail(true);
            try {
              const steps = editSteps.filter(s => (s.action || '').trim() || (s.expected || '').trim()).map((s, i) => ({ step: i + 1, action: s.action, expected: s.expected }));
              await axiosInstance.put(`/test-cases/${selectedTestCase.id}`, {
                name: editFormLocal.name, module: editFormLocal.module, priority: editFormLocal.priority,
                preconditions: editFormLocal.preconditions, expected_result: editFormLocal.expected_result,
                description: editFormLocal.description, test_steps: steps,
              });
              message.success('保存成功');
              setEditingCaseId(null);
              selectedTestCase.name = editFormLocal.name;
              selectedTestCase.module = editFormLocal.module;
              selectedTestCase.priority = editFormLocal.priority;
              selectedTestCase.preconditions = editFormLocal.preconditions;
              selectedTestCase.expected_result = editFormLocal.expected_result;
              selectedTestCase.description = editFormLocal.description;
              selectedTestCase.test_steps = steps;
              fetchTestCases();
            } catch (e: any) { message.error(e.response?.data?.detail || '保存失败'); }
            finally { setSavingDetail(false); }
          };

          return isEditing ? (
            <div>
              <Form layout="vertical" size="small">
                <Form.Item label="标题"><Input value={editFormLocal.name} onChange={e => setEditFormLocal({...editFormLocal, name: e.target.value})} /></Form.Item>
                <Row gutter={16}>
                  <Col span={12}><Form.Item label="模块"><Input value={editFormLocal.module} onChange={e => setEditFormLocal({...editFormLocal, module: e.target.value})} /></Form.Item></Col>
                  <Col span={12}><Form.Item label="优先级"><Select value={editFormLocal.priority} onChange={v => setEditFormLocal({...editFormLocal, priority: v})}><Select.Option value="P0">P0</Select.Option><Select.Option value="P1">P1</Select.Option><Select.Option value="P2">P2</Select.Option><Select.Option value="P3">P3</Select.Option></Select></Form.Item></Col>
                </Row>
                <Form.Item label="前置条件"><Input.TextArea rows={2} value={editFormLocal.preconditions} onChange={e => setEditFormLocal({...editFormLocal, preconditions: e.target.value})} /></Form.Item>
                <Form.Item label="测试步骤及预期结果">
                  <Table dataSource={editSteps.map((s: any, i: number) => ({ ...s, key: i }))} pagination={false} size="small" bordered
                    columns={[
                      { title: '#', width: 40, align: 'center', render: (_: any, __: any, i: number) => <Text strong>{i + 1}</Text> },
                      { title: '操作步骤', render: (v: any, _: any, i: number) => <Input.TextArea value={v?.action || ''} autoSize={{ minRows: 1, maxRows: 3 }} onChange={e => handleUpdateStep(i, 'action', e.target.value)} placeholder="操作步骤" style={{ border: 'none', background: 'transparent' }} /> },
                      { title: '预期结果', render: (v: any, _: any, i: number) => <Input.TextArea value={v?.expected || ''} autoSize={{ minRows: 1, maxRows: 3 }} onChange={e => handleUpdateStep(i, 'expected', e.target.value)} placeholder="预期结果" style={{ border: 'none', background: 'transparent' }} /> },
                      { title: '', width: 60, align: 'center', render: (_: any, __: any, i: number) => (<Space size={2}><Button size="small" type="text" icon={<PlusOutlined />} onClick={() => handleInsertStep(i)} /><Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => handleRemoveStep(i)} disabled={editSteps.length <= 1} /></Space>) },
                    ]}
                  />
                  <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={handleAddStep} block style={{ marginTop: 4 }}>添加步骤</Button>
                </Form.Item>
                <Form.Item label="描述"><Input.TextArea rows={2} value={editFormLocal.description} onChange={e => setEditFormLocal({...editFormLocal, description: e.target.value})} /></Form.Item>
              </Form>
              <div style={{ textAlign: 'right', marginTop: 12 }}>
                <Space><Button onClick={cancelEdit}>取消</Button><Button type="primary" icon={<SaveOutlined />} loading={savingDetail} onClick={handleSave}>保存</Button></Space>
              </div>
            </div>
          ) : (
            <div>
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label="用例名称" span={2}>{selectedTestCase.name}</Descriptions.Item>
                <Descriptions.Item label="所属模块">{selectedTestCase.module}</Descriptions.Item>
                <Descriptions.Item label="优先级"><Tag color={selectedTestCase.priority === 'high' ? 'red' : selectedTestCase.priority === 'medium' ? 'orange' : 'green'}>{selectedTestCase.priority === 'high' ? 'P0' : selectedTestCase.priority === 'medium' ? 'P1' : 'P2'}</Tag></Descriptions.Item>
                <Descriptions.Item label="描述" span={2}>{selectedTestCase.description || '-'}</Descriptions.Item>
                <Descriptions.Item label="前置条件" span={2}>{selectedTestCase.preconditions || '-'}</Descriptions.Item>
              </Descriptions>
              <div style={{ marginTop: 12 }}>
                <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>测试步骤及预期结果</Text>
                {initSteps.length > 0 ? (
                  <Table dataSource={initSteps.map((s: any, i: number) => ({ ...s, key: i }))} pagination={false} size="small" bordered
                    columns={[
                      { title: '#', dataIndex: 'step', width: 40, align: 'center' },
                      { title: '操作步骤', dataIndex: 'action' },
                      { title: '预期结果', dataIndex: 'expected', render: (v: string) => v || '-' },
                    ]}
                  />
                ) : <Text type="secondary">-</Text>}
              </div>
              <Descriptions bordered column={2} size="small" style={{ marginTop: 12 }}>
                <Descriptions.Item label="创建时间" span={2}>{selectedTestCase.lastRun}</Descriptions.Item>
              </Descriptions>
            </div>
          );
        })()}
      </Modal>
      
      <Modal
        title={<Space><ExportOutlined /> 批量导出测试用例</Space>}
        open={exportModalVisible}
        onCancel={() => setExportModalVisible(false)}
        onOk={handleExport}
        okText="开始导出"
        cancelText="取消"
        confirmLoading={exporting}
        width={500}
      maskClosable={false}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            将导出 {selectAllMode ? pagination.total : selectedTests.length} 条已选中的测试用例
          </Text>
        </div>
        <Divider>选择导出模板</Divider>
        <Radio.Group 
          value={exportTemplate} 
          onChange={(e) => setExportTemplate(e.target.value)}
          style={{ width: '100%' }}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Radio value="zentao_csv">
              <Space>
                <Tag color="blue">禅道</Tag>
                <span>CSV格式 - 适用于禅道测试用例导入</span>
              </Space>
            </Radio>
            <Radio value="zentao_xml">
              <Space>
                <Tag color="blue">禅道</Tag>
                <span>XML格式 - 适用于禅道测试用例导入</span>
              </Space>
            </Radio>
            <Radio value="jira_csv">
              <Space>
                <Tag color="purple">Jira</Tag>
                <span>CSV格式 - 适用于Jira测试用例导入</span>
              </Space>
            </Radio>
            <Radio value="excel">
              <Space>
                <Tag color="green">Excel</Tag>
                <span>XLSX格式 - 通用表格格式</span>
              </Space>
            </Radio>
            <Radio value="json">
              <Space>
                <Tag color="orange">JSON</Tag>
                <span>JSON格式 - 适用于其他系统导入</span>
              </Space>
            </Radio>
          </Space>
        </Radio.Group>
        <Divider />
        <div style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            提示：不同模板包含的字段略有差异，禅道格式包含：用例名称、所属模块、前置条件、测试步骤、预期结果等标准字段
          </Text>
        </div>
      </Modal>
      
      <style>{`
        .functional-test-tree .ant-tree-switcher {
          width: 24px !important;
          height: 32px !important;
          line-height: 32px !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
        }
        .functional-test-tree .ant-tree-switcher-icon {
          font-size: 16px !important;
        }
        .functional-test-tree .ant-tree-switcher-arrow svg {
          width: 14px !important;
          height: 14px !important;
        }
        .functional-test-tree .ant-tree-node-content-wrapper {
          min-height: 32px !important;
          display: flex !important;
          align-items: center !important;
          flex: 1 !important;
          padding-left: 0 !important;
        }
        .functional-test-tree .ant-tree-treenode {
          display: flex !important;
          align-items: center !important;
          height: 32px !important;
        }
        .functional-test-tree > .ant-tree-treenode {
          padding-left: 0 !important;
        }
        .functional-test-tree .ant-tree-child-tree {
          padding-left: 0 !important;
          margin-left: 8px !important;
        }
      `}</style>

      {/* 审核弹窗 */}
      <Modal
        title={reviewBatch ? `批量审核 ${selectAllMode ? pagination.total : selectedTests.length} 条` : '审核用例'}
        open={reviewVisible}
        onCancel={() => setReviewVisible(false)}
        onOk={handleReview}
        width={450}
        maskClosable={false}
      >
        <Form layout="vertical">
          <Form.Item label="审核结果">
            <Radio.Group value={reviewAction} onChange={e => setReviewAction(e.target.value)}>
              <Radio value="approve">✅ 通过</Radio>
              <Radio value="reject">❌ 驳回</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item label="审核意见">
            <Input.TextArea rows={2} placeholder="可选" value={reviewComment} onChange={e => setReviewComment(e.target.value)} />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI转化功能用例为UI用例弹窗 */}
      {/* 批量转化设置弹窗 */}
      <Modal
        title={<Space><ThunderboltOutlined style={{ color: '#722ed1' }} />批量转化设置</Space>}
        open={batchConvertModalVisible}
        onCancel={() => { abortRef.current?.abort(); setBatchConverting(false); setBatchConvertModalVisible(false); }}
        onOk={doBatchConvert}
        confirmLoading={batchConverting}
        footer={[
          // 调试解析+评分：临时测试按钮，2026-08-25 用户要求隐藏（保留代码，后续需要恢复时去掉 false && 即可）
          false && <Button key="debug" loading={debugLoading} onClick={async () => {
            setDebugLoading(true); setDebugResult(null);
            try {
              const ids = selectAllMode ? testCases.map(c => c.id) : selectedTests;
              const debugOut: any = {};
              // Step 1: 解析
              try {
                const { data: d1 } = await axiosInstance.post('/web-ui-tests/convert-batch-from-functional?debug=parse', {
                  test_case_ids: ids, browser: convertBrowser,
                  viewport_size: convertViewport, headless: convertHeadless,
                });
                debugOut.parse = d1;
              } catch (e: any) { debugOut.parse = { error: e.response?.data?.detail || '解析失败' }; }
              // Step 2: 评分
              try {
                const { data: d2 } = await axiosInstance.post('/web-ui-tests/convert-batch-from-functional?debug=score', {
                  test_case_ids: ids, browser: convertBrowser,
                  viewport_size: convertViewport, headless: convertHeadless,
                });
                debugOut.score = d2;
              } catch (e: any) { debugOut.score = { error: e.response?.data?.detail || '评分失败' }; }
              setDebugResult(debugOut);
            } catch (e: any) { message.error('调试失败'); }
            finally { setDebugLoading(false); }
          }}>🔍 调试解析+评分</Button>,
          <Button key="submit" type="primary" loading={batchConverting} disabled={batchConverting}
            onClick={doBatchConvert}>{batchConverting ? '转化中...' : '开始批量转化'}</Button>,
          <Button key="cancel" onClick={() => {
            // 转化中取消：先通知后端停止探索并关闭浏览器（fire-and-forget——后端在探索
            // 线程内检测取消标志后自行退出，前端无需等待），再重置本端状态
            if (batchConverting && batchTaskIdRef.current) {
              const _tid = batchTaskIdRef.current;
              (async () => {
                try {
                  const _ax = (await import('../../api/axiosConfig')).default;
                  await _ax.post(`/web-ui-tests/convert-batch-cancel/${_tid}`);
                } catch (_) { /* 取消通知失败不阻塞 UI 重置 */ }
              })();
            }
            batchTaskIdRef.current = null;
            abortRef.current?.abort(); setBatchConvertModalVisible(false); setBatchConverting(false); setDebugResult(null);
          }}>{batchConverting ? '取消转化' : '取消'}</Button>,
        ]}
        okText={batchConverting ? '转化中...' : '开始批量转化'}
        cancelText={batchConverting ? '转化中...' : '取消'}
        okButtonProps={{ disabled: batchConverting }}
        cancelButtonProps={{ disabled: batchConverting }}
        width={520}
        maskClosable={false}
      >
        {debugResult && (
          <div style={{ maxHeight: 400, overflow: 'auto', background: '#f5f5f5', borderRadius: 4, padding: 12, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap', marginBottom: 12 }}>
            {JSON.stringify(debugResult, null, 2)}
          </div>
        )}
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert type="info" showIcon
message="根据以下配置打开浏览器探索页面，提取交互元素，用于将功能用例转化为 POM + JSON 数据驱动的 Pytest 测试项目。"
            style={{ fontSize: 12 }} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            探索将使用项目设置中配置的目标 URL 与账号密码，无需在此输入。
          </Text>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Switch checked={convertForceExplore} onChange={setConvertForceExplore} size="small" />
            <Text type="secondary" style={{ fontSize: 12 }}>强制重新探索（忽略缓存，用于版本迭代变更场景）</Text>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* 无头模式与强制探索正交（可任意组合）：浏览器/视口跟随有头模式——无头时浏览器不可见，选择无意义置灰；关闭无头即可选 */}
            <Switch checked={convertHeadless} onChange={setConvertHeadless} size="small" />
            <Text type="secondary" style={{ fontSize: 12 }}>无头模式（后台运行浏览器，关闭可查看探索过程）</Text>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Text type="secondary">浏览器</Text>
              <Select value={convertBrowser} onChange={setConvertBrowser} style={{ width: '100%' }} disabled={convertHeadless}>
                <Option value="chromium">Chromium</Option>
                <Option value="firefox">Firefox</Option>
                <Option value="webkit">WebKit</Option>
              </Select>
            </div>
            <div style={{ flex: 1 }}>
              <Text type="secondary">视口尺寸</Text>
              <Select value={convertViewport} onChange={setConvertViewport} style={{ width: '100%' }} disabled={convertHeadless}>
                <Option value="1920x1080">桌面 1920×1080</Option>
                <Option value="1366x768">桌面 1366×768</Option>
                <Option value="768x1024">平板 768×1024</Option>
                <Option value="375x667">手机 375×667</Option>
              </Select>
            </div>
          </div>
        </Space>
        {/* 转化进度：底部按钮上方 + 进度条（2026-08-17 用户要求；2026-08-25 阶段化——探索/POM/转化分阶段显示，从点击转化即开始移动） */}
        {batchConverting && (
          <div style={{ marginTop: 16 }}>
            <Progress
              percent={convertPercent}
              status="active"
              strokeColor="#722ed1"
            />
            <Alert type="info" showIcon style={{ marginTop: 8, whiteSpace: 'pre-line' }}
              message={convertProgressText || '正在转化...'} />
          </div>
        )}
      </Modal>

      {/* 单条转化设置弹窗 */}
      <Modal
        title={<Space><ThunderboltOutlined style={{ color: '#722ed1' }} />AI 转化功能用例为 UI 自动化脚本</Space>}
        open={convertModalVisible}
        onCancel={() => setConvertModalVisible(false)}
        onOk={handleConvertToUI}
        confirmLoading={converting}
        okText="开始转化"
        width={520}
      maskClosable={false}
      >
        {convertingCase && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>功能用例：</Text>
              <Tag color="blue">{convertingCase.name}</Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              探索将使用项目设置中配置的目标 URL 与账号密码，无需在此输入。
            </Text>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Switch checked={convertForceExplore} onChange={setConvertForceExplore} size="small" />
              <Text type="secondary" style={{ fontSize: 12 }}>
                强制重新探索（忽略缓存，用于版本迭代变更场景）
              </Text>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {/* 浏览器/视口跟随有头模式：无头时浏览器不可见，选择无意义置灰；关闭无头即可选 */}
              <Switch checked={convertHeadless} onChange={setConvertHeadless} size="small" />
              <Text type="secondary" style={{ fontSize: 12 }}>
                无头模式（后台运行浏览器，关闭可查看探索过程）
              </Text>
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <Text type="secondary">浏览器</Text>
                <Select value={convertBrowser} onChange={setConvertBrowser} style={{ width: '100%' }} disabled={convertHeadless}>
                  <Option value="chromium">Chromium</Option>
                  <Option value="firefox">Firefox</Option>
                  <Option value="webkit">WebKit</Option>
                </Select>
              </div>
              <div style={{ flex: 1 }}>
                <Text type="secondary">视口尺寸</Text>
                <Select value={convertViewport} onChange={setConvertViewport} style={{ width: '100%' }} disabled={convertHeadless}>
                  <Option value="1920x1080">桌面 1920×1080</Option>
                  <Option value="1366x768">桌面 1366×768</Option>
                  <Option value="768x1024">平板 768×1024</Option>
                  <Option value="375x667">手机 375×667</Option>
                </Select>
              </div>
            </div>
            <Alert
              type="info"
              showIcon
              message="AI 将读取功能测试步骤，结合知识图谱中的页面元素定位器，自动生成 Playwright Python 脚本。转化结果可在「功能用例AI转化为UI用例」菜单查看。"
              style={{ fontSize: 12 }}
            />
          </Space>
        )}
      </Modal>


      {/* 用例导入弹窗（功能用例页：直接导入已评审用例） */}
      <Modal title="导入已评审用例" open={showImp} onCancel={()=>{setShowImp(false);setImpFile(null);}}
        onOk={async () => {
          if (!impFile) return;
          const fd = new FormData(); fd.append('file', impFile);
          try {
            await axiosInstance.post('/test-cases/import', fd, {
              params: { version_id: selectedVersionId, project_id: selectedProjectId },
              headers: { 'Content-Type': 'multipart/form-data' },
            });
            message.success('已导入'); setShowImp(false); setImpFile(null); fetchTestCases();
          } catch (e: any) { message.error(e.response?.data?.detail || '导入失败'); }
        }} width={500} destroyOnClose>
        <Alert type="info" showIcon style={{marginBottom:12}} message="直接导入已评审通过的功能用例，不走AI生成。支持 .csv / .xlsx 格式。表头列名支持中英文。" />
        <Dragger beforeUpload={file => { setImpFile(file); return false; }} accept=".xlsx,.csv"
          maxCount={1} onRemove={() => setImpFile(null)}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p>上传用例文件(.xlsx/.csv)</p>
        </Dragger>
      </Modal>

      {/* ===== 探索统计弹窗已移除 ===== */}
      {/* 探索结果现在通过知识图谱可视化页面查看: /knowledge-graph/:graphId */}
    </Layout>
  );
};

export default FunctionalTestPage;