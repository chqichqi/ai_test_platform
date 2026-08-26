import axiosInstance from './axiosConfig';

// ===== Locust 相关类型 =====

export interface LocustScript {
  id: number;
  project_id: number;
  name: string;
  description?: string;
  file_content?: string;
  file_size: number;
  host?: string;
  version: number;
  status: string;
  source_case_ids?: number[];
  created_by?: string;
  created_at: string;
  updated_at?: string;
}

export interface StepConfig {
  enabled: boolean;
  step_count: number;
  step_duration: number;
  step_thread_increment: number;
  max_users?: number;
}

export interface LocustExecutionStart {
  script_id?: number;
  project_id?: number;
  name?: string;
  host?: string;
  num_users: number;
  spawn_rate: number;
  run_time: number;
  step_config?: StepConfig;
}

export interface LocustExecution {
  id: number;
  project_id: number;
  script_id?: number;
  scenario_id?: number;
  name?: string;
  status: string;
  host?: string;
  num_users: number;
  spawn_rate: number;
  run_time: number;
  step_enabled: boolean;
  step_count: number;
  step_duration: number;
  step_thread_increment: number;
  start_time?: string;
  end_time?: string;
  actual_duration?: number;
  avg_tps?: number;
  max_tps?: number;
  avg_rt?: number;
  p50_rt?: number;
  p90_rt?: number;
  p95_rt?: number;
  p99_rt?: number;
  error_rate?: number;
  total_samples?: number;
  success_samples?: number;
  error_samples?: number;
  created_at: string;
}

export interface LocustMetricsData {
  status: string;
  metrics: Array<{
    timestamp: string;
    elapsed?: number;
    user_count: number;
    tps: number;
    avg_rt: number;
    min_rt?: number;
    max_rt?: number;
    fail_ratio: number;
    samples_count: number;
    error_count: number;
  }>;
  progress?: {
    elapsed: number;
    total: number;
  };
  summary?: {
    avg_tps?: number;
    max_tps?: number;
    avg_rt?: number;
    p90_rt?: number;
    p95_rt?: number;
    p99_rt?: number;
    error_rate?: number;
    total_samples?: number;
  };
}

export interface ApprovedApiCase {
  id: number;
  name: string;
  method?: string;
  path?: string;
  priority: string;
  case_type: string;
  description?: string;
  tags?: string[];
  created_at: string;
}

// ===== API 方法 =====

export const performanceApi = {
  // ===== Locust 脚本 =====
  createLocustScript: async (data: {
    project_id: number;
    name: string;
    description?: string;
    host: string;
    case_ids: number[];
  }): Promise<LocustScript> => {
    const response = await axiosInstance.post('/performance/locust/scripts', data);
    return response.data;
  },

  listLocustScripts: async (projectId: number): Promise<{ items: LocustScript[]; total: number }> => {
    const response = await axiosInstance.get('/performance/locust/scripts', { params: { project_id: projectId } });
    return response.data;
  },

  getLocustScript: async (scriptId: number): Promise<LocustScript> => {
    const response = await axiosInstance.get(`/performance/locust/scripts/${scriptId}`);
    return response.data;
  },

  updateLocustScript: async (scriptId: number, data: {
    name?: string;
    description?: string;
    file_content?: string;
  }): Promise<LocustScript> => {
    const response = await axiosInstance.put(`/performance/locust/scripts/${scriptId}`, null, { params: data });
    return response.data;
  },

  deleteLocustScript: async (scriptId: number): Promise<void> => {
    await axiosInstance.delete(`/performance/locust/scripts/${scriptId}`);
  },

  // ===== Locust 执行 =====
  startLocustExecution: async (data: LocustExecutionStart): Promise<LocustExecution> => {
    const response = await axiosInstance.post('/performance/locust/executions', data, { timeout: 60000 });
    return response.data;
  },

  stopLocustExecution: async (executionId: number): Promise<{ message: string }> => {
    const response = await axiosInstance.post(`/performance/locust/executions/${executionId}/stop`);
    return response.data;
  },

  listLocustExecutions: async (params?: {
    project_id?: number;
    script_id?: number;
  }): Promise<{ items: LocustExecution[]; total: number }> => {
    const response = await axiosInstance.get('/performance/locust/executions', { params });
    return response.data;
  },

  getLocustExecution: async (executionId: number): Promise<LocustExecution> => {
    const response = await axiosInstance.get(`/performance/locust/executions/${executionId}`);
    return response.data;
  },

  getLocustMetrics: async (executionId: number): Promise<LocustMetricsData> => {
    const response = await axiosInstance.get(`/performance/locust/executions/${executionId}/metrics`);
    return response.data;
  },

  // ===== 已审批 API 用例 =====
  getApprovedApiCases: async (params: {
    project_id: number;
    page?: number;
    page_size?: number;
    search?: string;
    method?: string;
    priority?: string;
  }): Promise<{ items: ApprovedApiCase[]; total: number; page: number; page_size: number }> => {
    const response = await axiosInstance.get('/performance/locust/approved-cases', { params });
    return response.data;
  },
};
