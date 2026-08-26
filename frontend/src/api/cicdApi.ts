import axiosInstance from './axiosConfig';

export interface CICDConfig {
  id: number;
  project_id: number;
  name: string;
  platform: string;
  platform_url?: string;
  username?: string;
  webhook_url?: string;
  enabled: boolean;
  last_sync_at?: string;
  sync_status?: string;
  created_at: string;
  updated_at: string;
}

export interface PipelineDefinition {
  id: number;
  config_id: number;
  project_id: number;
  name: string;
  external_id?: string;
  trigger_type: string;
  trigger_config?: Record<string, any>;
  test_plan_id?: number;
  test_case_ids?: number[];
  test_params?: Record<string, any>;
  environment?: string;
  timeout: number;
  notification_config?: Record<string, any>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface PipelineExecution {
  id: number;
  pipeline_id: number;
  project_id: number;
  external_build_id?: string;
  build_number?: number;
  build_url?: string;
  status: string;
  trigger_type?: string;
  trigger_by?: string;
  trigger_ref?: string;
  started_at?: string;
  finished_at?: string;
  duration?: number;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  skipped_cases: number;
  pass_rate: number;
  test_results?: Record<string, any>;
  error_message?: string;
  created_at: string;
}

export interface CICDConfigCreate {
  project_id: number;
  name: string;
  platform: string;
  platform_url?: string;
  api_token?: string;
  username?: string;
  webhook_secret?: string;
  config_data?: Record<string, any>;
  enabled?: boolean;
}

export interface PipelineCreate {
  config_id: number;
  project_id: number;
  name: string;
  external_id?: string;
  trigger_type?: string;
  trigger_config?: Record<string, any>;
  test_plan_id?: number;
  test_case_ids?: number[];
  test_params?: Record<string, any>;
  environment?: string;
  timeout?: number;
  notification_config?: Record<string, any>;
  enabled?: boolean;
}

export interface CICDDashboardStats {
  total_configs: number;
  active_configs: number;
  total_pipelines: number;
  active_pipelines: number;
  total_executions: number;
  success_rate: number;
  recent_executions: PipelineExecution[];
}

export const cicdApi = {
  listConfigs: async (projectId: number, page = 1, pageSize = 20) => {
    const response = await axiosInstance.get('/cicd/configs', {
      params: { project_id: projectId, page, page_size: pageSize }
    });
    return response.data;
  },

  getConfig: async (id: number): Promise<CICDConfig> => {
    const response = await axiosInstance.get(`/cicd/configs/${id}`);
    return response.data;
  },

  createConfig: async (data: CICDConfigCreate): Promise<CICDConfig> => {
    const response = await axiosInstance.post('/cicd/configs', data);
    return response.data;
  },

  updateConfig: async (id: number, data: Partial<CICDConfigCreate>): Promise<CICDConfig> => {
    const response = await axiosInstance.put(`/cicd/configs/${id}`, data);
    return response.data;
  },

  deleteConfig: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/cicd/configs/${id}`);
  },

  testConfig: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await axiosInstance.post(`/cicd/configs/${id}/test`);
    return response.data;
  },

  listPipelines: async (projectId: number, page = 1, pageSize = 20) => {
    const response = await axiosInstance.get('/cicd/pipelines', {
      params: { project_id: projectId, page, page_size: pageSize }
    });
    return response.data;
  },

  getPipeline: async (id: number): Promise<PipelineDefinition> => {
    const response = await axiosInstance.get(`/cicd/pipelines/${id}`);
    return response.data;
  },

  createPipeline: async (data: PipelineCreate): Promise<PipelineDefinition> => {
    const response = await axiosInstance.post('/cicd/pipelines', data);
    return response.data;
  },

  updatePipeline: async (id: number, data: Partial<PipelineCreate>): Promise<PipelineDefinition> => {
    const response = await axiosInstance.put(`/cicd/pipelines/${id}`, data);
    return response.data;
  },

  deletePipeline: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/cicd/pipelines/${id}`);
  },

  triggerPipeline: async (
    pipelineId: number,
    branch?: string,
    parameters?: Record<string, any>
  ): Promise<{ success: boolean; message: string; execution_id?: number }> => {
    const response = await axiosInstance.post('/cicd/pipelines/trigger', {
      pipeline_id: pipelineId,
      branch,
      parameters
    });
    return response.data;
  },

  listExecutions: async (
    projectId: number,
    pipelineId?: number,
    status?: string,
    page = 1,
    pageSize = 20
  ) => {
    const response = await axiosInstance.get('/cicd/executions', {
      params: { project_id: projectId, pipeline_id: pipelineId, status, page, page_size: pageSize }
    });
    return response.data;
  },

  getExecution: async (id: number): Promise<PipelineExecution> => {
    const response = await axiosInstance.get(`/cicd/executions/${id}`);
    return response.data;
  },

  getDashboard: async (projectId: number): Promise<CICDDashboardStats> => {
    const response = await axiosInstance.get(`/cicd/dashboard/${projectId}`);
    return response.data;
  },

  getJobs: async (configId: number): Promise<{ jobs?: any[]; projects?: any[]; workflows?: any[] }> => {
    const response = await axiosInstance.get(`/cicd/jobs/${configId}`);
    return response.data;
  }
};

export const PLATFORM_OPTIONS = [
  { value: 'jenkins', label: 'Jenkins', icon: '🔧' },
  { value: 'gitlab', label: 'GitLab CI', icon: '🦊' },
  { value: 'github', label: 'GitHub Actions', icon: '🐙' }
];

export const TRIGGER_OPTIONS = [
  { value: 'manual', label: '手动触发' },
  { value: 'on_commit', label: '提交触发' },
  { value: 'on_pr', label: 'PR触发' },
  { value: 'on_merge', label: '合并触发' },
  { value: 'scheduled', label: '定时触发' }
];

export const STATUS_OPTIONS = [
  { value: 'pending', label: '等待中', color: '#faad14' },
  { value: 'running', label: '执行中', color: '#1890ff' },
  { value: 'success', label: '成功', color: '#52c41a' },
  { value: 'failed', label: '失败', color: '#f5222d' },
  { value: 'cancelled', label: '已取消', color: '#8c8c8c' },
  { value: 'timeout', label: '超时', color: '#fa8c16' }
];