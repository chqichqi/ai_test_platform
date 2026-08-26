import axiosInstance from './axiosConfig';

export interface RequirementDocument {
  id: number;
  version_id: number;
  name: string;
  type: string;
  content: string | null;
  file_url: string | null;
  file_size: number | null;
  parsed_content: Record<string, unknown> | null;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementDocumentListResponse {
  items: RequirementDocument[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const requirementApi = {
  listDocuments: async (params: {
    page?: number;
    page_size?: number;
    version_id?: number;
    status?: string;
    search?: string;
  }): Promise<RequirementDocumentListResponse> => {
    const response = await axiosInstance.get('/requirements/', { params });
    return response.data;
  },

  getDocument: async (id: number): Promise<RequirementDocument> => {
    const response = await axiosInstance.get(`/requirements/${id}`);
    return response.data;
  },

  createDocument: async (data: {
    version_id: number;
    name: string;
    type?: string;
    content?: string;
    file_url?: string;
  }): Promise<RequirementDocument> => {
    const response = await axiosInstance.post('/requirements/', data);
    return response.data;
  },

  uploadDocument: async (versionId: number, file: File): Promise<RequirementDocument> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axiosInstance.post(`/requirements/upload?version_id=${versionId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  parseDocument: async (id: number): Promise<RequirementDocument> => {
    const response = await axiosInstance.post(`/requirements/${id}/parse`);
    return response.data;
  },

  deleteDocument: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/requirements/${id}`);
  },

  updateAndRegenerate: async (id: number, data: { content?: string; name?: string }, regenerate: boolean = true): Promise<UpdateAndRegenerateResponse> => {
    const response = await axiosInstance.post(`/requirements/${id}/update-and-regenerate`, data, {
      params: { regenerate }
    });
    return response.data;
  },
};

export interface UpdateAndRegenerateResponse {
  success: boolean;
  message: string;
  data: {
    document_updated: boolean;
    regenerated: boolean;
    test_cases_count: number;
    analysis_summary?: {
      total_count?: number;
      p0_count?: number;
      coverage_analysis?: string;
      risk_points?: string[];
    };
  };
  document: RequirementDocument;
}

export interface TestStep {
  step: number;
  action: string;
  expected: string;
}

export interface TestCase {
  id: number;
  project_id: number;
  version_id: number | null;
  module: string | null;
  name: string;
  description: string | null;
  preconditions: string | null;
  test_steps: TestStep[] | null;
  expected_result: string | null;
  test_data: Record<string, unknown> | null;
  priority: string;
  case_type: string;
  execution_type: string;
  status: string;
  tags: string[] | null;
  generated_by: string;
  reviewer_id: number | null;
  reviewed_at: string | null;
  review_comment: string | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  // 方案B 版本化：逻辑用例 id / 修订号 / 派生来源（v 徽标 + 派生提示）
  logical_case_id?: number | null;
  revision_no?: number | null;
  derived_from_id?: number | null;
}

export interface TestCaseListResponse {
  items: TestCase[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const testCaseApi = {
  list: async (params: {
    page?: number;
    page_size?: number;
    project_id?: number;
    version_id?: number;
    module?: string;
    priority?: string;
    status?: string;
    search?: string;
  }): Promise<TestCaseListResponse> => {
    // 不使用 API_BASE，因为 axiosInstance 已经有 baseURL
    const response = await axiosInstance.get('/test-cases/', { params });
    return response.data;
  },

  get: async (id: number): Promise<TestCase> => {
    const response = await axiosInstance.get(`/test-cases/${id}`);
    return response.data;
  },

  create: async (data: {
    project_id: number;
    version_id?: number;
    module?: string;
    name: string;
    description?: string;
    preconditions?: string;
    test_steps?: TestStep[];
    expected_result?: string;
    test_data?: Record<string, unknown>;
    priority?: string;
    case_type?: string;
    execution_type?: string;
    tags?: string[];
  }): Promise<TestCase> => {
    const response = await axiosInstance.post('/test-cases/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<{
    module: string;
    name: string;
    description: string;
    preconditions: string;
    test_steps: TestStep[];
    expected_result: string;
    test_data: Record<string, unknown>;
    priority: string;
    case_type: string;
    execution_type: string;
    tags: string[];
    status: string;
  }>): Promise<TestCase> => {
    const response = await axiosInstance.put(`/test-cases/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/test-cases/${id}`);
  },

  review: async (id: number, approved: boolean, comment?: string): Promise<TestCase> => {
    const params = new URLSearchParams();
    params.append('approved', String(approved));
    if (comment) params.append('comment', comment);
    const response = await axiosInstance.post(`/test-cases/${id}/review?${params.toString()}`);
    return response.data;
  },

  getModules: async (projectId: number): Promise<string[]> => {
    const response = await axiosInstance.get(`/test-cases/modules/${projectId}`);
    return response.data.modules || [];
  },
};