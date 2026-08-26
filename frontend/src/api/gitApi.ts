import axiosInstance from './axiosConfig';

export interface GitRepository {
  id: number;
  project_id: number;
  name: string;
  url: string;
  auth_type: string;
  default_branch: string;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GitRepositoryCreate {
  project_id: number;
  name: string;
  url: string;
  auth_type?: 'ssh' | 'token' | 'password' | 'none';
  auth_token?: string;
  ssh_key?: string;
  username?: string;
  password?: string;
  default_branch?: string;
}

export interface GitRepositoryUpdate {
  name?: string;
  auth_type?: 'ssh' | 'token' | 'password' | 'none';
  auth_token?: string;
  ssh_key?: string;
  username?: string;
  password?: string;
  default_branch?: string;
  status?: 'active' | 'inactive' | 'error';
}

export interface RepositoryTestResult {
  success: boolean;
  message: string;
  branch_count?: number;
  last_commit?: {
    hash: string;
    full_hash: string;
  };
}

export interface GitBranch {
  id: number;
  repository_id: number;
  name: string;
  last_commit_hash: string | null;
  last_commit_message: string | null;
  last_commit_author: string | null;
  last_commit_at: string | null;
  is_default: number;
  is_protected: number;
  ahead_count: number;
  behind_count: number;
  status: string;
}

export interface GitCommit {
  id: number;
  repository_id: number;
  commit_hash: string;
  short_hash: string | null;
  branch: string | null;
  author: string | null;
  author_email: string | null;
  message: string | null;
  committed_at: string | null;
  files_changed: number;
  additions: number;
  deletions: number;
  created_at: string;
}

export interface GitWebhook {
  id: number;
  repository_id: number;
  name: string | null;
  webhook_url: string | null;
  trigger_events: string[] | null;
  trigger_branches: string[] | null;
  trigger_paths: string[] | null;
  test_plan_id: number | null;
  execution_config: object | null;
  enabled: number;
  last_triggered_at: string | null;
  trigger_count: number;
  created_at: string;
  updated_at: string;
}

export interface GitWebhookCreate {
  repository_id: number;
  name?: string;
  trigger_events: string[];
  trigger_branches?: string[];
  trigger_paths?: string[];
  test_plan_id?: number;
  execution_config?: object;
}

export interface GitWebhookLog {
  id: number;
  webhook_id: number;
  event_type: string | null;
  triggered: number;
  trigger_reason: string | null;
  execution_id: number | null;
  error_message: string | null;
  ip_address: string | null;
  created_at: string;
}

export const gitApi = {
  listRepositories: async (params: {
    page?: number;
    page_size?: number;
    project_id?: number;
    status_filter?: string;
    search?: string;
  }) => {
    const response = await axiosInstance.get('/git/', { params });
    return response.data;
  },

  getRepository: async (id: number): Promise<GitRepository> => {
    const response = await axiosInstance.get(`/git/${id}`);
    return response.data;
  },

  createRepository: async (data: GitRepositoryCreate): Promise<GitRepository> => {
    const response = await axiosInstance.post('/git/', data);
    return response.data;
  },

  updateRepository: async (id: number, data: GitRepositoryUpdate): Promise<GitRepository> => {
    const response = await axiosInstance.put(`/git/${id}`, data);
    return response.data;
  },

  deleteRepository: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/git/${id}`);
  },

  testConnection: async (id: number): Promise<RepositoryTestResult> => {
    const response = await axiosInstance.post(`/git/${id}/test`);
    return response.data;
  },

  syncRepository: async (id: number, force: boolean = false): Promise<{
    success: boolean;
    message: string;
    branches_synced: number;
    commits_synced: number;
  }> => {
    const response = await axiosInstance.post(`/git/${id}/sync`, { force });
    return response.data;
  },

  listBranches: async (repoId: number): Promise<{ items: GitBranch[]; total: number }> => {
    const response = await axiosInstance.get(`/git/${repoId}/branches`);
    return response.data;
  },

  listCommits: async (repoId: number, params?: {
    page?: number;
    page_size?: number;
    branch?: string;
    author?: string;
    search?: string;
  }) => {
    const response = await axiosInstance.get(`/git/${repoId}/commits`, { params });
    return response.data;
  },

  getCommit: async (repoId: number, commitId: number): Promise<GitCommit> => {
    const response = await axiosInstance.get(`/git/${repoId}/commits/${commitId}`);
    return response.data;
  },

  listWebhooks: async (repoId: number): Promise<{ items: GitWebhook[]; total: number }> => {
    const response = await axiosInstance.get(`/git/${repoId}/webhooks`);
    return response.data;
  },

  createWebhook: async (repoId: number, data: GitWebhookCreate): Promise<GitWebhook> => {
    const response = await axiosInstance.post(`/git/${repoId}/webhooks`, data);
    return response.data;
  },

  updateWebhook: async (repoId: number, webhookId: number, data: Partial<GitWebhookCreate> & { enabled?: boolean }): Promise<GitWebhook> => {
    const response = await axiosInstance.put(`/git/${repoId}/webhooks/${webhookId}`, data);
    return response.data;
  },

  deleteWebhook: async (repoId: number, webhookId: number): Promise<void> => {
    await axiosInstance.delete(`/git/${repoId}/webhooks/${webhookId}`);
  },

  listWebhookLogs: async (repoId: number, webhookId: number, params?: {
    page?: number;
    page_size?: number;
  }) => {
    const response = await axiosInstance.get(`/git/${repoId}/webhooks/${webhookId}/logs`, { params });
    return response.data;
  },
};