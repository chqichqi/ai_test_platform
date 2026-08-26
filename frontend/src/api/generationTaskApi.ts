import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface GenerationTask {
  id: number;
  display_id: string;
  task_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  project_id: number;
  version_id: number;
  progress: number;
  current_step: string | null;
  total_batches: number;
  current_batch: number;
  generated_count: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  total: number;
  tasks: GenerationTask[];
}

export interface PollOptions {
  onProgress?: (task: GenerationTask) => void;
  onError?: (error: Error) => void;
  intervalMs?: number;
  maxRetries?: number;
  timeoutMs?: number;
}

export const generationTaskApi = {
  getTask: async (taskId: number): Promise<GenerationTask> => {
    try {
      const response = await axios.get(`${API_BASE}/generation/tasks/${taskId}`, {
        timeout: 10000
      });
      return response.data;
    } catch (error: any) {
      if (error.code === 'ECONNREFUSED' || error.response?.status === 503) {
        throw new Error('后端服务不可用，请检查服务状态');
      }
      throw error;
    }
  },

  listTasks: async (params?: {
    project_id?: number;
    version_id?: number;
    status?: string;
    skip?: number;
    limit?: number;
  }): Promise<TaskListResponse> => {
    const response = await axios.get(`${API_BASE}/generation/tasks`, { params });
    return response.data;
  },

  cancelTask: async (taskId: number): Promise<{ success: boolean; message: string }> => {
    const response = await axios.post(`${API_BASE}/generation/tasks/${taskId}/cancel`);
    return response.data;
  },

  pollTask: async (taskId: number, options?: PollOptions): Promise<GenerationTask> => {
    const {
      onProgress,
      onError,
      intervalMs = 3000,
      maxRetries = 5,
      timeoutMs = 1800000
    } = options || {};

    const startTime = Date.now();
    let retryCount = 0;
    let lastStatus: string | null = null;

    const poll = async (): Promise<GenerationTask> => {
      try {
        const task = await generationTaskApi.getTask(taskId);
        
        if (onProgress && task.status !== lastStatus) {
          onProgress(task);
          lastStatus = task.status;
        }
        
        if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') {
          return task;
        }
        
        if (Date.now() - startTime > timeoutMs) {
          const timeoutError = new Error('任务轮询超时（30分钟），请检查任务状态');
          if (onError) {
            onError(timeoutError);
          }
          throw timeoutError;
        }
        
        retryCount = 0;
        await new Promise(resolve => setTimeout(resolve, intervalMs));
        return poll();
        
      } catch (error: any) {
        retryCount++;
        
        if (retryCount > maxRetries) {
          const maxRetryError = new Error(`请求失败重试${maxRetries}次后仍无法连接，后端可能已崩溃`);
          if (onError) {
            onError(maxRetryError);
          }
          throw maxRetryError;
        }
        
        console.warn(`轮询失败，第${retryCount}次重试...`, error.message);
        
        if (onError && retryCount === 1) {
          onError(new Error(`连接失败，正在重试... (${retryCount}/${maxRetries})`));
        }
        
        await new Promise(resolve => setTimeout(resolve, intervalMs * 2));
        return poll();
      }
    };
    
    return poll();
  },

  checkTaskStatus: async (taskId: number): Promise<{
    isAlive: boolean;
    task?: GenerationTask;
    error?: string;
  }> => {
    try {
      const task = await generationTaskApi.getTask(taskId);
      return {
        isAlive: true,
        task
      };
    } catch (error: any) {
      return {
        isAlive: false,
        error: error.message || '无法获取任务状态'
      };
    }
  }
};