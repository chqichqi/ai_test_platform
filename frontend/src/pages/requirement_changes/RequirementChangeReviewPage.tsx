import React, { useState, useEffect } from 'react';
import {
  Card, Descriptions, Tag, Button, Space, Table, Modal, Form, Input,
  message, Row, Col, Statistic, Typography, Select,
  Upload, Empty, Spin, Progress, Alert, Divider, Checkbox
} from 'antd';
import {
  ArrowLeftOutlined, CheckOutlined, SyncOutlined,
  UploadOutlined, PlusOutlined, DeleteOutlined,
  CheckCircleOutlined, ReloadOutlined
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { versionApi, fileApi } from '../../api/projectApi';
import {
  requirementChangeApi,
  RequirementChangeRecord,
  ModuleChangeAnalysis,
  ChangeSummary,
  AffectedTestCase
} from '../../api/requirementChangeApi';
import type { Version } from '../../api/projectApi';

const { Title, Text } = Typography;
const { TextArea } = Input;

const RequirementChangeReviewPage: React.FC = () => {
  const { versionId } = useParams<{ versionId: string; projectId: string }>();
  const navigate = useNavigate();

  const [version, setVersion] = useState<Version | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const [supplementModalVisible, setSupplementModalVisible] = useState(false);
  const [supplementForm] = Form.useForm();
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [, setOcrResults] = useState<{filename: string; text: string}[]>([]);
  const [docProcessing, setDocProcessing] = useState(false);
  const [docProcessStatus, setDocProcessStatus] = useState<'none' | 'uploading' | 'extracting' | 'analyzing' | 'done' | 'error'>('none');
  const [autoProcessDoc, setAutoProcessDoc] = useState(true);
  const [needsManualProcess, setNeedsManualProcess] = useState(false);
  const [docAnalyzeResult, setDocAnalyzeResult] = useState<any>(null);
  
  const [changeRecords, setChangeRecords] = useState<RequirementChangeRecord[]>([]);
  const [changeSummary, setChangeSummary] = useState<ChangeSummary | null>(null);
  const [, setDetailAnalysis] = useState<ModuleChangeAnalysis[]>([]);
  const [, setBatchId] = useState<number | null>(null);
  const [recordStatusFilter, setRecordStatusFilter] = useState<string>('all');
  
  const [affectedCasesModalVisible, setAffectedCasesModalVisible] = useState(false);
  const [affectedCases, setAffectedCases] = useState<AffectedTestCase[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<RequirementChangeRecord | null>(null);
  
  const [approveModalVisible, setApproveModalVisible] = useState(false);
  const [approveForm] = Form.useForm();
  const [processing, setProcessing] = useState(false);
  
  const [batchApproveConfirmVisible, setBatchApproveConfirmVisible] = useState(false);
  const [batchApproveProgressVisible, setBatchApproveProgressVisible] = useState(false);
  const [batchApproveProgress, setBatchApproveProgress] = useState(0);
  const [batchApproveLogs, setBatchApproveLogs] = useState<{msg: string, time: string}[]>([]);
  const [batchApproveResult, setBatchApproveResult] = useState<{success: boolean; message: string; data: any} | null>(null);
  const [batchApproveSuccessVisible, setBatchApproveSuccessVisible] = useState(false);

  useEffect(() => {
    if (versionId) {
      fetchVersion();
      fetchChangeRecords('all');
    }
  }, [versionId]);

  const fetchVersion = async () => {
    try {
      const data = await versionApi.get(Number(versionId));
      setVersion(data);
    } catch (error) {
      message.error('获取版本详情失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchChangeRecords = async (status?: string) => {
    console.log('fetchChangeRecords called, versionId:', versionId);
    try {
      const filterStatus = status || recordStatusFilter;
      const params: any = {
        version_id: Number(versionId),
        page: 1,
        page_size: 100
      };
      if (filterStatus !== 'all') {
        params.status = filterStatus;
      }
      const data = await requirementChangeApi.listChangeRecords(params);
      console.log('fetchChangeRecords result:', data);
      setChangeRecords(data.items || []);
    } catch (error) {
      console.error('获取变更记录失败', error);
      message.error('获取变更记录失败');
    }
  };

  const checkDocFormat = (text: string): boolean => {
    if (!text || text.length < 100) return false;
    
    const lines = text.split('\n');
    
    const hasMdTitle = lines.some(line => 
      line.startsWith('# ') || line.startsWith('## ') || line.startsWith('### ')
    );
    
    const hasChineseNum = lines.some(line => 
      /^[一二三四五六七八九十]+[、.．]/.test(line.trim())
    );
    
    const hasDigitNum = lines.some(line => 
      /^\d+[、.．\s]/.test(line.trim()) && line.length < 50
    );
    
    const isStandard = hasMdTitle || hasChineseNum || hasDigitNum;
    
    const functionalKeywords = ['功能', '模块', '管理', '系统', '接口', '登录', '注册', '用户', '需求', '测试'];
    const hasKeywords = functionalKeywords.some(kw => text.includes(kw));
    
    return !isStandard && hasKeywords;
  };

  const processSupplementDocument = async (file: File) => {
    setDocProcessing(true);
    setDocProcessStatus('uploading');
    setNeedsManualProcess(false);
    setDocAnalyzeResult(null);
    
    try {
      setDocProcessStatus('extracting');
      const result = await fileApi.upload(file);
      
      if (result.success && result.extracted_text && result.extracted_text.length > 0) {
        const extractedText = result.extracted_text;
        const needsProcess = checkDocFormat(extractedText);
        
        if (needsProcess && autoProcessDoc) {
          setDocProcessStatus('analyzing');
          
          try {
            const analyzeRes = await fileApi.analyze({
              content: extractedText,
              document_type: result.file_type
            });
            
            if (analyzeRes.success && analyzeRes.markdown_content) {
              setDocProcessStatus('done');
              setDocAnalyzeResult(analyzeRes);
              supplementForm.setFieldsValue({
                supplement_content: analyzeRes.markdown_content
              });
              message.success(`文档已智能处理：识别到 ${analyzeRes.stats?.total_modules || 0} 个功能模块`);
            } else {
              setDocProcessStatus('done');
              supplementForm.setFieldsValue({ supplement_content: extractedText });
              message.info('文档处理完成，已使用原始内容');
            }
          } catch (analyzeError: any) {
            setDocProcessStatus('done');
            supplementForm.setFieldsValue({ supplement_content: extractedText });
            message.info('智能处理失败，已使用原始内容');
          }
        } else if (needsProcess && !autoProcessDoc) {
          setDocProcessStatus('done');
          setNeedsManualProcess(true);
          supplementForm.setFieldsValue({ supplement_content: extractedText });
          message.info('检测到文档格式不规范，可点击"智能处理"按钮优化');
        } else {
          setDocProcessStatus('done');
          supplementForm.setFieldsValue({ supplement_content: extractedText });
          message.success(`已提取文档内容 ${extractedText.length} 字符`);
        }
      } else if (['md', 'txt', 'markdown'].includes(result.file_type || '')) {
        setDocProcessStatus('done');
        supplementForm.setFieldsValue({ supplement_content: '' });
      } else {
        setDocProcessStatus('error');
        supplementForm.setFieldsValue({
          supplement_content: `[已上传文件：${file.name}，无法提取文本内容，请手动粘贴]`
        });
        message.warning('文档解析失败，请手动粘贴内容');
      }
    } catch (error: any) {
      setDocProcessStatus('error');
      message.error(error.response?.data?.detail || '文档处理失败');
    } finally {
      setDocProcessing(false);
    }
  };

  const handleManualAnalyze = async () => {
    const currentContent = supplementForm.getFieldValue('supplement_content');
    if (!currentContent || currentContent.length < 100) {
      message.warning('文档内容不足，无法处理');
      return;
    }
    
    setDocProcessing(true);
    setDocProcessStatus('analyzing');
    
    try {
      const analyzeRes = await fileApi.analyze({
        content: currentContent,
        document_type: 'txt'
      });
      
      if (analyzeRes.success && analyzeRes.markdown_content) {
        setDocProcessStatus('done');
        setDocAnalyzeResult(analyzeRes);
        setNeedsManualProcess(false);
        supplementForm.setFieldsValue({
          supplement_content: analyzeRes.markdown_content
        });
        message.success(`文档已智能处理：识别到 ${analyzeRes.stats?.total_modules || 0} 个功能模块`);
      } else {
        message.error('智能处理失败');
        setDocProcessStatus('done');
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '智能处理失败');
      setDocProcessStatus('done');
    } finally {
      setDocProcessing(false);
    }
  };

  const handleUploadSupplement = async (values: { supplement_content: string }) => {
    if (uploadedFiles.length === 0 && !values.supplement_content) {
      message.error('请上传文件或填写补充需求内容');
      return;
    }

    setUploading(true);
    try {
      const result = await requirementChangeApi.uploadSupplementWithImages(
        Number(versionId),
        uploadedFiles,
        values.supplement_content
      );

      if (result.success) {
        message.success(`补充需求上传成功，变更分析完成。OCR处理了 ${result.ocr_processed || 0} 张图片`);
        setSupplementModalVisible(false);
        supplementForm.resetFields();
        setUploadedFiles([]);
        setOcrResults([]);
        
        if (result.data) {
          setChangeSummary(result.data.change_summary);
          setDetailAnalysis(result.data.detail_analysis);
          setBatchId(result.data.batch_id);
          setChangeRecords(result.data.change_records as RequirementChangeRecord[]);
        }
        
        fetchChangeRecords();
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleViewAffectedCases = async (record: RequirementChangeRecord) => {
    setSelectedRecord(record);
    setAffectedCasesModalVisible(true);
    
    try {
      const result = await requirementChangeApi.getAffectedTestCases(record.id);
      setAffectedCases(result.test_cases);
    } catch (error) {
      message.error('获取受影响测试用例失败');
      setAffectedCases([]);
    }
  };

  const handleApproveChange = async (values: { action: string; comment: string }) => {
    if (!selectedRecord) return;

    setProcessing(true);
    try {
      const result = await requirementChangeApi.approveChangeRecord(
        selectedRecord.id,
        values.action,
        values.comment
      );

      if (result.success) {
        const data = result.data || {};
        const parts = ['变更处理完成'];
        if (data.generated_cases_count) parts.push(`生成 ${data.generated_cases_count} 个用例`);
        if (data.derived_count) parts.push(`派生 ${data.derived_count} 个修订（旧版归档待审核）`);
        if (data.ui_soft_deleted) parts.push(`下架 ${data.ui_soft_deleted} 条旧UI用例`);
        if (data.affected_ui_removed) parts.push(`移除 ${data.affected_ui_removed} 条UI用例`);
        if (data.affected_scene_removed) parts.push(`移除 ${data.affected_scene_removed} 条场景用例`);
        message.success(parts.join('，'));
        setApproveModalVisible(false);
        approveForm.resetFields();
        fetchChangeRecords();
      } else {
        message.error(result.message || '处理失败');
        // 后端已部分落库（如用例已生成但级联失败），刷新恢复真实状态
        fetchChangeRecords();
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '处理失败');
      fetchChangeRecords();
    } finally {
      setProcessing(false);
    }
  };

  const handleRejectChange = async (record: RequirementChangeRecord) => {
    Modal.confirm({
      title: '拒绝变更',
      content: (
        <Form>
          <Form.Item label="拒绝原因">
            <TextArea id="reject_reason" rows={3} placeholder="请输入拒绝原因" />
          </Form.Item>
        </Form>
      ),
      onOk: async () => {
        const reasonInput = document.getElementById('reject_reason') as HTMLTextAreaElement;
        const reason = reasonInput?.value || '无原因';
        
        try {
          await requirementChangeApi.rejectChangeRecord(record.id, reason);
          message.success('变更已拒绝');
          fetchChangeRecords();
        } catch (error: any) {
          message.error(error.response?.data?.detail || '拒绝失败');
        }
      }
    });
  };

  const handleBatchApprove = async () => {
    setBatchApproveConfirmVisible(true);
  };

  const handleBatchApproveConfirm = async () => {
    setBatchApproveConfirmVisible(false);
    setBatchApproveProgressVisible(true);
    setBatchApproveProgress(0);
    setBatchApproveLogs([]);
    setBatchApproveResult(null);

    const addLog = (msg: string) => {
      setBatchApproveLogs((prev) => [...prev, { msg, time: new Date().toLocaleTimeString() }]);
    };

    try {
      addLog('🚀 开始批量批准变更...');
      addLog(`📊 共有 ${changeRecords.length} 条待审核变更`);
      setBatchApproveProgress(10);

      addLog('⏳ 正在调用AI处理...');
      setBatchApproveProgress(30);

      const result = await requirementChangeApi.batchApproveChanges(Number(versionId), true);
      
      setBatchApproveProgress(80);
      addLog('✅ 处理完成');
      
      if (result.success) {
        const data = result.data || {};
        addLog(`📊 处理统计：共${data.total || 0}条，处理${data.processed || 0}条，失败${data.failed || 0}条`);
        addLog(`📝 生成测试用例：${data.generated_cases_count || 0}个`);
        setBatchApproveProgress(100);
        setBatchApproveResult(result);
        
        setTimeout(() => {
          setBatchApproveProgressVisible(false);
          setBatchApproveSuccessVisible(true);
          fetchChangeRecords();
        }, 1000);
      } else {
        addLog('❌ 处理失败：' + (result.message || '未知错误'));
        setBatchApproveResult(result);
        setTimeout(() => {
          setBatchApproveProgressVisible(false);
          message.error(result.message || '批量批准失败');
        }, 1500);
      }
    } catch (error: any) {
      addLog('❌ 请求失败：' + (error.response?.data?.detail || error.message || '网络错误'));
      setBatchApproveProgress(100);
      setBatchApproveResult({ success: false, message: error.response?.data?.detail || error.message || '批量批准失败', data: null });
      setTimeout(() => {
        setBatchApproveProgressVisible(false);
        message.error(error.response?.data?.detail || '批量批准失败');
      }, 1500);
    }
  };

  const getChangeTypeTag = (changeType: string) => {
    const config: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
      added: { color: 'green', text: '新增', icon: <PlusOutlined /> },
      modified: { color: 'orange', text: '修改', icon: <SyncOutlined /> },
      deleted: { color: 'red', text: '删除', icon: <DeleteOutlined /> },
      unchanged: { color: 'default', text: '无变化', icon: <CheckOutlined /> }
    };
    
    const item = config[changeType] || config.unchanged;
    return <Tag color={item.color} icon={item.icon}>{item.text}</Tag>;
  };

  const getImpactLevelTag = (impactLevel: string) => {
    const config: Record<string, { color: string; text: string }> = {
      high: { color: 'red', text: '高影响' },
      medium: { color: 'orange', text: '中影响' },
      low: { color: 'blue', text: '低影响' }
    };
    
    const item = config[impactLevel] || config.medium;
    return <Tag color={item.color}>{item.text}</Tag>;
  };

  const getActionText = (action: string) => {
    const config: Record<string, string> = {
      generate_new: '生成新用例',
      update_existing: '变更即派生',
      deprecate: '废弃旧用例',
      archive: '归档旧用例'
    };
    return config[action] || action;
  };

  const openApproveModal = (record: RequirementChangeRecord) => {
    setSelectedRecord(record);
    approveForm.setFieldsValue({
      action: record.suggested_action,
      comment: ''
    });
    setApproveModalVisible(true);
  };

  const recordColumns = [
    {
      title: '模块名称',
      dataIndex: 'module_name',
      key: 'module_name',
      width: 150
    },
    {
      title: '变更类型',
      dataIndex: 'change_type',
      key: 'change_type',
      width: 100,
      render: (type: string) => getChangeTypeTag(type)
    },
    {
      title: '影响级别',
      dataIndex: 'impact_level',
      key: 'impact_level',
      width: 100,
      render: (level: string) => getImpactLevelTag(level)
    },
    {
      title: '受影响用例',
      dataIndex: 'affected_test_cases_count',
      key: 'affected_test_cases_count',
      width: 100,
      render: (count: number, record: RequirementChangeRecord) => (
        count > 0 ? (
          <Button type="link" onClick={() => handleViewAffectedCases(record)}>
            {count} 个用例
          </Button>
        ) : (
          <Text type="secondary">0</Text>
        )
      )
    },
    {
      title: '建议动作',
      dataIndex: 'suggested_action',
      key: 'suggested_action',
      width: 120,
      render: (action: string) => <Text>{getActionText(action)}</Text>
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const config: Record<string, { color: string; text: string }> = {
          pending: { color: 'blue', text: '待审核' },
          approved: { color: 'green', text: '已批准' },
          rejected: { color: 'red', text: '已拒绝' },
          processing: { color: 'orange', text: '处理中' },
          completed: { color: 'green', text: '已完成' },
          failed: { color: 'red', text: '失败' }
        };
        const item = config[status] || config.pending;
        return <Tag color={item.color}>{item.text}</Tag>;
      }
    },
    {
      title: '新用例数',
      dataIndex: 'new_test_cases_count',
      key: 'new_test_cases_count',
      width: 80,
      render: (count: number) => count > 0 ? <Tag color="green">{count}</Tag> : '-'
    },
    {
      title: '审核时间',
      dataIndex: 'reviewed_at',
      key: 'reviewed_at',
      width: 120,
      render: (time: string) => time ? new Date(time).toLocaleString() : '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right' as const,
      render: (_: any, record: RequirementChangeRecord) => (
        record.status === 'pending' ? (
          <Space>
            <Button type="primary" size="small" onClick={() => openApproveModal(record)}>
              批准
            </Button>
            <Button danger size="small" onClick={() => handleRejectChange(record)}>
              拒绝
            </Button>
          </Space>
        ) : (
          <Space>
            <Button type="link" size="small" onClick={() => handleViewAffectedCases(record)}>
              查看详情
            </Button>
          </Space>
        )
      )
    }
  ];

  if (loading || !version) {
    return (
      <div style={{ padding: 6, textAlign: 'center' }}>
        {loading ? (
          <Spin size="large" tip="加载中..." />
        ) : (
          <Empty description="版本信息加载失败">
            <Button type="primary" onClick={() => { setLoading(true); fetchVersion(); }}>
              重试
            </Button>
          </Empty>
        )}
      </div>
    );
  }

  return (
    <div style={{ padding: 6 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          返回
        </Button>
        <Button 
          type="primary" 
          icon={<UploadOutlined />} 
          onClick={() => setSupplementModalVisible(true)}
        >
          上传补充需求
        </Button>
        {changeRecords.filter(r => r.status === 'pending').length > 0 && (
          <Button 
            type="primary" 
            icon={<CheckCircleOutlined />} 
            onClick={handleBatchApprove}
            loading={batchApproveProgressVisible}
          >
            一键批准所有
          </Button>
        )}
      </Space>

      <Title level={3}>
        需求变更审核 - {version.version_number}
      </Title>
      <Tag color={version.status === 'planning' ? 'blue' : 'orange'}>
        {version.status}
      </Tag>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={4}>
          <Descriptions.Item label="版本号">{version.version_number}</Descriptions.Item>
          <Descriptions.Item label="版本名称">{version.version_name || '-'}</Descriptions.Item>
          <Descriptions.Item label="测试用例数">
            <Tag color="blue">{version.test_cases_count || 0}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="变更记录">
            <Space>
              <Tag color="orange">{changeRecords.filter(r => r.status === 'pending').length} 待审核</Tag>
              <Tag color="green">{changeRecords.filter(r => r.status === 'completed').length} 已完成</Tag>
              <Tag color="blue">{changeRecords.length} 总计</Tag>
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {changeSummary && (
        <Card style={{ marginBottom: 16 }} title="变更摘要">
          <Row gutter={16}>
            <Col span={6}>
              <Statistic
                title="新增功能"
                value={changeSummary.added_count}
                prefix={<PlusOutlined style={{ color: '#52c41a' }} />}
                valueStyle={{ color: '#52c41a' }}
              />
              {(changeSummary.added_modules?.length ?? 0) > 0 && (
                <div style={{ marginTop: 8 }}>
                  {(changeSummary.added_modules ?? []).map(m => (
                    <Tag key={m} color="green">{m}</Tag>
                  ))}
                </div>
              )}
            </Col>
            <Col span={6}>
              <Statistic
                title="修改功能"
                value={changeSummary.modified_count}
                prefix={<SyncOutlined style={{ color: '#faad14' }} />}
                valueStyle={{ color: '#faad14' }}
              />
              {(changeSummary.modified_modules?.length ?? 0) > 0 && (
                <div style={{ marginTop: 8 }}>
                  {(changeSummary.modified_modules ?? []).map(m => (
                    <Tag key={m} color="orange">{m}</Tag>
                  ))}
                </div>
              )}
            </Col>
            <Col span={6}>
              <Statistic
                title="删除功能"
                value={changeSummary.deleted_count}
                prefix={<DeleteOutlined style={{ color: '#ff4d4f' }} />}
                valueStyle={{ color: '#ff4d4f' }}
              />
              {((changeSummary.removed_modules ?? changeSummary.deleted_modules)?.length ?? 0) > 0 && (
                <div style={{ marginTop: 8 }}>
                  {(changeSummary.removed_modules ?? changeSummary.deleted_modules ?? []).map(m => (
                    <Tag key={m} color="red">{m}</Tag>
                  ))}
                </div>
              )}
            </Col>
            <Col span={6}>
              <Statistic
                title="无变化"
                value={changeSummary.unchanged_count}
                prefix={<CheckOutlined style={{ color: '#1890ff' }} />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Col>
          </Row>
        </Card>
      )}

      <Card 
        title="变更记录列表"
        extra={
          <Space>
            <Text>状态筛选：</Text>
            <Select
              value={recordStatusFilter}
              onChange={(value) => {
                setRecordStatusFilter(value);
                fetchChangeRecords(value);
              }}
              style={{ width: 150 }}
              options={[
                { value: 'all', label: '全部记录' },
                { value: 'pending', label: '待审核' },
                { value: 'approved', label: '已批准' },
                { value: 'completed', label: '已完成' },
                { value: 'rejected', label: '已拒绝' },
                { value: 'failed', label: '处理失败' },
              ]}
            />
            <Button 
              icon={<ReloadOutlined />} 
              onClick={() => fetchChangeRecords()}
              size="small"
            >
              刷新
            </Button>
          </Space>
        }
      >
        {changeRecords.length > 0 ? (
          <Table
            columns={recordColumns}
            dataSource={changeRecords}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 900 }}
          />
        ) : (
          <Empty
            description={
              recordStatusFilter === 'pending' 
                ? "暂无待审核的变更记录，请先上传补充需求文档"
                : recordStatusFilter === 'all'
                  ? "暂无变更记录，请先上传补充需求文档"
                  : `暂无${recordStatusFilter === 'completed' ? '已完成' : recordStatusFilter === 'approved' ? '已批准' : recordStatusFilter === 'rejected' ? '已拒绝' : '该状态'}的变更记录`
            }
          />
        )}
      </Card>

      {/* 上传补充需求弹窗 */}
      <Modal
        title="上传补充需求文档"
        open={supplementModalVisible}
        onCancel={() => {
          setSupplementModalVisible(false);
          supplementForm.resetFields();
          setUploadedFiles([]);
          setOcrResults([]);
          setDocProcessing(false);
          setDocProcessStatus('none');
          setNeedsManualProcess(false);
          setDocAnalyzeResult(null);
        }}
        onOk={() => supplementForm.submit()}
        confirmLoading={uploading || docProcessing}
        okButtonProps={{ disabled: docProcessing }}
        cancelButtonProps={{ disabled: docProcessing }}
        maskClosable={!docProcessing}
        width={800}
      >
        {/* 文档处理进度遮罩 */}
        {docProcessing && (
          <div style={{ 
            position: 'absolute', 
            top: 0, 
            left: 0, 
            right: 0, 
            bottom: 0, 
            background: 'rgba(255,255,255,0.85)', 
            zIndex: 10,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            borderRadius: 8
          }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, fontSize: 16, fontWeight: 500 }}>
              {docProcessStatus === 'uploading' && '正在上传文档...'}
              {docProcessStatus === 'extracting' && '正在提取文档内容...'}
              {docProcessStatus === 'analyzing' && '正在智能分析文档格式...'}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
              {docProcessStatus === 'extracting' && 'OCR识别图片文字，提取文档结构'}
              {docProcessStatus === 'analyzing' && '使用AI自动提取功能模块，生成标准格式'}
            </div>
          </div>
        )}
        
        <Form form={supplementForm} layout="vertical" onFinish={handleUploadSupplement}>
          <Form.Item label="上传文件（支持文档和图片）">
            <div style={{ marginBottom: 8 }}>
              <Checkbox 
                checked={autoProcessDoc}
                onChange={(e) => setAutoProcessDoc(e.target.checked)}
                disabled={docProcessing}
              >
                文档格式不规范时自动智能处理
              </Checkbox>
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                （自动提取功能模块，生成标准格式）
              </Text>
            </div>
            <Upload.Dragger
              name="files"
              multiple={false}
              accept=".docx,.doc,.pdf,.md,.markdown,.txt,.png,.jpg,.jpeg,.bmp,.gif,.webp"
              beforeUpload={(file) => {
                setUploadedFiles([file]);
                processSupplementDocument(file);
                return false;
              }}
              fileList={uploadedFiles.map((file, idx) => ({
                uid: `${idx}`,
                name: file.name,
                status: docProcessing ? 'uploading' : 'done',
                size: file.size,
              }))}
              onRemove={() => {
                setUploadedFiles([]);
                supplementForm.setFieldsValue({ supplement_content: '' });
                setDocProcessStatus('none');
                setNeedsManualProcess(false);
                setDocAnalyzeResult(null);
              }}
              disabled={docProcessing}
            >
              <p className="ant-upload-text">点击或拖拽文件上传</p>
              <p className="ant-upload-hint">
                支持文档：Word、PDF、Markdown、文本格式<br/>
                支持图片：PNG、JPG、JPEG、BMP、GIF、WebP（将通过OCR提取文字）
              </p>
            </Upload.Dragger>
            
            {/* 处理状态提示 */}
            {docProcessStatus === 'done' && docAnalyzeResult && (
              <Alert 
                type="success" 
                message="文档已智能处理完成" 
                description={`识别到 ${docAnalyzeResult.stats?.total_modules || 0} 个功能模块，${docAnalyzeResult.stats?.total_features || 0} 个功能点`}
                style={{ marginTop: 8 }}
                showIcon
                action={
                  <Button size="small" type="link" onClick={() => setDocAnalyzeResult(null)}>
                    查看详情
                  </Button>
                }
              />
            )}
            
            {needsManualProcess && (
              <Alert 
                type="warning" 
                message="检测到文档格式不规范" 
                description="建议点击下方按钮进行智能处理，提取功能模块"
                style={{ marginTop: 8 }}
                showIcon
                action={
                  <Button 
                    size="small" 
                    type="primary" 
                    ghost 
                    onClick={handleManualAnalyze} 
                    loading={docProcessing}
                    disabled={docProcessing}
                  >
                    立即处理
                  </Button>
                }
              />
            )}
            
            {docProcessStatus === 'error' && (
              <Alert 
                type="error" 
                message="文档处理失败" 
                description="请手动粘贴需求内容或尝试其他文档"
                style={{ marginTop: 8 }}
                showIcon
              />
            )}
          </Form.Item>
          <Form.Item 
            name="supplement_content" 
            label="补充需求内容"
            required
            rules={[{ required: true, message: '请上传文件或填写补充需求内容' }]}
          >
            <TextArea 
              rows={12} 
              placeholder="上传文件后自动填充内容，也可直接粘贴补充需求内容" 
              disabled={docProcessing}
            />
          </Form.Item>
        </Form>
        <Alert 
          type="info" 
          message="说明" 
          description={
            <div>
              上传文件后，系统会自动提取内容并填充到上方文本框。<br/>
              若文档包含图片，会通过OCR自动提取文字；若格式不规范，会智能转换为标准格式。<br/>
              提交后，系统将对比原需求文档，识别变更并生成处理建议。
            </div>
          } 
          showIcon 
        />
      </Modal>

      {/* 受影响测试用例弹窗 */}
      <Modal
        title={`受影响的测试用例 - ${selectedRecord?.module_name}`}
        open={affectedCasesModalVisible}
        onCancel={() => {
          setAffectedCasesModalVisible(false);
          setAffectedCases([]);
          setSelectedRecord(null);
        }}
        footer={[
          <Button key="close" onClick={() => setAffectedCasesModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={800}
      >
        {selectedRecord && (
          <Descriptions column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="变更类型">
              {getChangeTypeTag(selectedRecord.change_type)}
            </Descriptions.Item>
            <Descriptions.Item label="影响级别">
              {getImpactLevelTag(selectedRecord.impact_level)}
            </Descriptions.Item>
            <Descriptions.Item label="原描述" span={2}>
              {selectedRecord.old_description || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="新描述" span={2}>
              {selectedRecord.new_description || '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
        
        <Divider>受影响测试用例列表</Divider>
        
        {affectedCases.length > 0 ? (
          <Table
            dataSource={affectedCases}
            rowKey="id"
            pagination={false}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 80 },
              { title: '用例名称', dataIndex: 'name', width: 200 },
              { title: '模块', dataIndex: 'module', width: 120 },
              { title: '状态', dataIndex: 'status', width: 100 },
              { title: '优先级', dataIndex: 'priority', width: 80 }
            ]}
          />
        ) : (
          <Empty description="暂无受影响的测试用例" />
        )}
      </Modal>

      {/* 批准变更弹窗 */}
      <Modal
        title="批准变更处理"
        open={approveModalVisible}
        onCancel={() => {
          setApproveModalVisible(false);
          approveForm.resetFields();
          setSelectedRecord(null);
        }}
        onOk={() => approveForm.submit()}
        confirmLoading={processing}
        width={600}
      >
        {selectedRecord && (
          <Alert 
            type="info"
            message={`模块：${selectedRecord.module_name}`}
            description={
              <Space direction="vertical">
                <Text>变更类型：{getChangeTypeTag(selectedRecord.change_type)}</Text>
                <Text>影响级别：{getImpactLevelTag(selectedRecord.impact_level)}</Text>
                <Text>受影响用例：{selectedRecord.affected_test_cases_count} 个</Text>
                <Text>AI建议：{getActionText(selectedRecord.suggested_action || '')}</Text>
                <Text type="secondary">原因：{selectedRecord.suggested_reason}</Text>
              </Space>
            }
            style={{ marginBottom: 16 }}
          />
        )}
        
        <Form form={approveForm} layout="vertical" onFinish={handleApproveChange}>
          <Form.Item name="action" label="处理动作" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="generate_new">生成新测试用例</Select.Option>
              <Select.Option value="update_existing">更新现有用例（变更即派生）</Select.Option>
              <Select.Option value="deprecate">废弃现有用例</Select.Option>
              <Select.Option value="archive">归档现有用例</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="comment" label="审核意见">
            <TextArea rows={3} placeholder="可选填写审核意见" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 一键批准确认弹窗 */}
      <Modal
        title="一键批准所有变更"
        open={batchApproveConfirmVisible}
        onCancel={() => setBatchApproveConfirmVisible(false)}
        onOk={handleBatchApproveConfirm}
        okText="确定批准"
        cancelText="取消"
        width={500}
      >
        <Alert 
          type="warning" 
          message="注意" 
          description="将按照AI建议的处理动作，自动处理所有待审核的变更记录。此操作将调用AI生成新的测试用例，可能需要较长时间。" 
          showIcon 
          style={{ marginBottom: 16 }}
        />
        <div style={{ marginBottom: 16 }}>
          <Text>当前待审核变更：<strong style={{ color: '#1890ff' }}>{changeRecords.length}</strong> 条</Text>
        </div>
        <div>
          <Text type="secondary">处理动作包括：</Text>
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            <li>生成新测试用例（新增模块）</li>
            <li>变更即派生：旧用例归档，派生新修订回草稿待审核（修改模块）</li>
            <li>废弃旧用例（删除模块）</li>
            <li>归档旧用例（删除模块）</li>
          </ul>
        </div>
      </Modal>

      {/* 批量批准进度弹窗 */}
      <Modal
        open={batchApproveProgressVisible}
        footer={null}
        closable={false}
        maskClosable={false}
        width={600}
        centered
        styles={{ body: { padding: 0 } }}
      >
        <div style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', padding: '20px', borderRadius: '12px 12px 0 0', color: '#fff' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ fontSize: '28px' }}>{batchApproveProgress < 100 ? '🚀' : '✅'}</div>
            <div>
              <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                {batchApproveProgress < 100 ? '正在批量批准变更' : '处理完成'}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.9 }}>
                {batchApproveProgress < 100 ? 'AI 正在生成测试用例...' : '所有变更已处理'}
              </div>
            </div>
          </div>
          <div style={{ marginTop: '16px' }}>
            <Progress 
              percent={batchApproveProgress} 
              status={batchApproveProgress < 100 ? 'active' : 'success'}
              strokeColor={{ from: '#00d4ff', to: '#00ff88' }}
              trailColor='rgba(255,255,255,0.2)'
            />
          </div>
        </div>
        
        <div style={{ padding: '20px', maxHeight: '350px', overflowY: 'auto', backgroundColor: '#f5f7fa' }}>
          <div style={{ backgroundColor: '#fff', borderRadius: '8px', padding: '16px' }}>
            <div style={{ marginBottom: '12px', color: '#999', fontSize: '12px' }}>📝 执行详情</div>
            {batchApproveLogs.map((log, i) => (
              <div key={i} style={{ 
                padding: '8px 12px', 
                marginBottom: '4px',
                borderRadius: '6px',
                fontSize: '13px',
                backgroundColor: log.msg.includes('✅') || log.msg.includes('🎉') ? '#f6ffed' : 
                               log.msg.includes('❌') ? '#fff1f0' : '#f5f5f5',
                color: log.msg.includes('❌') ? '#ff4d4f' : 
                       log.msg.includes('✅') || log.msg.includes('🎉') ? '#52c41a' : '#333',
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
        
        {batchApproveProgress < 100 && (
          <div style={{ padding: '16px', textAlign: 'center', borderTop: '1px solid #e8e8e8', backgroundColor: '#fff', color: '#667eea', fontSize: '13px' }}>
            <Spin size="small" style={{ marginRight: '8px' }} />
            ⏱️ 正在处理，请耐心等待...
          </div>
        )}
      </Modal>

      {/* 批量批准成功弹窗 */}
      <Modal
        title={<Space><CheckCircleOutlined style={{ color: '#52c41a' }} /><span>批量批准完成</span></Space>}
        open={batchApproveSuccessVisible}
        onCancel={() => setBatchApproveSuccessVisible(false)}
        footer={[
          <Button key="close" onClick={() => setBatchApproveSuccessVisible(false)}>
            关闭
          </Button>,
          <Button key="view" type="primary" onClick={() => {
            setBatchApproveSuccessVisible(false);
            navigate(`/tests/functional?projectId=${version?.project_id}&versionId=${versionId}&source=change`);
          }}>
            查看测试用例
          </Button>
        ]}
        width={450}
        centered
      >
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {batchApproveResult?.data && (
            <>
              <p style={{ fontSize: '16px', marginBottom: '12px' }}>
                处理变更：<strong style={{ color: '#1890ff', fontSize: '20px' }}>{batchApproveResult.data.processed || 0}</strong> 条
              </p>
              <p style={{ fontSize: '16px', marginBottom: '12px' }}>
                生成测试用例：<strong style={{ color: '#52c41a', fontSize: '20px' }}>{batchApproveResult.data.generated_cases_count || 0}</strong> 个
              </p>
              {batchApproveResult.data.derived_cases_count > 0 && (
                <p style={{ fontSize: '16px', marginBottom: '12px' }}>
                  派生修订：<strong style={{ color: '#52c41a', fontSize: '20px' }}>{batchApproveResult.data.derived_cases_count || 0}</strong> 个（旧版归档，回草稿待审核）
                </p>
              )}
              {(batchApproveResult.data.affected_ui_removed > 0 || batchApproveResult.data.affected_scene_removed > 0) && (
                <p style={{ fontSize: '14px', marginBottom: '12px', color: '#fa8c16' }}>
                  移除旧用例：UI {batchApproveResult.data.affected_ui_removed || 0} 条，场景 {batchApproveResult.data.affected_scene_removed || 0} 条
                </p>
              )}
              {batchApproveResult.data.failed > 0 && (
                <p style={{ fontSize: '14px', marginBottom: '12px', color: '#ff4d4f' }}>
                  处理失败：<strong>{batchApproveResult.data.failed}</strong> 条
                </p>
              )}
            </>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default RequirementChangeReviewPage;