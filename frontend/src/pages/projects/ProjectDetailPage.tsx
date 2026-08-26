import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Descriptions, Tag, Button, Space, Tabs, Table, Modal, Form, Input,
  message, Row, Col, Statistic, DatePicker, Typography, Tooltip, Popconfirm, Select,
  Upload, Empty, Spin, Progress, Checkbox, Alert
} from 'antd';
import {
  ArrowLeftOutlined, EditOutlined, PlusOutlined, DeleteOutlined,
  CalendarOutlined, CheckCircleOutlined, SyncOutlined,
  TeamOutlined, GlobalOutlined, SettingOutlined, BranchesOutlined,
  FileOutlined, EyeOutlined, RobotOutlined, DownloadOutlined,
  AuditOutlined, InfoCircleOutlined
} from '@ant-design/icons';
import { useNavigate, useParams, useLocation, useSearchParams } from 'react-router-dom';
import { projectApi, versionApi, fileApi } from '../../api/projectApi';
import { generationTaskApi } from '../../api/generationTaskApi';
import axiosInstance from '../../api/axiosConfig';
import ProjectMembers from '../../components/projects/ProjectMembers';
import ProjectEnvironments from '../../components/projects/ProjectEnvironments';
import ProjectSettings from '../../components/projects/ProjectSettings';
import { GenerateKnowledgeGraphModal, KnowledgeGraphProgressModal } from '../../components/knowledgeGraph';
import { knowledgeGraphApi, KnowledgeGraphGenerateRequest, KnowledgeGraphResponse, KnowledgeGraphProgressResponse } from '../../api/knowledgeGraphApi';
import type { ProjectDetailResponse, ProjectStats, ProjectUpdate } from '../../types/project';
import type { Version, VersionCreate } from '../../api/projectApi';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../../store';
import { selectUser } from '../../store/slices/authSlice';
import {
  resetForceOpen,
  trackTask,
  untrackTask,
  clearAllTaskState,
  setCurrentTask,
} from '../../store/slices/taskProgressSlice';

const { Title, Text } = Typography;
const { TextArea } = Input;

const ProjectDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState<ProjectDetailResponse | null>(null);
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [loading, setLoading] = useState(true);

  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editForm] = Form.useForm();

  const [versionModalVisible, setVersionModalVisible] = useState(false);
  const [versionForm] = Form.useForm();

  const [statusModalVisible, setStatusModalVisible] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);
  const [targetStatus, setTargetStatus] = useState<string>('');
  const [statusComment, setStatusComment] = useState('');
  const [activeTab, setActiveTab] = useState('versions');
  const [requirementModalVisible, setRequirementModalVisible] = useState(false);
  const [selectedRequirement, setSelectedRequirement] = useState<string | null>(null);
  const [selectedVersionForDoc, setSelectedVersionForDoc] = useState<Version | null>(null);
  const [docFileType, setDocFileType] = useState<string>('text');
  const [docFilePath, setDocFilePath] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedFileInfo, setUploadedFileInfo] = useState<{ file_path: string; file_type: string } | null>(null);
  
  const [uploadProgressModalVisible, setUploadProgressModalVisible] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadProgressStep, setUploadProgressStep] = useState('');
  const [uploadProgressStatus, setUploadProgressStatus] = useState<'uploading' | 'extracting' | 'analyzing' | 'completed' | 'error'>('uploading');
  const [uploadProgressMessage, setUploadProgressMessage] = useState('');
  
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<any>(null);
  const [analyzeModalVisible, setAnalyzeModalVisible] = useState(false);
  const [autoProcessDoc, setAutoProcessDoc] = useState(true);  // 默认开启自动处理
  const [docAnalysisStatus, setDocAnalysisStatus] = useState<'none' | 'analyzing' | 'needs-process' | 'processed'>('none');
  
  const [progressVisible, setProgressVisible] = useState(false);
  const [progressLogs, setProgressLogs] = useState<{msg: string, time: string}[]>([]);
  const [, setGeneratedStats] = useState({ testCases: 0 });
  const [successModalVisible, setSuccessModalVisible] = useState(false);
  const [successData, setSuccessData] = useState({ testCases: 0, durationSeconds: 0 });
  const [taskProgress, setTaskProgress] = useState(0);
  const [currentTaskId, setCurrentTaskId] = useState<number | null>(null);
  const [taskDisplayId, setTaskDisplayId] = useState<string | null>(null);
  
  // 知识图谱相关状态
  const [knowledgeGraphModalVisible, setKnowledgeGraphModalVisible] = useState(false);
  const [knowledgeGraphProgressVisible, setKnowledgeGraphProgressVisible] = useState(false);
  const [knowledgeGraphId, setKnowledgeGraphId] = useState<number | null>(null);
  const [knowledgeGraphRequest, setKnowledgeGraphRequest] = useState<KnowledgeGraphGenerateRequest | null>(null);
  // 项目级知识图谱状态（项目详情页顶部入口）
  const [kgStatus, setKgStatus] = useState<KnowledgeGraphResponse | null>(null);
  const [kgLoading, setKgLoading] = useState(false);
  
  const progressPollingRef = useRef<NodeJS.Timeout | null>(null);
  const lastProgressRef = useRef({ batch: 0, count: 0, step: '' });
  const abortControllerRef = useRef<AbortController | null>(null);
  const dispatch = useDispatch();
  const { 
    forceOpen, 
    taskId: trackedTaskId,
    runningTasks,
  } = useSelector((state: RootState) => state.taskProgress);
  
  const pollingTask = currentTaskId !== null || runningTasks.length > 0;
  
  // 取消任务确认状态
  const cancelConfirmingRef = useRef(false);
  const cancelModalRef = useRef<any>(null);
  const userCancelledRef = useRef(false); // 标记用户是否手动取消
  
  const handleCancelTask = useCallback(() => {
    // 防止重复弹出确认框
    if (cancelConfirmingRef.current || cancelModalRef.current) return;
    cancelConfirmingRef.current = true;
    
    // 立即停止轮询
    if (progressPollingRef.current) {
      clearInterval(progressPollingRef.current);
      progressPollingRef.current = null;
    }
    
    // 标记为用户手动取消
    userCancelledRef.current = true;
    
    // 保存当前taskId
    const taskIdToCancel = currentTaskId;
    const abortCtrl = abortControllerRef.current;
    
    cancelModalRef.current = Modal.confirm({
      title: '确认取消任务',
      content: '取消后已生成的数据将保留，但后续生成会停止。确定取消吗？',
      okText: '确定取消',
      okType: 'danger',
      cancelText: '继续执行',
      onOk: () => {
        cancelConfirmingRef.current = false;
        cancelModalRef.current = null;
        
        // 立即清理所有状态
        setProgressVisible(false);
        setVersionModalVisible(false);
        versionForm.resetFields();
        setUploadedFile(null);
        setUploadedFileInfo(null);
        setCreating(false);
        setCurrentTaskId(null);
        setTaskDisplayId(null);
        setAnalyzeResult(null);
        setDocAnalysisStatus('none');
        setAutoProcessDoc(true);
        setTaskProgress(0);
        setProgressLogs([]);
        
        // 清除 Redux 状态（包括 runningTasks）
        dispatch(clearAllTaskState(taskIdToCancel ?? undefined));
        
        // 取消HTTP请求
        if (abortCtrl) {
          abortCtrl.abort();
          abortControllerRef.current = null;
        }
        
        // 显示成功消息（只显示一次）
        message.success('任务已取消');
        
        // 后台异步调用取消API
        if (taskIdToCancel) {
          generationTaskApi.cancelTask(taskIdToCancel).then(() => {
            // 取消成功后，刷新数据
            fetchVersions();
            fetchStats();
          }).catch(() => {
            // 即使API失败，前端状态已清理
          });
        }
      },
      onCancel: () => {
        cancelConfirmingRef.current = false;
        cancelModalRef.current = null;
        userCancelledRef.current = false;
        // 恢复轮询
        if (taskIdToCancel && !progressPollingRef.current) {
          const pollTask = async () => {
            try {
              const t = await generationTaskApi.getTask(taskIdToCancel);
              if (t.status !== 'cancelled' && t.status !== 'completed' && t.status !== 'failed') {
                dispatch(setCurrentTask(t));
                if (t.progress > 0) setTaskProgress(t.progress);
              }
            } catch (e) {
              console.error('恢复轮询失败', e);
            }
          };
          pollTask();
          progressPollingRef.current = setInterval(pollTask, 3000);
        }
      }
    });
  }, [currentTaskId, dispatch]);

  useEffect(() => {
    return () => {
      if (progressPollingRef.current) {
        clearInterval(progressPollingRef.current);
      }
    };
}, []);

  const handleTrackTask = useCallback(async (taskIdToTrack: number, force: boolean = false) => {
    console.log('handleTrackTask called, taskId:', taskIdToTrack, 'force:', force);
    
    try {
      const task = await generationTaskApi.getTask(taskIdToTrack);
      console.log('Task fetched successfully:', task);
      
      if (task.status === 'completed') {
        setProgressVisible(true);
        setTaskProgress(100);
        setCurrentTaskId(task.id);
        setTaskDisplayId(task.display_id);
        setProgressLogs([
          { msg: '🎉 任务已完成！', time: new Date().toLocaleTimeString() },
          { msg: `📊 已生成 ${task.generated_count} 条测试用例`, time: new Date().toLocaleTimeString() },
        ]);
        setSuccessData({
          testCases: task.generated_count,
          durationSeconds: task.duration_seconds || 0
        });
        setTimeout(() => {
          setSuccessModalVisible(true);
          fetchVersions();
          fetchStats();
        }, 1500);
        return;
      }
      
      if (task.status === 'failed') {
        message.error(`任务失败：${task.error_message || '未知错误'}`);
        dispatch(untrackTask());
        return;
      }
      
      if (task.status === 'cancelled') {
        // 任务已被取消，清理状态但不显示消息（用户手动取消时已经显示过）
        dispatch(untrackTask());
        setProgressVisible(false);
        setCurrentTaskId(null);
        return;
      }
      
      dispatch(trackTask(taskIdToTrack));
      dispatch(setCurrentTask(task));
      
      setProgressVisible(true);
      setTaskProgress(task.progress || 0);
      setCurrentTaskId(task.id);
      setTaskDisplayId(task.display_id);
      setProgressLogs([]);
      lastProgressRef.current = { 
        batch: task.current_batch, 
        count: task.generated_count, 
        step: task.current_step || '' 
      };
      
      const addLog = (msg: string) => {
        setProgressLogs((prev) => [...prev, { msg, time: new Date().toLocaleTimeString() }]);
      };
      
      if (force) {
        addLog('🔄 恢复正在进行的生成任务...');
      }
      if (task.current_step) {
        addLog(`⚡ ${task.current_step}`);
      }
      if (task.current_batch > 0 && task.total_batches > 0) {
        addLog(`📊 进度: 第${task.current_batch}/${task.total_batches}批，已生成${task.generated_count}条用例`);
      } else if (task.progress > 0) {
        addLog(`📊 当前进度: ${task.progress}%`);
      }
      
      if (progressPollingRef.current) {
        clearInterval(progressPollingRef.current);
        progressPollingRef.current = null;
      }
      
      const pollTask = async () => {
        try {
          const t = await generationTaskApi.getTask(taskIdToTrack);
          dispatch(setCurrentTask(t));
          if (t.display_id) setTaskDisplayId(t.display_id);
          if (t.current_step && t.current_step !== lastProgressRef.current.step) {
            addLog(`⚡ ${t.current_step}`);
            lastProgressRef.current = { batch: t.current_batch, count: t.generated_count, step: t.current_step || '' };
          }
          if (t.progress > 0) setTaskProgress(t.progress);
          
          if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
            if (progressPollingRef.current) {
              clearInterval(progressPollingRef.current);
              progressPollingRef.current = null;
            }
            if (t.status === 'completed') {
              addLog('🎉 生成完成！共 ' + t.generated_count + ' 个测试用例');
              setTaskProgress(100);
              setSuccessData({ testCases: t.generated_count, durationSeconds: t.duration_seconds || 0 });
              // 清理所有相关状态
              cancelConfirmingRef.current = false;
              cancelModalRef.current = null;
              userCancelledRef.current = false;
              // 1.5秒后关闭进度弹窗并显示成功弹窗
              setTimeout(() => {
                setProgressVisible(false);
                setSuccessModalVisible(true);
                setCurrentTaskId(null);
                setCreating(false);
                fetchVersions();
                fetchStats();
                dispatch(clearAllTaskState(taskIdToTrack));
              }, 1500);
            } else if (t.status === 'failed') {
              addLog('❌ 生成失败：' + (t.error_message || '未知错误'));
              setTimeout(() => {
                setProgressVisible(false);
                message.error('测试用例生成失败: ' + (t.error_message || '未知错误'));
                dispatch(untrackTask());
              }, 2000);
            } else {
              addLog('⚠️ 任务已取消');
              setTimeout(() => {
                setProgressVisible(false);
                dispatch(untrackTask());
              }, 1000);
            }
          }
        } catch (e) {
          console.error('轮询任务状态失败', e);
          addLog('⚠️ 网络请求失败，正在重试...');
        }
      };
      
      pollTask();
      progressPollingRef.current = setInterval(pollTask, 3000);
    } catch (error: any) {
      console.error('获取任务信息失败', error);
      const errorMsg = error.response?.data?.detail || error.message || '网络连接失败';
      message.error(`获取任务信息失败: ${errorMsg}`);
    }
}, [dispatch]);
  
  useEffect(() => {
    if (forceOpen && trackedTaskId && Number(id)) {
      dispatch(resetForceOpen());
      handleTrackTask(trackedTaskId, true);
    }
  }, [forceOpen, trackedTaskId, id, dispatch, handleTrackTask]);
  
  const lastTrackedTaskIdRef = useRef<number | null>(null);
  
  useEffect(() => {
    if (!id) return;
    fetchProject();
    fetchStats();
    fetchVersions();
    fetchKgStatus();

    if (location.state?.openVersionModal) {
      setVersionModalVisible(true);
      navigate(location.pathname, { replace: true, state: {} });
    }
    return () => {
      // 跨项目切换（同组件实例 id 变化）：清空旧项目 KG 状态，避免残留展示
      setKgStatus(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 项目级知识图谱状态（顶部入口按钮状态 Tag）
  const fetchKgStatus = async () => {
    if (!id) return;
    setKgLoading(true);
    try {
      const list = await knowledgeGraphApi.listByProject(Number(id));
      setKgStatus(list && list.length > 0 ? list[0] : null);
    } catch {
      setKgStatus(null);
    } finally {
      setKgLoading(false);
    }
  };
  
  useEffect(() => {
    const taskIdParam = searchParams.get('taskId');
    const forceOpenParam = searchParams.get('forceOpen');
    
    if (taskIdParam && forceOpenParam === 'true' && id && !progressVisible) {
      const taskId = Number(taskIdParam);
      if (taskId && lastTrackedTaskIdRef.current !== taskId) {
        lastTrackedTaskIdRef.current = taskId;
        searchParams.delete('taskId');
        searchParams.delete('forceOpen');
        setSearchParams(searchParams, { replace: true });
        handleTrackTask(taskId, true);
      }
    }
  }, [searchParams, id, progressVisible]);
  
  useEffect(() => {
    if (runningTasks.length > 0 && id && !progressVisible) {
      const projectRunningTask = runningTasks.find(t => t.project_id === Number(id));
      if (projectRunningTask && lastTrackedTaskIdRef.current !== projectRunningTask.id) {
        lastTrackedTaskIdRef.current = projectRunningTask.id;
        handleTrackTask(projectRunningTask.id, false);
      }
    }
  }, [runningTasks.length, id, progressVisible]);

  const fetchProject = async () => {
    try {
      const data = await projectApi.get(Number(id));
      setProject(data);
    } catch (error) {
      message.error('获取项目详情失败');
    }
  };

  const fetchStats = async () => {
    try {
      const data = await projectApi.getStats(Number(id));
      setStats(data);
    } catch (error) {
      console.error('获取统计失败', error);
    }
  };

  const fetchVersions = async () => {
    try {
      const data = await versionApi.listByProject(Number(id));
      setVersions(data.items);
      setLoading(false);
    } catch (error) {
      message.error('获取版本列表失败');
      setLoading(false);
    }
  };

  const handleUpdateProject = async (values: ProjectUpdate) => {
    try {
      await projectApi.update(Number(id), values);
      message.success('更新项目成功');
      setEditModalVisible(false);
      fetchProject();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新项目失败');
    }
  };
  
  const handleAnalyzeDocument = async () => {
    if (!uploadedFileInfo) {
      message.warning('请先上传需求文档文件');
      return;
    }
    
    setAnalyzing(true);
    setDocAnalysisStatus('analyzing');
    try {
      const result = await fileApi.analyze({
        file_path: uploadedFileInfo.file_path,
        document_type: uploadedFileInfo.file_type
      });
      
      if (result.success) {
        setAnalyzeResult(result);
        setDocAnalysisStatus('processed');
        
        // 自动填充处理后的内容到表单
        if (result.markdown_content) {
          versionForm.setFieldValue('requirement_doc', result.markdown_content);
          message.success(`文档分析完成：识别到 ${result.stats?.total_modules || 0} 个功能模块`);
        }
        
        setAnalyzeModalVisible(true);
      } else {
        setDocAnalysisStatus('needs-process');
        message.error('文档分析失败');
      }
    } catch (error: any) {
      setDocAnalysisStatus('needs-process');
      message.error(error.response?.data?.detail || '文档分析失败');
    } finally {
      setAnalyzing(false);
    }
  };
  
  const handleUseAnalyzeResult = () => {
    if (analyzeResult?.markdown_content) {
      versionForm.setFieldValue('requirement_doc', analyzeResult.markdown_content);
      setAnalyzeModalVisible(false);
      message.success('已使用智能分析结果');
    }
  };

  const handleCreateVersion = async (values: VersionCreate) => {
    if (creating) return;
    
    if (!uploadedFileInfo && !values.requirement_doc) {
      message.error('请上传需求文档文件或填写需求文档内容');
      return;
    }
    
    setCreating(true);
    setVersionModalVisible(false);
    setProgressVisible(true);
    setProgressLogs([]);
    setTaskProgress(0);
    setCurrentTaskId(null);
    setTaskDisplayId(null);
    lastProgressRef.current = { batch: 0, count: 0, step: '' };
    
    abortControllerRef.current = new AbortController();
    
    const addLog = (msg: string) => {
      setProgressLogs((prev) => [...prev, { msg, time: new Date().toLocaleTimeString() }]);
    };
    
    try {
      addLog('🚀 开始创建版本...');
      addLog('📝 版本号：' + values.version_number);
      
      if (values.version_name) {
        addLog('🏷️ 版本名称：' + values.version_name);
      }
      
      if (uploadedFileInfo) {
        addLog('📎 需求文档文件：' + (uploadedFile?.name || '未知'));
      }
      
      addLog('💾 正在保存版本数据...');
      
      const versionData: VersionCreate = {
        ...values,
        project_id: Number(id),
        requirement_doc_file: uploadedFileInfo?.file_path,
        requirement_doc_file_type: uploadedFileInfo?.file_type,
      };
      
      const shouldAutoGenerate = !!values.requirement_doc &&
        values.requirement_doc.length > 50 &&
        !values.requirement_doc.startsWith('[已上传文件') &&
        !values.requirement_doc.includes('无法提取文本内容');
      
      // 使用异步模式，立即返回版本信息，后台生成测试用例
      const response = await versionApi.create(versionData, shouldAutoGenerate, true, abortControllerRef.current?.signal);
      
      addLog('✅ 版本保存成功');
      
      const generationTaskId = (response as any).generation_task_id;
      const respTaskDisplayId = (response as any).generation_task_display_id;
      const tcCount = (response as any).test_cases_count || 0;
      
      if (generationTaskId) {
        // 异步任务模式 - 启动快速轮询
        const displayIdToShow = respTaskDisplayId || `任务${generationTaskId}`;
        
        setTaskDisplayId(displayIdToShow);
        
        addLog('🤖 启动AI生成任务...');
        addLog('📋 任务ID: ' + displayIdToShow);
        addLog('⏳ AI正在分析需求文档...');
        setCurrentTaskId(generationTaskId);
        dispatch(trackTask(generationTaskId));
        
        // 启动快速轮询（每2秒）
        const startPolling = async () => {
          try {
            const task = await generationTaskApi.getTask(generationTaskId);
            dispatch(setCurrentTask(task));
            
            // 更新 display_id
            if (task.display_id) {
              setTaskDisplayId(task.display_id);
            }
            
            // 根据任务状态更新进度日志
            const addLogLocal = (msg: string) => {
              setProgressLogs((prev) => [...prev, { msg, time: new Date().toLocaleTimeString() }]);
            };
            
            if (task.current_step && task.current_step !== lastProgressRef.current.step) {
              addLogLocal(`⚡ ${task.current_step}`);
              lastProgressRef.current = { 
                batch: task.current_batch, 
                count: task.generated_count, 
                step: task.current_step || '' 
              };
            }
            
            if (task.progress > 0) {
              setTaskProgress(task.progress);
            }
            
            // 任务完成或失败时停止轮询
            if (task.status === 'completed' || task.status === 'failed') {
              if (progressPollingRef.current) {
                clearInterval(progressPollingRef.current);
                progressPollingRef.current = null;
              }
              
              if (task.status === 'completed') {
                addLogLocal('🎉 生成完成！共 ' + task.generated_count + ' 个测试用例');
                setGeneratedStats({ testCases: task.generated_count });
                setSuccessData({
                  testCases: task.generated_count,
                  durationSeconds: task.duration_seconds || 0
                });
                
                setTimeout(() => {
                  setProgressVisible(false);
                  setVersionModalVisible(false);
                  versionForm.resetFields();
                  setUploadedFile(null);
                  setUploadedFileInfo(null);
                  setSuccessModalVisible(true);
                  setTaskDisplayId(null);
                  setCreating(false);
                  setCurrentTaskId(null);
                  setAnalyzeResult(null);
                  setDocAnalysisStatus('none');
                  setAutoProcessDoc(true);
                  fetchVersions();
                  fetchStats();
                  dispatch(untrackTask());
                }, 1500);
              } else {
                addLogLocal('❌ 生成失败：' + (task.error_message || '未知错误'));
                setTimeout(() => {
                  setProgressVisible(false);
                  setVersionModalVisible(false);
                  versionForm.resetFields();
                  setUploadedFile(null);
                  setUploadedFileInfo(null);
                  message.error('测试用例生成失败');
                  setTaskDisplayId(null);
                  setCreating(false);
                  setCurrentTaskId(null);
                  setAnalyzeResult(null);
                  setDocAnalysisStatus('none');
                  setAutoProcessDoc(true);
                  dispatch(untrackTask());
                }, 2000);
              }
            }
          } catch (e) {
            console.error('轮询任务状态失败', e);
          }
        };
        
        // 立即执行一次
        startPolling();
        
        // 每2秒轮询
        progressPollingRef.current = setInterval(startPolling, 2000);
      } else if (tcCount > 0) {
        // 同步生成完成（小文档可能瞬间完成）
        addLog('🎉 生成完成！共 ' + tcCount + ' 个测试用例');
        setGeneratedStats({ testCases: tcCount });
        setSuccessData({ testCases: tcCount, durationSeconds: 0 });
        
        setTimeout(() => {
          setProgressVisible(false);
          setVersionModalVisible(false);
          versionForm.resetFields();
          setUploadedFile(null);
          setUploadedFileInfo(null);
          setCreating(false);
          setCurrentTaskId(null);
          setAnalyzeResult(null);
          setDocAnalysisStatus('none');
          setAutoProcessDoc(true);
          setSuccessModalVisible(true);
          fetchVersions();
          fetchStats();
        }, 1500);
      } else {
        addLog('✅ 版本创建完成');
        setTimeout(() => {
          setProgressVisible(false);
          setVersionModalVisible(false);
          versionForm.resetFields();
          setUploadedFile(null);
          setUploadedFileInfo(null);
          setCreating(false);
          setCurrentTaskId(null);
          setAnalyzeResult(null);
          setDocAnalysisStatus('none');
          setAutoProcessDoc(true);
          fetchVersions();
          fetchStats();
        }, 1500);
      }
      
    } catch (error: any) {
      if (error.name === 'CanceledError' || error.code === 'ERR_CANCELED') {
        addLog('⚠️ 请求已被取消');
        setTimeout(() => {
          setProgressVisible(false);
          setVersionModalVisible(false);
          versionForm.resetFields();
          setUploadedFile(null);
          setUploadedFileInfo(null);
          setCreating(false);
          setCurrentTaskId(null);
          setAnalyzeResult(null);
          setDocAnalysisStatus('none');
          setAutoProcessDoc(true);
          fetchVersions();
          fetchStats();
        }, 500);
      } else {
        addLog('❌ 创建失败：' + error.message);
        setTimeout(() => {
          setProgressVisible(false);
          setVersionModalVisible(false);
          versionForm.resetFields();
          setUploadedFile(null);
          setUploadedFileInfo(null);
          setCreating(false);
          setCurrentTaskId(null);
          setAnalyzeResult(null);
          setDocAnalysisStatus('none');
          setAutoProcessDoc(true);
          message.error('创建版本失败');
          fetchVersions();
          fetchStats();
        }, 2000);
      }
    } finally {
      setCreating(false);
      abortControllerRef.current = null;
    }
  };

  const handleStatusChange = async () => {
    if (!selectedVersion || !targetStatus) return;
    
    try {
      await versionApi.updateStatus(selectedVersion.id, targetStatus, statusComment || undefined);
      message.success('状态变更成功');
      setStatusModalVisible(false);
      fetchVersions();
      fetchStats();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '状态变更失败');
    }
  };

  const handleDeleteVersion = async (versionId: number) => {
    try {
      await versionApi.delete(versionId);
      message.success('删除版本成功');
      fetchVersions();
      fetchStats();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除版本失败');
    }
  };

  // 知识图谱生成处理（项目级：版本可空；版本来源由 Modal 端取最新版本，
  // 不写 selectedVersion——那是「变更状态」弹窗的选中状态，互不污染）
  const handleGenerateKnowledgeGraph = () => {
    setKnowledgeGraphModalVisible(true);
  };

  const handleKnowledgeGraphGenerate = async (request: KnowledgeGraphGenerateRequest) => {
    try {
      const result = await knowledgeGraphApi.generate(request);

      if (result.success && result.data) {
        setKnowledgeGraphId(result.data.graph_id);
        setKnowledgeGraphRequest(request);
        setKnowledgeGraphModalVisible(false);
        setKnowledgeGraphProgressVisible(true);
        // 拉取真实行状态（不手工拼装，避免字段错位导致 navigate 坏链）
        fetchKgStatus();
        message.success('知识图谱生成任务已启动');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '触发知识图谱生成失败');
      throw error; // 上抛给生成弹窗：失败不弹成功提示、不清空表单
    }
  };

  const handleViewKnowledgeGraph = (graphId: number) => {
    navigate(`/knowledge-graph/${graphId}`);
  };

  // 进度轮询回传：同步顶部状态 Tag（生成中 x% → 完成后已生成 n 页，无需手动刷新）
  const handleKgProgressUpdate = (prog: KnowledgeGraphProgressResponse) => {
    setKgStatus(s => (s ? {
      ...s,
      exploration_status: prog.exploration_status as KnowledgeGraphResponse['exploration_status'],
      progress_percentage: prog.progress_percentage,
      page_count: prog.page_count,
      menu_count: prog.menu_count,
      element_count: prog.element_count,
    } : s));
  };

  // 项目页顶部「知识图谱」入口：已完成→跳转可视化；生成中→进度弹窗；失败→提示并重开生成弹窗；无→生成弹窗
  const handleOpenKnowledgeGraph = () => {
    if (kgStatus && kgStatus.exploration_status === 'completed') {
      navigate(`/knowledge-graph/${kgStatus.id}`);
    } else if (kgStatus && (kgStatus.exploration_status === 'running' || kgStatus.exploration_status === 'pending')) {
      setKnowledgeGraphId(kgStatus.id);
      setKnowledgeGraphProgressVisible(true);
    } else {
      if (kgStatus && kgStatus.exploration_status === 'failed') {
        message.warning(kgStatus.error_message ? `上次生成失败：${kgStatus.error_message}` : '上次知识图谱生成失败，请重试');
      }
      handleGenerateKnowledgeGraph();
    }
  };

  const handleViewRequirement = (version: Version) => {
    setSelectedVersionForDoc(version);
    
    const fileType = version.requirement_doc_file_type;
    const filePath = version.requirement_doc_file;
    const docContent = version.requirement_doc;
    
    if (filePath && fileType) {
      // 设置文件路径用于下载原始文件
      setDocFilePath(filePath);
      setDocFileType(fileType);
      
      if (['md', 'txt', 'markdown'].includes(fileType)) {
        // Markdown/文本文件：显示内容
        fetchTextDocument(filePath);
      } else if (['pdf'].includes(fileType)) {
        // PDF文件：iframe预览
        setSelectedRequirement(null);
        setRequirementModalVisible(true);
      } else if (['docx', 'doc'].includes(fileType)) {
        // Word文件：显示转换后的markdown内容（如果有），否则提供下载
        if (docContent && docContent.length > 100 && !docContent.startsWith('[已上传文件')) {
          setSelectedRequirement(docContent);
          setDocFileType('markdown');  // 标记为markdown以便渲染
        } else {
          setSelectedRequirement(null);
        }
        setRequirementModalVisible(true);
      } else {
        // 其他类型：显示内容
        setSelectedRequirement(docContent || version.description || '暂无需求文档');
        setDocFileType('text');
        setRequirementModalVisible(true);
      }
    } else {
      // 没有文件路径，显示内容
      setSelectedRequirement(docContent || version.description || '暂无需求文档');
      setDocFileType('text');
      setDocFilePath(null);
      setRequirementModalVisible(true);
    }
  };

  const fetchTextDocument = async (filePath: string) => {
    try {
      const response = await axiosInstance.get(`/files/preview/${filePath}`);
      setSelectedRequirement(response.data.content || '');
      setDocFileType(response.data.file_type || 'text');
      setDocFilePath(null);
      setRequirementModalVisible(true);
    } catch (error) {
      message.error('获取文档内容失败');
      setSelectedRequirement('暂无需求文档');
      setDocFileType('text');
      setDocFilePath(null);
      setRequirementModalVisible(true);
    }
  };

  const openStatusModal = (version: Version) => {
    setSelectedVersion(version);
    setTargetStatus('');
    setStatusComment('');
    setStatusModalVisible(true);
  };

  const statusColors: Record<string, string> = {
    planning: 'blue',
    developing: 'orange',
    testing: 'purple',
    frozen: 'cyan',
    released: 'green',
    archived: 'default',
  };

  const statusNames: Record<string, string> = {
    planning: '规划中',
    developing: '开发中',
    testing: '测试中',
    frozen: '已冻结',
    released: '已发布',
    archived: '已归档',
  };

  const handleUploadRequirement = async (file: File) => {
    if (uploadedFile && uploadedFile.name === file.name) {
      Modal.confirm({
        title: '文件已存在',
        content: `文件"${file.name}"已上传，是否覆盖？`,
        okText: '覆盖',
        cancelText: '取消',
        onOk: () => {
          setUploadedFile(file);
          performUpload(file);
        }
      });
      return;
    }
    
    setUploadedFile(file);
    performUpload(file);
  };

  const performUpload = async (file: File) => {
    setUploading(true);
    setDocAnalysisStatus('none');
    setAnalyzeResult(null);
    
    // 打开进度弹窗
    setUploadProgressModalVisible(true);
    setUploadProgress(0);
    setUploadProgressStep('上传文件');
    setUploadProgressStatus('uploading');
    setUploadProgressMessage('正在上传文件到服务器...');
    
    try {
      const result = await fileApi.upload(file, (progress) => {
        // 上传进度（0-40%）
        const adjustedProgress = Math.round(progress * 0.4);
        setUploadProgress(adjustedProgress);
        setUploadProgressMessage(`上传进度：${progress}%`);
      });
      
      if (result.success) {
        // 文件上传完成，开始提取文本（40-50%）
        setUploadProgress(40);
        setUploadProgressStep('提取文本');
        setUploadProgressStatus('extracting');
        setUploadProgressMessage('正在提取文档文本内容...');
        
        setUploadedFileInfo({
          file_path: result.file_path,
          file_type: result.file_type
        });
        
        // 模拟提取文本的进度
        setTimeout(() => setUploadProgress(45), 300);
        setTimeout(() => setUploadProgress(50), 600);
        
        if (result.extracted_text && result.extracted_text.length > 0) {
          // 检查文档格式是否规范
          const extractedText = result.extracted_text;
          const needsProcess = checkDocFormat(extractedText);
          
          if (needsProcess && autoProcessDoc) {
            // 自动调用LLM处理文档（50-100%）
            setUploadProgress(50);
            setUploadProgressStep('智能分析');
            setUploadProgressStatus('analyzing');
            setUploadProgressMessage('正在使用 AI 分析文档格式...');
            
            try {
              const analyzeRes = await fileApi.analyze({
                content: extractedText,
                document_type: result.file_type
              });
              
              if (analyzeRes.success && analyzeRes.markdown_content) {
                // 模拟分析进度
                setUploadProgress(70);
                setTimeout(() => setUploadProgress(85), 200);
                setTimeout(() => setUploadProgress(95), 400);
                setTimeout(() => setUploadProgress(100), 600);
                
                setUploadProgressStep('完成');
                setUploadProgressStatus('completed');
                setUploadProgressMessage(`文档处理完成！识别到 ${analyzeRes.stats?.total_modules || 0} 个功能模块`);
                
                setDocAnalysisStatus('processed');
                setAnalyzeResult(analyzeRes);
                versionForm.setFieldsValue({
                  requirement_doc: analyzeRes.markdown_content
                });
                
                // 2秒后关闭进度弹窗
                setTimeout(() => {
                  setUploadProgressModalVisible(false);
                  setUploading(false);
                  message.success(`文档已自动处理：识别到 ${analyzeRes.stats?.total_modules || 0} 个功能模块`);
                }, 2000);
              } else {
                setUploadProgress(100);
                setUploadProgressStep('完成');
                setUploadProgressStatus('completed');
                setUploadProgressMessage('文档处理完成，已使用原始内容');
                
                setDocAnalysisStatus('processed');
                versionForm.setFieldsValue({ requirement_doc: extractedText });
                
                setTimeout(() => {
                  setUploadProgressModalVisible(false);
                  setUploading(false);
                  message.info('文档处理完成，已使用原始内容');
                }, 2000);
              }
            } catch (analyzeError: any) {
              setUploadProgress(100);
              setUploadProgressStep('完成');
              setUploadProgressStatus('completed');
              setUploadProgressMessage('文档处理完成，已使用原始内容');
              
              setDocAnalysisStatus('processed');
              versionForm.setFieldsValue({ requirement_doc: extractedText });
              
              setTimeout(() => {
                setUploadProgressModalVisible(false);
                setUploading(false);
                message.info('文档处理完成，已使用原始内容');
              }, 2000);
            }
          } else if (needsProcess && !autoProcessDoc) {
            // 格式不规范且用户关闭了自动处理 → 显示手动按钮
            setUploadProgress(100);
            setUploadProgressStep('完成');
            setUploadProgressStatus('completed');
            setUploadProgressMessage('文档上传完成，需要手动智能分析');
            
            setDocAnalysisStatus('needs-process');
            versionForm.setFieldsValue({ requirement_doc: extractedText });
            
            setTimeout(() => {
              setUploadProgressModalVisible(false);
              setUploading(false);
              message.info('检测到文档格式不规范，可点击"智能分析"按钮处理');
            }, 2000);
          } else {
            // 格式规范，直接使用
            setUploadProgress(100);
            setUploadProgressStep('完成');
            setUploadProgressStatus('completed');
            setUploadProgressMessage('文档上传完成');
            
            setDocAnalysisStatus('processed');
            versionForm.setFieldsValue({ requirement_doc: extractedText });
            
            setTimeout(() => {
              setUploadProgressModalVisible(false);
              setUploading(false);
              message.info(`已提取文档内容 ${extractedText.length} 字符`);
            }, 1500);
          }
        } else if (['md', 'txt', 'markdown'].includes(result.file_type)) {
          setUploadProgress(100);
          setUploadProgressStep('完成');
          setUploadProgressStatus('completed');
          setUploadProgressMessage('文档上传完成');
          
          versionForm.setFieldsValue({ requirement_doc: '' });
          
          setTimeout(() => {
            setUploadProgressModalVisible(false);
            setUploading(false);
          }, 1500);
        } else {
          setUploadProgress(100);
          setUploadProgressStep('完成');
          setUploadProgressStatus('completed');
          setUploadProgressMessage('文档上传完成，但无法提取文本');
          
          versionForm.setFieldsValue({
            requirement_doc: `[已上传文件：${file.name}，无法提取文本内容]`
          });
          
          setTimeout(() => {
            setUploadProgressModalVisible(false);
            setUploading(false);
            message.warning('文档解析失败，请手动粘贴内容');
          }, 2000);
        }
      }
    } catch (error: any) {
      setUploadProgressStatus('error');
      setUploadProgressMessage('上传失败：' + (error.response?.data?.detail || error.message || '未知错误'));
      
      message.error(error.response?.data?.detail || '文件上传失败');
      setUploadedFile(null);
      setUploadedFileInfo(null);
      setDocAnalysisStatus('none');
      
      setTimeout(() => {
        setUploadProgressModalVisible(false);
        setUploading(false);
      }, 2000);
    }
  };
  
  const checkDocFormat = (text: string): boolean => {
    // 检查文档格式是否规范
    // 规范的文档应包含：Markdown标题、中式编号、数字编号
    // 不规范的文档：纯文本，无任何标题结构
    
    if (!text || text.length < 100) return false;
    
    const lines = text.split('\n');
    
    // 检查是否有Markdown标题
    const hasMdTitle = lines.some(line => 
      line.startsWith('# ') || line.startsWith('## ') || line.startsWith('### ')
    );
    
    // 检查是否有中式编号
    const hasChineseNum = lines.some(line => 
      /^[一二三四五六七八九十]+[、.．]/.test(line.trim())
    );
    
    // 检查是否有数字编号标题
    const hasDigitNum = lines.some(line => 
      /^\d+[、.．\s]/.test(line.trim()) && line.length < 50
    );
    
    // 如果没有任何标题结构，认为不规范
    const isStandard = hasMdTitle || hasChineseNum || hasDigitNum;
    
    // 同时检查是否包含功能相关关键词
    const functionalKeywords = ['功能', '模块', '管理', '系统', '接口', '登录', '注册', '用户'];
    const hasKeywords = functionalKeywords.some(kw => text.includes(kw));
    
    // 如果没有标题结构但有功能关键词，也需要处理
    return !isStandard && hasKeywords;
  };

  const openEditModal = () => {
    if (project) {
      editForm.setFieldsValue({
        name: project.name,
        description: project.description,
        status: project.status,
      });
      setEditModalVisible(true);
    }
  };

  const versionColumns = [
    {
      title: '版本号',
      dataIndex: 'version_number',
      key: 'version_number',
      width: 150,
      render: (text: string, record: Version) => (
        <a onClick={() => navigate(`/projects/${id}/versions/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '版本名称',
      dataIndex: 'version_name',
      key: 'version_name',
      width: 150,
      render: (text: string) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColors[status]}>{statusNames[status] || status}</Tag>
      ),
    },
    {
      title: '需求文档',
      key: 'requirement_doc',
      width: 120,
      render: (_: any, record: Version) => {
        const hasDoc = true;
        return hasDoc ? (
          <Tooltip title="点击查看">
            <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => handleViewRequirement(record)}>
              <FileOutlined /> 已上传
            </Tag>
          </Tooltip>
        ) : (
          <Tag color="default">无</Tag>
        );
      },
    },
    {
      title: '测试用例',
      key: 'test_cases',
      width: 100,
      render: (_: any, record: Version) => record.test_cases_count || 0,
    },
    {
      title: '计划时间',
      key: 'plan_dates',
      width: 200,
      render: (_: any, record: Version) => {
        if (!record.plan_start_date && !record.plan_end_date) return '-';
        return (
          <Space>
            <CalendarOutlined />
            <Text>
              {record.plan_start_date ? new Date(record.plan_start_date).toLocaleDateString() : '-'}
              {' ~ '}
              {record.plan_end_date ? new Date(record.plan_end_date).toLocaleDateString() : '-'}
            </Text>
          </Space>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
      fixed: 'right' as const,
      render: (_: any, record: Version) => (
        <Space>
          <Tooltip title="版本详情">
            <Button
              type="link"
              icon={<InfoCircleOutlined />}
              onClick={() => navigate(`/projects/${id}/versions/${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="需求变更审核">
            <Button
              type="link"
              icon={<AuditOutlined />}
              onClick={() => navigate(`/projects/${id}/versions/${record.id}/change-review`)}
            />
          </Tooltip>
          <Tooltip title="查看需求文档">
            <Button
              type="link"
              icon={<FileOutlined />}
              onClick={() => handleViewRequirement(record)}
              disabled={false}
            />
          </Tooltip>
          <Tooltip title="查看测试用例">
            <Button
              type="link"
              icon={<CheckCircleOutlined />}
              onClick={() => navigate(`/tests/functional?projectId=${id}&versionId=${record.id}&source=change`)}
            />
          </Tooltip>
          <Tooltip title="变更状态">
            <Button
              type="link"
              icon={<SyncOutlined />}
              onClick={() => openStatusModal(record)}
            />
          </Tooltip>
          {record.status === 'planning' && (
            <Popconfirm
              title="确定删除此版本？"
              onConfirm={() => handleDeleteVersion(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" danger icon={<DeleteOutlined />} title="删除版本" />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const currentUser = useSelector(selectUser);
  const isOwner = !!project && !!currentUser && project.owner_id === currentUser.id;

  const tabItems = [
    {
      key: 'versions',
      label: (
        <Space>
          <BranchesOutlined /> 版本列表
          <Tag color="blue">{versions.length}</Tag>
        </Space>
      ),
      children: (
        <Table
          columns={versionColumns}
          dataSource={versions}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1200 }}
        />
      ),
    },
    {
      key: 'members',
      label: (
        <Space>
          <TeamOutlined /> 项目成员
        </Space>
      ),
      children: <ProjectMembers projectId={Number(id)} isOwner={isOwner} />,
    },
    {
      key: 'environments',
      label: (
        <Space>
          <GlobalOutlined /> 环境配置
        </Space>
      ),
      children: <ProjectEnvironments projectId={Number(id)} />,
    },
    {
      key: 'settings',
      label: (
        <Space>
          <SettingOutlined /> 项目设置
        </Space>
      ),
      children: <ProjectSettings projectId={Number(id)} />,
    },
  ];

  const statsPassed = stats?.passed_test_cases || 0;
  const statsTotal = statsPassed + (stats?.failed_test_cases || 0);
  const passRate = statsTotal > 0 ? Math.round((statsPassed / statsTotal) * 1000) / 10 : 0;

  return (
    <div style={{ padding: 6 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>
          返回项目列表
        </Button>
        {/* 知识图谱：项目级资产入口（已完成→查看；生成中→进度弹窗；无/失败→生成弹窗） */}
        <Button
          icon={<BranchesOutlined />}
          loading={kgLoading}
          onClick={handleOpenKnowledgeGraph}
        >
          知识图谱
          {kgStatus && (
            <Tag
              color={
                kgStatus.exploration_status === 'completed' ? 'green' :
                kgStatus.exploration_status === 'running' || kgStatus.exploration_status === 'pending' ? 'blue' :
                kgStatus.exploration_status === 'failed' ? 'red' : 'default'
              }
              style={{ marginInlineStart: 6 }}
            >
              {kgStatus.exploration_status === 'completed'
                ? `已生成 ${kgStatus.page_count} 页`
                : kgStatus.exploration_status === 'running' || kgStatus.exploration_status === 'pending'
                  ? `生成中 ${kgStatus.progress_percentage}%`
                  : kgStatus.exploration_status === 'failed'
                    ? '生成失败'
                    : '未生成'}
            </Tag>
          )}
        </Button>
        <Button type="primary" icon={<EditOutlined />} onClick={openEditModal}>
          编辑项目
        </Button>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={() => {
            // 检查是否有正在运行的任务
            if (pollingTask && currentTaskId) {
              // 有正在运行的任务，显示进度弹窗
              setProgressVisible(true);
              message.info('当前有正在进行的生成任务，请等待完成后再创建新版本');
            } else {
              // 没有正在运行的任务，打开创建版本表单
              setVersionModalVisible(true);
            }
          }}
          disabled={pollingTask}
        >
          {pollingTask ? '生成中...' : '创建版本'}
        </Button>
      </Space>

      {project && (
        <Card style={{ marginBottom: 16 }}>
          <Descriptions column={3}>
            <Descriptions.Item label="项目名称" span={2}>
              <Title level={3} style={{ margin: 0 }}>{project.name}</Title>
            </Descriptions.Item>
            <Descriptions.Item label="项目状态">
              <Tag color={statusColors[project.status] || 'default'}>
                {statusNames[project.status] || project.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="项目编码">{project.code || '-'}</Descriptions.Item>
            <Descriptions.Item label="负责人">{typeof project.owner === 'string' ? project.owner : (project.owner as any)?.username || '-'}</Descriptions.Item>
            <Descriptions.Item label="描述" span={3}>
              {project.description || '-'}
            </Descriptions.Item>
          </Descriptions>

          <Row gutter={16} style={{ marginTop: 24 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="总版本数"
                  value={stats?.total_versions || 0}
                  prefix={<BranchesOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="总用例数"
                  value={stats?.total_test_cases || 0}
                  prefix={<CheckCircleOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="通过率"
                  value={passRate}
                  precision={1}
                  suffix="%"
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
          </Row>
        </Card>
      )}

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          type="card"
          items={tabItems}
        />
      </Card>

      <Modal
        title="编辑项目"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        maskClosable={false}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdateProject}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="status" label="项目状态">
            <Select>
              <Select.Option value="active">进行中</Select.Option>
              <Select.Option value="completed">已完成</Select.Option>
              <Select.Option value="suspended">已暂停</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="创建版本"
        open={versionModalVisible}
        onCancel={() => {
          if (!creating && docAnalysisStatus !== 'analyzing') {
            setVersionModalVisible(false);
            versionForm.resetFields();
            setUploadedFile(null);
            setUploadedFileInfo(null);
            setAnalyzeResult(null);
            setDocAnalysisStatus('none');
            setAutoProcessDoc(true);
          }
        }}
        onOk={() => versionForm.submit()}
        confirmLoading={creating || docAnalysisStatus === 'analyzing'}
        okButtonProps={{ disabled: creating || docAnalysisStatus === 'analyzing', loading: creating || docAnalysisStatus === 'analyzing' }}
        cancelButtonProps={{ disabled: creating || docAnalysisStatus === 'analyzing' }}
        maskClosable={!creating && docAnalysisStatus !== 'analyzing'}
        width={800}
      >
        <Form form={versionForm} layout="vertical" onFinish={handleCreateVersion}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="version_number" label="版本号" rules={[{ required: true }]}>
                <Input placeholder="如：1.0.0" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="version_name" label="版本名称">
                <Input placeholder="如：第一版" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="上传需求文档附件">
            <div style={{ marginBottom: 8 }}>
              <Checkbox 
                checked={autoProcessDoc}
                onChange={(e) => setAutoProcessDoc(e.target.checked)}
                disabled={uploading || docAnalysisStatus === 'analyzing' || creating}
              >
                文档格式不规范时自动智能处理
              </Checkbox>
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                （自动提取功能模块，生成标准格式）
              </Text>
            </div>
            <Upload.Dragger
              name="file"
              multiple={false}
              accept=".docx,.doc,.pdf,.md,.markdown,.txt"
              disabled={uploading || docAnalysisStatus === 'analyzing' || creating}
              beforeUpload={(file) => {
                handleUploadRequirement(file);
                return false;
              }}
              fileList={uploadedFile ? [{
                uid: '-1',
                name: uploadedFile.name,
                status: 'done',
                size: uploadedFile.size,
              }] : []}
              onRemove={() => {
                if (docAnalysisStatus !== 'analyzing' && !creating) {
                  setUploadedFile(null);
                  setUploadedFileInfo(null);
                  setAnalyzeResult(null);
                  setDocAnalysisStatus('none');
                  setAnalyzeModalVisible(false);
                  versionForm.setFieldValue('requirement_doc', '');
                }
              }}
            >
              <p className="ant-upload-text">点击或拖拽文件上传</p>
              <p className="ant-upload-hint">支持 Word、PDF、Markdown、文本格式</p>
            </Upload.Dragger>
            
            {/* 文档分析状态提示 */}
            {docAnalysisStatus === 'processed' && analyzeResult && (
              <Alert 
                type="success" 
                message="文档已自动处理完成" 
                description={`识别到 ${analyzeResult.stats?.total_modules || 0} 个功能模块，${analyzeResult.stats?.total_features || 0} 个功能点`}
                style={{ marginTop: 8 }}
                showIcon
                action={
                  <Button size="small" type="link" onClick={() => setAnalyzeModalVisible(true)}>
                    查看详情
                  </Button>
                }
              />
            )}
            
            {docAnalysisStatus === 'needs-process' && (
              <Alert 
                type="warning" 
                message="检测到文档格式不规范" 
                description="建议点击下方按钮进行智能分析，提取功能模块"
                style={{ marginTop: 8 }}
                showIcon
                action={
                  <Button 
                    size="small" 
                    type="primary" 
                    ghost 
                    onClick={handleAnalyzeDocument} 
                    loading={analyzing}
                    disabled={uploading || creating}
                  >
                    立即处理
                  </Button>
                }
              />
            )}
            
            {/* 手动分析按钮 - 仅在用户关闭自动处理时显示 */}
            {uploadedFileInfo && !autoProcessDoc && docAnalysisStatus === 'needs-process' && (
              <div style={{ marginTop: 8 }}>
                <Button 
                  type="primary" 
                  ghost 
                  icon={<RobotOutlined />}
                  loading={analyzing}
                  onClick={handleAnalyzeDocument}
                  disabled={uploading || creating}
                >
                  智能分析文档
                </Button>
                <Text type="secondary" style={{ marginLeft: 8 }}>使用 AI 自动提取功能模块</Text>
              </div>
            )}
          </Form.Item>
          <Form.Item 
            name="requirement_doc" 
            label="需求文档内容" 
            required
            rules={[
              { required: true, message: '请上传需求文档文件或填写需求文档内容' }
            ]}
          >
            <TextArea 
              rows={12} 
              placeholder="上传文件后点击「智能分析」自动生成，或直接粘贴文本内容" 
              disabled={docAnalysisStatus === 'analyzing' || creating}
            />
          </Form.Item>
          <Form.Item name="description" label="版本描述">
            <TextArea rows={3} disabled={docAnalysisStatus === 'analyzing' || creating} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="plan_start_date" label="计划开始日期">
                <DatePicker style={{ width: '100%' }} disabled={docAnalysisStatus === 'analyzing' || creating} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="plan_end_date" label="计划结束日期">
                <DatePicker style={{ width: '100%' }} disabled={docAnalysisStatus === 'analyzing' || creating} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="变更版本状态"
        open={statusModalVisible}
        onCancel={() => {
          setStatusModalVisible(false);
          setSelectedVersion(null);
        }}
        onOk={handleStatusChange}
        maskClosable={false}
      >
        {selectedVersion && (
          <>
            <p>当前版本：<strong>{selectedVersion.version_number}</strong></p>
            <p>当前状态：<Tag color={statusColors[selectedVersion.status]}>{statusNames[selectedVersion.status]}</Tag></p>
            <Form.Item label="目标状态">
              <Select value={targetStatus} onChange={setTargetStatus}>
                {selectedVersion.status === 'planning' && <Select.Option value="developing">开发中</Select.Option>}
                {selectedVersion.status === 'developing' && (
                  <>
                    <Select.Option value="testing">测试中</Select.Option>
                    <Select.Option value="planning">规划中</Select.Option>
                  </>
                )}
                {selectedVersion.status === 'testing' && (
                  <>
                    <Select.Option value="frozen">已冻结</Select.Option>
                    <Select.Option value="developing">开发中</Select.Option>
                  </>
                )}
                {selectedVersion.status === 'frozen' && (
                  <>
                    <Select.Option value="released">已发布</Select.Option>
                    <Select.Option value="testing">测试中</Select.Option>
                  </>
                )}
                {selectedVersion.status === 'released' && <Select.Option value="archived">已归档</Select.Option>}
              </Select>
            </Form.Item>
            <Form.Item label="备注">
              <Input.TextArea value={statusComment} onChange={(e) => setStatusComment(e.target.value)} rows={2} />
            </Form.Item>
          </>
        )}
      </Modal>

      <Modal
        title={<Space><FileOutlined /><span>需求文档 - {selectedVersionForDoc?.version_number}</span></Space>}
        open={requirementModalVisible}
        onCancel={() => {
          setRequirementModalVisible(false);
          setSelectedRequirement(null);
          setSelectedVersionForDoc(null);
          setDocFileType('text');
          setDocFilePath(null);
        }}
        footer={[
          docFilePath && <Button key="download" icon={<DownloadOutlined />} onClick={() => {
            const url = fileApi.getDownloadUrl(docFilePath);
            window.open(url, '_blank');
          }}>下载原始文件</Button>,
          <Button key="close" onClick={() => {
            setRequirementModalVisible(false);
            setSelectedRequirement(null);
            setSelectedVersionForDoc(null);
            setDocFileType('text');
            setDocFilePath(null);
          }}>关闭</Button>
        ]}
        width={1000}
        maskClosable={false}
      >
        <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
          {docFileType === 'pdf' && docFilePath ? (
            <iframe 
              src={fileApi.getPreviewUrl(docFilePath)} 
              style={{ width: '100%', height: '50vh', border: 'none' }}
              title="PDF预览"
            />
          ) : (docFileType === 'docx' || docFileType === 'doc') && !selectedRequirement ? (
            <div style={{ textAlign: 'center', padding: '40px' }}>
              <p style={{ fontSize: '16px', marginBottom: '20px' }}>Word 文档预览</p>
              <Button type="primary" icon={<EyeOutlined />} onClick={() => {
                if (docFilePath) {
                  const url = fileApi.getPreviewUrl(docFilePath);
                  window.open(url, '_blank');
                }
              }}>
                打开文档查看
              </Button>
              <Button style={{ marginLeft: '10px' }} icon={<DownloadOutlined />} onClick={() => {
                if (docFilePath) {
                  const url = fileApi.getDownloadUrl(docFilePath);
                  window.open(url, '_blank');
                }
              }}>
                下载原始文档
              </Button>
            </div>
          ) : selectedRequirement ? (
            <div style={{ padding: '16px' }}>
              {docFileType === 'markdown' ? (
                <div style={{ 
                  whiteSpace: 'pre-wrap', 
                  wordWrap: 'break-word', 
                  fontFamily: 'monospace', 
                  fontSize: '14px', 
                  lineHeight: '1.8',
                  backgroundColor: '#f5f5f5', 
                  borderRadius: '4px',
                  padding: '16px'
                }}>
                  {selectedRequirement}
                </div>
              ) : (
                <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word', fontFamily: 'monospace', fontSize: '14px', lineHeight: '1.6', padding: '16px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                  {selectedRequirement}
                </pre>
              )}
            </div>
          ) : (
            <Empty description="暂无需求文档" />
          )}
        </div>
      </Modal>

      <Modal
        open={progressVisible}
        footer={null}
        closable={false}
        maskClosable={false}
        destroyOnClose={true}
        width={750}
        centered
        styles={{ body: { padding: 0 } }}
      >
        <div style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', padding: '20px', borderRadius: '12px 12px 0 0', color: '#fff' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ fontSize: '28px' }}>{creating || pollingTask ? '🚀' : '✅'}</div>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                  {creating || pollingTask ? '正在创建版本' : '创建完成'}
                  {taskDisplayId && <span style={{ fontSize: '12px', marginLeft: '8px', opacity: 0.8 }}>#{taskDisplayId}</span>}
                </div>
                <div style={{ fontSize: '12px', opacity: 0.9 }}>{pollingTask ? 'AI 正在生成测试用例' : creating ? '正在保存版本数据' : '所有资产已准备就绪'}</div>
              </div>
            </div>
{(creating || pollingTask) && (
              <Button 
                type="text" 
                size="small"
                danger
                style={{ color: '#fff', opacity: 0.8 }}
                onClick={handleCancelTask}
              >
                取消任务
              </Button>
            )}
          </div>
          {taskProgress > 0 && (
            <div style={{ marginTop: '16px' }}>
              <Progress 
                percent={taskProgress} 
                status={pollingTask ? 'active' : 'success'}
                strokeColor={{ from: '#00d4ff', to: '#00ff88' }}
                trailColor='rgba(255,255,255,0.2)'
                style={{ marginBottom: '8px' }}
              />
              <div style={{ fontSize: '12px', opacity: 0.9 }}>生成进度: {taskProgress}%</div>
            </div>
          )}
        </div>
        
        <div style={{ padding: '20px', maxHeight: '450px', overflowY: 'auto', backgroundColor: '#f5f7fa' }}>
          <div style={{ backgroundColor: '#fff', borderRadius: '8px', padding: '16px', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', color: '#999', fontSize: '12px' }}><span>📝 执行详情</span></div>
            {progressLogs.map((log, i) => (
              <div key={i} style={{ 
                padding: '8px 12px', 
                marginBottom: '4px',
                borderRadius: '6px',
                fontSize: '13px',
                backgroundColor: log.msg.includes('✅') || log.msg.includes('🎉') ? '#f6ffed' : 
                               log.msg.includes('❌') ? '#fff1f0' : '#f5f5f5',
                color: log.msg.includes('❌') ? '#ff4d4f' : 
                       log.msg.includes('✅') || log.msg.includes('🎉') ? '#52c41a' : '#333',
                transition: 'all 0.3s',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span style={{ flex: 1 }}>{log.msg}</span>
                <span style={{ fontSize: '11px', color: '#999', marginLeft: '16px' }}>{log.time}</span>
              </div>
            ))}
            <div ref={(el) => el?.scrollIntoView({ behavior: 'smooth' })} />
          </div>
        </div>
        
        {(creating || pollingTask) && (
          <div style={{ padding: '16px', textAlign: 'center', borderTop: '1px solid #e8e8e8', backgroundColor: '#fff', color: '#667eea', fontSize: '13px' }}>
            <Spin size="small" style={{ marginRight: '8px' }} />
            ⏱️ AI 正在生成测试用例，请耐心等待完成...
          </div>
        )}
      </Modal>

      <Modal
        title="🎉 版本创建成功"
        open={successModalVisible}
        onCancel={() => {
          setSuccessModalVisible(false);
          setVersionModalVisible(false);
          setUploadedFile(null);
          setUploadedFileInfo(null);
          versionForm.resetFields();
          fetchVersions();
        }}
        maskClosable={false}
        onOk={() => {
          setSuccessModalVisible(false);
          setVersionModalVisible(false);
          setUploadedFile(null);
          setUploadedFileInfo(null);
          versionForm.resetFields();
          fetchVersions();
          navigate('/tests/functional');
        }}
        okText="查看测试用例"
        cancelText="关闭"
        width={400}
        centered
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <p style={{ fontSize: '16px', marginBottom: '12px' }}>
            已生成 <strong style={{ color: '#1890ff', fontSize: '20px' }}>{successData.testCases}</strong> 个测试用例
          </p>
          {successData.durationSeconds > 0 && (
            <p style={{ fontSize: '16px', marginBottom: '12px', color: '#666' }}>
              总耗时：<strong style={{ fontSize: '18px' }}>
                {successData.durationSeconds >= 60 
                  ? `${Math.floor(successData.durationSeconds / 60)}分${Math.floor(successData.durationSeconds % 60)}秒`
                  : `${Math.floor(successData.durationSeconds)}秒`}
              </strong>
            </p>
          )}
        </div>
      </Modal>
      
      {/* 文档上传和处理进度弹窗 */}
      <Modal
        open={uploadProgressModalVisible}
        footer={null}
        closable={false}
        maskClosable={false}
        width={500}
        centered
        styles={{ body: { padding: '32px 24px' } }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>
            {uploadProgressStatus === 'completed' ? '✅' : 
             uploadProgressStatus === 'error' ? '❌' : '📤'}
          </div>
          
          <Title level={4} style={{ marginBottom: '8px' }}>
            {uploadProgressStep}
          </Title>
          
          <Text type="secondary" style={{ fontSize: '14px', marginBottom: '24px', display: 'block' }}>
            {uploadProgressMessage}
          </Text>
          
          <Progress 
            percent={uploadProgress}
            status={uploadProgressStatus === 'error' ? 'exception' :
                    uploadProgressStatus === 'completed' ? 'success' : 'active'}
            strokeColor={{
              '0%': uploadProgressStatus === 'error' ? '#ff4d4f' : '#108ee9',
              '100%': uploadProgressStatus === 'error' ? '#ff4d4f' : 
                      uploadProgressStatus === 'completed' ? '#52c41a' : '#87d068',
            }}
            style={{ marginBottom: '16px' }}
          />
          
          {uploadProgressStatus !== 'completed' && uploadProgressStatus !== 'error' && (
            <div style={{ marginTop: '16px', color: '#666', fontSize: '12px' }}>
              <Spin size="small" style={{ marginRight: '8px' }} />
              请稍候，正在处理文档...
            </div>
          )}
          
          {uploadProgressStatus === 'error' && (
            <Button 
              type="primary" 
              onClick={() => setUploadProgressModalVisible(false)}
              style={{ marginTop: '16px' }}
            >
              关闭
            </Button>
          )}
        </div>
      </Modal>

      <Modal
        title="智能文档分析结果"
        open={analyzeModalVisible}
        onCancel={() => setAnalyzeModalVisible(false)}
        onOk={handleUseAnalyzeResult}
        okText="使用此结果"
        cancelText="取消"
        width={700}
        maskClosable={false}
        centered
      >
        {analyzeResult && (
          <div>
            <Descriptions column={4} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="文档标题">{analyzeResult.document_title}</Descriptions.Item>
              <Descriptions.Item label="模块总数">{analyzeResult.stats?.total_modules}</Descriptions.Item>
              <Descriptions.Item label="P0模块">{analyzeResult.stats?.p0_count}</Descriptions.Item>
              <Descriptions.Item label="功能点">{analyzeResult.stats?.total_features}</Descriptions.Item>
            </Descriptions>
            
            <div style={{ marginBottom: 16 }}>
              <Text strong>功能模块列表：</Text>
              <div style={{ marginTop: 8 }}>
                {analyzeResult.modules?.map((module: any, index: number) => (
                  <Card key={index} size="small" style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text strong>{module.name}</Text>
                      <Tag color={module.priority === 'P0' ? 'red' : module.priority === 'P1' ? 'orange' : 'blue'}>
                        {module.priority}
                      </Tag>
                    </div>
                    <Text type="secondary">{module.description}</Text>
                    <div style={{ marginTop: 8 }}>
                      {module.features?.map((feature: any, fIndex: number) => (
                        <div key={fIndex} style={{ marginBottom: 4, padding: 4, background: '#f5f5f5', borderRadius: 4 }}>
                          {typeof feature === 'string' ? (
                            <Tag>{feature}</Tag>
                          ) : (
                            <div>
                              <Text strong style={{ fontSize: 12 }}>{feature.name}</Text>
                              <div style={{ fontSize: 11, color: '#666' }}>
                                {feature.inputs && <span>输入: {feature.inputs.join(', ')} | </span>}
                                {feature.outputs && <span>输出: {feature.outputs.join(', ')} | </span>}
                                {feature.rules && <span>规则: {feature.rules.length}条 | </span>}
                                {feature.edge_cases && <span>边界: {feature.edge_cases.length}条</span>}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
            
            <div>
              <Text strong>生成的标准格式：</Text>
              <pre style={{ 
                marginTop: 8, 
                padding: 12, 
                backgroundColor: '#f5f5f5', 
                borderRadius: 4,
                maxHeight: 200,
                overflow: 'auto',
                fontSize: 12
              }}>
                {analyzeResult.markdown_content?.slice(0, 2000)}
                {analyzeResult.markdown_content?.length > 2000 && '...'}
              </pre>
            </div>
          </div>
        )}
      </Modal>

      {/* 知识图谱生成配置弹窗（versionId 取当前最新版本，无版本传 undefined——
          后端 Optional 语义；不得传 0，MySQL FK 无 id=0 行会 IntegrityError） */}
      <GenerateKnowledgeGraphModal
        visible={knowledgeGraphModalVisible}
        projectId={Number(id)}
        versionId={versions?.[0]?.id ?? undefined}
        onCancel={() => setKnowledgeGraphModalVisible(false)}
        onGenerate={handleKnowledgeGraphGenerate}
      />

      {/* 知识图谱生成进度弹窗 */}
      <KnowledgeGraphProgressModal
        visible={knowledgeGraphProgressVisible}
        graphId={knowledgeGraphId}
        generateRequest={knowledgeGraphRequest}
        onCancel={() => setKnowledgeGraphProgressVisible(false)}
        onViewGraph={handleViewKnowledgeGraph}
        onProgressUpdate={handleKgProgressUpdate}
      />
    </div>
  );
};


export default ProjectDetailPage;