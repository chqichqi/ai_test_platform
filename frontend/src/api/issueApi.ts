import axiosInstance from './axiosConfig';

export interface Issue {
  id: number;
  project_id: number;
  version_id?: number;
  execution_id?: number;
  case_id?: number;
  title: string;
  description?: string;
  severity: string;
  priority: string;
  status: string;
  failure_type?: string;
  root_cause?: string;
  ai_analysis?: string;
  ai_suggestion?: string;
  ai_confidence?: number;
  assignee_id?: number;
  reporter_id?: number;
  resolved_at?: string;
  resolved_by?: number;
  resolution_note?: string;
  tags?: string[];
  affected_cases?: number[];
  created_at: string;
  updated_at: string;
}

export interface IssueListResponse {
  items: Issue[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface IssueCreate {
  project_id: number;
  version_id?: number;
  execution_id?: number;
  case_id?: number;
  title: string;
  description?: string;
  severity?: string;
  priority?: string;
  failure_type?: string;
  tags?: string[];
  assignee_id?: number;
}

export interface IssueUpdate {
  title?: string;
  description?: string;
  severity?: string;
  priority?: string;
  status?: string;
  assignee_id?: number;
  tags?: string[];
  resolution_note?: string;
}

export interface IssueStats {
  total: number;
  open: number;
  in_progress: number;
  resolved: number;
  closed: number;
  by_severity: Record<string, number>;
  by_priority: Record<string, number>;
  by_failure_type: Record<string, number>;
}

export interface IssueTrend {
  start_date: string;
  end_date: string;
  trend: Array<{
    date: string;
    created: number;
    resolved: number;
    closed: number;
  }>;
}

export interface IssueSummary {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_priority: Record<string, number>;
  by_failure_type: Record<string, number>;
  top_assignees: Array<{
    assignee_id: number;
    count: number;
  }>;
  avg_resolution_time_hours?: number;
  resolution_rate: number;
}

export interface IssueDashboard {
  summary: {
    total: number;
    open: number;
    in_progress: number;
    resolved_this_week: number;
    new_this_week: number;
    new_this_month: number;
    critical_open: number;
    high_open: number;
  };
  recent_issues: Array<{
    id: number;
    title: string;
    severity: string;
    status: string;
    created_at: string;
  }>;
  health_score: number;
}

export interface FailureAnalysisRequest {
  execution_id: number;
  case_id?: number;
  project_id: number;
  failure_message?: string;
  stack_trace?: string;
  screenshot_base64?: string;
  dom_snapshot?: string;
  console_logs?: Array<Record<string, unknown>>;
  network_logs?: Array<Record<string, unknown>>;
}

export interface FailureAnalysisResponse {
  id: number;
  execution_id: number;
  case_id?: number;
  failure_type?: string;
  failure_message?: string;
  root_cause?: string;
  ai_analysis?: string;
  confidence?: number;
  suggested_fix?: string;
  auto_fix_available: boolean;
  affected_locators?: Array<Record<string, unknown>>;
  affected_cases?: Array<Record<string, unknown>>;
  created_at: string;
  similar_issues?: Array<{
    id: number;
    title: string;
    resolution_note?: string;
    created_at?: string;
    resolved_at?: string;
  }>;
  severity_recommendation?: string;
  priority_recommendation?: string;
}

export const issueApi = {
  list: async (params: {
    project_id: number;
    page?: number;
    page_size?: number;
    status?: string;
    severity?: string;
    priority?: string;
    assignee_id?: number;
    search?: string;
  }): Promise<IssueListResponse> => {
    const response = await axiosInstance.get('/issues/', { params });
    return response.data;
  },

  get: async (id: number): Promise<Issue> => {
    const response = await axiosInstance.get(`/issues/${id}`);
    return response.data;
  },

  create: async (data: IssueCreate): Promise<Issue> => {
    const response = await axiosInstance.post('/issues/', data);
    return response.data;
  },

  update: async (id: number, data: IssueUpdate): Promise<Issue> => {
    const response = await axiosInstance.put(`/issues/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/issues/${id}`);
  },

  assign: async (id: number, assigneeId: number): Promise<{ message: string }> => {
    const response = await axiosInstance.post(`/issues/${id}/assign`, null, {
      params: { assignee_id: assigneeId }
    });
    return response.data;
  },

  resolve: async (id: number, resolutionNote?: string): Promise<{ message: string }> => {
    const response = await axiosInstance.post(`/issues/${id}/resolve`, null, {
      params: { resolution_note: resolutionNote }
    });
    return response.data;
  },

  close: async (id: number): Promise<{ message: string }> => {
    const response = await axiosInstance.post(`/issues/${id}/close`);
    return response.data;
  },

  reopen: async (id: number): Promise<{ message: string }> => {
    const response = await axiosInstance.post(`/issues/${id}/reopen`);
    return response.data;
  },

  getStats: async (projectId: number): Promise<IssueStats> => {
    const response = await axiosInstance.get(`/issues/stats/${projectId}`);
    return response.data;
  },

  getTrend: async (projectId: number, days: number = 30): Promise<IssueTrend> => {
    const response = await axiosInstance.get(`/issues/stats/${projectId}/trend`, {
      params: { days }
    });
    return response.data;
  },

  getSummary: async (projectId: number, versionId?: number): Promise<IssueSummary> => {
    const response = await axiosInstance.get(`/issues/stats/${projectId}/summary`, {
      params: { version_id: versionId }
    });
    return response.data;
  },

  getDashboard: async (projectId: number): Promise<IssueDashboard> => {
    const response = await axiosInstance.get(`/issues/dashboard/${projectId}`);
    return response.data;
  },

  getRelated: async (id: number): Promise<{
    issue_id: number;
    by_failure_type: Array<{ id: number; title: string; status: string; created_at?: string }>;
    by_case: Array<{ id: number; title: string; status: string; created_at?: string }>;
    by_root_cause: Array<{ id: number; title: string; status: string; created_at?: string }>;
  }> => {
    const response = await axiosInstance.get(`/issues/${id}/related`);
    return response.data;
  },

  export: async (params: {
    project_id: number;
    format?: 'excel' | 'csv' | 'json';
    status?: string;
    severity?: string;
  }): Promise<Blob> => {
    const response = await axiosInstance.get('/issues/export', {
      params,
      responseType: 'blob'
    });
    return response.data;
  },

  analyzeFailure: async (data: FailureAnalysisRequest): Promise<FailureAnalysisResponse> => {
    const response = await axiosInstance.post('/issues/analyze', data);
    return response.data;
  },

  createFromAnalysis: async (analysisId: number, additionalDescription?: string): Promise<Issue> => {
    const response = await axiosInstance.post(`/issues/analyze/${analysisId}/create-issue`, null, {
      params: { additional_description: additionalDescription }
    });
    return response.data;
  },

  batchAssign: async (issueIds: number[], assigneeId: number): Promise<{ message: string }> => {
    const response = await axiosInstance.post('/issues/batch/assign', {
      issue_ids: issueIds,
      assignee_id: assigneeId
    });
    return response.data;
  },

  batchUpdateStatus: async (issueIds: number[], status: string, resolutionNote?: string): Promise<{ message: string }> => {
    const response = await axiosInstance.post('/issues/batch/status', {
      issue_ids: issueIds,
      status,
      resolution_note: resolutionNote
    });
    return response.data;
  }
};

export const SEVERITY_OPTIONS = [
  { value: 'critical', label: '严重', color: '#f5222d' },
  { value: 'high', label: '高', color: '#fa8c16' },
  { value: 'medium', label: '中', color: '#faad14' },
  { value: 'low', label: '低', color: '#52c41a' }
];

export const PRIORITY_OPTIONS = [
  { value: 'P0', label: 'P0 - 紧急', color: '#f5222d' },
  { value: 'P1', label: 'P1 - 高', color: '#fa8c16' },
  { value: 'P2', label: 'P2 - 中', color: '#faad14' },
  { value: 'P3', label: 'P3 - 低', color: '#52c41a' }
];

export const STATUS_OPTIONS = [
  { value: 'open', label: '待处理', color: '#1890ff' },
  { value: 'in_progress', label: '处理中', color: '#722ed1' },
  { value: 'resolved', label: '已解决', color: '#52c41a' },
  { value: 'closed', label: '已关闭', color: '#8c8c8c' },
  { value: 'reopened', label: '重新打开', color: '#fa8c16' }
];

export const FAILURE_TYPE_OPTIONS = [
  { value: 'element_not_found', label: '元素定位失败' },
  { value: 'assertion_failed', label: '断言失败' },
  { value: 'timeout', label: '超时' },
  { value: 'network_error', label: '网络错误' },
  { value: 'environment_error', label: '环境错误' },
  { value: 'data_error', label: '数据错误' },
  { value: 'business_bug', label: '业务Bug' },
  { value: 'script_error', label: '脚本错误' },
  { value: 'unknown', label: '未知' }
];