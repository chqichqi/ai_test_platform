import axiosInstance from './axiosConfig';

export interface SystemStats {
  total_projects: number;
  total_versions: number;
  total_test_cases: number;
  total_executions: number;
  total_issues: number;
  pass_rate: number;
  recent_executions: ExecutionSummary[];
  recent_issues: IssueSummary[];
  test_trend: TrendData[];
  issue_trend: TrendData[];
}

export interface ExecutionSummary {
  id: number;
  name: string;
  status: string;
  start_time: string;
  end_time: string | null;
  passed: number;
  failed: number;
  skipped: number;
  total: number;
}

export interface IssueSummary {
  id: number;
  title: string;
  status: string;
  priority: string;
  created_at: string;
  assignee: string | null;
}

export interface TrendData {
  date: string;
  count: number;
  passed?: number;
  failed?: number;
  skipped?: number;
}

export interface ProjectDashboardStats {
  total_versions: number;
  total_test_cases: number;
  total_executions: number;
  pass_rate: number;
  version_status_distribution: Record<string, number>;
  test_case_status_distribution: Record<string, number>;
  recent_executions: ExecutionSummary[];
  test_execution_trend: TrendData[];
  issue_stats: {
    total: number;
    open: number;
    resolved: number;
    by_priority: Record<string, number>;
  };
}

export const dashboardApi = {
  // System-wide statistics
  getSystemStats: async (): Promise<SystemStats> => {
    const response = await axiosInstance.get('/dashboard/stats');
    return response.data;
  },

  // Project-specific dashboard
  getProjectDashboard: async (projectId: number): Promise<ProjectDashboardStats> => {
    const response = await axiosInstance.get(`/dashboard/projects/${projectId}/dashboard`);
    return response.data;
  },

  // Performance dashboard
  getPerformanceDashboard: async (projectId: number): Promise<any> => {
    const response = await axiosInstance.get(`/performance/dashboard/${projectId}`);
    return response.data;
  },

  // CI/CD dashboard
  getCICDDashboard: async (projectId: number): Promise<any> => {
    const response = await axiosInstance.get(`/cicd/dashboard/${projectId}`);
    return response.data;
  },

  // Issues dashboard
  getIssuesDashboard: async (projectId: number): Promise<any> => {
    const response = await axiosInstance.get(`/issues/dashboard/${projectId}`);
    return response.data;
  },

  // Test execution trend
  getTestTrend: async (params?: {
    project_id?: number;
    days?: number;
  }): Promise<TrendData[]> => {
    const response = await axiosInstance.get('/dashboard/test-trend', { params });
    return response.data;
  },

  // Issue trend
  getIssueTrend: async (params?: {
    project_id?: number;
    days?: number;
  }): Promise<TrendData[]> => {
    const response = await axiosInstance.get('/dashboard/issue-trend', { params });
    return response.data;
  },
};
