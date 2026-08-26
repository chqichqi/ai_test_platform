import React, { useEffect, useRef } from 'react';
import { notification } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { generationTaskApi } from '../../api/generationTaskApi';
import {
  setRunningTasks,
  setCurrentTask,
  removeRunningTask,
  setBackendHealthy,
  updateTaskProgress,
} from '../../store/slices/taskProgressSlice';
import { RootState } from '../../store';

const GenerationTaskNotifier: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  
  const listPollingRef = useRef<NodeJS.Timeout | null>(null);
  const detailPollingRef = useRef<NodeJS.Timeout | null>(null);
  const notifiedCompletedRef = useRef<Set<number>>(new Set());
  const notifiedFailedRef = useRef<Set<number>>(new Set());
  const lastRunningTaskIdsRef = useRef<string>('');
  const hasNotifiedRecovery = useRef(false);  // 防止反复弹恢复通知

  const { backendHealthy, runningTasks, taskId: trackedTaskId } = useSelector(
    (state: RootState) => state.taskProgress
  );

  useEffect(() => {
    pollRunningTasksList();
    listPollingRef.current = setInterval(pollRunningTasksList, 15000);
    
    return () => {
      if (listPollingRef.current) {
        clearInterval(listPollingRef.current);
      }
      if (detailPollingRef.current) {
        clearInterval(detailPollingRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const currentIds = runningTasks.map(t => t.id).sort().join(',');
    const hasNewTasks = currentIds !== lastRunningTaskIdsRef.current;
    lastRunningTaskIdsRef.current = currentIds;
    
    if (runningTasks.length > 0 && hasNewTasks) {
      pollTaskDetails();
    }
    
    if (runningTasks.length > 0 && !detailPollingRef.current) {
      detailPollingRef.current = setInterval(pollTaskDetails, 10000);
    } else if (runningTasks.length === 0 && detailPollingRef.current) {
      clearInterval(detailPollingRef.current);
      detailPollingRef.current = null;
    }
  }, [runningTasks.length]);

  const pollRunningTasksList = async () => {
    try {
      const taskList = await generationTaskApi.listTasks({
        status: 'running',
        limit: 10
      });

      dispatch(setBackendHealthy(true));
      dispatch(setRunningTasks(taskList.tasks));

      if (!hasNotifiedRecovery.current) {
        hasNotifiedRecovery.current = true;
        notification.success({
          message: '后端服务已恢复',
          description: '连接正常',
          duration: 3,
          placement: 'topRight'
        });
      }

    } catch (error: any) {
      console.error('轮询任务列表失败', error);

      if (backendHealthy) {
        dispatch(setBackendHealthy(false));
        hasNotifiedRecovery.current = false;  // 重置，下次恢复时再通知

        notification.warning({
          message: '后端服务异常',
          description: '无法连接后端服务',
          duration: 0,
          placement: 'topRight',
          key: 'backend-down',
          onClick: () => notification.destroy('backend-down'),
        });
      }
    }
  };

  const pollTaskDetails = async () => {
    if (runningTasks.length === 0) return;
    
    try {
      const taskIds = runningTasks.map(t => t.id);
      const details = await Promise.all(
        taskIds.map(id => generationTaskApi.getTask(id))
      );
      
      for (const detail of details) {
        if (detail.status === 'cancelled') {
          dispatch(removeRunningTask(detail.id));
          continue;
        }
        
        dispatch(updateTaskProgress({ taskId: detail.id, task: detail }));
        
        if (trackedTaskId === detail.id) {
          dispatch(setCurrentTask(detail));
        }
        
        if (detail.status === 'completed' && !notifiedCompletedRef.current.has(detail.id)) {
          notifiedCompletedRef.current.add(detail.id);
          dispatch(removeRunningTask(detail.id));
          
          const durationStr = detail.duration_seconds 
            ? (detail.duration_seconds >= 60 
              ? `${Math.floor(detail.duration_seconds / 60)}分${Math.floor(detail.duration_seconds % 60)}秒`
              : `${Math.floor(detail.duration_seconds)}秒`)
            : '';
          
          notification.success({
            message: '测试用例生成完成！',
            description: `已生成 ${detail.generated_count} 条测试用例${durationStr ? `，耗时 ${durationStr}` : ''}`,
            duration: 10,
            placement: 'topRight',
            onClick: () => {
              notification.destroy();
              navigate('/tests/functional');
            },
          });
        }
        
        if (detail.status === 'failed' && !notifiedFailedRef.current.has(detail.id)) {
          notifiedFailedRef.current.add(detail.id);
          dispatch(removeRunningTask(detail.id));
          
          notification.error({
            message: '测试用例生成失败',
            description: detail.error_message || '未知错误',
            duration: 8,
            placement: 'topRight',
            onClick: () => {
              notification.destroy();
              navigate('/tests/functional');
            },
          });
        }
      }
    } catch (error: any) {
      console.error('获取任务详情失败', error);
    }
  };

  return null;
};

export default GenerationTaskNotifier;