import React, { useState, useEffect } from 'react';
import {
  Card, Typography, Button, Table, Space, Tag, Select, Input, Modal,
  message, Empty, Descriptions, Tree, Layout, Spin, Progress,
  Form, Switch, Slider, Divider, Alert, Tooltip, Popconfirm, Checkbox, Dropdown
} from 'antd';
import type { MenuProps } from 'antd';
import {
  PlayCircleOutlined, PlusOutlined, EyeOutlined,
  DeleteOutlined, LeftOutlined, RightOutlined, FolderOutlined,
  FileTextOutlined, ApiOutlined, SyncOutlined, CheckCircleOutlined,
  CloseCircleOutlined, LoadingOutlined, PlusCircleOutlined,
  StopOutlined, MinusCircleOutlined, SendOutlined, DownloadOutlined,
  FileExcelOutlined, FileTextOutlined as FileCsvOutlined,
  BarChartOutlined, SettingOutlined, EditOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { projectApi } from '../../api/projectApi';
import { apiTestApi, ApiTestCase, SwaggerAutoGenerateRequest, ApiEnvironment, AuthConfig } from '../../api/apiTestApi';

const { Title, Text } = Typography;
const { Option } = Select;
const { Sider, Content } = Layout;
const { Search } = Input;

interface ProjectInfo {
  id: number;
  name: string;
  code: string;
}

interface VersionInfo {
  id: number;
  version_number: string;
  version_name?: string;
  status: string;
  test_cases_count: number;
  is_api_test_only?: boolean;
  query_version_id: number;
}

const APITestPage: React.FC = () => {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [treeData, setTreeData] = useState<any[]>([]);
  const [loadingTree, setLoadingTree] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);

  const [testCases, setTestCases] = useState<ApiTestCase[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [selectedTests, setSelectedTests] = useState<number[]>([]);
  const [searchText, setSearchText] = useState('');
  const [filterCaseType, setFilterCaseType] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20, total: 0 });

  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedTestCase, setSelectedTestCase] = useState<ApiTestCase | null>(null);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);

  const [swaggerModalVisible, setSwaggerModalVisible] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationLogs, setGenerationLogs] = useState<string[]>([]);
  const [swaggerForm] = Form.useForm();

  const [executingIds, setExecutingIds] = useState<Set<number>>(new Set());
  const [batchExecuting, setBatchExecuting] = useState(false);

  const [executeDetailModalVisible, setExecuteDetailModalVisible] = useState(false);
  const [executeDetail, setExecuteDetail] = useState<any>(null);
  const [executeType, setExecuteType] = useState<'single' | 'batch' | 'detail'>('single');
  const [executeProgress, setExecuteProgress] = useState(0);
  const [executeLogs, setExecuteLogs] = useState<Array<{text: string; status: 'running' | 'success' | 'error' | 'warning'}>>([]);
  const [batchResults, setBatchResults] = useState<any[]>([]);
  
  const [failedDetailModalVisible, setFailedDetailModalVisible] = useState(false);
  const [failedDetail, setFailedDetail] = useState<any>(null);

  const [addVersionModalVisible, setAddVersionModalVisible] = useState(false);
  const [addVersionForm] = Form.useForm();
  
  const [selectAllMode, setSelectAllMode] = useState(false);

  // 审批相关状态
  const [reviewModalVisible, setReviewModalVisible] = useState(false);
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject'>('approve');
  const [reviewComment, setReviewComment] = useState('');
  const [reviewingCaseId, setReviewingCaseId] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);

  // 报告相关状态
  const [reportModalVisible, setReportModalVisible] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [reportLoading, setReportLoading] = useState(false);

  // 环境与鉴权相关状态
  const [environments, setEnvironments] = useState<ApiEnvironment[]>([]);
  const [selectedEnvId, setSelectedEnvId] = useState<number | null>(null);
  const [envConfigModalVisible, setEnvConfigModalVisible] = useState(false);
  const [, setEditingEnv] = useState<ApiEnvironment | null>(null);
  const [envForm] = Form.useForm();
  const [authTesting, setAuthTesting] = useState(false);
  const [authTestResult, setAuthTestResult] = useState<{success: boolean; message: string} | null>(null);

  // 请求体编辑状态
  const [bodyEditorVisible, setBodyEditorVisible] = useState(false);
  const [editingBodyTestCase, setEditingBodyTestCase] = useState<ApiTestCase | null>(null);
  const [bodyType, setBodyType] = useState<string>('json');
  const [bodyFields, setBodyFields] = useState<Array<{name: string; type: 'text' | 'file'; value: string; filePath?: string; fileName?: string}>>([]);
  const [bodyJsonText, setBodyJsonText] = useState('');

  useEffect(() => {
    loadProjects();
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadVersions(selectedProjectId);
      loadEnvironments(selectedProjectId);
    } else {
      setVersions([]);
      setSelectedVersionId(null);
      setTestCases([]);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    buildTree();
  }, [projects, versions, selectedProjectId, selectedVersionId, expandedKeys]);

  useEffect(() => {
    if (selectedVersionId) {
      fetchTestCases(1);
      setPagination(prev => ({ ...prev, page: 1 }));
    } else {
      setTestCases([]);
      setPagination({ page: 1, pageSize: 20, total: 0 });
    }
  }, [selectedVersionId, searchText, filterCaseType, filterPriority, pagination.pageSize]);

  useEffect(() => {
    if (selectedVersionId && pagination.page > 1) {
      fetchTestCases(pagination.page);
    }
  }, [pagination.page]);

  const loadProjects = async () => {
    setLoadingTree(true);
    try {
      const response = await projectApi.list({ page_size: 100 });
      setProjects(response.items || []);
      if (response.items?.length > 0) {
        setSelectedProjectId(response.items[0].id);
        setExpandedKeys([`project-${response.items[0].id}`]);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载项目列表失败');
    } finally {
      setLoadingTree(false);
    }
  };

  const loadVersions = async (projectId: number) => {
    try {
      const response = await apiTestApi.listApiTestVersions(projectId);
      const versionList = response.items.map(v => ({
        id: v.id,
        version_number: v.version_number || v.name,
        version_name: v.name,
        status: 'active',
        test_cases_count: v.test_cases_count,
        is_api_test_only: v.is_api_test_only,
        query_version_id: v.query_version_id
      }));
      setVersions(versionList);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载版本列表失败');
    }
  };

  const handleDeleteVersion = async (versionId: number) => {
    try {
      await apiTestApi.deleteApiTestVersion(versionId);
      message.success('版本删除成功');
      if (selectedProjectId) {
        loadVersions(selectedProjectId);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除版本失败');
    }
  };

  const handleAddVersion = async () => {
    try {
      const values = await addVersionForm.validateFields();
      if (!selectedProjectId) {
        message.error('请先选择项目');
        return;
      }
      
      await apiTestApi.createApiTestVersion({
        project_id: selectedProjectId,
        name: values.name,
        version_number: values.version_number,
        description: values.description,
        is_api_test_only: true
      });
      
      message.success('版本添加成功');
      setAddVersionModalVisible(false);
      addVersionForm.resetFields();
      loadVersions(selectedProjectId);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '添加版本失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedTests.length === 0 && !selectAllMode) {
      message.warning('请选择要删除的用例');
      return;
    }
    
    try {
      let caseIdsToDelete: number[] = [];
      
      if (selectAllMode) {
        // 全选模式：分批获取所有用例ID
        const pageSize = 100;
        const totalPages = Math.ceil(pagination.total / pageSize);
        
        for (let page = 1; page <= totalPages; page++) {
          const response = await apiTestApi.listTestCasesByVersion(
            Number(selectedVersionId?.replace('version-', '') || 0),
            { page: page, page_size: pageSize }
          );
          caseIdsToDelete = caseIdsToDelete.concat(response.items.map((c: any) => c.id));
        }
        
        caseIdsToDelete = caseIdsToDelete.slice(0, pagination.total);
      } else {
        caseIdsToDelete = selectedTests;
      }
      
      if (caseIdsToDelete.length === 0) {
        message.warning('没有可删除的用例');
        return;
      }
      
      const result = await apiTestApi.batchDelete({ case_ids: caseIdsToDelete });
      message.success(result.message);
      setSelectedTests([]);
      setSelectAllMode(false);
      fetchTestCases();
      if (selectedProjectId) {
        loadVersions(selectedProjectId);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '批量删除失败');
    }
  };

  const handleBatchExecute = async (baseUrl?: string) => {
    if (selectedTests.length === 0 && !selectAllMode) {
      message.warning('请选择要执行的用例');
      return;
    }
    
    const defaultBaseUrl = testCases[0]?.base_url || 'http://localhost:8000';
    const normalizedBaseUrl = baseUrl || defaultBaseUrl;
    
    setExecuteType('batch');
    setExecuteProgress(0);
    setExecuteLogs([{ text: '开始批量执行测试用例...', status: 'running' }]);
    setBatchResults([]);
    setExecuteDetail({
      status: 'running',
      total: 0,
      passed: 0,
      failed: 0,
      error: 0
    });
    setExecuteDetailModalVisible(true);
    setBatchExecuting(true);
    
    try {
      let caseIdsToExecute: number[] = [];
      
      setExecuteProgress(10);
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'success' : l.status })),
        { text: '正在收集测试用例ID...', status: 'running' }]);
      
      if (selectAllMode) {
        const pageSize = 100;
        const totalPages = Math.ceil(pagination.total / pageSize);
        
        for (let page = 1; page <= totalPages; page++) {
          const response = await apiTestApi.listTestCasesByVersion(
            Number(selectedVersionId?.replace('version-', '') || 0),
            { page: page, page_size: pageSize }
          );
          caseIdsToExecute = caseIdsToExecute.concat(response.items.map((c: any) => c.id));
        }
        
        caseIdsToExecute = caseIdsToExecute.slice(0, pagination.total);
      } else {
        caseIdsToExecute = selectedTests;
      }
      
      if (caseIdsToExecute.length === 0) {
        setExecuteProgress(100);
        setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'error' : l.status })),
          { text: '没有可执行的用例', status: 'error' }]);
        setExecuteDetail({ status: 'error', error: '没有可执行的用例' });
        setBatchExecuting(false);
        return;
      }
      
      setExecuteProgress(20);
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'success' : l.status })),
        { text: `共 ${caseIdsToExecute.length} 个测试用例，开始执行...`, status: 'running' }]);
      
      const result = await apiTestApi.batchExecute({
        case_ids: caseIdsToExecute,
        base_url: normalizedBaseUrl
      });
      
      setExecuteProgress(60);
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'success' : l.status })),
        { text: '执行完成，汇总结果...', status: 'running' }]);
      
      setBatchResults(result.results || []);
      setExecuteDetail({
        status: 'completed',
        total: result.total,
        passed: result.passed,
        failed: result.failed,
        error: result.error,
        summary: `${result.passed}/${result.total} 通过`
      });
      
      setExecuteProgress(100);
      const finalStatus = result.passed === result.total ? 'success' : 'warning';
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? finalStatus : l.status })),
        { text: result.passed === result.total 
          ? `✅ 执行完成: 全部通过 (${result.passed}/${result.total})`
          : `⚠️ 执行完成: ${result.passed}通过, ${result.failed}失败, ${result.error}错误`, 
          status: finalStatus }]);
      
      setSelectedTests([]);
      setSelectAllMode(false);
      fetchTestCases();
    } catch (error: any) {
      setExecuteProgress(100);
      setExecuteDetail({
        status: 'error',
        error: error.response?.data?.detail || '批量执行失败'
      });
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'error' : l.status })),
        { text: `❌ 执行失败: ${error.response?.data?.detail || error.message}`, status: 'error' }]);
    } finally {
      setBatchExecuting(false);
    }
  };

  const buildTree = () => {
    const truncateName = (name: string, maxLen: number = 10) => {
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
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between', 
              width: '100%', 
              minHeight: 32, 
              cursor: 'pointer',
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
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <FolderOutlined style={{ fontSize: 16 }} />
<Tooltip title={project.name}>
                <span style={{ 
                  marginLeft: 4,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  display: 'inline-block',
                  maxWidth: '100px',
                  lineHeight: '16px'
                }}>
                  {truncateName(project.name)}
                </span>
              </Tooltip>
              {project.id === selectedProjectId && <Tag color="blue" style={{ marginLeft: 24, fontSize: 12 }}>当前</Tag>}
            </div>
            {project.id === selectedProjectId && (
              <Tooltip title="添加API测试专用版本">
                <Button
                  type="text"
                  size="small"
                  icon={<PlusCircleOutlined style={{ fontSize: 16 }} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    setAddVersionModalVisible(true);
                    addVersionForm.resetFields();
                  }}
                  style={{ marginRight: 4 }}
                />
              </Tooltip>
            )}
          </div>
        ),
        children: versions
          .filter(() => projects.find(p => p.id === selectedProjectId)?.id === project.id || project.id === selectedProjectId)
          .map(version => ({
            key: `version-${version.query_version_id}`,
title: (
               <div style={{ 
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
                 ...(`version-${version.query_version_id}` === selectedVersionId ? { background: 'rgba(82, 196, 26, 0.15)' } : {})
               }}>
                 <div style={{ display: 'flex', alignItems: 'center' }}>
                   <FileTextOutlined style={{ fontSize: 16 }} />
                   <span style={{ marginLeft: 4 }}>{version.version_number || version.version_name}</span>
                   <Tag color="green" style={{ marginLeft: 8 }}>{version.test_cases_count || 0}用例</Tag>
                 </div>
                 {version.is_api_test_only && (
                   <Tooltip title="删除此版本">
                     <Popconfirm
                       title="确定删除此版本？"
                       description="删除后该版本下的测试用例将变为未分类"
                       onConfirm={(e) => {
                         e?.stopPropagation();
                         handleDeleteVersion(version.id);
                       }}
                       onCancel={(e) => e?.stopPropagation()}
                     >
                       <Button
                         type="text"
                         size="small"
                         danger
                         icon={<MinusCircleOutlined style={{ fontSize: 14 }} />}
                         onClick={(e) => e.stopPropagation()}
                         style={{ marginRight: 4 }}
                       />
                     </Popconfirm>
                   </Tooltip>
                 )}
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
      setSelectedVersionId(key);
      setSelectedTests([]);
      setSelectAllMode(false);
    }
  };

  const fetchTestCases = async (targetPage?: number) => {
    if (!selectedVersionId) return;

    const pageToFetch = targetPage ?? pagination.page;
    setLoadingCases(true);
    try {
      const versionId = Number(selectedVersionId.toString().replace('version-', ''));
      const response = await apiTestApi.listTestCasesByVersion(versionId, {
        page: pageToFetch,
        page_size: pagination.pageSize,
        case_type: filterCaseType !== 'all' ? filterCaseType : undefined,
        priority: filterPriority !== 'all' ? filterPriority : undefined,
        search: searchText || undefined,
      });
      
      // 如果当前页没有数据但total>0，说明删除后需要跳到上一页
      if (response.items?.length === 0 && response.total > 0 && pageToFetch > 1) {
        // 重新获取第一页
        const firstPageResponse = await apiTestApi.listTestCasesByVersion(versionId, {
          page: 1,
          page_size: pagination.pageSize,
          case_type: filterCaseType !== 'all' ? filterCaseType : undefined,
          priority: filterPriority !== 'all' ? filterPriority : undefined,
          search: searchText || undefined,
        });
        setPagination(prev => ({ ...prev, total: firstPageResponse.total, page: 1 }));
        setTestCases(firstPageResponse.items || []);
      } else {
        setPagination(prev => ({ ...prev, total: response.total, page: pageToFetch }));
        setTestCases(response.items || []);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载测试用例失败');
    } finally {
      setLoadingCases(false);
    }
  };

  const handleDeleteCase = async (caseId: number) => {
    try {
      await apiTestApi.deleteTestCase(caseId);
      message.success('删除成功');
      setSelectedTests(prev => prev.filter(testId => testId !== caseId));
      fetchTestCases();
      if (selectedProjectId) {
        loadVersions(selectedProjectId);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败');
    }
  };

  // ===== 审批处理函数 =====

  const handleSubmitReview = async (caseId: number) => {
    try {
      await apiTestApi.submitForReview(caseId);
      message.success('已提交审批');
      fetchTestCases();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '提交审批失败');
    }
  };

  const handleOpenReviewModal = (caseId: number, action: 'approve' | 'reject') => {
    setReviewingCaseId(caseId);
    setReviewAction(action);
    setReviewComment('');
    setReviewModalVisible(true);
  };

  const handleConfirmReview = async () => {
    if (!reviewingCaseId) return;
    setReviewing(true);
    try {
      await apiTestApi.reviewCase(reviewingCaseId, reviewAction, reviewComment || undefined);
      message.success(reviewAction === 'approve' ? '审批通过' : '已驳回');
      setReviewModalVisible(false);
      fetchTestCases();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '审批操作失败');
    } finally {
      setReviewing(false);
    }
  };

  // ===== 导出处理函数 =====

  const handleExport = async (format: 'csv' | 'xlsx') => {
    try {
      const versionIdStr = selectedVersionId?.replace('version-', '');
      const versionIdNum = versionIdStr ? Number(versionIdStr) : undefined;

      const blob = await apiTestApi.exportCases({
        project_id: selectedProjectId || undefined,
        version_id: versionIdNum,
        case_type: filterCaseType !== 'all' ? filterCaseType : undefined,
        priority: filterPriority !== 'all' ? filterPriority : undefined,
        search: searchText || undefined,
        format,
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const ext = format === 'csv' ? 'csv' : 'xlsx';
      a.download = `API测试用例_${timestamp}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      message.success(`成功导出 ${ext.toUpperCase()} 文件`);
    } catch (error: any) {
      message.error('导出失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const exportMenuItems: MenuProps['items'] = [
    { key: 'csv', icon: <FileCsvOutlined />, label: 'CSV 格式 (.csv)' },
    { key: 'xlsx', icon: <FileExcelOutlined />, label: 'Excel 格式 (.xlsx)' },
  ];

  const handleExportMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleExport(key as 'csv' | 'xlsx');
  };

  // ===== 报告处理函数 =====

  const handleViewReport = async (executionIds?: number[]) => {
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }
    setReportLoading(true);
    setReportModalVisible(true);
    try {
      const versionIdStr = selectedVersionId?.replace('version-', '');
      const data = await apiTestApi.generateReport({
        project_id: selectedProjectId,
        version_id: versionIdStr ? Number(versionIdStr) : undefined,
        execution_ids: executionIds,
      });
      setReportData(data);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '生成报告失败');
      setReportModalVisible(false);
    } finally {
      setReportLoading(false);
    }
  };

  const handleExportReport = async (format: 'html' | 'pdf') => {
    if (!selectedProjectId) return;
    try {
      const blob = await apiTestApi.exportReport({
        project_id: selectedProjectId,
        format,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      a.download = `API测试报告_${timestamp}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      message.success(`报告已导出为 ${format.toUpperCase()}`);
    } catch (error: any) {
      message.error('导出报告失败');
    }
  };

  const validateUrl = (url: string): { valid: boolean; error?: string; corrected?: string; normalized?: string } => {
    if (!url) {
      return { valid: false, error: 'URL不能为空' };
    }

    const normalized = url.replace(/：/g, ':');

    try {
      new URL(normalized);
      return { valid: true, normalized };
    } catch (e) {
      return { valid: false, error: 'URL格式无效，请检查', normalized };
    }
  };

  const handleExecuteTest = async (caseId: number, baseUrl?: string, fromDetail?: boolean) => {
    const testCase = testCases.find(t => t.id === caseId);
    const actualBaseUrl = baseUrl || testCase?.base_url || '';
    
    const urlValidation = validateUrl(actualBaseUrl);
    const normalizedBaseUrl = urlValidation.normalized || actualBaseUrl;
    
    setExecutingIds(prev => new Set(prev).add(caseId));
    setExecuteType(fromDetail ? 'detail' : 'single');
    setExecuteDetail(null);
    setExecuteProgress(0);
    setExecuteLogs([{ text: '开始执行测试用例...', status: 'running' }]);
    setExecuteDetailModalVisible(true);
    
    if (fromDetail) {
      setExecuteDetail({
        testCase: testCase,
        status: 'running',
        request: {
          method: testCase?.method,
          url: `${normalizedBaseUrl}${testCase?.path}`,
          headers: testCase?.headers,
          query_params: testCase?.query_params,
          request_body: testCase?.request_body
        }
      });
    }
    
    setExecuteProgress(10);
    setExecuteLogs(prev => [...prev, { text: `请求: ${testCase?.method} ${testCase?.path}`, status: 'running' }]);
    
    try {
      const result = await apiTestApi.executeTest({ 
        case_id: caseId,
        base_url: normalizedBaseUrl
      });
      
      setExecuteProgress(50);
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'success' : l.status })), 
        { text: `收到响应: 状态码 ${result.actual_status}`, status: 'running' }]);
      
      setExecuteDetail({
        testCase: testCase,
        result: result,
        status: result.status,
        request: {
          method: testCase?.method,
          url: `${normalizedBaseUrl}${testCase?.path}`,
          headers: testCase?.headers,
          query_params: testCase?.query_params,
          request_body: testCase?.request_body
        },
        response: {
          status: result.actual_status,
          headers: result.actual_headers,
          body: result.actual_body,
          duration: result.duration,
          error: result.error_message
        }
      });
      
      setExecuteProgress(80);
      if (result.assert_results && result.assert_results.length > 0) {
        const passedCount = result.assert_results.filter(a => a.passed).length;
        const assertTotal = result.assert_results.length;
        setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'success' : l.status })),
          { text: `断言检查: ${passedCount}/${assertTotal} 通过`, status: 'running' }]);
      }
      
      setExecuteProgress(100);
      const finalStatus = result.status === 'passed' ? 'success' : result.status === 'failed' ? 'warning' : 'error';
      const finalIcon = result.status === 'passed' ? '✅' : result.status === 'failed' ? '⚠️' : '❌';
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? finalStatus : l.status })),
        { text: `执行完成: ${finalIcon} ${result.status === 'passed' ? '通过' : result.status === 'failed' ? '失败' : '错误'}`, status: finalStatus }]);
      
      fetchTestCases();
    } catch (error: any) {
      setExecuteProgress(100);
      setExecuteDetail({
        testCase: testCase,
        status: 'error',
        error: error.response?.data?.detail || error.message || '执行测试失败'
      });
      setExecuteLogs(prev => [...prev.map(l => ({ ...l, status: l.status === 'running' ? 'error' : l.status })),
        { text: `❌ 执行失败: ${error.response?.data?.detail || error.message}`, status: 'error' }]);
    } finally {
      setExecutingIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(caseId);
        return newSet;
      });
    }
  };

  const loadEnvironments = async (projectId: number) => {
    try {
      const envs = await apiTestApi.listEnvironments(projectId);
      setEnvironments(envs || []);
      const defaultEnv = (envs || []).find(e => e.is_default);
      setSelectedEnvId(defaultEnv?.id || null);
    } catch {
      // 环境列表加载失败不影响主流程
    }
  };

  const handleOpenEnvConfigModal = () => {
    const env = environments.find(e => e.id === selectedEnvId) || null;
    setEditingEnv(env);
    setAuthTestResult(null);
    const authConfig = env?.auth_config || { enabled: false, auth_type: 'bearer_token' };
    envForm.setFieldsValue({
      name: env?.name || '',
      base_url: env?.base_url || '',
      auth_type: (authConfig as any)?.auth_type || 'bearer_token',
      login_url: (authConfig as any)?.login_url || '',
      login_method: (authConfig as any)?.login_method || 'POST',
      json_path: (authConfig as any)?.token_extraction?.json_path || 'data.token',
      token: (authConfig as any)?.credentials?.token || '',
      username: (authConfig as any)?.credentials?.username || '',
      password: (authConfig as any)?.credentials?.password || '',
      api_key_name: (authConfig as any)?.token_injection?.header_name || 'X-API-Key',
      api_key_value: (authConfig as any)?.credentials?.api_key || '',
      cookie_name: (authConfig as any)?.credentials?.cookie_name || '',
      cookie_value: (authConfig as any)?.credentials?.cookie_value || '',
      auth_enabled: (authConfig as any)?.enabled || false,
    });
    setEnvConfigModalVisible(true);
  };

  const handleSaveEnvConfig = async () => {
    try {
      const values = envForm.getFieldsValue();
      if (!selectedEnvId || !selectedProjectId) return;

      const authConfig: AuthConfig = {
        enabled: values.auth_enabled,
        auth_type: values.auth_type,
        credentials: {},
        token_extraction: { source: 'body', json_path: values.json_path },
        token_injection: { location: 'header', header_name: 'Authorization', prefix: 'Bearer ' },
        token_cache_duration: 3600,
      };

      if (values.auth_type === 'bearer_token') {
        authConfig.login_url = values.login_url;
        authConfig.login_method = values.login_method;
        authConfig.credentials = { username: values.username, password: values.password };
      } else if (values.auth_type === 'basic_auth') {
        authConfig.credentials = { username: values.username, password: values.password };
      } else if (values.auth_type === 'api_key') {
        authConfig.token_injection = { location: 'header', header_name: values.api_key_name };
        authConfig.credentials = { api_key: values.api_key_value };
      } else if (values.auth_type === 'cookie') {
        authConfig.credentials = { cookie_name: values.cookie_name, cookie_value: values.cookie_value };
      }

      await apiTestApi.updateEnvironment(selectedEnvId, {
        name: values.name,
        base_url: values.base_url,
        auth_config: authConfig,
      });
      message.success('环境配置已保存');
      setEnvConfigModalVisible(false);
      loadEnvironments(selectedProjectId);
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存失败');
    }
  };

  const handleTestAuth = async () => {
    if (!selectedEnvId || !selectedProjectId) return;
    setAuthTesting(true);
    setAuthTestResult(null);
    try {
      const env = environments.find(e => e.id === selectedEnvId);
      const result = await apiTestApi.testEnvironmentAuth(
        selectedEnvId,
        selectedProjectId,
        env?.base_url
      );
      setAuthTestResult(result);
    } catch (error: any) {
      setAuthTestResult({ success: false, message: error.response?.data?.detail || '鉴权测试失败' });
    } finally {
      setAuthTesting(false);
    }
  };

  // 请求体编辑
  const handleOpenBodyEditor = (testCase: ApiTestCase) => {
    setEditingBodyTestCase(testCase);
    const body = testCase.request_body || {};
    const bt = (body as any)?._body_type || 'json';
    setBodyType(bt);

    if (bt === 'json' || !bt || bt === 'form') {
      setBodyJsonText(JSON.stringify(body, null, 2));
      setBodyFields([]);
    } else if (bt === 'multipart') {
      const fields = (body as any)?.fields || [];
      setBodyFields(fields);
      setBodyJsonText('');
    }
    setBodyEditorVisible(true);
  };

  const handleSaveBody = async () => {
    if (!editingBodyTestCase) return;
    try {
      let requestBody: any;
      if (bodyType === 'multipart') {
        requestBody = { _body_type: 'multipart', fields: bodyFields };
      } else if (bodyType === 'form') {
        try {
          requestBody = JSON.parse(bodyJsonText);
          requestBody._body_type = 'form';
        } catch {
          message.error('JSON格式无效');
          return;
        }
      } else {
        try {
          requestBody = JSON.parse(bodyJsonText);
        } catch {
          requestBody = {};
        }
      }
      await apiTestApi.updateTestCase(editingBodyTestCase.id, { request_body: requestBody });
      message.success('请求体已更新');
      setBodyEditorVisible(false);
      fetchTestCases();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '保存失败');
    }
  };

  const handleAddBodyField = () => {
    setBodyFields([...bodyFields, { name: '', type: 'text', value: '' }]);
  };

  const handleRemoveBodyField = (index: number) => {
    setBodyFields(bodyFields.filter((_, i) => i !== index));
  };

  const handleUpdateBodyField = (index: number, field: Partial<typeof bodyFields[0]>) => {
    const updated = [...bodyFields];
    updated[index] = { ...updated[index], ...field };
    setBodyFields(updated);
  };

  const handleFileSelectAndHash = async (index: number, file: File) => {
    try {
      const hashResult = await apiTestApi.getFileHash(file);
      const updated = [...bodyFields];
      updated[index] = {
        ...updated[index],
        type: 'file',
        fileName: file.name,
        value: `MD5: ${hashResult.md5} | SHA256: ${hashResult.sha256}`,
        filePath: file.name,
      };
      setBodyFields(updated);
      message.success(`文件Hash已计算: MD5=${hashResult.md5?.substring(0, 8)}...`);
    } catch (error: any) {
      message.error('文件Hash计算失败');
    }
  };

  const handleOpenExecuteModal = (caseId: number) => {
    const testCase = testCases.find(t => t.id === caseId);
    if (!testCase) return;
    
    const baseUrl = testCase.base_url || 'http://localhost:8000';
    const fromDetail = detailVisible;
    
    handleExecuteTest(caseId, baseUrl, fromDetail);
  };

  const handlePrevTestCase = () => {
    if (currentIndex > 0) {
      const newIndex = currentIndex - 1;
      setCurrentIndex(newIndex);
      setSelectedTestCase(testCases[newIndex]);
    }
  };

  const handleNextTestCase = () => {
    if (currentIndex < testCases.length - 1) {
      const newIndex = currentIndex + 1;
      setCurrentIndex(newIndex);
      setSelectedTestCase(testCases[newIndex]);
    }
  };

  const handleOpenSwaggerModal = () => {
    swaggerForm.resetFields();
    swaggerForm.setFieldsValue({
      include_normal: true,
      include_error: true,
      include_boundary: true,
      include_auth: true,
      max_cases_per_endpoint: 5,
    });
    setGenerationProgress(0);
    setGenerationLogs([]);
    setSwaggerModalVisible(true);
  };

  const handleSwaggerGenerate = async () => {
    try {
      const values = await swaggerForm.validateFields();
      if (!values.swagger_url) {
        message.error('请输入Swagger URL');
        return;
      }

      if (!selectedProjectId) {
        message.error('请先选择项目');
        return;
      }

      if (!selectedVersionId) {
        message.error('请先选择版本');
        return;
      }

      setGenerating(true);
      setGenerationProgress(10);
      setGenerationLogs(['开始导入Swagger文档...']);

      // 从 selectedVersionId 中提取数字ID
      let versionIdNum: number | undefined = undefined;
      if (selectedVersionId && selectedVersionId.startsWith('version-')) {
        versionIdNum = Number(selectedVersionId.replace('version-', ''));
      }

      const request: SwaggerAutoGenerateRequest = {
        project_id: selectedProjectId,
        version_id: versionIdNum,
        swagger_url: values.swagger_url,
        base_url: values.base_url,
        include_normal: values.include_normal,
        include_error: values.include_error,
        include_boundary: values.include_boundary,
        include_auth: values.include_auth,
        max_cases_per_endpoint: values.max_cases_per_endpoint,
      };

      setGenerationProgress(30);
      setGenerationLogs(prev => [...prev, '正在解析Swagger文档...']);

      setTimeout(() => {
        setGenerationProgress(50);
        setGenerationLogs(prev => [...prev, '提取接口信息...']);
      }, 1000);

      const result = await apiTestApi.autoGenerateFromSwagger(request);

      setGenerationProgress(90);
      setGenerationLogs(prev => [
        ...prev,
        `发现 ${result.endpoints_count} 个接口`,
        `正在生成测试用例...`,
      ]);

      setTimeout(() => {
        setGenerationProgress(100);
        setGenerationLogs(prev => [
          ...prev,
          `生成完成！共 ${result.generated_count} 个测试用例`,
          ...Object.entries(result.generation_summary?.case_type_distribution || {})
            .map(([type, count]) => `${type}场景: ${count}个`)
        ]);
      }, 500);

      setTimeout(() => {
        setGenerating(false);
        setSwaggerModalVisible(false);
        message.success(result.message);
        if (selectedVersionId) {
          fetchTestCases();
        }
        if (selectedProjectId) {
          loadVersions(selectedProjectId);
        }
      }, 1500);

    } catch (error: any) {
      setGenerating(false);
      setGenerationLogs(prev => [...prev, `错误: ${error.response?.data?.detail || error.message}`]);
      message.error(error.response?.data?.detail || '生成测试用例失败');
    }
  };

  const filteredCases = testCases.filter(caseItem => {
    const matchesSearch = searchText === '' ||
      caseItem.name.toLowerCase().includes(searchText.toLowerCase()) ||
      (caseItem.description?.toLowerCase() || '').includes(searchText.toLowerCase());
    const matchesType = filterCaseType === 'all' || caseItem.case_type === filterCaseType;
    const matchesPriority = filterPriority === 'all' || caseItem.priority === filterPriority;
    return matchesSearch && matchesType && matchesPriority;
  });

  const methodColors: Record<string, string> = {
    GET: 'green',
    POST: 'blue',
    PUT: 'orange',
    DELETE: 'red',
    PATCH: 'cyan',
  };

  const caseTypeColors: Record<string, string> = {
    normal: 'green',
    error: 'red',
    boundary: 'orange',
    auth: 'purple',
  };

  const priorityColors: Record<string, string> = {
    P0: 'red',
    P1: 'orange',
    P2: 'green',
    P3: 'gray',
  };

  const columns: ColumnsType<ApiTestCase> = [
    {
      title: '用例名称',
      dataIndex: 'name',
      key: 'name',
      width: 250,
      ellipsis: {
        showTitle: false,
      },
      render: (text, record) => (
        <Tooltip placement="topLeft" title={text}>
          <Space>
            <Tag color={methodColors[record.method || 'GET']}>{record.method}</Tag>
            <Text>{text}</Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: '接口路径',
      dataIndex: 'path',
      key: 'path',
      width: 150,
      ellipsis: {
        showTitle: false,
      },
      render: (path) => (
        <Tooltip placement="topLeft" title={path}>
          <Text code>{path}</Text>
        </Tooltip>
      ),
    },
{
      title: '类型',
      dataIndex: 'case_type',
      key: 'case_type',
      width: 100,
      ellipsis: { showTitle: false },
      render: (caseType) => (
        <Tag color={caseTypeColors[caseType] || 'default'}>
          {caseType === 'normal' ? '正常' :
           caseType === 'error' ? '异常' :
           caseType === 'boundary' ? '边界' :
           caseType === 'auth' ? '权限' : caseType}
        </Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      ellipsis: { showTitle: false },
      render: (priority) => (
        <Tag color={priorityColors[priority] || 'default'}>{priority}</Tag>
      ),
    },
    {
      title: '生成方式',
      dataIndex: 'generated_by',
      key: 'generated_by',
      width: 100,
      ellipsis: { showTitle: false },
      render: (generatedBy) => (
        <Tag color={generatedBy === 'ai' ? 'purple' : 'blue'}>
          {generatedBy === 'ai' ? 'AI生成' : '手动创建'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      ellipsis: { showTitle: false },
      render: (status: string) => {
        const statusConfig: Record<string, { color: string; label: string }> = {
          draft: { color: 'default', label: '草稿' },
          pending_review: { color: 'processing', label: '待审批' },
          approved: { color: 'success', label: '已通过' },
          rejected: { color: 'error', label: '已驳回' },
        };
        const config = statusConfig[status] || { color: 'default', label: status };
        return <Tag color={config.color}>{config.label}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      ellipsis: true,
      render: (time) => {
        if (!time) return '-';
        const date = new Date(time);
        const formatted = date.toLocaleString('zh-CN');
        return (
          <Tooltip placement="topLeft" title={formatted}>
            <span>{formatted}</span>
          </Tooltip>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      fixed: 'right',
      ellipsis: { showTitle: false },
      render: (_, record) => (
        <Space size="small">
          {/* 执行按钮 - 已通过和草稿状态的用例可执行 */}
          {(record.status === 'approved' || record.status === 'draft') && (
            <Tooltip title="执行测试">
              <Button
                type="link"
                size="small"
                icon={<PlayCircleOutlined />}
                loading={executingIds.has(record.id)}
                onClick={() => handleOpenExecuteModal(record.id)}
              />
            </Tooltip>
          )}
          <Tooltip title="查看详情">
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
            />
          </Tooltip>
          {/* 审批按钮 */}
          {record.status === 'draft' && (
            <Tooltip title="提交审批">
              <Button
                type="link"
                size="small"
                icon={<SendOutlined />}
                onClick={() => handleSubmitReview(record.id)}
              />
            </Tooltip>
          )}
          {record.status === 'rejected' && (
            <Tooltip title="重新提交审批">
              <Button
                type="link"
                size="small"
                icon={<SendOutlined style={{ color: '#fa8c16' }} />}
                onClick={() => handleSubmitReview(record.id)}
              />
            </Tooltip>
          )}
          {record.status === 'pending_review' && (
            <>
              <Tooltip title="通过">
                <Button
                  type="link"
                  size="small"
                  icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                  onClick={() => handleOpenReviewModal(record.id, 'approve')}
                />
              </Tooltip>
              <Tooltip title="驳回">
                <Button
                  type="link"
                  size="small"
                  icon={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
                  onClick={() => handleOpenReviewModal(record.id, 'reject')}
                />
              </Tooltip>
            </>
          )}
          <Popconfirm
            title="确定删除此测试用例？"
            onConfirm={() => handleDeleteCase(record.id)}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const stats = {
    total: pagination.total,
    normal: testCases.filter(t => t.case_type === 'normal').length,
    error: testCases.filter(t => t.case_type === 'error').length,
    boundary: testCases.filter(t => t.case_type === 'boundary').length,
    auth: testCases.filter(t => t.case_type === 'auth').length,
    aiGenerated: testCases.filter(t => t.generated_by === 'ai').length,
  };

  return (
    <Layout style={{ minHeight: '100vh', background: '#f0f2f5' }}>
      <Sider width={280} style={{ background: '#fff', borderRight: '1px solid #e8e8e8' }}>
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
              className="api-test-tree"
              selectedKeys={[]}
            />
          )}
        </Card>
      </Sider>

      <Content style={{ padding: '6px' }}>
<Card>
           <Space direction="vertical" style={{ width: '100%' }} size="middle">
             <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
               <Space>
                 <Title level={4} style={{ margin: 0 }}>
                   {selectedVersionId ? (
                     <Space>
                       <ApiOutlined />
                       <Tag color="blue">{projects.find(p => p.id === selectedProjectId)?.name}</Tag>
                       <Tag color="green">{versions.find(v => `version-${v.query_version_id}` === selectedVersionId)?.version_number}</Tag>
                       API测试用例
                     </Space>
                   ) : '请先选择版本'}
                 </Title>
                 {selectedVersionId && (
                   <Text type="secondary">共 {pagination.total} 条用例</Text>
                 )}
               </Space>
{selectedVersionId && (
                  <Space>
                    <Dropdown menu={{ items: exportMenuItems, onClick: handleExportMenuClick }}>
                      <Button icon={<DownloadOutlined />}>
                        导出用例
                      </Button>
                    </Dropdown>
                    <Button
                      type="primary"
                      icon={<ApiOutlined />}
                      onClick={handleOpenSwaggerModal}
                    >
                      导入Swagger自动生成
                    </Button>
                  </Space>
                )}
             </div>

             {/* 环境选择器 + 鉴权配置 */}
             {selectedVersionId && (
               <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: -8 }}>
                 <Text type="secondary" style={{ fontSize: 12 }}>环境:</Text>
                 <Select
                   size="small"
                   style={{ width: 160 }}
                   placeholder="选择环境"
                   value={selectedEnvId}
                   onChange={setSelectedEnvId}
                   options={environments.map(e => ({
                     value: e.id,
                     label: <span>{e.name} {e.is_default ? <Tag color="blue" style={{ fontSize: 10 }}>默认</Tag> : null}</span>,
                   }))}
                 />
                 <Button size="small" icon={<SettingOutlined />} onClick={handleOpenEnvConfigModal}>
                   鉴权配置
                 </Button>
                 {selectedEnvId && environments.find(e => e.id === selectedEnvId)?.auth_config?.enabled && (
                   <Tag color="green" style={{ fontSize: 11 }}>🔐 已启用鉴权</Tag>
                 )}
               </div>
             )}

             {selectedVersionId && (
               <>
<div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginTop: -8 }}>
                    <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>总用例</Text>
                      <Title level={5} style={{ margin: 0 }}>{stats.total}</Title>
                    </Card>
                    <Tooltip title="当前页统计">
                      <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>正常场景</Text>
                        <Title level={5} style={{ margin: 0, color: '#52c41a' }}>{stats.normal}</Title>
                      </Card>
                    </Tooltip>
                    <Tooltip title="当前页统计">
                      <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>异常场景</Text>
                        <Title level={5} style={{ margin: 0, color: '#f5222d' }}>{stats.error}</Title>
                      </Card>
                    </Tooltip>
                    <Tooltip title="当前页统计">
                      <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>边界测试</Text>
                        <Title level={5} style={{ margin: 0, color: '#fa8c16' }}>{stats.boundary}</Title>
                      </Card>
                    </Tooltip>
                    <Tooltip title="当前页统计">
                      <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>权限测试</Text>
                        <Title level={5} style={{ margin: 0, color: '#722ed1' }}>{stats.auth}</Title>
                      </Card>
                    </Tooltip>
                    <Tooltip title="当前页统计">
                      <Card size="small" style={{ textAlign: 'center', padding: '4px 0' }} bodyStyle={{ padding: '4px 8px' }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>AI生成</Text>
                        <Title level={5} style={{ margin: 0, color: '#13c2c2' }}>{stats.aiGenerated}</Title>
                      </Card>
                    </Tooltip>
                  </div>

<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: -8 }}>
                   <Space>
                     <Search
                       placeholder="搜索用例名称"
                       allowClear
                       onSearch={setSearchText}
                       style={{ width: 200 }}
                     />
                     <Select
                       value={filterCaseType}
                       onChange={setFilterCaseType}
                       style={{ width: 120 }}
                     >
                       <Option value="all">全部类型</Option>
                       <Option value="normal">正常场景</Option>
                       <Option value="error">异常场景</Option>
                       <Option value="boundary">边界测试</Option>
                       <Option value="auth">权限测试</Option>
                     </Select>
                     <Select
                       value={filterPriority}
                       onChange={setFilterPriority}
                       style={{ width: 100 }}
                     >
                       <Option value="all">全部优先级</Option>
                       <Option value="P0">P0</Option>
<Option value="P1">P1</Option>
                        <Option value="P2">P2</Option>
                        <Option value="P3">P3</Option>
                      </Select>
                    </Space>
                  </div>
                  
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingLeft: 12, marginTop: -8 }}>
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
                    <Space>
                      {(selectedTests.length > 0 || selectAllMode) && (
                        <Text type="secondary">已选中 {selectAllMode ? pagination.total : selectedTests.length} 条</Text>
                      )}
                      <Popconfirm
                        title={`确定删除选中的 ${selectAllMode ? pagination.total : selectedTests.length} 条用例？`}
                        onConfirm={handleBatchDelete}
                        disabled={selectedTests.length === 0 && !selectAllMode}
                      >
                        <Button 
                          icon={<DeleteOutlined />}
                          disabled={selectedTests.length === 0 && !selectAllMode}
                          style={{ background: '#fff1f0', borderColor: '#ffa39e', color: '#cf1322' }}
                        >
                          批量删除
                        </Button>
                      </Popconfirm>
                      <Button
                        icon={<PlayCircleOutlined />}
                        disabled={selectedTests.length === 0 && !selectAllMode}
                        onClick={() => handleBatchExecute()}
                        style={{ background: '#d9f7be', borderColor: '#b7eb8f', color: '#389e0d' }}
                      >
                        批量执行
                      </Button>
                    </Space>
                  </div>

                 <Table
                    columns={columns}
                    dataSource={filteredCases}
                    rowKey="id"
                    loading={loadingCases}
                    style={{ marginTop: -8 }}
rowSelection={{
                      selectedRowKeys: selectAllMode ? filteredCases.map(c => c.id) : selectedTests,
                      onChange: (keys) => {
                        setSelectedTests(keys as number[]);
                        setSelectAllMode(false);
                      },
                      getCheckboxProps: () => ({
                        disabled: selectAllMode,
                      }),
                      columnWidth: 40,
                    }}
                  pagination={{
                    current: pagination.page,
                    pageSize: pagination.pageSize,
                    total: pagination.total,
                    showSizeChanger: true,
                    showTotal: (total) => `共 ${total} 条`,
                    onChange: (page, pageSize) => setPagination({ page, pageSize, total: pagination.total }),
                  }}
                  scroll={{ x: 1050 }}
                />
              </>
            )}

            {!selectedVersionId && (
              <Empty
                description="请在左侧选择项目下的版本查看API测试用例"
                style={{ padding: '60px 0' }}
              />
            )}
          </Space>
        </Card>
      </Content>

      <Modal
        title={
          <Space>
            <ApiOutlined />
            <span>导入Swagger自动生成测试用例</span>
          </Space>
        }
        open={swaggerModalVisible}
        onCancel={() => {
          if (!generating) setSwaggerModalVisible(false);
        }}
        footer={generating ? null : [
          <Button key="cancel" onClick={() => setSwaggerModalVisible(false)}>取消</Button>,
          <Button key="generate" type="primary" icon={<SyncOutlined />} onClick={handleSwaggerGenerate}>
            开始生成
          </Button>,
        ]}
        width={700}
        maskClosable={false}
      >
        {generating ? (
          <div style={{ padding: '24px' }}>
            <Progress percent={generationProgress} status="active" />
            <div style={{ marginTop: 16, maxHeight: 300, overflow: 'auto' }}>
              {generationLogs.map((log, index) => (
                <div key={index} style={{ marginBottom: 8 }}>
                  <Text>
                    {log.includes('完成') || log.includes('成功') ? (
                      <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    ) : log.includes('错误') ? (
                      <CloseCircleOutlined style={{ color: '#f5222d', marginRight: 8 }} />
                    ) : (
                      <LoadingOutlined style={{ marginRight: 8 }} />
                    )}
                    {log}
                  </Text>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <Form form={swaggerForm} layout="vertical">
            <Alert
              message="只需传入Swagger URL，系统将自动解析所有接口并生成可执行的测试用例"
              description="生成的测试用例包含完整的前置条件、测试步骤和断言规则，可直接运行执行"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            <Form.Item
              name="swagger_url"
              label="Swagger文档URL"
              rules={[{ required: true, message: '请输入Swagger文档URL' }]}
            >
              <Input placeholder="例如: https://petstore.swagger.io/v2/swagger.json" />
            </Form.Item>

            <Form.Item name="base_url" label="API基础URL（可选）">
              <Input placeholder="可覆盖Swagger文档中的base_url，例如: http://localhost:8080" />
            </Form.Item>

            <Divider>生成场景配置</Divider>

            <Space wrap>
              <Form.Item name="include_normal" label="正常场景" valuePropName="checked">
                <Switch defaultChecked />
              </Form.Item>
              <Form.Item name="include_error" label="异常场景" valuePropName="checked">
                <Switch defaultChecked />
              </Form.Item>
              <Form.Item name="include_boundary" label="边界测试" valuePropName="checked">
                <Switch defaultChecked />
              </Form.Item>
              <Form.Item name="include_auth" label="权限测试" valuePropName="checked">
                <Switch defaultChecked />
              </Form.Item>
            </Space>

            <Form.Item
              name="max_cases_per_endpoint"
              label="每个接口最多生成用例数"
              tooltip="控制生成的测试用例数量，避免过多"
            >
              <Slider min={1} max={10} defaultValue={5} marks={{ 1: '1', 5: '5', 10: '10' }} />
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        title={
          <Space>
            <ApiOutlined />
            <span>测试用例详情</span>
            {selectedTestCase && (
              <Space>
                <Tag color="blue">{projects.find(p => p.id === selectedProjectId)?.name}</Tag>
                <Tag color="green">{versions.find(v => `version-${v.query_version_id}` === selectedVersionId)?.version_number}</Tag>
              </Space>
            )}
          </Space>
        }
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="bodyedit" icon={<EditOutlined />} onClick={() => {
            if (selectedTestCase) handleOpenBodyEditor(selectedTestCase);
          }}>
            编辑请求体
          </Button>,
          <Button key="prev" icon={<LeftOutlined />} onClick={handlePrevTestCase} disabled={currentIndex <= 0}>
            上一个
          </Button>,
          <Button key="next" icon={<RightOutlined />} onClick={handleNextTestCase} disabled={currentIndex >= testCases.length - 1}>
            下一个
          </Button>,
          <Button key="execute" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleOpenExecuteModal(selectedTestCase?.id!)}>
            执行测试
          </Button>,
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {selectedTestCase && (
          <Descriptions bordered column={2} size="small" labelStyle={{ width: 100, padding: '8px 12px' }} contentStyle={{ padding: '8px 12px' }}>
            <Descriptions.Item label="用例名称" span={2}>{selectedTestCase.name}</Descriptions.Item>
            <Descriptions.Item label="基础URL">
              <Text code>{selectedTestCase.base_url}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="接口路径">
              <Text code>{selectedTestCase.path}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="请求方法">
              <Tag color={methodColors[selectedTestCase.method || 'GET']}>{selectedTestCase.method}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="用例类型">
              <Tag color={caseTypeColors[selectedTestCase.case_type] || 'default'}>
                {selectedTestCase.case_type === 'normal' ? '正常' :
                 selectedTestCase.case_type === 'error' ? '异常' :
                 selectedTestCase.case_type === 'boundary' ? '边界' :
                 selectedTestCase.case_type === 'auth' ? '权限' : selectedTestCase.case_type}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="优先级">
              <Tag color={priorityColors[selectedTestCase.priority] || 'default'}>{selectedTestCase.priority}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="描述">{selectedTestCase.description || '-'}</Descriptions.Item>
            <Descriptions.Item label="请求头" span={2}>
              {selectedTestCase.headers && Object.keys(selectedTestCase.headers).length > 0 ? (
                <>
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4 }}>
                    {JSON.stringify(selectedTestCase.headers, null, 2)}
                  </pre>
                  {selectedTestCase.headers['Authorization']?.includes('{{auth_token}}') && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginTop: 6 }}
                      message={<>请求头 <Text code>Authorization</Text> 为鉴权参数化占位符：执行时按项目 api_auth 配置自动调登录接口获取实时 Token 并替换，不落明文</>}
                    />
                  )}
                </>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="路径参数" span={2}>
              {selectedTestCase.path_params && Object.keys(selectedTestCase.path_params).length > 0 ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4 }}>
                  {JSON.stringify(selectedTestCase.path_params, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="查询参数" span={2}>
              {selectedTestCase.query_params && Object.keys(selectedTestCase.query_params).length > 0 ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4 }}>
                  {JSON.stringify(selectedTestCase.query_params, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="请求体" span={2}>
              {selectedTestCase.request_body && Object.keys(selectedTestCase.request_body).length > 0 ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4 }}>
                  {JSON.stringify(selectedTestCase.request_body, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="前置条件" span={2}>
              {selectedTestCase.preconditions || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="测试步骤" span={2}>
              {selectedTestCase.test_steps && selectedTestCase.test_steps.length > 0 ? (
                <div>
                  {selectedTestCase.test_steps.map((step, index) => (
                    <div key={index} style={{ marginBottom: 4, padding: 6, background: '#f5f5f5', borderRadius: 4 }}>
                      <Text strong>步骤{step.step || index + 1}:</Text>
                      <div><Text type="secondary">操作: </Text>{step.action}</div>
                      <div><Text type="secondary">预期: </Text>{step.expected}</div>
                    </div>
                  ))}
                </div>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="预期结果" span={2}>
              {selectedTestCase.expected_result || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="预期响应体" span={2}>
              {selectedTestCase.expected_body && Object.keys(selectedTestCase.expected_body).length > 0 ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4 }}>
                  {JSON.stringify(selectedTestCase.expected_body, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="断言规则" span={2}>
              {selectedTestCase.assert_rules && selectedTestCase.assert_rules.length > 0 ? (
                <div>
                  {selectedTestCase.assert_rules.map((rule, index) => (
                    <div key={index} style={{ marginBottom: 2 }}>
                      <Tag color="geekblue">{rule.type}</Tag>
                      {rule.field && <Text code>{rule.field}</Text>}
                      {rule.value !== undefined && <Text type="secondary"> = {JSON.stringify(rule.value)}</Text>}
                      <Text type="secondary" style={{ marginLeft: 8 }}>{rule.description || ''}</Text>
                    </div>
                  ))}
                </div>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间" span={2}>
              {selectedTestCase.created_at ? new Date(selectedTestCase.created_at).toLocaleString('zh-CN') : '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* 添加API测试专用版本弹窗 */}
      <Modal
        title="添加API测试专用版本"
        open={addVersionModalVisible}
        onCancel={() => setAddVersionModalVisible(false)}
        onOk={handleAddVersion}
        okText="添加"
        cancelText="取消"
        width={400}
      >
        <Alert
          message="此版本仅用于API测试，不会同步到项目管理模块"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form form={addVersionForm} layout="vertical">
          <Form.Item
            name="name"
            label="版本名称"
            rules={[{ required: true, message: '请输入版本名称' }]}
          >
            <Input placeholder="例如: v1.0.0-beta、历史版本测试" />
          </Form.Item>
          <Form.Item
            name="version_number"
            label="版本号"
          >
            <Input placeholder="例如: 1.0.0、v2.1" />
          </Form.Item>
          <Form.Item
            name="description"
            label="版本描述"
          >
            <Input.TextArea placeholder="描述此版本用途，例如：用于测试历史接口功能" rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          <Space>
            <PlayCircleOutlined />
            <span>执行详情</span>
            {executeDetail?.testCase && (
              <Tag color="blue">{executeDetail.testCase.name}</Tag>
            )}
            {executeType === 'batch' && executeDetail?.status === 'completed' && executeDetail?.total && (
              <Tag color="purple">批量执行 {executeDetail.total} 条</Tag>
            )}
          </Space>
        }
        open={executeDetailModalVisible}
        onCancel={() => {
          if (!batchExecuting && executeProgress === 100) {
            setExecuteDetailModalVisible(false);
          }
        }}
        footer={executeProgress === 100 ? (
          <Space>
            {executeType === 'batch' && executeDetail?.status === 'completed' && (
              <Button
                key="report"
                type="primary"
                icon={<BarChartOutlined />}
                onClick={() => handleViewReport()}
              >
                查看测试报告
              </Button>
            )}
            <Button key="close" onClick={() => setExecuteDetailModalVisible(false)}>
              关闭
            </Button>
          </Space>
        ) : null}
        width={900}
        maskClosable={false}
        closable={executeProgress === 100}
      >
        <div style={{ marginBottom: 16 }}>
          <Progress 
            percent={executeProgress} 
            status={executeProgress < 100 ? 'active' : executeDetail?.status === 'passed' ? 'success' : 'exception'}
          />
        </div>

        <div style={{ maxHeight: 150, overflow: 'auto', marginBottom: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
          {executeLogs.map((log, index) => (
            <div key={index} style={{ marginBottom: 4 }}>
              <Text style={{ fontSize: 12 }}>
                {log.status === 'success' ? (
                  <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                ) : log.status === 'error' ? (
                  <CloseCircleOutlined style={{ color: '#f5222d', marginRight: 8 }} />
                ) : log.status === 'warning' ? (
                  <StopOutlined style={{ color: '#fa8c16', marginRight: 8 }} />
                ) : (
                  <LoadingOutlined style={{ marginRight: 8 }} />
                )}
                {log.text}
              </Text>
            </div>
          ))}
        </div>

        {executeType === 'single' && executeDetail?.testCase && (
          <Card title="测试用例信息" size="small" style={{ marginBottom: 16 }}>
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="用例名称">{executeDetail.testCase.name}</Descriptions.Item>
              <Descriptions.Item label="请求方法">
                <Tag color={methodColors[executeDetail.testCase.method || 'GET']}>
                  {executeDetail.testCase.method}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="接口路径" span={2}>
                <Text code>{executeDetail.testCase.path}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {executeType !== 'batch' && executeDetail?.request && (
          <Card title="请求详情" size="small" style={{ marginBottom: 16 }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="请求URL">
                <Text code>{executeDetail.request.url}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="请求方法">
                <Tag color={methodColors[executeDetail.request.method || 'GET']}>
                  {executeDetail.request.method}
                </Tag>
              </Descriptions.Item>
              {executeDetail.request.headers && Object.keys(executeDetail.request.headers).length > 0 && (
                <Descriptions.Item label="请求头">
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {JSON.stringify(executeDetail.request.headers, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
              {executeDetail.request.query_params && Object.keys(executeDetail.request.query_params).length > 0 && (
                <Descriptions.Item label="查询参数">
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {JSON.stringify(executeDetail.request.query_params, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
              {executeDetail.request.request_body && Object.keys(executeDetail.request.request_body).length > 0 && (
                <Descriptions.Item label="请求体">
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {JSON.stringify(executeDetail.request.request_body, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        )}

        {executeType !== 'batch' && executeDetail?.response && (
          <Card title="响应详情" size="small" style={{ marginBottom: 16 }}>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="响应状态码">
                <Tag color={executeDetail.response.status >= 200 && executeDetail.response.status < 300 ? 'green' : 'red'}>
                  {executeDetail.response.status || '-'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="响应时间">
                <Text>{executeDetail.response.duration || '-'} ms</Text>
              </Descriptions.Item>
              {executeDetail.response.error && (
                <Descriptions.Item label="错误信息" span={2}>
                  <Text type="danger">{executeDetail.response.error}</Text>
                </Descriptions.Item>
              )}
              {executeDetail.response.headers && Object.keys(executeDetail.response.headers).length > 0 && (
                <Descriptions.Item label="响应头" span={2}>
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 150, overflow: 'auto' }}>
                    {JSON.stringify(executeDetail.response.headers, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
              {executeDetail.response.body && (
                <Descriptions.Item label="响应体" span={2}>
                  <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
                    {typeof executeDetail.response.body === 'string' 
                      ? executeDetail.response.body 
                      : JSON.stringify(executeDetail.response.body, null, 2)}
                  </pre>
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        )}

        {executeType !== 'batch' && executeDetail?.result?.assert_results && executeDetail.result.assert_results.length > 0 && (
          <Card title="断言结果" size="small" style={{ marginBottom: 16 }}>
            <div>
              {executeDetail.result.assert_results.map((assert: any, index: number) => (
                <div key={index} style={{ marginBottom: 8, padding: 8, background: assert.passed ? '#f6ffed' : '#fff2e8', borderRadius: 4 }}>
                  <Space>
                    {assert.passed ? (
                      <CheckCircleOutlined style={{ color: '#52c41a' }} />
                    ) : (
                      <CloseCircleOutlined style={{ color: '#f5222d' }} />
                    )}
                    <Text>{assert.rule || `断言${index + 1}`}</Text>
                    {!assert.passed && (
                      <Text type="danger"> - {assert.message}</Text>
                    )}
                  </Space>
                </div>
              ))}
            </div>
          </Card>
        )}

        {executeType === 'batch' && executeDetail?.status === 'completed' && (
          <>
            <Card title="执行汇总" size="small" style={{ marginBottom: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                <div style={{ textAlign: 'center', padding: 12, background: '#f0f2f5', borderRadius: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>总数</Text>
                  <Title level={4} style={{ margin: 0 }}>{executeDetail.total}</Title>
                </div>
                <div style={{ textAlign: 'center', padding: 12, background: '#f6ffed', borderRadius: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>通过</Text>
                  <Title level={4} style={{ margin: 0, color: '#52c41a' }}>{executeDetail.passed}</Title>
                </div>
                <div style={{ textAlign: 'center', padding: 12, background: '#fff2e8', borderRadius: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>失败</Text>
                  <Title level={4} style={{ margin: 0, color: '#fa8c16' }}>{executeDetail.failed}</Title>
                </div>
                <div style={{ textAlign: 'center', padding: 12, background: '#fff1f0', borderRadius: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>错误</Text>
                  <Title level={4} style={{ margin: 0, color: '#f5222d' }}>{executeDetail.error}</Title>
                </div>
              </div>
            </Card>

            {batchResults.length > 0 && (
              <Card title="执行明细" size="small">
                <Table
                  dataSource={batchResults}
                  rowKey="case_id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                  columns={[
                    {
                      title: '用例名称',
                      dataIndex: 'name',
                      key: 'name',
                      ellipsis: true,
                      render: (text: string) => <Text ellipsis>{text}</Text>
                    },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      key: 'status',
                      width: 100,
                      render: (status: string) => (
                        <Tag color={status === 'passed' ? 'green' : status === 'failed' ? 'orange' : 'red'}>
                          {status === 'passed' ? '通过' : status === 'failed' ? '失败' : '错误'}
                        </Tag>
                      )
                    },
                    {
                      title: '响应时间',
                      dataIndex: 'duration',
                      key: 'duration',
                      width: 100,
                      render: (duration: number) => duration ? `${duration}ms` : '-'
                    },
                    {
                      title: '状态码',
                      dataIndex: 'actual_status',
                      key: 'actual_status',
                      width: 80,
                      render: (status: number) => status ? (
                        <Tag color={status >= 200 && status < 300 ? 'green' : 'red'}>{status}</Tag>
                      ) : '-'
                    },
                    {
                      title: '说明',
                      dataIndex: 'message',
                      key: 'message',
                      ellipsis: true,
                      render: (text: string) => <Text type="secondary" ellipsis>{text}</Text>
                    },
                    {
                      title: '操作',
                      key: 'action',
                      width: 80,
                      render: (_, record) => (
                        record.status !== 'passed' ? (
                          <Button
                            type="link"
                            size="small"
                            icon={<EyeOutlined />}
                            onClick={() => {
                              setFailedDetail(record);
                              setFailedDetailModalVisible(true);
                            }}
                          >
                            详情
                          </Button>
                        ) : null
                      )
                    }
                  ]}
                />
              </Card>
            )}
          </>
        )}

        {executeDetail?.error && executeType !== 'batch' && (
          <Alert
            message="执行失败"
            description={executeDetail.error}
            type="error"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </Modal>
      
      {/* 失败详情弹窗 - 在执行详情弹窗之上 */}
      <Modal
        title={
          <Space>
            <CloseCircleOutlined style={{ color: '#f5222d' }} />
            <span>执行失败详情</span>
            {failedDetail && <Tag color="orange">{failedDetail.name}</Tag>}
          </Space>
        }
        open={failedDetailModalVisible}
        onCancel={() => setFailedDetailModalVisible(false)}
        footer={
          <Button key="close" onClick={() => setFailedDetailModalVisible(false)}>
            关闭
          </Button>
        }
        width={800}
        maskClosable={false}
        style={{ top: 20 }}
      >
        {failedDetail && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="用例名称" span={2}>{failedDetail.name}</Descriptions.Item>
            <Descriptions.Item label="执行状态">
              <Tag color={failedDetail.status === 'passed' ? 'green' : failedDetail.status === 'failed' ? 'orange' : 'red'}>
                {failedDetail.status === 'passed' ? '通过' : failedDetail.status === 'failed' ? '失败' : '错误'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="HTTP状态码">
              <Tag color={failedDetail.actual_status && failedDetail.actual_status >= 200 && failedDetail.actual_status < 300 ? 'green' : 'red'}>
                {failedDetail.actual_status && failedDetail.actual_status !== 0 ? failedDetail.actual_status : '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="响应时间">{failedDetail.duration ? `${failedDetail.duration}ms` : '-'}</Descriptions.Item>
            <Descriptions.Item label="失败原因" span={2}>
              <Text type="danger">{failedDetail.message || failedDetail.error_message || '未知错误'}</Text>
            </Descriptions.Item>
            
            <Descriptions.Item label="请求URL" span={2}>
              <Text code>{failedDetail.request_url || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="请求方法">
              <Tag color={methodColors[failedDetail.method || 'GET']}>{failedDetail.method || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="请求头">
              {failedDetail.request_headers ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4, maxHeight: 100, overflow: 'auto' }}>
                  {JSON.stringify(failedDetail.request_headers, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            
            <Descriptions.Item label="请求参数" span={2}>
              {failedDetail.request_params || failedDetail.request_body ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4, maxHeight: 150, overflow: 'auto' }}>
                  {JSON.stringify(failedDetail.request_params || failedDetail.request_body, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            
            <Descriptions.Item label="响应头" span={2}>
              {failedDetail.response_headers ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#f5f5f5', padding: 6, borderRadius: 4, maxHeight: 100, overflow: 'auto' }}>
                  {JSON.stringify(failedDetail.response_headers, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            
            <Descriptions.Item label="响应体" span={2}>
              {failedDetail.response_body ? (
                <pre style={{ margin: 0, fontSize: 12, background: '#fff2e8', padding: 6, borderRadius: 4, maxHeight: 200, overflow: 'auto' }}>
                  {typeof failedDetail.response_body === 'string' 
                    ? failedDetail.response_body 
                    : JSON.stringify(failedDetail.response_body, null, 2)}
                </pre>
              ) : '-'}
            </Descriptions.Item>
            
            {failedDetail.assert_results && failedDetail.assert_results.length > 0 && (
              <Descriptions.Item label="断言结果" span={2}>
                <div>
                  {failedDetail.assert_results.map((assert: any, index: number) => (
                    <div key={index} style={{ marginBottom: 4, padding: 6, background: assert.passed ? '#f6ffed' : '#fff2e8', borderRadius: 4 }}>
                      <Space>
                        {assert.passed ? (
                          <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        ) : (
                          <CloseCircleOutlined style={{ color: '#f5222d' }} />
                        )}
                        <Text>{assert.rule || assert.type || `断言${index + 1}`}</Text>
                        {!assert.passed && (
                          <Text type="danger"> - {assert.message || '验证失败'}</Text>
                        )}
                      </Space>
                    </div>
                  ))}
                </div>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
      
      <style>{`
        .api-test-tree .ant-tree-switcher {
          width: 24px !important;
          height: 32px !important;
          line-height: 32px !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
        }
        .api-test-tree .ant-tree-switcher-icon {
          font-size: 16px !important;
        }
        .api-test-tree .ant-tree-switcher-arrow svg {
          width: 14px !important;
          height: 14px !important;
        }
        .api-test-tree .ant-tree-node-content-wrapper {
          min-height: 32px !important;
          display: flex !important;
          align-items: center !important;
          flex: 1 !important;
        }
        .api-test-tree .ant-tree-treenode {
          display: flex !important;
          align-items: center !important;
          height: 32px !important;
        }
        .api-test-tree > .ant-tree-treenode {
          padding-left: 0 !important;
        }
        .api-test-tree .ant-tree-child-tree {
          padding-left: 0 !important;
          margin-left: 8px !important;
        }
      `}</style>

      {/* ===== 审批弹窗 ===== */}
      <Modal
        title={
          <Space>
            {reviewAction === 'approve' ? (
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
            ) : (
              <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
            )}
            <span>{reviewAction === 'approve' ? '通过审批' : '驳回用例'}</span>
          </Space>
        }
        open={reviewModalVisible}
        onOk={handleConfirmReview}
        onCancel={() => setReviewModalVisible(false)}
        confirmLoading={reviewing}
        okText={reviewAction === 'approve' ? '确认通过' : '确认驳回'}
        okButtonProps={{
          danger: reviewAction === 'reject',
        }}
        width={480}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            {reviewAction === 'approve'
              ? '确认审批通过此测试用例？用例状态将变为"已通过"。'
              : '确认驳回此测试用例？用例状态将变为"已驳回"，创建人可修改后重新提交。'}
          </Text>
        </div>
        <Text strong>审批意见（可选）：</Text>
        <Input.TextArea
          value={reviewComment}
          onChange={(e) => setReviewComment(e.target.value)}
          placeholder={reviewAction === 'approve' ? '通过理由...' : '驳回原因...'}
          rows={3}
          style={{ marginTop: 8 }}
        />
      </Modal>

      {/* ===== 测试报告弹窗 ===== */}
      <Modal
        title={
          <Space>
            <BarChartOutlined />
            <span>测试执行报告</span>
          </Space>
        }
        open={reportModalVisible}
        onCancel={() => { setReportModalVisible(false); setReportData(null); }}
        width={960}
        footer={[
          <Button key="html" icon={<DownloadOutlined />} onClick={() => handleExportReport('html')}>
            导出 HTML
          </Button>,
          <Button key="pdf" icon={<DownloadOutlined />} onClick={() => handleExportReport('pdf')}>
            导出 PDF
          </Button>,
          <Button key="close" type="primary" onClick={() => { setReportModalVisible(false); setReportData(null); }}>
            关闭
          </Button>,
        ]}
        style={{ top: 20 }}
      >
        {reportLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" tip="正在生成报告..." />
          </div>
        ) : reportData ? (
          <div>
            {/* 概览卡片 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
              <Card size="small" style={{ textAlign: 'center', background: '#f0f5ff' }}>
                <Text type="secondary">执行总数</Text>
                <Title level={3} style={{ margin: 0 }}>{reportData.total}</Title>
              </Card>
              <Card size="small" style={{ textAlign: 'center', background: '#f6ffed' }}>
                <Text type="secondary">通过</Text>
                <Title level={3} style={{ margin: 0, color: '#52c41a' }}>{reportData.passed}</Title>
              </Card>
              <Card size="small" style={{ textAlign: 'center', background: '#fff2f0' }}>
                <Text type="secondary">失败/错误</Text>
                <Title level={3} style={{ margin: 0, color: '#ff4d4f' }}>{reportData.failed + (reportData.error || 0)}</Title>
              </Card>
              <Card size="small" style={{ textAlign: 'center', background: '#fff7e6' }}>
                <Text type="secondary">通过率</Text>
                <Title level={3} style={{ margin: 0, color: '#fa8c16' }}>{reportData.pass_rate}%</Title>
              </Card>
            </div>

            {/* 耗时统计 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
              <Card size="small" title="耗时统计">
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="平均耗时">{reportData.duration_stats?.avg_ms?.toFixed(0)} ms</Descriptions.Item>
                  <Descriptions.Item label="最大耗时">{reportData.duration_stats?.max_ms} ms</Descriptions.Item>
                  <Descriptions.Item label="最小耗时">{reportData.duration_stats?.min_ms} ms</Descriptions.Item>
                  <Descriptions.Item label="总耗时">{reportData.duration_stats?.total_ms} ms</Descriptions.Item>
                </Descriptions>
              </Card>
              <Card size="small" title="断言统计">
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="总断言">{reportData.assertion_summary?.total_asserts}</Descriptions.Item>
                  <Descriptions.Item label="通过">{reportData.assertion_summary?.passed_asserts}</Descriptions.Item>
                  <Descriptions.Item label="失败">{reportData.assertion_summary?.failed_asserts}</Descriptions.Item>
                </Descriptions>
              </Card>
            </div>

            {/* 按用例类型统计 */}
            <Card size="small" title="按用例类型统计" style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {Object.entries(reportData.case_type_stats || {}).map(([type, stats]: [string, any]) => (
                  <Tag key={type} style={{ padding: '4px 12px', fontSize: 13 }}>
                    {type === 'normal' ? '正常' : type === 'error' ? '异常' : type === 'boundary' ? '边界' : type === 'auth' ? '权限' : type}
                    : {stats.passed}/{stats.total} 通过
                  </Tag>
                ))}
              </div>
            </Card>

            {/* 执行结果表格 */}
            <Card size="small" title={`执行明细（共 ${reportData.results?.length || 0} 条）`} style={{ marginBottom: 12 }}>
              <Table
                dataSource={reportData.results || []}
                rowKey="execution_id"
                size="small"
                pagination={{ pageSize: 10 }}
                columns={[
                  { title: '用例名称', dataIndex: 'case_name', key: 'case_name', ellipsis: true, width: 200 },
                  { title: '接口', key: 'api', width: 200, ellipsis: true,
                    render: (_: any, r: any) => <Text code>{r.method} {r.path}</Text> },
                  { title: '状态', dataIndex: 'status', key: 'status', width: 80,
                    render: (s: string) => (
                      <Tag color={s === 'passed' ? 'green' : s === 'failed' ? 'orange' : 'red'}>
                        {s === 'passed' ? '通过' : s === 'failed' ? '失败' : '错误'}
                      </Tag>
                    ) },
                  { title: '耗时(ms)', dataIndex: 'duration', key: 'duration', width: 80 },
                  { title: '状态码', dataIndex: 'actual_status', key: 'actual_status', width: 80 },
                  { title: '错误信息', dataIndex: 'error_message', key: 'error_message', ellipsis: true },
                ]}
              />
            </Card>
          </div>
        ) : null}
      </Modal>

      {/* ===== 环境鉴权配置弹窗 ===== */}
      <Modal
        title={<Space><SettingOutlined /> 环境鉴权配置</Space>}
        open={envConfigModalVisible}
        onCancel={() => { setEnvConfigModalVisible(false); setAuthTestResult(null); }}
        onOk={handleSaveEnvConfig}
        width={640}
        maskClosable={false}
      >
        <Form form={envForm} layout="vertical">
          <Form.Item name="name" label="环境名称">
            <Input placeholder="如: 测试环境" />
          </Form.Item>
          <Form.Item name="base_url" label="基础URL">
            <Input placeholder="如: http://localhost:8000" />
          </Form.Item>
          <Divider />
          <Form.Item name="auth_enabled" label="🔐 启用鉴权" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(pv, cv) => pv.auth_enabled !== cv.auth_enabled}>
            {({ getFieldValue }) => getFieldValue('auth_enabled') ? (
              <>
                <Form.Item name="auth_type" label="鉴权类型">
                  <Select>
                    <Select.Option value="bearer_token">Bearer Token（登录获取）</Select.Option>
                    <Select.Option value="basic_auth">Basic Auth</Select.Option>
                    <Select.Option value="api_key">API Key</Select.Option>
                    <Select.Option value="cookie">Cookie</Select.Option>
                  </Select>
                </Form.Item>
                <Form.Item noStyle shouldUpdate={(pv, cv) => pv.auth_type !== cv.auth_type}>
                  {({ getFieldValue }) => {
                    const authType = getFieldValue('auth_type') || 'bearer_token';
                    if (authType === 'bearer_token') {
                      return (
                        <>
                          <Form.Item name="login_url" label="登录接口路径" rules={[{ required: true }]}>
                            <Input placeholder="/auth/login" />
                          </Form.Item>
                          <Form.Item name="login_method" label="登录方法">
                            <Select>
                              <Select.Option value="POST">POST</Select.Option>
                              <Select.Option value="GET">GET</Select.Option>
                            </Select>
                          </Form.Item>
                          <Form.Item name="username" label="用户名">
                            <Input placeholder="admin" />
                          </Form.Item>
                          <Form.Item name="password" label="密码">
                            <Input.Password placeholder="password" />
                          </Form.Item>
                          <Form.Item name="json_path" label="Token提取路径" tooltip="从登录响应中提取Token的JSON路径">
                            <Input placeholder="data.token" />
                          </Form.Item>
                        </>
                      );
                    }
                    if (authType === 'basic_auth') {
                      return (
                        <>
                          <Form.Item name="username" label="用户名"><Input /></Form.Item>
                          <Form.Item name="password" label="密码"><Input.Password /></Form.Item>
                        </>
                      );
                    }
                    if (authType === 'api_key') {
                      return (
                        <>
                          <Form.Item name="api_key_name" label="Key名称" tooltip="请求头名称"><Input placeholder="X-API-Key" /></Form.Item>
                          <Form.Item name="api_key_value" label="Key值"><Input.Password /></Form.Item>
                        </>
                      );
                    }
                    if (authType === 'cookie') {
                      return (
                        <>
                          <Form.Item name="cookie_name" label="Cookie名称"><Input /></Form.Item>
                          <Form.Item name="cookie_value" label="Cookie值"><Input.Password /></Form.Item>
                        </>
                      );
                    }
                    return null;
                  }}
                </Form.Item>
              </>
            ) : null}
          </Form.Item>
          {authTestResult && (
            <Alert
              type={authTestResult.success ? 'success' : 'error'}
              message={authTestResult.success ? '鉴权测试成功' : '鉴权测试失败'}
              description={authTestResult.message}
              style={{ marginTop: 8 }}
              closable
              onClose={() => setAuthTestResult(null)}
            />
          )}
          <div style={{ marginTop: 12 }}>
            <Button
              onClick={handleTestAuth}
              loading={authTesting}
              icon={<PlayCircleOutlined />}
            >
              测试鉴权
            </Button>
          </div>
        </Form>
      </Modal>

      {/* ===== 请求体编辑弹窗 ===== */}
      <Modal
        title={<Space><EditOutlined /> 编辑请求体</Space>}
        open={bodyEditorVisible}
        onCancel={() => setBodyEditorVisible(false)}
        onOk={handleSaveBody}
        width={700}
        maskClosable={false}
      >
        {editingBodyTestCase && (
          <>
            <div style={{ marginBottom: 12 }}>
              <Tag color={methodColors[editingBodyTestCase.method || 'GET']}>{editingBodyTestCase.method}</Tag>
              <Text code>{editingBodyTestCase.path}</Text>
            </div>
            <Form.Item label="请求体类型">
              <Select value={bodyType} onChange={(v) => setBodyType(v)} style={{ width: 200 }}>
                <Select.Option value="json">JSON</Select.Option>
                <Select.Option value="form">Form URL-Encoded</Select.Option>
                <Select.Option value="multipart">Multipart Form-Data</Select.Option>
              </Select>
            </Form.Item>

            {bodyType === 'multipart' ? (
              <div>
                {bodyFields.map((field, index) => (
                  <div key={index} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
                    <Input
                      placeholder="字段名"
                      value={field.name}
                      onChange={(e) => handleUpdateBodyField(index, { name: e.target.value })}
                      style={{ width: 150 }}
                    />
                    <Select
                      value={field.type}
                      onChange={(v) => handleUpdateBodyField(index, { type: v as 'text' | 'file' })}
                      style={{ width: 80 }}
                    >
                      <Select.Option value="text">文本</Select.Option>
                      <Select.Option value="file">文件</Select.Option>
                    </Select>
                    {field.type === 'file' ? (
                      <Space>
                        <input
                          type="file"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleFileSelectAndHash(index, file);
                          }}
                          style={{ fontSize: 12 }}
                        />
                        {field.fileName && (
                          <Tooltip title={field.value}>
                            <Tag color="blue" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {field.fileName}
                            </Tag>
                          </Tooltip>
                        )}
                      </Space>
                    ) : (
                      <Input
                        placeholder="值"
                        value={field.value}
                        onChange={(e) => handleUpdateBodyField(index, { value: e.target.value })}
                        style={{ flex: 1 }}
                      />
                    )}
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveBodyField(index)} />
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={handleAddBodyField} block>
                  添加字段
                </Button>
                <Divider />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  💡 文件字段会自动计算MD5/SHA256。执行时将文件内容作为multipart请求体发送。
                </Text>
              </div>
            ) : (
              <Form.Item label={bodyType === 'form' ? 'Form Body (JSON格式)' : 'JSON Body'}>
                <Input.TextArea
                  value={bodyJsonText}
                  onChange={(e) => setBodyJsonText(e.target.value)}
                  rows={12}
                  placeholder={bodyType === 'json' ? '{"key": "value"}' : '{"key1": "value1", "key2": "value2"}'}
                  style={{ fontFamily: 'monospace', fontSize: 13 }}
                />
              </Form.Item>
            )}
          </>
        )}
      </Modal>
    </Layout>
  );
};

export default APITestPage;