import React, { useState, useEffect, useRef } from 'react';
import {
  Card, Tag, Button, Space, Tabs, Typography, message, Empty, Spin, Modal,
  Upload, Input, Popconfirm, Progress, Table, Select, Row, Col,
  Alert, Divider, Form, Descriptions, Radio, Collapse, Statistic
} from 'antd';
const { Dragger } = Upload;
const { Panel } = Collapse;
import {
  ArrowLeftOutlined, FileTextOutlined,
  DeleteOutlined, PlusOutlined,
  SyncOutlined,
  ApiOutlined, ImportOutlined,
  EditOutlined, SaveOutlined, InboxOutlined,
  ThunderboltOutlined, CopyOutlined
} from '@ant-design/icons';
import { projectSettingApi } from '../../api/projectExtApi';
import { useNavigate, useParams } from 'react-router-dom';
import { versionApi, fileApi } from '../../api/projectApi';
import { requirementApi } from '../../api/requirementApi';
import type { RequirementDocument } from '../../api/requirementApi';
import type { VersionDetailResponse } from '../../api/projectApi';
import { requirementChangeApi } from '../../api/requirementChangeApi';
import axiosInstance from '../../api/axiosConfig';

const { Title, Text, Paragraph } = Typography;

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  pending_review: { color: 'processing', label: '待审批' },
  approved: { color: 'success', label: '已通过' },
  published: { color: 'success', label: '已发布' },
  rejected: { color: 'error', label: '已驳回' },
};

const SOURCE_LABEL: Record<string, string> = {
  ai_generated: 'AI生成', imported_req: '导入业务流/需求', imported_cases: '用例导入',
  manual: '手动创建',
};
const SOURCE_COLOR: Record<string, string> = {
  ai_generated: '#7c3aed', imported_req: '#e67e00', imported_cases: '#2e7d32',
  manual: '#999',
};

const MODULE_LIST: string[] = [];  // 模块由AI生成后动态填充

const VersionDetailPage: React.FC = () => {
  const { id, projectId } = useParams<{ id: string; projectId: string }>();
  const navigate = useNavigate();

  // 版本数据
  const [version, setVersion] = useState<VersionDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // 用例表格
  const [testCases, setTestCases] = useState<any[]>([]);
  const [, setLoadingTC] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [selectAllPages, setSelectAllPages] = useState(false);
  const [tcPage, setTcPage] = useState(1);
  const [tcTotal, setTcTotal] = useState(0);
  const [tcFilters] = useState({ search: '', priority: '', status: '', module: '' });
  const [sourceTab, setSourceTab] = useState('ai');
  const [hasLoginModule, setHasLoginModule] = useState(true);
  const [projectConfigReady, setProjectConfigReady] = useState(false); // 项目是否已配置 base_url+username+password
  const [loginModuleContent, setLoginModuleContent] = useState('');
  const [loginModuleSaved, setLoginModuleSaved] = useState(false); // 已成功导入并固化

  // 导入业务流/需求弹窗（统一入口）
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importGen, setImportGen] = useState(false);
  const [genProgress, setGenProgress] = useState(0);
  const [genStatus, setGenStatus] = useState<'idle' | 'processing' | 'completed' | 'failed'>('idle');
  const [genLogs, setGenLogs] = useState<string[]>([]);
  const [genResult, setGenResult] = useState<any>(null);
  const [genError, setGenError] = useState('');
  const genLogRef = useRef<HTMLDivElement>(null);
  const progressTimerRef = useRef<any>(null);

  // 自动滚动日志到底部
  useEffect(() => {
    if (genLogRef.current) {
      genLogRef.current.scrollTop = genLogRef.current.scrollHeight;
    }
  }, [genLogs]);

  const [swaggerUrl, setSwaggerUrl] = useState('');
  const [swaggerImporting, setSwaggerImporting] = useState(false);
  const [showSwagger, setShowSwagger] = useState(false);  // Swagger 导入弹窗
  // API 鉴权配置
  const [apiAuth, setApiAuth] = useState<any>({});
  const [apiAuthBaseUrl, setApiAuthBaseUrl] = useState('');
  const [apiCredentialReady, setApiCredentialReady] = useState(false);
  const [apiCredUser, setApiCredUser] = useState('');
  const [apiCredPass, setApiCredPass] = useState('');
  const [authCandidates, setAuthCandidates] = useState<any[]>([]);
  const [authTesting, setAuthTesting] = useState(false);
  const [authSaving, setAuthSaving] = useState(false);
  const [showChange, setShowChange] = useState(false);    // 补充变更弹窗
  const [changeText, setChangeText] = useState('');
  const [changeSubmitting, setChangeSubmitting] = useState(false);
  const [changeResult, setChangeResult] = useState<any>(null);  // 分析结果
  const [changeApplying, setChangeApplying] = useState(false);   // 正在应用变更

  // 跨版本复用用例（全模块 / 勾选两种模式）
  const [reuseVisible, setReuseVisible] = useState(false);
  const [reuseVersions, setReuseVersions] = useState<any[]>([]);       // 同项目其他版本（来源可选）
  const [reuseSourceVid, setReuseSourceVid] = useState<number | null>(null);
  const [reuseSourceCases, setReuseSourceCases] = useState<any[]>([]); // 来源版本视角生效用例
  const [reuseSourceLoading, setReuseSourceLoading] = useState(false);
  const [reuseModuleFilter, setReuseModuleFilter] = useState<string | null>(null); // 模块单选筛选
  const [reuseSelected, setReuseSelected] = useState<number[]>([]);
  const [reuseSubmitting, setReuseSubmitting] = useState(false);


  // 详情/编辑弹窗
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailCase, setDetailCase] = useState<any>(null);
  const [editingDetail, setEditingDetail] = useState(false);
  const [editSteps, setEditSteps] = useState<any[]>([]);
  const [editForm, setEditForm] = useState({ name: '', description: '', module: '', priority: 'P2', sort_order: 0, preconditions: '', expected_result: '', change_summary: '' });
  const [savingDetail, setSavingDetail] = useState(false);
  const [, setDetailTab] = useState('info');

  // 审核弹窗
  const [reviewVisible, setReviewVisible] = useState(false);
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject'>('approve');
  const [reviewComment, setReviewComment] = useState('');
  const [reviewCaseId] = useState<number | null>(null);
  const [reviewBatch] = useState(false);

  // 模块列表
  const [moduleList, setModuleList] = useState<string[]>(MODULE_LIST);
  // 原始需求/业务流文档
  const [originalDocs, setOriginalDocs] = useState<RequirementDocument[]>([]);
  const [showOriginalDoc, setShowOriginalDoc] = useState<RequirementDocument | null>(null);

  // 从已生成的用例中自动提取模块列表
  const refreshModuleList = (cases?: any[]) => {
    const source = cases || testCases;
    if (!source.length) return;
    setModuleList(prev => {
      const modules = new Set(prev);
      source.forEach((tc: any) => {
        const m = tc.module || (Array.isArray(tc.tags) ? tc.tags[0] : '');
        if (m && m.length < 30) modules.add(m);
      });
      return modules.size > prev.length ? Array.from(modules) : prev;
    });
  };

  const versionId = Number(id);

  useEffect(() => {
    if (id) { fetchVersionDetail(); loadOriginalDocs(); }
    // 检查登录模块是否已导入
    axiosInstance.get('/web-ui-tests/check-login-module', {
      params: { project_id: projectId }
    }).then(
      (res: any) => setHasLoginModule(!!res.data?.has_login_module)
    ).catch(() => setHasLoginModule(true));
    // 检查项目是否已配置 base_url + username + password
    if (projectId) {
      axiosInstance.get(`/projects/${projectId}/settings`).then((res: any) => {
        const web = res.data?.exploration_config?.web || {};
        const ready = !!(web.base_url || (web.environments?.length && web.active_environment)) && !!web.username && !!web.password;
        setProjectConfigReady(ready);
      }).catch(() => setProjectConfigReady(false));
    }
  }, [id]);

  // 切换 Tab 时刷新对应配置状态
  useEffect(() => {
    if (sourceTab === 'swagger_import' && projectId) {
      loadApiAuthConfig();
    }
    // 任意 Tab 切换时刷新项目配置就绪状态（凭证可能在另一 Tab 被更新）
    if (projectId) {
      axiosInstance.get(`/projects/${projectId}/settings`).then((res: any) => {
        const web = res.data?.exploration_config?.web || {};
        const ready = !!(web.base_url || (web.environments?.length && web.active_environment)) && !!web.username && !!web.password;
        setProjectConfigReady(ready);
      }).catch(() => {});
    }
  }, [sourceTab, projectId]);

  const loadOriginalDocs = async () => {
    try {
      const res = await requirementApi.listDocuments({ version_id: versionId, page_size: 50 });
      let items = res.items || [];

      // 业务流去重：同一内容只保留最新一份，删除旧重复项
      const seen = new Map<string, any>();
      const toDelete: number[] = [];
      for (const doc of items) {
        if (doc.type !== 'business_flow') continue;
        const key = (doc.content || '').trim().slice(0, 500);
        if (!key) continue;
        if (seen.has(key)) {
          // 保留较新的，删除旧的
          const prev = seen.get(key);
          if (new Date(doc.created_at) > new Date(prev.created_at)) {
            toDelete.push(prev.id);
            seen.set(key, doc);
          } else {
            toDelete.push(doc.id);
          }
        } else {
          seen.set(key, doc);
        }
      }
      if (toDelete.length > 0) {
        // 静默删除重复文档
        Promise.all(toDelete.map(id => requirementApi.deleteDocument(id).catch(() => {})));
        items = items.filter(d => !toDelete.includes(d.id));
      }

      // 加载已保存的登录模块内容
      const loginDoc = items.find((d: any) => d.type === 'business_flow' && d.name === '登录模块' && d.content?.trim());
      if (loginDoc && loginDoc.content) {
        setLoginModuleContent(loginDoc.content.trim());
        setLoginModuleSaved(true);
      }
      setOriginalDocs(items);
    } catch { setOriginalDocs([]); }
  };

  // 检查是否已存在相同内容的文档，返回已存在的文档或 null
  const findDuplicateDoc = (content: string, docType?: string) => {
    if (!content || !content.trim()) return null;
    const key = content.trim().slice(0, 500); // 取前500字符比较
    return originalDocs.find(d => {
      const existing = (d.content || '').trim().slice(0, 500);
      return existing === key && (!docType || d.type === docType);
    }) || null;
  };

  // ===== 数据获取 =====
  const fetchVersionDetail = async () => {
    try {
      const data = await versionApi.get(versionId);
      setVersion(data);
    } catch { message.error('获取版本详情失败'); }
    finally { setLoading(false); }
  };

  const fetchTestCases = async () => {
    setLoadingTC(true);
    try {
      const params: any = {
        version_id: versionId, page: tcPage, page_size: 20,
        search: tcFilters.search || undefined,
        priority: tcFilters.priority || undefined,
        status: tcFilters.status || undefined,
      };
      if (sourceTab) params.source = sourceTab;
      const { data } = await axiosInstance.get('/test-cases/', { params });
      setTestCases(data.items || []);
      setTcTotal(data.total || 0);
      setSelectedRowKeys([]);
      setSelectAllPages(false);
    } catch { setTestCases([]); }
    finally { setLoadingTC(false); }
  };

  // ===== 跨版本复用用例（任意历史版本 → 全模块 / 勾选两种模式）=====
  const openReuseModal = async () => {
    setReuseVisible(true);
    setReuseSourceVid(null); setReuseSourceCases([]); setReuseModuleFilter(null); setReuseSelected([]);
    try {
      const res = await versionApi.listByProject(Number(projectId), { page_size: 100 });
      setReuseVersions((res.items || []).filter((v: any) => v.id !== Number(versionId)));
    } catch { setReuseVersions([]); }
  };

  const loadReuseSourceCases = async (vid: number) => {
    setReuseSourceLoading(true);
    setReuseModuleFilter(null); setReuseSelected([]);
    try {
      // 来源版本视角【生效行】（被派生冻结的旧用例在来源视角不可见，与后端口径一致）。
      // 接口 page_size 上限 100 → 分页拉取拼接（上限 5 页=500 条，覆盖正常规模）
      const all: any[] = [];
      for (let p = 1; p <= 5; p++) {
        const { data } = await axiosInstance.get('/test-cases/', { params: { version_id: vid, page: p, page_size: 100 } });
        all.push(...(data.items || []));
        if (all.length >= (data.total || 0) || all.length === 0) break;
      }
      setReuseSourceCases(all);
    } catch { setReuseSourceCases([]); }
    finally { setReuseSourceLoading(false); }
  };

  const submitReuse = async (payload: { source_version_id: number; module?: string; case_ids?: number[] }) => {
    setReuseSubmitting(true);
    try {
      const res = await versionApi.reuseCases(Number(versionId), payload);
      message.success(res.message);
      setReuseVisible(false);
      fetchTestCases();
    } catch (e: any) {
      message.error('复用失败：' + (e?.response?.data?.detail || e?.message || '未知错误'));
    } finally { setReuseSubmitting(false); }
  };

  // 全模块模式：来源版本视角该模块全部生效用例一起复制
  const handleReuseModule = (module: string) => {
    if (!reuseSourceVid) return;
    submitReuse({ source_version_id: reuseSourceVid, module });
  };

  // 勾选模式：只复制勾选的用例（模块筛选只是列表浏览维度）
  const handleReuseSelected = () => {
    if (!reuseSourceVid || reuseSelected.length === 0) return;
    submitReuse({ source_version_id: reuseSourceVid, case_ids: reuseSelected });
  };

  // ===== 统一导入 (业务流/需求 → 功能用例) =====
  const handleImportFile = async (info: any) => {
    const file = info.file;
    if (file.name.endsWith('.docx') || file.name.endsWith('.doc')) {
      const hide = message.loading('正在解析 Word 文档...', 0);
      try {
        const result = await fileApi.upload(file);
        hide();
        if (result?.extracted_text) {
          setImportText(result.extracted_text);
          setImportFile(file);
          message.success('文档解析成功，请确认内容后点击生成');
        } else {
          message.warning('文档解析失败，请尝试粘贴文本内容');
        }
      } catch (e: any) {
        hide();
        message.error('文档解析失败：' + (e?.message || '未知错误'));
      }
      return;
    }
    if (file.name.endsWith('.pdf')) {
      const hide = message.loading('正在解析 PDF 文档...', 0);
      try {
        const result = await fileApi.upload(file);
        hide();
        if (result?.extracted_text) {
          setImportText(result.extracted_text);
          setImportFile(file);
          message.success('PDF 解析成功，请确认内容后点击生成');
        } else {
          message.warning('PDF 解析失败，请尝试粘贴文本内容');
        }
      } catch (e: any) {
        hide();
        message.error('文档解析失败：' + (e?.message || '未知错误'));
      }
      return;
    }
    const reader = new FileReader();
    reader.onload = () => { setImportText(reader.result as string); setImportFile(file); };
    reader.readAsText(file, 'UTF-8');
  };

  const doImportGenerate = async () => {
    if (!importText.trim()) return;
    setImportGen(true); setGenStatus('processing'); setGenProgress(10);
    const now = new Date();
    const ts = new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 19).replace('T', ' ');
    setGenLogs([
      `📄 输入文档: ${importText.trim().length} 字符`,
      `📋 步骤 1/5 — 保存原始文档...`,
    ]);

    progressTimerRef.current = setInterval(() => {
      setGenProgress(p => Math.min(p + 2, 88));
    }, 1500);

    try {
      // 1) 保存文档（同版本唯一：新文档替换旧文档）
      // 排除登录模块：业务流内容不得写入「登录模块」文档（会被原始文档列表过滤且污染登录模块）
      const existingDoc = originalDocs.find(d => d.type !== 'swagger' && d.name !== '登录模块');
      let savedDocName: string;
      if (existingDoc) {
        // 已有文档 → 更新内容（不创建新的）
        savedDocName = existingDoc.name;
        try {
          await requirementApi.updateAndRegenerate(existingDoc.id, {
            content: importText.trim(),
            name: savedDocName,
          }, false);  // regenerate=false, 下面手动调用 generateAssets
        } catch {
          // 更新失败 → 删旧建新
          await requirementApi.deleteDocument(existingDoc.id);
          await requirementApi.createDocument({
            version_id: versionId, name: savedDocName,
            type: 'text', content: importText.trim(),
          });
        }
        setGenLogs(prev => [...prev, `   ✅ 文档已更新: ${savedDocName}`]);
      } else {
        savedDocName = importFile
          ? `需求文档_${importFile.name}_${ts}`
          : `需求文档_${ts}`;
        await requirementApi.createDocument({
          version_id: versionId, name: savedDocName,
          type: 'text', content: importText.trim(),
        });
        setGenLogs(prev => [...prev, `   ✅ 文档已保存: ${savedDocName}`]);
      }

      // 2) 更新版本
      await versionApi.update(versionId, { requirement_doc: importText.trim() } as any);
      setGenLogs(prev => [...prev,
        `📋 步骤 2/5 — 提取功能点 (Step1)...`,
        `   🤖 LLM 分析文档，提取可测试的功能点...`,
      ]);

      // 3) 调用后端生成（Step1→Step2→Auditor→Save）
      const genResult = await versionApi.generateAssets(versionId, 'ai');
      const data = (genResult as any)?.data || genResult;
      if (!data?.success && data?.success !== undefined) {
        setGenStatus('failed');
        setGenError(data?.error || data?.detail || 'LLM 调用失败');
        setGenLogs(prev => [...prev, `   ❌ 生成失败: ${data?.error || '未知错误'}`]);
        message.error('生成失败，请检查 LLM 配置是否激活');
        return;
      }
      if (progressTimerRef.current) { clearInterval(progressTimerRef.current); progressTimerRef.current = null; }
      const count = data?.test_cases_count || 0;
      setGenProgress(100); setGenStatus('completed');
      setGenResult({ total: count, created: count, updated: 0, saved: count });
      setGenLogs(prev => [...prev,
        `📋 步骤 3/5 — 生成测试用例 (Step2)...`,
        `   ✅ 1:1 约束: 每个功能点生成 1 条用例`,
        `   ✅ UI 元素命名约定: 「」标记元素, \"\" 标记值`,
        `📋 步骤 4/5 — Auditor 评审数量...`,
        `   ✅ 数量校验 + 补偿/裁剪 (如需)`,
        `📋 步骤 5/5 — 保存到数据库...`,
        `   ✅ 清理同来源旧草稿 + 保护已审核用例`,
        `─────────────────────────`,
        `🎉 完成! 共 ${count} 条功能用例`,
        `📌 下一步: 前往「功能用例」页面审核 → 批量转化为 UI 用例`,
      ]);
      if (count > 0) message.success(`生成 ${count} 条功能用例`);
      else message.warning('生成完成，但未产生用例，请检查 LLM 配置或需求内容');
      fetchTestCases(); refreshModuleList(); loadOriginalDocs();
    } catch (e: any) {
      if (progressTimerRef.current) { clearInterval(progressTimerRef.current); progressTimerRef.current = null; }
      setGenStatus('failed');
      setGenError(e.response?.data?.detail || e.message || '未知错误');
      setGenLogs(prev => [...prev, `   ❌ 异常: ${e.response?.data?.detail || e.message}`]);
    } finally { setImportGen(false); }
  };

  // ===== 导入登录模块（专用——有头探索+立即验证）=====
  const [loginImporting, setLoginImporting] = useState(false);
  const [loginImportError, setLoginImportError] = useState('');
  const handleImportLoginModule = async () => {
    setLoginImportError('');  // 重新尝试时清除旧错误
    if (!loginModuleContent.trim()) {
      message.warning('请先填写登录模块的业务流描述');
      return;
    }
    setLoginImporting(true);
    // 导入含真实浏览器探索+登录验证（约1-2分钟），axios 默认 120s 超时接近耗时上限，专用 600s
    message.info('正在导入登录模块并验证登录流程（含浏览器探索，约 1-2 分钟），请勿关闭页面…', 6);
    try {
      const { data } = await axiosInstance.post('/business-flow/import-login-module', {
        version_id: versionId,
        login_content: loginModuleContent.trim(),
      }, { timeout: 600000 });
      if (data.success) {
        // API 鉴权自动联动结果（登录模块导入成功后自动检测/验证 Swagger 登录接口）
        const authStatus = data.api_auth_auto?.status;
        const authMsg = authStatus === 'success'
          ? `；API 鉴权已自动联动验证通过（${data.api_auth_auto.login_url} → ${data.api_auth_auto.token_path}）`
          : authStatus === 'partial'
            ? `；API 鉴权已自动填充配置但验证未通过（${data.api_auth_auto.reason}），可到 Swagger Tab 手动测试`
            : authStatus === 'failed'
              ? `；API 鉴权自动联动失败（${data.api_auth_auto.reason}），可到 Swagger Tab 手动配置`
              : authStatus === 'skipped'
                ? `；API 鉴权自动联动跳过（${data.api_auth_auto.reason}）`
                : '';
        message.success(`登录模块验证成功！已固化业务流文档 + 生成UI用例 + 执行通过${authMsg}`, 8);
        setLoginModuleSaved(true);
        setHasLoginModule(true);
        fetchTestCases(); refreshModuleList();
        // 联动可能已写入 api_auth（已验证/待验证），刷新 Swagger Tab 的鉴权配置卡片状态
        loadApiAuthConfig();
      } else {
        const errMsg = data.execution_result?.error || data.error || '验证未通过';
        message.warning(`登录模块验证失败：${errMsg}。请修改业务流描述后重试。`);
      }
    } catch (e: any) {
      const errDetail = e.response?.data?.message || e.response?.data?.detail || '登录模块导入失败，请修改后重试';
      setLoginImportError(errDetail);
      message.error(errDetail);
    } finally {
      setLoginImporting(false);
    }
  };

  // ===== API 鉴权配置 =====
  const loadApiAuthConfig = async () => {
    try {
      const res = await projectSettingApi.getApiAuth(Number(projectId));
      setApiAuth(res.api_auth || {});
      setApiAuthBaseUrl(res.base_url || '');
      setApiCredentialReady(res.credential_ready || false);
      setApiCredUser(res.username || '');
      setApiCredPass(res.password || '');
      // 同时加载候选登录接口
      const candRes = await projectSettingApi.getLoginCandidates(Number(projectId));
      setAuthCandidates(candRes.candidates || []);
    } catch { /* ignore */ }
  };

  const handleSaveApiCredentials = async () => {
    // 将手动录入的凭证保存到 WEB 配置中（API 和 WEB 共享）
    setAuthSaving(true);
    try {
      await axiosInstance.patch(`/projects/${projectId}/settings/exploration`, {
        web: { username: apiCredUser, password: apiCredPass },
      });
      setApiCredentialReady(true);
      message.success('凭证已保存到项目配置');
    } catch (e: any) {
      message.error(e.response?.data?.detail || '保存凭证失败');
    } finally { setAuthSaving(false); }
  };

  const handleSaveApiAuth = async () => {
    setAuthSaving(true);
    try {
      // 如果用户手动填了凭证且之前未配置，先保存凭证
      if (!apiCredentialReady && apiCredUser && apiCredPass) {
        await axiosInstance.patch(`/projects/${projectId}/settings/exploration`, {
          web: { username: apiCredUser, password: apiCredPass },
        });
        setApiCredentialReady(true);
      }
      await projectSettingApi.saveApiAuth(Number(projectId), apiAuth);
      message.success('API 鉴权配置已保存');
    } catch (e: any) {
      message.error(e.response?.data?.detail || '保存失败');
    } finally { setAuthSaving(false); }
  };

  const handleTestApiAuth = async () => {
    setAuthTesting(true);
    try {
      const res = await projectSettingApi.testApiAuth(Number(projectId));
      if (res.success) {
        message.success(`鉴权验证通过！Token: ${res.token_preview}`);
        setApiAuth((prev: any) => ({ ...prev, verified: true }));
      } else {
        message.warning(res.detail || '鉴权验证未通过');
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || '鉴权测试失败');
    } finally { setAuthTesting(false); }
  };

  // 选择候选登录接口后自动填充配置
  const handleSelectCandidate = (candidate: any) => {
    const body: Record<string, string> = {};
    // 凭证字段识别关键词（与后端 WebExplorationConfig.login_username/password_keywords 语义对齐，
    // 中英通用字段名全覆盖：账号/帐号/手机号/邮箱/username/user/account 与 密码/pass/pwd）
    const userKws = ['user', 'account', '手机号', '账号', '帐号', '用户名', '邮箱', 'email'];
    const passKws = ['pass', 'pwd', '密码', '口令'];
    if (candidate.request_body_params) {
      for (const [k, _type] of Object.entries(candidate.request_body_params)) {
        const kl = k.toLowerCase();
        if (userKws.some(kw => kl.includes(kw))) body[k] = '{username}';
        else if (passKws.some(kw => kl.includes(kw))) body[k] = '{password}';
        else body[k] = '';
      }
    }
    // 如果请求体为空，补默认的 username/password 模板
    if (Object.keys(body).length === 0) {
      body['username'] = '{username}';
      body['password'] = '{password}';
    }
    setApiAuth({
      ...apiAuth,
      login_endpoint: `${candidate.method} ${candidate.path}`,
      login_url: candidate.path,
      login_method: candidate.method,
      request_body: body,
      token_source: 'body',
      // 优先用候选推断的 Token 路径（Swagger 响应 schema 递归扫描），无则保留现值/默认
      token_path: candidate.token_path_candidates?.[0] || apiAuth.token_path || 'data.token',
      token_inject_location: 'header',
      token_inject_name: 'Authorization',
      token_inject_template: 'Bearer {token}',
    });
  };

  const closeImportModal = () => {
    if (progressTimerRef.current) { clearInterval(progressTimerRef.current); progressTimerRef.current = null; }
    setShowImport(false); setImportText(''); setImportFile(null);
    setGenStatus('idle'); setGenProgress(0); setGenLogs([]); setGenResult(null);
    fetchTestCases(); refreshModuleList();
  };


  // ===== 用例操作 =====
  const handleReview = async () => {
    if (!reviewCaseId && !reviewBatch) return;
    try {
      if (reviewBatch) {
        const ids = await getAllSelectedIds();
        await axiosInstance.post('/test-cases/batch-review', {
          case_ids: ids, action: reviewAction, comment: reviewComment,
        });
        const count = ids.length;
        setReviewVisible(false); setReviewComment('');
        if (reviewAction === 'approve' && count > 0) {
          // 审核通过后，提示是否批量转化为UI
          Modal.confirm({
            title: `已通过 ${count} 条用例`,
            content: '是否立即将这些已通过的用例转化为 UI 自动化用例？\n\n（也可以在功能用例页面随时手动转化）',
            okText: '立即转化',
            cancelText: '稍后再说',
            onOk: () => handleBatchGenerateUI(),
          });
        } else {
          message.success(`${reviewAction === 'approve' ? '已通过' : '已驳回'} ${count} 条`);
        }
        setSelectedRowKeys([]); setSelectAllPages(false);
      } else {
        await axiosInstance.post(`/test-cases/${reviewCaseId}/review`, {
          action: reviewAction, comment: reviewComment,
        });
        setReviewVisible(false); setReviewComment('');
        if (reviewAction === 'approve') {
          Modal.confirm({
            title: '已通过',
            content: '是否立即将此用例转化为 UI 自动化用例？',
            okText: '立即转化',
            cancelText: '稍后再说',
            onOk: () => handleGenerateUISingle({ id: reviewCaseId }),
          });
        } else {
          message.success('已驳回');
        }
      }
      fetchTestCases();
    } catch (e: any) { message.error(e.response?.data?.detail || '审核失败'); }
  };

  // ===== 单条UI生成 =====
  const handleGenerateUISingle = async (row: any) => {
    const hide = message.loading(`正在为「${row.name || row.title}」生成UI用例...`, 0);
    try {
      await axiosInstance.post('/test-cases/generate-ui', {
        case_ids: [row.id], project_id: row.project_id || undefined,
      }, { timeout: 120000 });
      hide(); message.success(`UI生成成功: ${row.name || row.title}`); fetchTestCases();
    } catch (e: any) { hide(); message.error(e.response?.data?.detail || 'UI生成失败'); }
  };

  // ===== 获取全选ID（跨页） =====
  const getAllSelectedIds = async (): Promise<number[]> => {
    if (selectAllPages) {
      // 跨页全选：分页拉取全部ID（后端 page_size 最大100）
      const allIds: number[] = [];
      try {
        const params: any = {
          version_id: versionId, page_size: 100, page: 1,
          search: tcFilters.search || undefined,
          priority: tcFilters.priority || undefined,
          status: tcFilters.status || undefined,
        };
        if (sourceTab) params.source = sourceTab;

        // 逐页拉取直到拿完
        while (true) {
          const { data } = await axiosInstance.get('/test-cases/', { params });
          const ids = (data.items || []).map((t: any) => t.id);
          allIds.push(...ids);
          if (allIds.length >= data.total || ids.length === 0) break;
          params.page++;
        }
        return allIds;
      } catch { return testCases.map(t => t.id); }
    }
    return selectedRowKeys;
  };

  const handleBatchGenerateUI = async () => {
    const ids = await getAllSelectedIds();
    if (!ids.length) return;
    Modal.confirm({
      title: `确定为选中的 ${ids.length} 条用例生成UI？`,
      okText: '确定', onOk: async () => {
        const hide = message.loading(`正在批量生成UI用例(${ids.length}条)...`, 0);
        try {
          await axiosInstance.post('/test-cases/generate-ui', { case_ids: ids }, { timeout: 300000 });
          hide();
          message.success(`UI批量生成完成: ${ids.length} 条`);
          setSelectedRowKeys([]); setSelectAllPages(false);
          fetchTestCases();
        } catch (e: any) { hide(); message.error(e.response?.data?.detail || 'UI生成失败'); }
      },
    });
  };

  const normalizeSteps = (raw: any) => {
    // 后端 _process_test_steps 存的是纯字符串数组: ["操作1", "操作2"]
    // 手动编辑存的是对象数组: [{step, action, expected}]
    let steps = raw?.steps || raw?.test_steps;
    if (typeof steps === 'string') {
      try { steps = JSON.parse(steps); } catch { steps = []; }
    }
    if (!steps || !Array.isArray(steps) || steps.length === 0) {
      return [];
    }
    return steps.map((s: any, i: number) => {
      // 纯字符串格式（AI生成）
      if (typeof s === 'string') {
        return { step: i + 1, action: s, expected: '' };
      }
      // 对象格式（手动编辑）
      return {
        step: s.step || s.seq || s.step_no || i + 1,
        action: s.action || s.操作 || s.desc || '',
        expected: s.expected || s.预期 || s.expected_result || s.expect || '',
      };
    });
  };

  const openDetail = async (row: any) => {
    setDetailCase(row); setDetailVisible(true); setEditingDetail(false); setDetailTab('info');
    setEditSteps(normalizeSteps(row));
    const tags = Array.isArray(row.tags) ? row.tags : [];
    setEditForm({
      name: row.name || row.title || '',
      description: row.description || '',
      module: tags[0] || row.module || '',
      priority: row.priority || 'P2',
      sort_order: (row as any).sort_order || 0,
      preconditions: row.preconditions || '',
      expected_result: row.expected_result || '',
      change_summary: '',
    });
  };

  // 上一条/下一条
  const handlePrevCase = () => {
    if (!detailCase) return;
    const idx = testCases.findIndex(t => t.id === detailCase.id);
    if (idx > 0) {
      const row = testCases[idx - 1];
      openDetail(row);
      scrollTableToRow(idx - 1);
    } else { message.info('已是第一条'); }
  };

  const handleNextCase = () => {
    if (!detailCase) return;
    const idx = testCases.findIndex(t => t.id === detailCase.id);
    if (idx < testCases.length - 1) {
      const row = testCases[idx + 1];
      openDetail(row);
      scrollTableToRow(idx + 1);
    } else { message.info('已是最后一条'); }
  };

  const scrollTableToRow = (idx: number) => {
    setTimeout(() => {
      const rows = document.querySelectorAll('.ant-table-row');
      if (rows[idx]) {
        rows[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);
  };

  const handleEditDetail = () => {
    if (!detailCase) return;
    const tags = Array.isArray(detailCase.tags) ? detailCase.tags : [];
    setEditForm({
      name: detailCase.name || detailCase.title || '',
      description: detailCase.description || '',
      module: tags[0] || detailCase.module || '',
      priority: detailCase.priority || 'P2',
      sort_order: (detailCase as any).sort_order || 0,
      preconditions: detailCase.preconditions || '',
      expected_result: detailCase.expected_result || '',
      change_summary: '',
    });
    setEditSteps(normalizeSteps(detailCase));
    setEditingDetail(true);
  };

  const handleCancelEdit = () => {
    setEditingDetail(false);
    if (detailCase) {
      setEditSteps(normalizeSteps(detailCase));
      setEditForm({
        name: detailCase.name || detailCase.title || '',
        description: detailCase.description || '',
        module: (Array.isArray(detailCase.tags) ? detailCase.tags[0] : '') || detailCase.module || '',
        priority: detailCase.priority || 'P2',
        sort_order: (detailCase as any).sort_order || 0,
        preconditions: detailCase.preconditions || '',
        expected_result: detailCase.expected_result || '',
        change_summary: '',
      });
    }
  };

  const handleAddStep = () => {
    setEditSteps([...editSteps, { step: editSteps.length + 1, action: '', expected: '' }]);
  };

  const handleInsertStep = (index: number) => {
    const updated = [...editSteps];
    updated.splice(index + 1, 0, { step: 0, action: '', expected: '' });
    setEditSteps(updated.map((s, i) => ({ ...s, step: i + 1 })));
  };

  const handleRemoveStep = (index: number) => {
    if (editSteps.length <= 1) return;
    const updated = editSteps.filter((_, i) => i !== index);
    setEditSteps(updated.map((s, i) => ({ ...s, step: i + 1 })));
  };

  const handleUpdateStep = (index: number, field: string, value: string) => {
    const updated = [...editSteps];
    updated[index] = { ...updated[index], [field]: value };
    setEditSteps(updated);
  };

  const handleSaveDetail = async () => {
    if (!detailCase) return;
    setSavingDetail(true);
    try {
      // 过滤空步骤
      const steps = editSteps
        .filter((s: any) => (s.action || '').trim() || (s.expected || '').trim())
        .map((s: any, i: number) => ({ step: i + 1, action: s.action, expected: s.expected }));
      await axiosInstance.put(`/test-cases/${detailCase.id}`, {
        name: editForm.name,
        description: editForm.description,
        module: editForm.module,
        priority: editForm.priority,
        sort_order: editForm.sort_order,
        preconditions: editForm.preconditions,
        expected_result: editForm.expected_result,
        test_steps: steps.length > 0 ? steps : undefined,
        tags: editForm.module ? [editForm.module] : undefined,
        change_summary: editForm.change_summary,
      });
      message.success('保存成功（新版本已创建）');
      setEditingDetail(false);
      setDetailCase({
        ...detailCase,
        name: editForm.name,
        description: editForm.description,
        module: editForm.module,
        priority: editForm.priority,
        preconditions: editForm.preconditions,
        expected_result: editForm.expected_result,
        test_steps: steps,
        steps: steps,
        tags: editForm.module ? [editForm.module] : detailCase.tags,
      });
      fetchTestCases();
    } catch (e: any) { message.error(e.response?.data?.detail || '保存失败'); }
    finally { setSavingDetail(false); }
  };

  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [exportFormat, setExportFormat] = useState('zentao_csv');
  const [exporting, setExporting] = useState(false);

  const formatTestSteps = (steps: any) => {
    if (!steps || !Array.isArray(steps)) return '';
    return steps.map((s: any, i: number) => `${i + 1}. ${s.action || ''} → ${s.expected || ''}`).join('\n');
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      // 分页拉取全部数据
      let allCases: any[] = [];
      let page = 1;
      while (true) {
        const params: any = { version_id: versionId, page_size: 100, page };
        if (sourceTab) params.source = sourceTab;
        const { data } = await axiosInstance.get('/test-cases/', { params });
        allCases.push(...(data.items || []));
        if (allCases.length >= data.total) break;
        page++;
      }

      const vn = version?.version_number || 'unknown';
      const projectName = version?.project?.name || '';
      let content = '', filename = '', mimeType = '';

      if (exportFormat === 'zentao_csv') {
        const h = ['用例名称', '所属模块', '优先级', '前置条件', '测试步骤', '预期结果', '关键词'];
        const rows = allCases.map(c => [c.name||'', c.module||Array.isArray(c.tags)?c.tags.join(';'):'', c.priority||'P2', c.preconditions||'', formatTestSteps(c.test_steps), c.expected_result||'', ''].map(v => `"${String(v).replace(/"/g,'""')}"`).join(','));
        content = '﻿' + [h.join(','), ...rows].join('\n');
        filename = `${projectName}_${vn}_禅道.csv`; mimeType = 'text/csv;charset=utf-8';
      } else if (exportFormat === 'jira_csv') {
        const h = ['Summary','Issue Type','Priority','Description','Test Steps','Expected Result'];
        const rows = allCases.map(c => [c.name||'','Test',c.priority||'P2',c.description||'',formatTestSteps(c.test_steps),c.expected_result||''].map(v => `"${String(v).replace(/"/g,'""')}"`).join(','));
        content = '﻿' + [h.join(','), ...rows].join('\n');
        filename = `${projectName}_${vn}_Jira.csv`; mimeType = 'text/csv;charset=utf-8';
      } else if (exportFormat === 'json') {
        content = JSON.stringify({ project: projectName, version: vn, export_time: new Date().toISOString(), total: allCases.length, test_cases: allCases }, null, 2);
        filename = `${projectName}_${vn}_用例.json`; mimeType = 'application/json';
      } else if (exportFormat === 'excel') {
        const h = ['用例ID','用例名称','所属模块','优先级','描述','前置条件','测试步骤','预期结果'];
        const rows = allCases.map(c => [c.id,c.name||'',c.module||'','','',c.preconditions||'',formatTestSteps(c.test_steps),c.expected_result||'']);
        content = '﻿' + [h.join('\t'), ...rows.map(r => r.join('\t'))].join('\n');
        filename = `${projectName}_${vn}_用例.xls`; mimeType = 'application/vnd.ms-excel';
      }

      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob); const a = document.createElement('a');
      a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
      message.success(`导出成功：${allCases.length} 条`);
    } catch { message.error('导出失败'); }
    finally { setExporting(false); setExportModalVisible(false); }
  };


  if (loading || !version) return <div style={{textAlign:'center',padding:60}}><Spin size="large" /></div>;

  // AI 导入区的原始文档（排除 Swagger 文档与登录模块）
  const aiOriginalDocs = originalDocs.filter(d => d.type !== 'swagger' && d.name !== '登录模块');

  return (
    <div style={{ padding: 16 }}>
      {/* ===== 顶部 ===== */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>返回</Button>
        <Title level={3} style={{ margin: 0 }}>{version.version_number}</Title>
        <Text type="secondary">{version.version_name}</Text>
        <div style={{ flex: 1 }} />
        {/* 知识图谱入口已移至项目详情页顶部（项目级资产） */}
        <Button icon={<CopyOutlined />} onClick={openReuseModal}>复用用例</Button>
      </div>

      {/* ===== 来源Tab ===== */}
      <Tabs activeKey={sourceTab} onChange={(k) => { setSourceTab(k); setTcPage(1); }}
        className="source-tabs" style={{ marginBottom: 12 }}>
        <Tabs.TabPane tab={
          <span style={{ padding: '4px 16px', fontSize: 14, fontWeight: sourceTab==='ai'?600:400 }}>
            📋 导入 业务流/需求
          </span>
        } key="ai" />
        <Tabs.TabPane tab={
          <span style={{ padding: '4px 16px', fontSize: 14, fontWeight: sourceTab==='swagger_import'?600:400 }}>
            🔌 Swagger导入
          </span>
        } key="swagger_import" />
      </Tabs>

      {/* ===== 操作栏 ===== */}
      {!projectConfigReady ? (
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
          message="项目尚未配置连接信息。请先在「项目设置 → 项目配置」中填写目标系统 URL、登录用户名和密码。" />
      ) : !hasLoginModule ? (
        <Alert type="info" showIcon style={{ marginBottom: 8 }}
          message="请先导入「登录模块」相关业务流并点击「导入并验证」通过后，方能导入后续的「业务流/需求」。" />
      ) : null}
      {sourceTab === 'swagger_import' && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: 8, gap: 12 }}>
          <Button type="primary" size="small" icon={<ApiOutlined />} onClick={() => setShowSwagger(true)}>
            + 导入生成 API 用例
          </Button>
        </div>
      )}

      {/* ===== 登录模块（前置）===== */}
      {sourceTab === 'ai' && (
        <Card size="small" style={{ marginBottom: 12, border: `1px solid ${loginModuleSaved ? '#b7eb8f' : '#ffd591'}` }}
          title={<Space>
            <Tag color="gold">🔑 前置</Tag>
            <Text strong style={{ fontSize: 13 }}>登录模块</Text>
            {loginModuleSaved ? <Tag color="success">已导入验证</Tag> : <Tag color="warning">待导入验证</Tag>}
          </Space>}
          extra={loginModuleSaved ? (
            <Text type="success" style={{ fontSize: 12 }}>✅ 登录验证已通过</Text>
          ) : (
            <Button type="primary" size="small" danger icon={<ThunderboltOutlined />}
              loading={loginImporting}
              onClick={handleImportLoginModule}>
              导入并验证
            </Button>
          )}>
          {!loginModuleSaved && (
            <Alert type="info" showIcon style={{ marginBottom: 8 }}
              message="请根据实际系统登录流程修改以下描述，点击「导入并验证」确认登录可用。验证通过后才会固化保存。" />
          )}
          {loginImportError && (
            <Alert type="error" showIcon closable style={{ marginBottom: 8 }}
              message="导入失败"
              description={loginImportError}
              onClose={() => setLoginImportError('')} />
          )}
          <Input.TextArea
            rows={6}
            value={loginModuleContent}
            onChange={e => { setLoginModuleContent(e.target.value); setLoginImportError(''); }}
            disabled={loginModuleSaved}
            placeholder="请描述系统登录流程（每步一行）..."
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />
        </Card>
      )}

      {/* ===== 导入操作区（登录模块下方）===== */}
      {sourceTab === 'ai' && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: 12, gap: 12 }}>
          <Button type="primary" size="small" icon={<ImportOutlined />}
            disabled={!hasLoginModule}
            onClick={() => setShowImport(true)}>
            导入 业务流/需求
          </Button>
          <Button size="small" icon={<SyncOutlined />}
            disabled={!hasLoginModule || aiOriginalDocs.length === 0}
            onClick={() => setShowChange(true)}>
            补充变更
          </Button>
        </div>
      )}

      {/* ===== API 鉴权配置（Swagger Tab）===== */}
      {sourceTab === 'swagger_import' && (
        <Card size="small" style={{ marginBottom: 12, border: `1px solid ${apiAuth?.verified ? '#b7eb8f' : '#ffd591'}` }}
          title={<Space>
            <Tag color="gold">🔑 API 鉴权</Tag>
            <Text strong style={{ fontSize: 13 }}>登录接口配置</Text>
            {apiAuth?.verified ? <Tag color="success">已验证</Tag> : <Tag color="warning">待验证</Tag>}
          </Space>}
          extra={<Space>
            {apiAuth?.verified ? (
              <Text type="success" style={{ fontSize: 12 }}>✅ 鉴权验证已通过</Text>
            ) : (
              <Button type="primary" size="small" danger icon={<ThunderboltOutlined />}
                loading={authTesting} onClick={handleTestApiAuth}>
                测试鉴权
              </Button>
            )}
          </Space>}>
          {!apiAuth?.verified && (
            <Alert type="info" showIcon style={{ marginBottom: 8 }}
              message="配置登录鉴权接口后，所有 API 用例执行前会自动获取 Token 并注入请求。" />
          )}
          {/* 凭证状态 */}
          {apiCredentialReady ? (
            <Alert type="success" showIcon style={{ marginBottom: 8 }}
              message={<span>✅ 凭证已配置（来自项目设置）— 用户名：<Text code>{apiCredUser}</Text>，密码已隐藏。修改凭证请前往「项目设置 → 项目配置」。</span>} />
          ) : (
            <Alert type="warning" showIcon style={{ marginBottom: 8 }}
              message="⚠️ 尚未配置登录凭证。请在下方填写，或前往「项目设置 → 项目配置」统一配置（WEB 和 API 共用）。" />
          )}
          {/* 手动录入凭证（仅在未配置时显示）*/}
          {!apiCredentialReady && (
            <Row gutter={12} style={{ marginBottom: 8 }}>
              <Col span={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>登录用户名</Text>
                <Input size="small" placeholder="手机号 / 用户名"
                  value={apiCredUser} autoComplete="new-password"
                  onChange={e => setApiCredUser(e.target.value)} />
              </Col>
              <Col span={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>登录密码</Text>
                <Input.Password size="small" placeholder="密码"
                  value={apiCredPass} autoComplete="new-password"
                  onChange={e => setApiCredPass(e.target.value)} />
              </Col>
              <Col span={8} style={{ display: 'flex', alignItems: 'flex-end' }}>
                <Button size="small" icon={<SaveOutlined />} loading={authSaving}
                  disabled={!apiCredUser || !apiCredPass}
                  onClick={handleSaveApiCredentials}>保存凭证</Button>
              </Col>
            </Row>
          )}
          {/* 目标系统 URL 展示 */}
          <div style={{ marginBottom: 8 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>目标系统：</Text>
            <Text code style={{ fontSize: 11 }}>{apiAuthBaseUrl || '（未配置，请在项目设置中填写 base_url）'}</Text>
          </div>
          {/* 候选登录接口检测 */}
          {authCandidates.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>📡 从 Swagger 文档中检测到以下候选登录接口（选择自动填充）：</Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {authCandidates.slice(0, 6).map((c: any, i: number) => (
                  <Tag key={i} color="blue" style={{ cursor: 'pointer' }}
                    onClick={() => handleSelectCandidate(c)}>
                    {c.method} {c.path} {c.score >= 2 ? '⭐' : ''}
                  </Tag>
                ))}
              </div>
            </div>
          )}
          {/* 配置表单：主区仅保留用户可理解的登录接口 + 请求方法；Token 提取/注入参数由联动与候选选择自动推断 */}
          <Row gutter={12}>
            <Col span={16}>
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>登录接口 URL</Text>
                <Input size="small" placeholder="/api/v1/auth/login"
                  value={apiAuth?.login_url || ''}
                  onChange={e => setApiAuth({ ...apiAuth, login_url: e.target.value, login_endpoint: `${apiAuth?.login_method || 'POST'} ${e.target.value}` })} />
              </div>
            </Col>
            <Col span={8}>
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: 11 }}>请求方法</Text>
                <Select size="small" style={{ width: '100%' }}
                  value={apiAuth?.login_method || 'POST'}
                  onChange={v => setApiAuth({ ...apiAuth, login_method: v, login_endpoint: `${v} ${apiAuth?.login_url || ''}` })}>
                  {['GET', 'POST', 'PUT', 'PATCH'].map(m => <Select.Option key={m} value={m}>{m}</Select.Option>)}
                </Select>
              </div>
            </Col>
          </Row>
          {/* 高级设置：登录模块导入 / 选择候选接口时已自动推断填充，默认收起，懂协议的人可展开修改 */}
          <Collapse ghost size="small" style={{ marginBottom: 8, background: 'transparent' }}>
            <Panel header={<Text type="secondary" style={{ fontSize: 12 }}>高级设置（Token 提取与注入参数已自动推断，一般无需修改）</Text>} key="api_auth_advanced">
              <Row gutter={12}>
                <Col span={12}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Token 提取路径（响应体 JSONPath；来源=响应头时填响应头字段名）</Text>
                    <Input size="small" placeholder="data.access_token"
                      value={apiAuth?.token_path || ''}
                      onChange={e => setApiAuth({ ...apiAuth, token_path: e.target.value })} />
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Token 来源</Text>
                    <Select size="small" style={{ width: '100%' }}
                      value={apiAuth?.token_source || 'body'}
                      onChange={v => setApiAuth({ ...apiAuth, token_source: v })}>
                      <Select.Option value="body">响应体</Select.Option>
                      <Select.Option value="header">响应头</Select.Option>
                    </Select>
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Token 注入位置</Text>
                    <Select size="small" style={{ width: '100%' }}
                      value={apiAuth?.token_inject_location || 'header'}
                      onChange={v => setApiAuth({ ...apiAuth, token_inject_location: v })}>
                      <Select.Option value="header">Header</Select.Option>
                      <Select.Option value="query">Query Param</Select.Option>
                    </Select>
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>注入参数名</Text>
                    <Input size="small" placeholder="Authorization"
                      value={apiAuth?.token_inject_name || ''}
                      onChange={e => setApiAuth({ ...apiAuth, token_inject_name: e.target.value })} />
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>注入模板</Text>
                    <Input size="small" placeholder="Bearer {token}"
                      value={apiAuth?.token_inject_template || ''}
                      onChange={e => setApiAuth({ ...apiAuth, token_inject_template: e.target.value })} />
                  </div>
                </Col>
              </Row>
            </Panel>
          </Collapse>
          <div style={{ textAlign: 'right' }}>
            <Button size="small" icon={<SaveOutlined />} loading={authSaving}
              onClick={handleSaveApiAuth} style={{ marginRight: 8 }}>保存配置</Button>
            <Button size="small" danger icon={<ThunderboltOutlined />}
              loading={authTesting} onClick={handleTestApiAuth}>测试鉴权</Button>
          </div>
        </Card>
      )}

      {/* ===== 文档列表区 ===== */}
      {sourceTab === 'ai' ? (
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col span={24}>
            <Card size="small" title={<span style={{ fontSize: 13 }}>📋 原始文档 ({aiOriginalDocs.length})</span>}
              extra={<Button size="small" type="link" onClick={() => { const pid = version?.project_id || projectId; navigate(`/tests/functional?projectId=${pid}&versionId=${versionId}&source=ai`); }}>查看功能用例 →</Button>}>
              {aiOriginalDocs.length === 0 ? (
                <Empty description="暂无文档，请点击上方「导入 业务流/需求」按钮导入" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '20px 0' }} />
              ) : (
                aiOriginalDocs.map(doc => (
                  <div key={doc.id} style={{ padding: '8px 10px', marginBottom: 6, cursor: 'pointer', border: '1px solid #e8f0fe', borderRadius: 6, background: doc.type === 'business_flow' ? '#fafcff' : '#fffdf7' }}
                    onClick={() => setShowOriginalDoc(doc)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space>
                        <Tag color={doc.type === 'business_flow' ? 'blue' : 'orange'} style={{ fontSize: 10, lineHeight: '18px' }}>
                          {doc.type === 'business_flow' ? '业务流' : '需求'}
                        </Tag>
                        <Text strong style={{ fontSize: 12 }}>{doc.name}</Text>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 11 }}>{new Date(doc.created_at).toLocaleDateString('zh-CN')}</Text>
                    </div>
                    <Paragraph ellipsis={{ rows: 2 }} style={{ fontSize: 11, color: '#666', margin: '4px 0 0' }}>{doc.content?.slice(0, 200) || '(空)'}</Paragraph>
                  </div>
                ))
              )}
            </Card>
          </Col>
        </Row>
      ) : (
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col span={24}>
            <Card size="small" title={<span style={{ fontSize: 13 }}>🔌 Swagger API 文档 ({originalDocs.filter(d => d.type === 'swagger').length})</span>}
              extra={<Button size="small" type="link" onClick={() => { const pid = version?.project_id || projectId; navigate(`/tests/api?projectId=${pid}&versionId=${versionId}`); }}>查看 API 用例 →</Button>}>
              {originalDocs.filter(d => d.type === 'swagger').length === 0 ? (
                <Empty description="暂无 Swagger 文档，请点击上方按钮导入" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '20px 0' }} />
              ) : (
                originalDocs.filter(d => d.type === 'swagger').map(doc => (
                  <div key={doc.id} style={{ padding: '8px 10px', marginBottom: 6, cursor: 'pointer', border: '1px solid #f3e8ff', borderRadius: 6, background: '#fdfaff' }}
                    onClick={() => setShowOriginalDoc(doc)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong style={{ fontSize: 12, color: '#722ed1' }}>{doc.name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>{new Date(doc.created_at).toLocaleDateString('zh-CN')}</Text>
                    </div>
                    <Paragraph ellipsis={{ rows: 2 }} style={{ fontSize: 11, color: '#666', margin: '4px 0 0' }}>{doc.content?.slice(0, 200) || '(空)'}</Paragraph>
                  </div>
                ))
              )}
            </Card>
          </Col>
        </Row>
      )}

      {/* ===== 导入业务流/需求 → 功能用例弹窗（统一入口） ===== */}
      <Modal title="导入 业务流/需求 → AI 生成功能用例" open={showImport} onCancel={closeImportModal}
        footer={null} width={650} destroyOnClose maskClosable={false}>
        <Alert type="info" showIcon style={{ marginBottom: 12, fontSize: 12 }}
          message="💡 粘贴业务流描述或需求文档内容，AI 将分析并生成功能测试用例。生成后请在「用例管理 → 功能用例」中查看与审核。" />
        <Input.TextArea rows={8} placeholder="在此粘贴业务流描述或需求文档内容（支持中文自然语言、Markdown、纯文本）..." value={importText}
          onChange={e => setImportText(e.target.value)} disabled={genStatus === 'processing'} />
        <div style={{ marginTop: 8 }}>
          <Dragger beforeUpload={file => { handleImportFile({file}); return false; }} showUploadList={false}
            accept=".txt,.md,.docx,.doc,.pdf" disabled={genStatus === 'processing'} maxCount={1}
            fileList={importFile ? [{uid:'1', name:importFile.name, status:'done' as const}] : []}
            onRemove={() => { setImportFile(null); setImportText(''); }}
            style={{ padding: '6px 0' }}>
            <p className="ant-upload-drag-icon" style={{ marginBottom: 4 }}><InboxOutlined style={{ fontSize: 26 }} /></p>
            <p style={{ marginBottom: 0, fontSize: 12 }}>或拖拽上传文档 (.txt / .md / .docx / .pdf)</p>
          </Dragger>
        </div>

        {genStatus !== 'idle' && (
          <div style={{ marginTop: 12, border: '1px solid #ebeef5', borderRadius: 6, padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text strong>AI 生成进度</Text>
              <Tag color={genStatus==='processing'?'processing':genStatus==='completed'?'success':'error'}>
                {genStatus==='processing'?'处理中':genStatus==='completed'?'完成':'失败'}</Tag>
            </div>
            <Progress percent={genProgress} status={genStatus==='failed'?'exception':(genStatus==='completed'?'success':'active')} />
            <div ref={genLogRef} style={{ marginTop: 8, background: '#f5f7fa', borderRadius: 4, padding: 8,
              maxHeight: 200, overflow: 'auto', fontSize: 12, fontFamily: 'monospace' }}>
              {genLogs.map((log, i) => <div key={i} style={{ padding: '2px 0', color: '#606266' }}>{log}</div>)}
            </div>
            {genStatus === 'completed' && genResult && (
              <Alert type="success" style={{ marginTop: 8 }} showIcon
                message={`生成完成：${genResult.total} 条功能用例`} />
            )}
            {genStatus === 'failed' && (
              <Alert type="error" message={genError || '生成失败'} style={{ marginTop: 8 }} showIcon />
            )}
          </div>
        )}

        <div style={{ marginTop: 12, textAlign: 'right' }}>
          {genStatus === 'completed' || genStatus === 'failed' ? (
            <Space>
              <Button onClick={closeImportModal}>关闭</Button>
              <Button onClick={() => setGenStatus('idle')} type="default">重新生成</Button>
            </Space>
          ) : (
            <Space>
              <Button onClick={()=>{setShowImport(false);setImportText('');setImportFile(null);}}>取消</Button>
              <Button type="primary" loading={importGen} disabled={!importText.trim() || genStatus==='processing'}
                onClick={doImportGenerate}>生成功能用例</Button>
            </Space>
          )}
        </div>
      </Modal>


      {/* ===== 详情/编辑弹窗 ===== */}
      <Modal
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: 48 }}>
            <span>{editingDetail ? '编辑用例' : '用例详情'}</span>
            {!editingDetail && (
              <Space size={4}>
                <Button size="small" onClick={handlePrevCase}>上一条</Button>
                <Button size="small" onClick={handleNextCase}>下一条</Button>
                <Button size="small" type="primary" icon={<EditOutlined />} onClick={handleEditDetail}>编辑</Button>
              </Space>
            )}
          </div>
        }
        open={detailVisible}
        onCancel={() => { setDetailVisible(false); setEditingDetail(false); }}
        footer={
          editingDetail ? [
            <Button key="cancel" onClick={handleCancelEdit}>取消</Button>,
            <Button key="save" type="primary" icon={<SaveOutlined />} loading={savingDetail} onClick={handleSaveDetail}>保存</Button>,
          ] : [
            <Button key="close" onClick={() => setDetailVisible(false)}>关闭</Button>,
          ]
        }
        width={750}
        destroyOnClose
        maskClosable={false}
      >
        {detailCase && (
          <div>
            {editingDetail ? (
              <>
                {detailCase?.status === 'published' && (
                  <Alert message="该用例已发布，编辑后将退回草稿状态，需重新审核" type="warning" showIcon style={{ marginBottom: 12 }} />
                )}
                <Form layout="vertical" size="small">
                  <Form.Item label="标题">
                    <Input value={editForm.name} onChange={e => setEditForm({...editForm, name: e.target.value})} />
                  </Form.Item>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label="模块">
                        <Select value={editForm.module || undefined} onChange={v => setEditForm({...editForm, module: v || ''})}
                          allowClear placeholder="选择模块"
                          dropdownRender={menu => (<>{menu}<Divider style={{margin:'4px 0'}}/><Input placeholder="新模块名"
                            onKeyDown={e => { if (e.key==='Enter') { const val=(e.target as any).value?.trim(); if(val&&!moduleList.includes(val)){setModuleList([...moduleList,val]);setEditForm(f=>({...f,module:val}));}} }} /></>)}>
                          {moduleList.map(m => <Select.Option key={m} value={m}>{m}</Select.Option>)}
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item label="优先级">
                        <Select value={editForm.priority} onChange={v => setEditForm({...editForm, priority: v})}>
                          <Select.Option value="P0">P0</Select.Option><Select.Option value="P1">P1</Select.Option>
                          <Select.Option value="P2">P2</Select.Option><Select.Option value="P3">P3</Select.Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={6}>
                      <Form.Item label="执行顺序">
                        <Input type="number" value={editForm.sort_order} onChange={e => setEditForm({...editForm, sort_order: Number(e.target.value) || 0})}
                          style={{ width: '100%' }} min={0} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item label="前置条件">
                    <Input.TextArea rows={2} value={editForm.preconditions} onChange={e => setEditForm({...editForm, preconditions: e.target.value})} />
                  </Form.Item>

                  {/* 测试步骤编辑 — 表格形式 */}
                  <Form.Item label="测试步骤">
                    <Table
                      dataSource={editSteps.map((s, i) => ({ ...s, key: i, idx: i }))}
                      pagination={false}
                      size="small"
                      bordered
                      columns={[
                        { title: '步骤', dataIndex: 'step', width: 50, align: 'center',
                          render: (_: any, __: any, i: number) => <Text strong>{i + 1}</Text> },
                        { title: '操作步骤', dataIndex: 'action', width: 220,
                          render: (v: string, _: any, i: number) =>
                            <Input.TextArea value={v || ''} autoSize={{ minRows: 1, maxRows: 3 }}
                              onChange={e => handleUpdateStep(i, 'action', e.target.value)}
                              placeholder="操作步骤" style={{ border: 'none', background: 'transparent', resize: 'none' }} /> },
                        { title: '预期结果', dataIndex: 'expected', width: 220,
                          render: (v: string, _: any, i: number) =>
                            <Input.TextArea value={v || ''} autoSize={{ minRows: 1, maxRows: 3 }}
                              onChange={e => handleUpdateStep(i, 'expected', e.target.value)}
                              placeholder="预期结果" style={{ border: 'none', background: 'transparent', resize: 'none' }} /> },
                        { title: '', width: 70, align: 'center',
                          render: (_: any, __: any, i: number) => (
                            <Space size={2}>
                              <Button size="small" type="text" icon={<PlusOutlined />} onClick={() => handleInsertStep(i)} title="在下方插入" />
                              <Button size="small" type="text" danger icon={<DeleteOutlined />}
                                onClick={() => handleRemoveStep(i)} disabled={editSteps.length <= 1} title="删除" />
                            </Space>
                          )},
                      ]}
                    />
                    <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={handleAddStep} style={{ marginTop: 4 }} block>
                      添加步骤
                    </Button>
                  </Form.Item>
                  <Form.Item label="变更说明">
                    <Input placeholder="简述本次修改内容" value={editForm.change_summary}
                      onChange={e => setEditForm({...editForm, change_summary: e.target.value})} />
                  </Form.Item>
                </Form>
              </>
            ) : (
              <>
                {/* 查看模式 — FunctionalTestPage风格 */}
                {/* 操作按钮 */}
                <div style={{ marginBottom: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {(detailCase.status === 'draft' || detailCase.status === 'rejected') && (
                    <Button size="small" type="primary" onClick={async () => {
                      await axiosInstance.post(`/test-cases/${detailCase.id}/review`, { action: 'submit_for_review', reviewer: 'user' });
                      message.success('已提交审核'); fetchTestCases(); setDetailVisible(false);
                    }}>提交审核</Button>
                  )}
                  {detailCase.status === 'pending_review' && (
                    <>
                      <Button size="small" type="primary" onClick={async () => {
                        await axiosInstance.post(`/test-cases/${detailCase.id}/review`, { action: 'approve', reviewer: 'admin' });
                        message.success('已通过'); fetchTestCases(); setDetailVisible(false);
                      }}>审核通过</Button>
                      <Button size="small" danger onClick={async () => {
                        await axiosInstance.post(`/test-cases/${detailCase.id}/review`, { action: 'reject', reviewer: 'admin' });
                        message.success('已驳回'); fetchTestCases(); setDetailVisible(false);
                      }}>驳回</Button>
                    </>
                  )}
                </div>

                <Descriptions bordered column={2} size="small">
                  <Descriptions.Item label="用例名称" span={2}>{detailCase.name || detailCase.title}</Descriptions.Item>
                  <Descriptions.Item label="所属模块">
                    {Array.isArray(detailCase.tags) ? detailCase.tags.join(', ') : (detailCase.module || '-')}
                  </Descriptions.Item>
                  <Descriptions.Item label="优先级">
                    <Tag color={detailCase.priority==='P0'?'red':'default'}>{detailCase.priority}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={STATUS_MAP[detailCase.status]?.color}>{STATUS_MAP[detailCase.status]?.label}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="来源">
                    <Text style={{color:SOURCE_COLOR[detailCase.source]}}>{SOURCE_LABEL[detailCase.source]||detailCase.source||'手动'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="描述" span={2}>{detailCase.description || '-'}</Descriptions.Item>
                  <Descriptions.Item label="前置条件" span={2}>{detailCase.preconditions || '-'}</Descriptions.Item>

                  {/* 测试步骤 — 表格展示 */}
                  <Descriptions.Item label="测试步骤及预期结果" span={2}>
                    {(() => {
                      const steps = normalizeSteps(detailCase);
                      return steps.length > 0 && steps.some((s: any) => s.action || s.expected) ? (
                        <Table
                          dataSource={steps.map((s: any, i: number) => ({ ...s, key: i }))}
                          pagination={false}
                          size="small"
                          bordered
                          columns={[
                            { title: '步骤', dataIndex: 'step', width: 55, align: 'center' },
                            { title: '操作描述', dataIndex: 'action' },
                            { title: '预期结果', dataIndex: 'expected', render: (v: string) => v || '-' },
                          ]}
                        />
                      ) : <Text type="secondary">-</Text>;
                    })()}
                  </Descriptions.Item>

                  <Descriptions.Item label="预期结果" span={2}>{detailCase.expected_result || '-'}</Descriptions.Item>
                  <Descriptions.Item label="创建时间" span={2}>{detailCase.created_at ? new Date(detailCase.created_at).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
                </Descriptions>
              </>
            )}
          </div>
        )}
      </Modal>

      {/* ===== 导出格式弹窗 ===== */}
      <Modal title="导出用例" open={exportModalVisible} onCancel={() => setExportModalVisible(false)}
        onOk={handleExport} confirmLoading={exporting} width={420} maskClosable={false}>
        <Form layout="vertical">
          <Form.Item label="导出格式">
            <Select value={exportFormat} onChange={setExportFormat}>
              <Select.Option value="zentao_csv">禅道 CSV — 可直接导入禅道</Select.Option>
              <Select.Option value="jira_csv">Jira CSV — 可直接导入Jira</Select.Option>
              <Select.Option value="json">JSON — 完整数据结构</Select.Option>
              <Select.Option value="excel">Excel (TSV) — 可用Excel打开</Select.Option>
            </Select>
          </Form.Item>
          <Alert message={`将导出当前筛选条件下的全部 ${tcTotal} 条用例`} type="info" showIcon />
        </Form>
      </Modal>

      {/* ===== 审核弹窗 ===== */}
      <Modal title={reviewBatch ? `批量审核 ${selectAllPages ? tcTotal : selectedRowKeys.length} 条` : '审核用例'} open={reviewVisible}
        onCancel={() => setReviewVisible(false)} onOk={handleReview} width={450} maskClosable={false}>
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

      {/* ===== Swagger → API 用例弹窗 ===== */}
      <Modal title="Swagger/OpenAPI → AI 生成 API 用例" open={showSwagger}
        onCancel={() => { setShowSwagger(false); setSwaggerUrl(''); }}
        footer={null} width={600} destroyOnClose maskClosable={false}>
        <Alert type="info" showIcon style={{ marginBottom: 12, fontSize: 12 }}
          message="💡 支持 OpenAPI 3.0 / Swagger 2.0 规范的 JSON 或 YAML 格式。导入后生成 API 测试用例，原始文档自动保存供查看。" />
        <Form layout="vertical">
          <Form.Item label="Swagger/OpenAPI URL">
            <Input placeholder="https://example.com/openapi.json 或 /docs 页面地址"
              value={swaggerUrl} onChange={e => setSwaggerUrl(e.target.value)}
              disabled={swaggerImporting} prefix={<ApiOutlined />} />
          </Form.Item>
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <Button type="primary" icon={<ApiOutlined />} loading={swaggerImporting}
              disabled={!swaggerUrl.trim()}
              onClick={async () => {
                if (!swaggerUrl.trim()) { message.warning('请输入 Swagger/OpenAPI URL'); return; }
                setSwaggerImporting(true);
                try {
                  const now = new Date();
                const ts = new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 19).replace('T', ' ');
                  const res = await axiosInstance.post('/api-tests/auto-generate', {
                    project_id: version?.project_id,
                    version_id: versionId,
                    swagger_url: swaggerUrl.trim(),
                    include_normal: true,
                    include_error: true,
                    include_auth: true,
                    max_cases_per_endpoint: 5,
                  });
                  const swaggerJson = JSON.stringify(res.data?.raw_spec || res.data, null, 2);
                  const dupSw = findDuplicateDoc(swaggerJson, 'swagger');
                  if (!dupSw) {
                    await requirementApi.createDocument({
                      version_id: versionId,
                      name: `Swagger_API_${ts}`,
                      type: 'swagger',
                      content: swaggerJson,
                    });
                  }
                  if (res.data?.success === false) {
                    message.warning(res.data?.message || `导入失败，生成了 0 条用例`);
                  } else {
                    message.success(`导入成功：${res.data?.generated_count || 0} 条API用例`);
                  }
                  if (res.data?.generated_count > 0) {
                    setShowSwagger(false); setSwaggerUrl('');
                  }
                  loadOriginalDocs();
                  loadApiAuthConfig();  // 刷新鉴权候选接口
                } catch (e: any) {
                  message.error(e.response?.data?.detail || '导入失败');
                } finally { setSwaggerImporting(false); }
              }}>
              导入并生成 API 用例
            </Button>
          </div>
        </Form>
        <Divider plain style={{ fontSize: 12, color: '#999' }}>或上传 JSON / YAML 文件</Divider>
        <Dragger
          beforeUpload={async (file) => {
            setSwaggerImporting(true);
            const fd = new FormData();
            fd.append('file', file);
            try {
              const res = await axiosInstance.post('/api-tests/import/file', fd);
              const reader = new FileReader();
              reader.onload = async () => {
                const content = reader.result as string;
                const dupFile = findDuplicateDoc(content, 'swagger');
                if (!dupFile) {
                  const n = new Date(); const ts = new Date(n.getTime() + 8 * 3600000).toISOString().slice(0, 19).replace('T', ' ');
                  await requirementApi.createDocument({
                    version_id: versionId, name: `Swagger_${file.name}_${ts}`,
                    type: 'swagger', content: content,
                  });
                }
                loadOriginalDocs();
              };
              reader.readAsText(file);
              message.success(`导入成功：${res.data?.endpoint_count || 0} 个接口`);
              setShowSwagger(false);
            } catch (e: any) {
              message.error(e.response?.data?.detail || '导入失败');
            } finally { setSwaggerImporting(false); }
            return false;
          }}
          accept=".json,.yaml,.yml" maxCount={1} disabled={swaggerImporting}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p>点击或拖拽上传 Swagger/OpenAPI 文件</p>
        </Dragger>
      </Modal>

      {/* ===== 原始需求/业务流查看弹窗 ===== */}
      <Modal
        title={<Space><FileTextOutlined /><span>{showOriginalDoc?.name || '原始文档'}</span></Space>}
        open={!!showOriginalDoc}
        maskClosable={false}
        onCancel={() => setShowOriginalDoc(null)}
        footer={[
          <Button key="copy" onClick={() => {
            if (showOriginalDoc?.content) {
              navigator.clipboard.writeText(showOriginalDoc.content);
              message.success('已复制到剪贴板');
            }
          }}>复制内容</Button>,
          <Button key="close" onClick={() => setShowOriginalDoc(null)}>关闭</Button>,
        ]}
        width={800}
      >
        {showOriginalDoc && (() => {
          const sameTypeDocs = originalDocs.filter(d => d.type === showOriginalDoc.type);
          const curIdx = sameTypeDocs.findIndex(d => d.id === showOriginalDoc.id);
          return (
            <div>
              {sameTypeDocs.length > 1 && (
                <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Button size="small" disabled={curIdx <= 0}
                    onClick={() => setShowOriginalDoc(sameTypeDocs[curIdx - 1])}>← 上一条</Button>
                  <Text type="secondary" style={{ fontSize: 12 }}>{curIdx + 1} / {sameTypeDocs.length}</Text>
                  <Button size="small" disabled={curIdx >= sameTypeDocs.length - 1}
                    onClick={() => setShowOriginalDoc(sameTypeDocs[curIdx + 1])}>下一条 →</Button>
                </div>
              )}
              <div style={{ maxHeight: '55vh', overflow: 'auto' }}>
                <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
                  <Descriptions.Item label="类型">{showOriginalDoc.type === 'business_flow' ? '业务流' : showOriginalDoc.type === 'swagger' ? 'Swagger API' : '需求文档'}</Descriptions.Item>
                  <Descriptions.Item label="大小">{showOriginalDoc.file_size ? `${(showOriginalDoc.file_size / 1024).toFixed(1)} KB` : '-'}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{new Date(showOriginalDoc.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
                </Descriptions>
                <pre style={{
                  whiteSpace: 'pre-wrap', wordWrap: 'break-word',
                  fontFamily: 'monospace', fontSize: 13, lineHeight: 1.6,
                  padding: 12, backgroundColor: '#f5f5f5', borderRadius: 4,
                  maxHeight: '45vh', overflow: 'auto',
                }}>
                  {showOriginalDoc.content || '(无内容)'}
                </pre>
              </div>
            </div>
          );
        })()}
      </Modal>

      {/* ===== 补充变更弹窗 ===== */}
      <Modal title="补充变更" open={showChange} maskClosable={false} onCancel={() => { setShowChange(false); setChangeText(''); setChangeResult(null); }}
        footer={null} width={700} destroyOnClose>
        {!changeResult ? (
          <>
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
              message="粘贴本次迭代的变更内容（业务流/需求均可）。AI 将自动对比原文档，分析新增/修改/删除的功能点。" />
            <Input.TextArea rows={8} placeholder="粘贴变更内容..." value={changeText}
              onChange={e => setChangeText(e.target.value)}
              disabled={changeSubmitting} />
            <div style={{ marginTop: 12, textAlign: 'right' }}>
              <Space>
                <Button onClick={() => { setShowChange(false); setChangeText(''); }}>取消</Button>
                <Button type="primary" loading={changeSubmitting} disabled={!changeText.trim()}
                  onClick={async () => {
                    setChangeSubmitting(true);
                    try {
                      const result = await requirementChangeApi.analyzeChange(versionId, changeText.trim());
                      if (result.is_first_import) {
                      message.success(result.message || '首次导入完成');
                      setShowChange(false); setChangeText('');
                      fetchTestCases();
                    } else {
                      setChangeResult(result);
                    }
                    } catch (e: any) {
                      message.error(e.response?.data?.detail || '分析失败');
                    } finally { setChangeSubmitting(false); }
                  }}>
                  分析变更
                </Button>
              </Space>
            </div>
          </>
        ) : (
          <>
            {/* 变更摘要 */}
            <Alert type="success" showIcon style={{ marginBottom: 16 }}
              message={changeResult.message || '分析完成'} />
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center', borderColor: '#52c41a' }}>
                  <Statistic title="新增" value={changeResult.change_summary?.added_count || 0} valueStyle={{ color: '#52c41a' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center', borderColor: '#faad14' }}>
                  <Statistic title="修改" value={changeResult.change_summary?.modified_count || 0} valueStyle={{ color: '#faad14' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center', borderColor: '#ff4d4f' }}>
                  <Statistic title="删除" value={changeResult.change_summary?.deleted_count || 0} valueStyle={{ color: '#ff4d4f' }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Statistic title="影响用例" value={changeResult.total_affected_cases || 0} valueStyle={{ color: '#1890ff' }} />
                </Card>
              </Col>
            </Row>

            {/* 模块级明细 */}
            <div style={{ maxHeight: 300, overflow: 'auto', marginBottom: 12 }}>
              <Table
                dataSource={changeResult.detail_analysis || []}
                rowKey="module_name"
                size="small"
                pagination={false}
                columns={[
                  { title: '模块', dataIndex: 'module_name', width: 100 },
                  { title: '变更类型', dataIndex: 'change_type', width: 80, render: (t: string) => {
                    const m: Record<string, { color: string; label: string }> = { added: { color: 'green', label: '新增' }, modified: { color: 'orange', label: '修改' }, deleted: { color: 'red', label: '删除' }, unchanged: { color: 'default', label: '不变' } };
                    return <Tag color={m[t]?.color}>{m[t]?.label || t}</Tag>;
                  }},
                  { title: '影响级别', dataIndex: 'impact_level', width: 80, render: (t: string) => <Tag color={t==='high'?'red':t==='medium'?'orange':'blue'}>{t}</Tag> },
                  { title: '建议操作', dataIndex: 'suggested_action', width: 100, render: (t: string) => {
                    const m: Record<string, string> = { generate_new: '生成新用例', update_existing: '更新已有', deprecate: '标记废弃', keep_old: '保留不变' };
                    return m[t] || t;
                  }},
                  { title: '影响用例', dataIndex: 'affected_test_cases_count', width: 70 },
                ]}
              />
            </div>

            {/* 操作按钮 */}
            <div style={{ textAlign: 'right' }}>
              <Space>
                <Button onClick={() => { setChangeResult(null); }}>返回修改</Button>
                <Button onClick={() => { setShowChange(false); setChangeText(''); setChangeResult(null); }}>取消</Button>
                <Popconfirm
                  title="确认应用变更？将按建议操作处理受影响用例，关联的UI用例和执行中心条目将被移除。"
                  onConfirm={async () => {
                    setChangeApplying(true);
                    try {
                      const res = await requirementChangeApi.batchApproveChanges(versionId, true);
                      const data = (res as any)?.data || res;
                      const uiRemoved = data?.affected_ui_removed || 0;
                      const sceneRemoved = data?.affected_scene_removed || 0;
                      const generated = data?.generated_cases_count || 0;
                      const processed = data?.processed || 0;

                      const lines = [`✅ 变更已应用`, `📊 处理变更: ${processed} 条`, `🆕 新增用例: ${generated} 条`];
                      if (uiRemoved > 0) lines.push(`🗑️ 移除旧 UI 用例: ${uiRemoved} 条`);
                      if (sceneRemoved > 0) lines.push(`🗑️ 移除执行中心用例: ${sceneRemoved} 条`);

                      Modal.success({
                        title: '变更应用完成',
                        content: (
                          <div>
                            {lines.map((l, i) => <p key={i} style={{ margin: '4px 0' }}>{l}</p>)}
                            {uiRemoved > 0 && (
                              <p style={{ marginTop: 12, color: '#fa8c16', fontSize: 12 }}>
                                ⚠️ 已移除 {uiRemoved} 条旧 UI 用例。新的功能用例已生成，请前往「用例管理 → 功能用例」重新审核，通过后可重新转化为 UI 用例。
                              </p>
                            )}
                          </div>
                        ),
                      });
                      setShowChange(false); setChangeText(''); setChangeResult(null);
                      loadOriginalDocs();
                    } catch (e: any) {
                      message.error(e.response?.data?.detail || '应用失败');
                    } finally { setChangeApplying(false); }
                  }}
                >
                  <Button type="primary" loading={changeApplying}>
                    确认变更应用
                  </Button>
                </Popconfirm>
              </Space>
            </div>
          </>
        )}
      </Modal>

      {/* ===== 跨版本复用用例 Modal（全模块 / 勾选两种模式）===== */}
      <Modal title="复用用例（跨版本）" open={reuseVisible} width={780}
        onCancel={() => setReuseVisible(false)} footer={null}>
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
          message="从任意历史版本选择用例复制到当前版本：点模块标签的「复用全部」一键复制整个模块，或勾选表格中的用例按需复制。被派生冻结的旧用例在来源版本视角不可见。" />
        <div style={{ marginBottom: 12 }}>
          <Text strong>来源版本：</Text>
          <Select
            style={{ minWidth: 240, marginLeft: 8 }}
            placeholder="选择历史版本"
            value={reuseSourceVid}
            onChange={(v: number) => { setReuseSourceVid(v); loadReuseSourceCases(v); }}
            options={reuseVersions.map((v: any) => ({
              value: v.id,
              label: `${v.version_number}${v.version_name ? ` ${v.version_name}` : ''}`,
            }))}
          />
        </div>
        {reuseSourceVid && (
          <Spin spinning={reuseSourceLoading}>
            {reuseSourceCases.length === 0 ? (
              <Empty description="该版本暂无生效用例（被派生冻结的用例在来源视角不可见）" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '24px 0' }} />
            ) : (
              <>
                {/* 模块筛选（单选）：标签即筛选，右侧按钮一键全模块复用 */}
                <div style={{ marginBottom: 8 }}>
                  <Tag style={{ cursor: 'pointer' }} color={!reuseModuleFilter ? 'blue' : undefined}
                    onClick={() => setReuseModuleFilter(null)}>全部</Tag>
                  {Array.from(new Set(reuseSourceCases.map((c: any) => c.module || '未分组'))).map(m => {
                    const count = reuseSourceCases.filter((c: any) => (c.module || '未分组') === m).length;
                    return (
                      <Space key={m} size={4} style={{ marginRight: 8 }}>
                        <Tag style={{ cursor: 'pointer' }} color={reuseModuleFilter === m ? 'blue' : undefined}
                          onClick={() => setReuseModuleFilter(reuseModuleFilter === m ? null : m)}>{m}（{count}）</Tag>
                        <Button size="small" type="link" disabled={reuseSubmitting} onClick={() => handleReuseModule(m)}>复用全部</Button>
                      </Space>
                    );
                  })}
                </div>
                <Table
                  size="small" rowKey="id"
                  dataSource={reuseSourceCases.filter((c: any) => !reuseModuleFilter || (c.module || '未分组') === reuseModuleFilter)}
                  rowSelection={{ selectedRowKeys: reuseSelected, onChange: (keys: any[]) => setReuseSelected(keys) }}
                  pagination={{ pageSize: 10, showTotal: (t: number) => `共 ${t} 条` }}
                  columns={[
                    { title: '模块', dataIndex: 'module', width: 120, ellipsis: true },
                    { title: '用例名称', dataIndex: 'name', ellipsis: true },
                    { title: '版本', width: 70, render: (_: any, r: any) => (r.revision_no ? <Tag>v{r.revision_no}</Tag> : null) },
                    { title: '状态', width: 90, render: (_: any, r: any) => { const m = STATUS_MAP[r.status]; return m ? <Tag color={m.color}>{m.label}</Tag> : (r.status || '-'); } },
                  ]}
                />
                <div style={{ textAlign: 'right', marginTop: 12 }}>
                  <Space>
                    <Text type="secondary">已选 {reuseSelected.length} 条</Text>
                    <Button disabled={reuseSelected.length === 0} loading={reuseSubmitting} onClick={handleReuseSelected}>
                      复用勾选用例
                    </Button>
                  </Space>
                </div>
              </>
            )}
          </Spin>
        )}
      </Modal>
    </div>
  );
};

export default VersionDetailPage;
