import axiosInstance from './axiosConfig';

// ==================== 项目成员管理 ====================

export interface ProjectRole {
  code: string;
  name: string;
  description: string;
  permissions: string[];
}

export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: string;
  user: {
    id: string;
    username: string;
    full_name: string | null;
    email: string | null;
    avatar: string | null;
  };
  role: string;
  permissions: Record<string, any> | null;
  joined_at: string;
  joined_by: string | null;
  inviter: {
    id: string;
    username: string;
    full_name: string | null;
    email: string | null;
    avatar: string | null;
  } | null;
  is_active: boolean;
}

export interface ProjectMemberCreate {
  user_id: string;
  role?: string;
  permissions?: Record<string, any>;
}

export interface ProjectMemberUpdate {
  role?: string;
  permissions?: Record<string, any>;
}

// ==================== 项目环境配置 ====================

export interface ProjectEnvironment {
  id: number;
  project_id: number;
  name: string;
  code: string;
  base_url: string | null;
  headers: Record<string, string> | null;
  variables: Record<string, string> | null;
  db_config: Record<string, any> | null;
  is_default: boolean;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectEnvironmentCreate {
  name: string;
  code: string;
  base_url?: string;
  headers?: Record<string, string>;
  variables?: Record<string, string>;
  db_config?: Record<string, any>;
  is_default?: boolean;
  description?: string;
}

export interface ProjectEnvironmentUpdate {
  name?: string;
  base_url?: string;
  headers?: Record<string, string>;
  variables?: Record<string, string>;
  db_config?: Record<string, any>;
  is_default?: boolean;
  is_active?: boolean;
  description?: string;
}

// ==================== 项目设置 ====================

export interface NotificationConfig {
  execution_completed: boolean;
  execution_failed: boolean;
  issue_created: boolean;
  channels: string[];
}

export interface ExecutionDefaults {
  parallel: number;
  retry: number;
  timeout: number;
}

export interface TestDefaults {
  browser: string;
  viewport: { width: number; height: number };
  headless: boolean;
}

export interface LoginRulesConfig {
  username_selector?: string;
  password_selector?: string;
  submit_text?: string;
  submit_fallback?: string;
  save_auth?: boolean;
  logged_in_url_patterns?: string[];
  auth_param_names?: string[];
  org_url_keyword?: string;
  org_title_keyword?: string;
  org_card_selector?: string;
  org_confirm_text?: string;
  org_select_name?: string;
  render_wait?: number;
  login_poll_interval?: number;
  login_max_wait?: number;
  page_timeout?: number;
}

export interface WebExplorationConfig {
  base_url?: string;
  username?: string;
  password?: string;
  login_rules?: LoginRulesConfig;
  convert_batch_size?: number;
}

export interface AppExplorationConfig {
  appium_url?: string;
  username?: string;
  password?: string;
  auto_launch?: boolean;
}

export interface ExplorationConfig {
  web?: WebExplorationConfig;
  app?: AppExplorationConfig;
}

export interface ProjectSetting {
  id: number;
  project_id: number;
  notification_config: NotificationConfig | null;
  execution_defaults: ExecutionDefaults | null;
  test_defaults: TestDefaults | null;
  exploration_config: ExplorationConfig | null;
  custom_settings: Record<string, any> | null;
  updated_at: string;
}

export interface ProjectSettingUpdate {
  notification_config?: NotificationConfig;
  execution_defaults?: ExecutionDefaults;
  test_defaults?: TestDefaults;
  exploration_config?: ExplorationConfig;
  custom_settings?: Record<string, any>;
}

// ==================== 版本文档历史 ====================

export interface VersionDocHistory {
  id: number;
  version_id: number;
  doc_type: string | null;
  doc_url: string | null;
  doc_content: Record<string, any> | null;
  change_summary: string | null;
  uploaded_by: string | null;
  uploader: {
    id: string;
    username: string;
    full_name: string | null;
    email: string | null;
    avatar: string | null;
  } | null;
  uploaded_at: string;
}

// ==================== API 接口 ====================

export const projectMemberApi = {
  getRoles: async (): Promise<ProjectRole[]> => {
    const response = await axiosInstance.get('/projects/roles');
    return response.data;
  },

  list: async (projectId: number): Promise<{ items: ProjectMember[]; total: number }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/members`);
    return response.data;
  },

  create: async (projectId: number, data: ProjectMemberCreate): Promise<ProjectMember> => {
    const response = await axiosInstance.post(`/projects/${projectId}/members`, data);
    return response.data;
  },

  update: async (projectId: number, memberId: number, data: ProjectMemberUpdate): Promise<ProjectMember> => {
    const response = await axiosInstance.put(`/projects/${projectId}/members/${memberId}`, data);
    return response.data;
  },

  delete: async (projectId: number, memberId: number): Promise<void> => {
    await axiosInstance.delete(`/projects/${projectId}/members/${memberId}`);
  },

  transferOwnership: async (projectId: number, newOwnerId: string): Promise<void> => {
    await axiosInstance.post(`/projects/${projectId}/transfer-ownership`, { new_owner_id: newOwnerId });
  },
};

export const projectEnvironmentApi = {
  list: async (projectId: number, includeInactive: boolean = false): Promise<{ items: ProjectEnvironment[]; total: number }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/environments`, {
      params: { include_inactive: includeInactive }
    });
    return response.data;
  },

  create: async (projectId: number, data: ProjectEnvironmentCreate): Promise<ProjectEnvironment> => {
    const response = await axiosInstance.post(`/projects/${projectId}/environments`, data);
    return response.data;
  },

  get: async (projectId: number, envId: number): Promise<ProjectEnvironment> => {
    const response = await axiosInstance.get(`/projects/${projectId}/environments/${envId}`);
    return response.data;
  },

  update: async (projectId: number, envId: number, data: ProjectEnvironmentUpdate): Promise<ProjectEnvironment> => {
    const response = await axiosInstance.put(`/projects/${projectId}/environments/${envId}`, data);
    return response.data;
  },

  delete: async (projectId: number, envId: number): Promise<void> => {
    await axiosInstance.delete(`/projects/${projectId}/environments/${envId}`);
  },

  setDefault: async (projectId: number, envId: number): Promise<void> => {
    await axiosInstance.post(`/projects/${projectId}/environments/${envId}/set-default`);
  },
};

export const projectSettingApi = {
  get: async (projectId: number): Promise<ProjectSetting> => {
    const response = await axiosInstance.get(`/projects/${projectId}/settings`);
    return response.data;
  },

  update: async (projectId: number, data: ProjectSettingUpdate): Promise<ProjectSetting> => {
    const response = await axiosInstance.put(`/projects/${projectId}/settings`, data);
    return response.data;
  },

  updateNotification: async (projectId: number, config: Partial<NotificationConfig>): Promise<ProjectSetting> => {
    const response = await axiosInstance.patch(`/projects/${projectId}/settings/notification`, config);
    return response.data;
  },

  updateExecutionDefaults: async (projectId: number, defaults: Partial<ExecutionDefaults>): Promise<ProjectSetting> => {
    const response = await axiosInstance.patch(`/projects/${projectId}/settings/execution-defaults`, defaults);
    return response.data;
  },

  updateTestDefaults: async (projectId: number, defaults: Partial<TestDefaults>): Promise<ProjectSetting> => {
    const response = await axiosInstance.patch(`/projects/${projectId}/settings/test-defaults`, defaults);
    return response.data;
  },

  updateExplorationConfig: async (projectId: number, config: Record<string, any>): Promise<ProjectSetting> => {
    const response = await axiosInstance.patch(`/projects/${projectId}/settings/exploration`, config);
    return response.data;
  },

  deleteCustomSetting: async (projectId: number, key: string): Promise<void> => {
    await axiosInstance.delete(`/projects/${projectId}/settings/custom/${key}`);
  },

  // API 鉴权配置
  getApiAuth: async (projectId: number): Promise<{ project_id: number; api_auth: any; base_url: string; credential_ready: boolean; username: string; password: string }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/settings/api-auth`);
    return response.data;
  },

  saveApiAuth: async (projectId: number, config: Record<string, any>): Promise<any> => {
    const response = await axiosInstance.post(`/projects/${projectId}/settings/api-auth`, config);
    return response.data;
  },

  testApiAuth: async (projectId: number): Promise<any> => {
    const response = await axiosInstance.post(`/projects/${projectId}/settings/api-auth/test`);
    return response.data;
  },

  getLoginCandidates: async (projectId: number): Promise<{ project_id: number; candidates: any[] }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/settings/api-auth/candidates`);
    return response.data;
  },
};

export const versionDocHistoryApi = {
  list: async (projectId: number, versionId: number, params?: {
    doc_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ items: VersionDocHistory[]; total: number }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/versions/${versionId}/doc-history`, { params });
    return response.data;
  },

  get: async (projectId: number, versionId: number, historyId: number): Promise<VersionDocHistory> => {
    const response = await axiosInstance.get(`/projects/${projectId}/versions/${versionId}/doc-history/${historyId}`);
    return response.data;
  },

  create: async (projectId: number, versionId: number, data: {
    doc_type?: string;
    doc_url?: string;
    doc_content?: Record<string, any>;
    change_summary?: string;
  }): Promise<VersionDocHistory> => {
    const response = await axiosInstance.post(`/projects/${projectId}/versions/${versionId}/doc-history`, data);
    return response.data;
  },

  delete: async (projectId: number, versionId: number, historyId: number): Promise<void> => {
    await axiosInstance.delete(`/projects/${projectId}/versions/${versionId}/doc-history/${historyId}`);
  },

  compare: async (projectId: number, versionId: number, historyId: number, compareWithId?: number): Promise<{
    current: any;
    compare_with: any;
  }> => {
    const response = await axiosInstance.get(`/projects/${projectId}/versions/${versionId}/doc-history/${historyId}/compare`, {
      params: { compare_with_id: compareWithId }
    });
    return response.data;
  },
};
