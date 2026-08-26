import axiosInstance from './axiosConfig';

export interface SwaggerAutoGenerateRequest {
  project_id: number;
  version_id?: number;
  swagger_url: string;
  base_url?: string;
  include_normal?: boolean;
  include_error?: boolean;
  include_boundary?: boolean;
  include_auth?: boolean;
  max_cases_per_endpoint?: number;
}

export interface GeneratedApiTestCase {
  id: number;
  name: string;
  endpoint_path: string;
  method: string;
  case_type: string;
  priority: string;
  description?: string;
  preconditions?: string;
  test_steps?: Array<{step: number; action: string; expected: string}>;
  expected_result?: string;
  headers?: Record<string, string>;
  query_params?: Record<string, any>;
  request_body?: Record<string, any>;
  expected_status?: number;
  assert_rules?: Array<{type: string; field?: string; value?: any; description: string}>;
}

export interface SwaggerAutoGenerateResponse {
  success: boolean;
  message: string;
  definition_id?: number;
  endpoints_count: number;
  generated_count: number;
  test_cases: GeneratedApiTestCase[];
  generation_summary?: {
    total_endpoints: number;
    generated_cases: number;
    case_type_distribution: Record<string, number>;
    base_url: string;
    swagger_version: string;
  };
}

export interface ApiTestCase {
  id: number;
  project_id: number;
  endpoint_id?: number;
  version_id?: number;
  name: string;
  description?: string;
  method?: string;
  path?: string;
  base_url?: string;
  headers?: Record<string, string>;
  query_params?: Record<string, any>;
  path_params?: Record<string, string>;
  request_body?: Record<string, any>;
  expected_status?: number;
  expected_headers?: Record<string, string>;
  expected_body?: Record<string, any>;
  assert_rules?: Array<{type: string; field?: string; value?: any; description: string}>;
  preconditions?: string;
  test_steps?: Array<{step: number; action: string; expected: string}>;
  expected_result?: string;
  case_type: string;
  priority: string;
  status: string;
  tags?: string[];
  depends_on?: number[];
  variable_extractions?: Array<{name: string; source: string; json_path?: string; regex?: string}>;
  generated_by: string;
  created_at: string;
  updated_at?: string;
}

export interface ApiTestCaseListResponse {
  items: ApiTestCase[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiTestCaseCreate {
  project_id: number;
  endpoint_id?: number;
  version_id?: number;
  name: string;
  description?: string;
  method?: string;
  path?: string;
  base_url?: string;
  headers?: Record<string, string>;
  query_params?: Record<string, any>;
  path_params?: Record<string, string>;
  request_body?: Record<string, any>;
  expected_status?: number;
  expected_headers?: Record<string, string>;
  expected_body?: Record<string, any>;
  assert_rules?: Array<{type: string; field?: string; value?: any; description: string}>;
  case_type?: string;
  priority?: string;
  tags?: string[];
  depends_on?: number[];
  variable_extractions?: Array<{name: string; source: string; json_path?: string; regex?: string}>;
}

export interface ApiTestCaseUpdate {
  name?: string;
  description?: string;
  method?: string;
  path?: string;
  base_url?: string;
  headers?: Record<string, string>;
  query_params?: Record<string, any>;
  path_params?: Record<string, string>;
  request_body?: Record<string, any>;
  expected_status?: number;
  expected_headers?: Record<string, string>;
  expected_body?: Record<string, any>;
  assert_rules?: Array<{type: string; field?: string; value?: any; description: string}>;
  case_type?: string;
  priority?: string;
  tags?: string[];
  depends_on?: number[];
  variable_extractions?: Array<{name: string; source: string; json_path?: string; regex?: string}>;
  status?: string;
}

export interface ApiTestExecutionRequest {
  case_id: number;
  environment?: string;
  base_url?: string;
}

export interface ApiTestExecutionResponse {
  id: number;
  case_id: number;
  project_id: number;
  environment?: string;
  status: string;
  start_time?: string;
  end_time?: string;
  duration?: number;
  actual_status?: number;
  actual_headers?: Record<string, string>;
  actual_body?: Record<string, any>;
  error_message?: string;
  assert_results?: Array<{rule: string; passed: boolean; message: string}>;
  created_at: string;
}

export interface ApiTestVersionResponse {
  id: number;
  project_id: number;
  version_id?: number;
  name: string;
  version_number?: string;
  description?: string;
  is_api_test_only: boolean;
  query_version_id: number;
  test_cases_count: number;
  created_by?: string;
  created_at: string;
}

export interface ApiTestVersionListResponse {
  items: ApiTestVersionResponse[];
  total: number;
}

export interface ApiTestVersionCreate {
  project_id: number;
  version_id?: number;
  name: string;
  version_number?: string;
  description?: string;
  is_api_test_only?: boolean;
}

export interface BatchDeleteRequest {
  case_ids: number[];
}

export interface BatchExecuteRequest {
  case_ids: number[];
  base_url?: string;
  environment?: string;
}

export interface BatchExecuteResponse {
  total: number;
  passed: number;
  failed: number;
  error: number;
  results: Array<{
    case_id: number;
    name: string;
    status: string;
    duration?: number;
    actual_status?: number;
    message: string;
  }>;
}

export interface ApiTestExecutionListResponse {
  items: ApiTestExecutionResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiDefinition {
  id: number;
  project_id: number;
  name?: string;
  source_type?: string;
  source_url?: string;
  version?: string;
  base_url?: string;
  description?: string;
  imported_at?: string;
  created_at: string;
}

export interface ApiEndpoint {
  id: number;
  definition_id: number;
  path: string;
  method: string;
  tag?: string;
  summary?: string;
  description?: string;
  parameters?: Array<{name: string; in: string; required?: boolean; type?: string; description?: string}>;
  request_body?: Record<string, any>;
  responses?: Record<string, any>;
  deprecated: boolean;
}

export interface AuthConfig {
  enabled: boolean;
  auth_type: 'bearer_token' | 'basic_auth' | 'api_key' | 'oauth2' | 'cookie';
  login_url?: string;
  login_method?: string;
  login_headers?: Record<string, string>;
  login_body?: Record<string, any>;
  content_type?: string;
  credentials?: Record<string, string>;
  token_extraction?: TokenExtraction;
  token_injection?: TokenInjection;
  token_url?: string;
  client_id?: string;
  client_secret?: string;
  grant_type?: string;
  token_cache_duration?: number;
}

export interface TokenExtraction {
  source: 'body' | 'header' | 'cookie';
  json_path?: string;
  header_name?: string;
  cookie_name?: string;
}

export interface TokenInjection {
  location: 'header' | 'query' | 'cookie';
  header_name?: string;
  prefix?: string;
}

export interface ApiEnvironment {
  id: number;
  project_id: number;
  name: string;
  base_url?: string;
  variables?: Record<string, string>;
  headers?: Record<string, string>;
  auth_config?: AuthConfig;
  is_default: boolean;
  created_at: string;
}

export interface ReviewStatistics {
  project_id: number;
  total: number;
  draft: number;
  pending_review: number;
  approved: number;
  rejected: number;
}

export interface ReportData {
  project_id: number;
  version_id?: number;
  report_time: string;
  total: number;
  passed: number;
  failed: number;
  error: number;
  pass_rate: number;
  duration_stats: {
    avg_ms: number;
    max_ms: number;
    min_ms: number;
    total_ms: number;
  };
  case_type_stats: Record<string, { passed: number; failed: number; total: number }>;
  results: Array<{
    execution_id: number;
    case_id: number;
    case_name: string;
    method: string;
    path: string;
    status: string;
    duration?: number;
    actual_status?: number;
    error_message?: string;
    assert_results: Array<{ type?: string; field?: string; passed: boolean; message: string }>;
    start_time?: string;
  }>;
  assertion_summary: {
    total_asserts: number;
    passed_asserts: number;
    failed_asserts: number;
  };
  slowest_cases: Array<{ case_id: number; name: string; duration: number }>;
  most_failed_assertions: Array<{ message: string; count: number }>;
}

export interface TestAuthResponse {
  success: boolean;
  message: string;
  token_preview?: string;
  token_type?: string;
}

export interface FileHashResponse {
  file_name: string;
  file_size: number;
  md5?: string;
  sha1?: string;
  sha256?: string;
  mime_type?: string;
}

export const apiTestApi = {
  autoGenerateFromSwagger: async (request: SwaggerAutoGenerateRequest): Promise<SwaggerAutoGenerateResponse> => {
    const response = await axiosInstance.post('/api-tests/auto-generate', request, {
      timeout: 600000,
    });
    return response.data;
  },

  listTestCasesByVersion: async (versionId: number, params?: {
    page?: number;
    page_size?: number;
    case_type?: string;
    priority?: string;
    search?: string;
  }): Promise<ApiTestCaseListResponse> => {
    const response = await axiosInstance.get(`/api-tests/cases/version/${versionId}`, { params });
    return response.data;
  },

  listTestCasesByProject: async (projectId: number, params?: {
    include_unclassified?: boolean;
    page?: number;
    page_size?: number;
    case_type?: string;
    priority?: string;
    search?: string;
  }): Promise<ApiTestCaseListResponse> => {
    const response = await axiosInstance.get(`/api-tests/cases/project/${projectId}`, { params });
    return response.data;
  },

  listUnclassifiedTestCases: async (projectId: number, params?: {
    page?: number;
    page_size?: number;
    case_type?: string;
    priority?: string;
    search?: string;
  }): Promise<ApiTestCaseListResponse> => {
    const response = await axiosInstance.get(`/api-tests/cases/unclassified/${projectId}`, { params });
    return response.data;
  },

  listTestCases: async (params: {
    project_id: number;
    page?: number;
    page_size?: number;
    case_type?: string;
    priority?: string;
    search?: string;
  }): Promise<ApiTestCaseListResponse> => {
    const response = await axiosInstance.get('/api-tests/cases', { params });
    return response.data;
  },

  getTestCase: async (caseId: number): Promise<ApiTestCase> => {
    const response = await axiosInstance.get(`/api-tests/cases/${caseId}`);
    return response.data;
  },

  createTestCase: async (data: ApiTestCaseCreate): Promise<ApiTestCase> => {
    const response = await axiosInstance.post('/api-tests/cases', data);
    return response.data;
  },

  updateTestCase: async (caseId: number, data: ApiTestCaseUpdate): Promise<ApiTestCase> => {
    const response = await axiosInstance.put(`/api-tests/cases/${caseId}`, data);
    return response.data;
  },

  deleteTestCase: async (caseId: number): Promise<void> => {
    await axiosInstance.delete(`/api-tests/cases/${caseId}`);
  },

  executeTest: async (request: ApiTestExecutionRequest): Promise<ApiTestExecutionResponse> => {
    const response = await axiosInstance.post('/api-tests/execute', request);
    return response.data;
  },

  importSwagger: async (request: {
    project_id: number;
    source_type: string;
    source_url?: string;
    name?: string;
  }): Promise<ApiDefinition> => {
    const response = await axiosInstance.post('/api-tests/import', request);
    return response.data;
  },

  uploadSwaggerFile: async (projectId: number, file: File): Promise<ApiDefinition> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axiosInstance.post('/api-tests/import/file', formData, {
      params: { project_id: projectId },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  listDefinitions: async (projectId: number): Promise<ApiDefinition[]> => {
    const response = await axiosInstance.get(`/api-tests/definitions/${projectId}`);
    return response.data;
  },

  listEndpoints: async (definitionId: number, params?: {
    tag?: string;
    method?: string;
    page?: number;
    page_size?: number;
  }): Promise<{items: ApiEndpoint[]; total: number; page: number; page_size: number}> => {
    const response = await axiosInstance.get(`/api-tests/endpoints/${definitionId}`, { params });
    return response.data;
  },

  getTags: async (definitionId: number): Promise<{tags: string[]}> => {
    const response = await axiosInstance.get(`/api-tests/tags/${definitionId}`);
    return response.data;
  },

  generateCasesForEndpoint: async (request: {
    endpoint_id: number;
    include_normal?: boolean;
    include_error?: boolean;
    include_boundary?: boolean;
    include_auth?: boolean;
  }): Promise<{generated_count: number; test_cases: ApiTestCase[]}> => {
    const response = await axiosInstance.post('/api-tests/cases/generate', request);
    return response.data;
  },

  listEnvironments: async (projectId: number): Promise<ApiEnvironment[]> => {
    const response = await axiosInstance.get(`/api-tests/environments/${projectId}`);
    return response.data;
  },

  createEnvironment: async (data: {
    project_id: number;
    name: string;
    base_url?: string;
    variables?: Record<string, string>;
    headers?: Record<string, string>;
    auth_config?: Record<string, any>;
    is_default?: boolean;
  }): Promise<ApiEnvironment> => {
    const response = await axiosInstance.post('/api-tests/environments', data);
    return response.data;
  },

  getExecutionHistory: async (caseId: number, params?: {
    page?: number;
    page_size?: number;
  }): Promise<ApiTestExecutionListResponse> => {
    const response = await axiosInstance.get(`/api-tests/executions`, {
      params: { case_id: caseId, ...params }
    });
    return response.data;
  },

  batchDelete: async (request: BatchDeleteRequest): Promise<{message: string; deleted_count: number}> => {
    const response = await axiosInstance.post('/api-tests/cases/batch-delete', request);
    return response.data;
  },

  batchExecute: async (request: BatchExecuteRequest): Promise<BatchExecuteResponse> => {
    const response = await axiosInstance.post('/api-tests/cases/batch-execute', request, {
      timeout: 300000,
    });
    return response.data;
  },

  listApiTestVersions: async (projectId: number): Promise<ApiTestVersionListResponse> => {
    const response = await axiosInstance.get(`/api-tests/versions/${projectId}`);
    return response.data;
  },

  createApiTestVersion: async (data: ApiTestVersionCreate): Promise<ApiTestVersionResponse> => {
    const response = await axiosInstance.post('/api-tests/versions', data);
    return response.data;
  },

  deleteApiTestVersion: async (versionId: number): Promise<void> => {
    await axiosInstance.delete(`/api-tests/versions/${versionId}`);
  },

  // ===== 审批相关 =====
  submitForReview: async (caseId: number, comment?: string): Promise<{ message: string; case_id: number; status: string }> => {
    const response = await axiosInstance.post(`/api-tests/cases/${caseId}/submit-review`, { comment });
    return response.data;
  },

  reviewCase: async (caseId: number, action: 'approve' | 'reject', comment?: string): Promise<{ message: string; case_id: number; status: string }> => {
    const response = await axiosInstance.post(`/api-tests/cases/${caseId}/review`, { action, comment });
    return response.data;
  },

  getReviewStats: async (projectId?: number, versionId?: number): Promise<ReviewStatistics> => {
    const response = await axiosInstance.get('/api-tests/cases/review-statistics', { params: { project_id: projectId, version_id: versionId } });
    return response.data;
  },

  // ===== 导出相关 =====
  exportCases: async (params: {
    project_id?: number;
    version_id?: number;
    case_type?: string;
    priority?: string;
    search?: string;
    format: 'csv' | 'xlsx';
  }): Promise<Blob> => {
    const response = await axiosInstance.get('/api-tests/cases/export', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  // ===== 报告相关 =====
  generateReport: async (params: {
    project_id: number;
    version_id?: number;
    execution_ids?: number[];
  }): Promise<ReportData> => {
    const response = await axiosInstance.post('/api-tests/executions/report', params);
    return response.data;
  },

  exportReport: async (params: {
    project_id: number;
    version_id?: number;
    execution_ids?: string;
    format: 'html' | 'pdf';
  }): Promise<Blob> => {
    const response = await axiosInstance.get('/api-tests/executions/report/export', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  // ===== 环境鉴权相关 =====
  testEnvironmentAuth: async (environmentId: number, projectId: number, baseUrl?: string): Promise<TestAuthResponse> => {
    const response = await axiosInstance.post(`/api-tests/environments/${environmentId}/test-auth`, {
      environment_id: environmentId,
      project_id: projectId,
      base_url: baseUrl,
    });
    return response.data;
  },

  updateEnvironment: async (environmentId: number, data: {
    name?: string;
    base_url?: string;
    variables?: Record<string, string>;
    headers?: Record<string, string>;
    auth_config?: AuthConfig;
    is_default?: boolean;
  }): Promise<ApiEnvironment> => {
    const response = await axiosInstance.put(`/api-tests/environments/${environmentId}`, data);
    return response.data;
  },

  deleteEnvironment: async (environmentId: number): Promise<void> => {
    await axiosInstance.delete(`/api-tests/environments/${environmentId}`);
  },

  // ===== 文件Hash相关 =====
  getFileHash: async (file: File): Promise<FileHashResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axiosInstance.post('/api-tests/files/hash', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};