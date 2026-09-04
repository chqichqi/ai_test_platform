import axiosInstance from './axiosConfig';
import { Project, ProjectCreate, ProjectUpdate, ProjectListResponse, ProjectDetailResponse, ProjectStats } from '../types/project';

export const projectApi = {
  list: async (params: {
    page?: number;
    page_size?: number;
    search?: string;
    status_filter?: string;
    include_deleted?: boolean;
  }): Promise<ProjectListResponse> => {
    const response = await axiosInstance.get('/projects/', { params });
    return response.data;
  },

  get: async (id: number): Promise<ProjectDetailResponse> => {
    const response = await axiosInstance.get(`/projects/${id}`);
    return response.data;
  },

  getByCode: async (code: string): Promise<Project> => {
    const response = await axiosInstance.get(`/projects/code/${code}`);
    return response.data;
  },

  create: async (data: ProjectCreate): Promise<Project> => {
    console.log('创建项目请求数据:', data);
    const response = await axiosInstance.post('/projects/', data);
    return response.data;
  },

  update: async (id: number, data: ProjectUpdate): Promise<Project> => {
    const response = await axiosInstance.put(`/projects/${id}`, data);
    return response.data;
  },

  delete: async (id: number, hardDelete: boolean = false): Promise<void> => {
    await axiosInstance.delete(`/projects/${id}`, { params: { hard_delete: hardDelete } });
  },

  restore: async (id: number): Promise<Project> => {
    const response = await axiosInstance.post(`/projects/${id}/restore`);
    return response.data;
  },

  getStats: async (id: number): Promise<ProjectStats> => {
    const response = await axiosInstance.get(`/projects/${id}/stats`);
    return response.data;
  },
};

export const versionApi = {
  list: async (params: {
    page?: number;
    page_size?: number;
    project_id?: number;
    status_filter?: string;
    search?: string;
  }): Promise<VersionListResponse> => {
    const response = await axiosInstance.get('/versions/', { params });
    return response.data;
  },

  listByProject: async (projectId: number, params?: {
    page?: number;
    page_size?: number;
    status_filter?: string;
    include_generating?: boolean;
  }): Promise<VersionListResponse> => {
    const response = await axiosInstance.get(`/versions/project/${projectId}`, { params });
    return response.data;
  },

  get: async (id: number): Promise<VersionDetailResponse> => {
    const response = await axiosInstance.get(`/versions/${id}`);
    return response.data;
  },

  create: async (data: VersionCreate, auto_generate: boolean = true, async_mode: boolean = false, signal?: AbortSignal): Promise<Version> => {
    const response = await axiosInstance.post('/versions/', data, {
      params: { 
        auto_generate: auto_generate ? 'true' : 'false',
        async_mode: async_mode ? 'true' : 'false'
      },
      timeout: 600000,  // 10分钟超时，同步生成需要等待LLM响应
      signal  // 支持取消请求
    });
    return response.data;
  },

  update: async (id: number, data: VersionUpdate): Promise<Version> => {
    const response = await axiosInstance.put(`/versions/${id}`, data);
    return response.data;
  },

  updateStatus: async (id: number, status: string, comment?: string): Promise<Version> => {
    const response = await axiosInstance.put(`/versions/${id}/status`, { status, comment });
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/versions/${id}`);
  },

  getStatusHistory: async (id: number): Promise<VersionStatusHistory> => {
    const response = await axiosInstance.get(`/versions/${id}/status-history`);
    return response.data;
  },

  generateAssets: async (id: number, sourceType: string = 'ai', content?: string): Promise<GenerateAssetsResponse> => {
    // content(可选) = 本次"新导入块"：若传入，后端只针对该块增量生成（新模块追加、同模块更新，不动其它模块）；
    // 不传则按版本整份需求文档生成。两步法同步生成实测需 ~16-20 分钟（分模块逐批 LLM），超时必须给足余量。
    const response = await axiosInstance.post(`/versions/${id}/generate-assets`, content ? { content } : null, {
      params: { source_type: sourceType },
      timeout: 2400000,  // 40 分钟
    });
    return response.data;
  },

  /** 跨版本复用用例：全模块模式（module）或勾选模式（case_ids），至少一项 */
  reuseCases: async (versionId: number, data: {
    source_version_id: number;
    case_ids?: number[];
    module?: string;
  }): Promise<{ success: boolean; message: string; reused_count: number; skipped_count: number; reused_ids: number[] }> => {
    const response = await axiosInstance.post(`/versions/${versionId}/reuse-cases`, data);
    return response.data;
  },

  /** 业务流 → 探索 → UI 用例 */
  generateUIFromBusinessFlow: async (id: number, params: {
    business_flow_text: string;
    base_url: string;
    username: string;
    password: string;
    force_explore?: boolean;
  }): Promise<BusinessFlowUIResponse> => {
    const response = await axiosInstance.post(
      `/business-flow/generate-ui-from-business-flow/${id}`,
      params,
      { timeout: 900000 }
    );
    return response.data;
  },
};

export const fileApi = {
  upload: async (file: File, onUploadProgress?: (progress: number) => void): Promise<FileUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axiosInstance.post('/files/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onUploadProgress) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onUploadProgress(progress);
        }
      },
    });
    return response.data;
  },
  
  getPreviewUrl: (filePath: string): string => {
    const baseUrl = axiosInstance.defaults.baseURL || '';
    return `${baseUrl}/files/preview/${filePath}`;
  },
  
  getDownloadUrl: (filePath: string): string => {
    const baseUrl = axiosInstance.defaults.baseURL || '';
    return `${baseUrl}/files/download/${filePath}`;
  },
  
  analyze: async (params: { content?: string; file_path?: string; document_type?: string }): Promise<DocumentAnalyzeResponse> => {
    const response = await axiosInstance.post('/files/analyze', params, {
      timeout: 120000,
    });
    return response.data;
  },
};

export interface FileUploadResponse {
  success: boolean;
  file_path: string;
  file_type: string;
  file_name: string;
  file_size: number;
  extracted_text?: string;
  message: string;
}

export interface DocumentModule {
  name: string;
  description: string;
  features: string[];
  priority: string;
}

export interface DocumentAnalyzeResponse {
  success: boolean;
  document_title: string;
  modules: DocumentModule[];
  markdown_content: string;
  stats: {
    total_modules: number;
    p0_count: number;
    p1_count: number;
    total_features: number;
  };
  message: string;
}

export interface Version {
  id: number;
  project_id: number;
  project?: {
    id: number;
    name: string;
    code: string;
  };
  version_number: string;
  version_name: string | null;
  description: string | null;
  requirement_doc: string | null;
  requirement_doc_file: string | null;
  requirement_doc_file_type: string | null;
  status: string;
  status_display: string;
  test_cases_count?: number;
  plan_start_date: string | null;
  plan_end_date: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface VersionDetailResponse extends Version {
  requirement_doc: string | null;
  requirement_doc_url: string | null;
  requirement_doc_file: string | null;
  requirement_doc_file_type: string | null;
  test_cases_count: number;
  test_plans_count: number;
}

export interface VersionListResponse {
  items: Version[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface VersionCreate {
  project_id: number;
  version_number: string;
  version_name?: string;
  description?: string;
  requirement_doc?: string;
  requirement_doc_file?: string;
  requirement_doc_file_type?: string;
  plan_start_date?: string;
  plan_end_date?: string;
}

export interface VersionUpdate {
  version_name?: string;
  description?: string;
  plan_start_date?: string;
  plan_end_date?: string;
  actual_start_date?: string;
  actual_end_date?: string;
}

export interface VersionStatusHistory {
  version_id: number;
  version_number: string;
  current_status: string;
  status_display: string;
  available_transitions: string[];
}

export interface GenerateAssetsResponse {
  success: boolean;
  message: string;
  data: {
    success: boolean;
    test_cases_count: number;
    analysis_summary?: {
      total_count?: number;
      p0_count?: number;
      coverage_analysis?: string;
      risk_points?: string[];
    };
  };
}

/** 业务流 → UI 用例 响应 */
export interface BusinessFlowUIResponse {
  success: boolean;
  ui_cases: Array<{
    case_id: string;
    title: string;
    module: string;
    steps: Array<{
      seq: number;
      action: string;
      args?: Record<string, any>;
      desc: string;
      assert?: boolean;
    }>;
  }>;
  ui_cases_count: number;
  explored_modules: string[];
  cached_modules: string[];
  elapsed_seconds: number;
  error?: string;
}

// ===== 场景编排 API =====

export interface SceneInfo {
  id: number;
  name: string;
  description?: string;
  scene_type: string;
  project_id: number;
  version_id?: number;
  status: string;
  config: Record<string, any>;
  item_count: number;
  items?: SceneItemInfo[];
  created_at?: string;
  updated_at?: string;
}

export interface SceneItemInfo {
  id: number;
  scene_id: number;
  case_id: number;
  case_type: string;
  sort_order: number;
  enabled: boolean;
  custom_params: Record<string, any>;
  /** 方案B：绑定的 WUI 实例（派生软删后执行时按逻辑 id 重解析） */
  wui_id?: string | null;
  /** 后端解析出的用例展示名（第3项；ui 条目=WUI title，api 条目可能为空） */
  case_name?: string;
  /** 后端解析出的用例所属模块（第3项；ui 条目=WUI test_data.module） */
  case_module?: string;
}

export const sceneApi = {
  list: async (params: { project_id?: number; scene_type?: string }): Promise<{ items: SceneInfo[]; total: number }> => {
    const response = await axiosInstance.get('/scenes/', { params });
    return response.data;
  },
  get: async (id: number): Promise<SceneInfo> => {
    const response = await axiosInstance.get(`/scenes/${id}`);
    return response.data;
  },
  create: async (data: { name: string; description?: string; scene_type: string; project_id: number; version_id?: number; config?: any }): Promise<SceneInfo> => {
    const response = await axiosInstance.post('/scenes/', data);
    return response.data;
  },
  update: async (id: number, data: Record<string, any>): Promise<SceneInfo> => {
    const response = await axiosInstance.put(`/scenes/${id}`, data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/scenes/${id}`);
  },
  addItems: async (sceneId: number, caseIds: number[], caseType: string): Promise<any> => {
    const response = await axiosInstance.post(`/scenes/${sceneId}/items`, { case_ids: caseIds, case_type: caseType });
    return response.data;
  },
  reorder: async (sceneId: number, itemIds: number[]): Promise<void> => {
    await axiosInstance.put(`/scenes/${sceneId}/items/reorder`, { item_ids: itemIds });
  },
  toggleItem: async (sceneId: number, itemId: number, enabled: boolean): Promise<void> => {
    await axiosInstance.put(`/scenes/${sceneId}/items/${itemId}/toggle`, { enabled });
  },
  removeItem: async (sceneId: number, itemId: number): Promise<void> => {
    await axiosInstance.delete(`/scenes/${sceneId}/items/${itemId}`);
  },
  execute: async (sceneId: number, params?: {
    version_id?: number;
    headless?: boolean;
    browser_mode?: string;
    slow_mo?: number;
  }): Promise<any> => {
    const response = await axiosInstance.post(`/scenes/${sceneId}/execute`, null, { params });
    return response.data;
  },
};