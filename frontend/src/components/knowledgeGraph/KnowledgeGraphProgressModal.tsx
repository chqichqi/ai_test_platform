/**
 * 知识图谱生成进度弹窗
 * 实时显示：进度百分比、当前页面、统计信息
 * 完成后提供"查看知识图谱"/"取消"按钮
 */

import React, { useState, useEffect, useRef } from 'react';
import { Modal, Progress, Button, Space, Statistic, Alert, Typography, message } from 'antd';
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined, 
  SyncOutlined,
  EyeOutlined,
  FileTextOutlined,
  ApiOutlined,
  SettingOutlined
} from '@ant-design/icons';
import { 
  KnowledgeGraphProgressResponse,
  KnowledgeGraphGenerateRequest,
  pollKnowledgeGraphProgress
} from '../../api/knowledgeGraphApi';

const { Text } = Typography;

interface KnowledgeGraphProgressModalProps {
  visible: boolean;
  graphId: number | null;
  generateRequest: KnowledgeGraphGenerateRequest | null;
  onCancel: () => void;
  onViewGraph: (graphId: number) => void;
  /** 每次轮询返回时回传进度（供父组件同步顶部状态 Tag） */
  onProgressUpdate?: (progress: KnowledgeGraphProgressResponse) => void;
}

const KnowledgeGraphProgressModal: React.FC<KnowledgeGraphProgressModalProps> = ({
  visible,
  graphId,
  generateRequest,
  onCancel,
  onViewGraph,
  onProgressUpdate,
}) => {
  const [progress, setProgress] = useState<KnowledgeGraphProgressResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 取消/卸载标记：轮询每轮检查，false 即停止（防泄漏：取消后不再继续查询、
  // 不再弹 toast，切项目不串图）
  const activeRef = useRef(false);

  // 开始轮询进度；卸载/关闭时终止
  useEffect(() => {
    if (visible && graphId) {
      activeRef.current = true;
      setError(null);
      startPolling(graphId);
    } else {
      activeRef.current = false;
    }
    return () => {
      activeRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, graphId]);

  const startPolling = async (id: number) => {
    try {
      await pollKnowledgeGraphProgress(
        id,
        (prog) => {
          if (!activeRef.current) return; // 已取消，忽略迟到响应
          setProgress(prog);
          onProgressUpdate?.(prog);

          // 检查是否完成或失败
          if (prog.exploration_status === 'completed') {
            activeRef.current = false;
            message.success('知识图谱生成完成！');
          } else if (prog.exploration_status === 'failed') {
            activeRef.current = false;
            setError(prog.error_message || '生成失败');
            message.error('知识图谱生成失败');
          }
        },
        3000, // 3秒间隔
        100, // 最大100次查询（约5分钟）
        () => activeRef.current
      );
    } catch (err: any) {
      if (!activeRef.current) return;
      setError(err.message || '轮询失败');
      message.error('进度查询失败');
    }
  };

  const handleViewGraph = () => {
    if (graphId) {
      onViewGraph(graphId);
      onCancel();
    }
  };

  const handleCancel = () => {
    activeRef.current = false;
    setProgress(null);
    setError(null);
    onCancel();
  };

  const getStatusIcon = () => {
    if (!progress) return <SyncOutlined spin />;
    
    switch (progress.exploration_status) {
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed':
        return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'running':
        return <SyncOutlined spin style={{ color: '#1890ff' }} />;
      default:
        return <SyncOutlined spin />;
    }
  };

  const getProgressColor = () => {
    if (!progress) return '#1890ff';
    
    if (progress.exploration_status === 'completed') return '#52c41a';
    if (progress.exploration_status === 'failed') return '#ff4d4f';
    return '#1890ff';
  };

  return (
    <Modal
      title={
        <Space>
          {getStatusIcon()}
          <span>知识图谱生成进度</span>
        </Space>
      }
      open={visible}
      onCancel={handleCancel}
      footer={
        progress?.exploration_status === 'completed' ? (
          <Space>
            <Button type="primary" icon={<EyeOutlined />} onClick={handleViewGraph}>
              查看知识图谱
            </Button>
            <Button onClick={handleCancel}>取消</Button>
          </Space>
        ) : progress?.exploration_status === 'failed' ? (
          <Button onClick={handleCancel}>关闭</Button>
        ) : (
          <Button onClick={handleCancel}>取消生成</Button>
        )
      }
      width={700}
      centered
    >
      {/* 错误信息 */}
      {error && (
        <Alert
          message="生成失败"
          description={error}
          type="error"
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 进度条 */}
      <div style={{ marginBottom: 24 }}>
        <Progress
          percent={progress?.progress_percentage || 0}
          status={
            progress?.exploration_status === 'completed' ? 'success' :
            progress?.exploration_status === 'failed' ? 'exception' :
            'active'
          }
          strokeColor={getProgressColor()}
          strokeWidth={12}
        />
        
        {/* 当前页面 */}
        {progress?.current_page && (
          <Text type="secondary" style={{ marginTop: 8, display: 'block' }}>
            当前正在爬取：{progress.current_page}
          </Text>
        )}
      </div>

      {/* 统计信息 */}
      {progress && (
        <Space size="large" style={{ marginBottom: 24, width: '100%', justifyContent: 'space-around' }}>
          <Statistic
            title="已爬取页面"
            value={progress.page_count}
            prefix={<FileTextOutlined />}
            valueStyle={{ color: '#3f8600' }}
          />
          <Statistic
            title="已识别元素"
            value={progress.element_count}
            prefix={<SettingOutlined />}
            valueStyle={{ color: '#1890ff' }}
          />
          <Statistic
            title="已发现菜单"
            value={progress.menu_count}
            prefix={<ApiOutlined />}
            valueStyle={{ color: '#722ed1' }}
          />
        </Space>
      )}

      {/* 配置信息 */}
      {generateRequest && (
        <Alert
          message="生成配置"
          description={
            <Space direction="vertical" size="small">
              <Text>项目URL：{generateRequest.base_url}</Text>
              <Text>登录用户：{generateRequest.login_username}</Text>
              <Text>爬取策略：{generateRequest.exploration_strategy}</Text>
              <Text>跳过租户：{generateRequest.skip_tenant ? '是' : '否'}</Text>
            </Space>
          }
          type="info"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}

      {/* 完成提示 */}
      {progress?.exploration_status === 'completed' && (
        <Alert
          message="知识图谱生成完成"
          description={`共爬取 ${progress.page_count} 个页面，识别 ${progress.element_count} 个元素。点击"查看知识图谱"按钮查看详细信息。`}
          type="success"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}
    </Modal>
  );
};

export default KnowledgeGraphProgressModal;