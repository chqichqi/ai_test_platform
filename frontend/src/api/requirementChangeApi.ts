import axiosInstance from './axiosConfig';

export interface ChangeSummary {
  added_modules: string[];
  modified_modules: string[];
  removed_modules?: string[];
  /** 兼容旧数据：旧字段 deleted_modules 已由 removed_modules 取代 */
  deleted_modules?: string[];
  unchanged_modules: string[];
  added_count: number;
  modified_count: number;
  deleted_count: number;
  unchanged_count: number;
}

export interface ModuleChangeAnalysis {
  module_name: string;
  change_type: string;
  old_description: string | null;
  new_description: string | null;
  impact_level: string;
  affected_test_cases: number[];
  affected_test_cases_count: number;
  suggested_action: string;
  suggested_reason: string;
}

export interface AnalyzeChangeResponse {
  success: boolean;
  batch_id: number;
  change_summary: ChangeSummary;
  detail_analysis: ModuleChangeAnalysis[];
  change_records: Array<{
    id: number;
    module_name: string;
    change_type: string;
    status: string;
  }>;
  total_affected_cases: number;
  total_related_cases?: number;
  estimated_new_cases: number;
  is_first_import?: boolean;
  message: string;
}

export interface RequirementChangeRecord {
  id: number;
  version_id: number;
  change_type: string;
  module_name: string;
  old_description: string | null;
  new_description: string | null;
  impact_level: string;
  affected_test_cases: number[];
  affected_test_cases_count: number;
  suggested_action: string | null;
  suggested_reason: string | null;
  status: string;
  action_taken: string | null;
  new_test_cases: number[];
  new_test_cases_count: number;
  created_by: string | null;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  processed_by: string | null;
  processed_at: string | null;
  error_message: string | null;
}

export interface RequirementChangeRecordListResponse {
  items: RequirementChangeRecord[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface RequirementChangeBatch {
  id: number;
  version_id: number;
  batch_name: string | null;
  batch_description: string | null;
  change_summary: ChangeSummary | null;
  added_count: number;
  modified_count: number;
  deleted_count: number;
  unchanged_count: number;
  total_affected_cases: number;
  total_new_cases: number;
  status: string;
  created_by: number | null;
  created_at: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  completed_at: string | null;
}

export interface RequirementChangeBatchListResponse {
  items: RequirementChangeBatch[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AffectedTestCase {
  id: number;
  name: string;
  module: string | null;
  status: string;
  priority: string;
  created_at: string | null;
}

export const requirementChangeApi = {
  analyzeChange: async (versionId: number, supplementRequirement: string): Promise<AnalyzeChangeResponse> => {
    const response = await axiosInstance.post('/requirement-changes/analyze', {
      version_id: versionId,
      supplement_requirement: supplementRequirement
    });
    return response.data;
  },

  uploadSupplement: async (
    versionId: number,
    file?: File,
    content?: string
  ): Promise<{ success: boolean; message: string; data: AnalyzeChangeResponse }> => {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const params = new URLSearchParams();
      params.append('version_id', versionId.toString());
      if (content) params.append('content', content);
      
      const response = await axiosInstance.post(
        `/requirement-changes/upload-supplement?${params.toString()}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      return response.data;
    } else {
      const response = await axiosInstance.post(
        `/requirement-changes/upload-supplement?version_id=${versionId}&content=${encodeURIComponent(content || '')}`
      );
      return response.data;
    }
  },

  uploadSupplementWithImages: async (
    versionId: number,
    files: File[],
    content?: string
  ): Promise<{ success: boolean; message: string; data: AnalyzeChangeResponse; ocr_processed?: number }> => {
    if (files.length === 0 && !content) {
      throw new Error('请提供文件或内容');
    }

    const formData = new FormData();
    
    const docFiles = files.filter(f => !/\.(png|jpg|jpeg|bmp|gif|webp)$/i.test(f.name));
    const imageFiles = files.filter(f => /\.(png|jpg|jpeg|bmp|gif|webp)$/i.test(f.name));
    
    if (docFiles.length > 0) {
      formData.append('doc_file', docFiles[0]);
    }
    
    imageFiles.forEach((img) => {
      formData.append('images', img);
    });
    
    if (content) {
      formData.append('content', content);
    }
    
    const params = new URLSearchParams();
    params.append('version_id', versionId.toString());
    
    const response = await axiosInstance.post(
      `/requirement-changes/upload-supplement-with-images?${params.toString()}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  },

  listChangeRecords: async (params: {
    version_id?: number;
    status?: string;
    change_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<RequirementChangeRecordListResponse> => {
    const queryParams = new URLSearchParams();
    if (params.version_id) queryParams.append('version_id', params.version_id.toString());
    if (params.status) queryParams.append('status', params.status);
    if (params.change_type) queryParams.append('change_type', params.change_type);
    if (params.page) queryParams.append('page', params.page.toString());
    if (params.page_size) queryParams.append('page_size', params.page_size.toString());
    
    const response = await axiosInstance.get(`/requirement-changes/records?${queryParams.toString()}`);
    return response.data;
  },

  getChangeRecord: async (recordId: number): Promise<RequirementChangeRecord> => {
    const response = await axiosInstance.get(`/requirement-changes/records/${recordId}`);
    return response.data;
  },

  approveChangeRecord: async (
    recordId: number,
    action: string,
    reviewComment?: string
  ): Promise<{ success: boolean; message: string; data: any }> => {
    const response = await axiosInstance.post(`/requirement-changes/records/${recordId}/approve`, {
      action,
      review_comment: reviewComment
    });
    return response.data;
  },

  rejectChangeRecord: async (
    recordId: number,
    reason: string
  ): Promise<{ success: boolean; message: string; record_id: number }> => {
    const response = await axiosInstance.post(
      `/requirement-changes/records/${recordId}/reject?reason=${encodeURIComponent(reason)}`
    );
    return response.data;
  },

  batchApproveChanges: async (
    versionId: number,
    approveAll: boolean = false,
    actions?: Array<{ module: string; action: string }>
  ): Promise<{ success: boolean; message: string; data: any }> => {
    const response = await axiosInstance.post(
      `/requirement-changes/batch-approve?version_id=${versionId}`,
      { approve_all: approveAll, actions },
      { timeout: 600000 }
    );
    return response.data;
  },

  listChangeBatches: async (params: {
    version_id?: number;
    page?: number;
    page_size?: number;
  }): Promise<RequirementChangeBatchListResponse> => {
    const response = await axiosInstance.get('/requirement-changes/batches', { params });
    return response.data;
  },

  getChangeBatch: async (batchId: number): Promise<RequirementChangeBatch> => {
    const response = await axiosInstance.get(`/requirement-changes/batches/${batchId}`);
    return response.data;
  },

  getBatchRecords: async (batchId: number): Promise<RequirementChangeRecordListResponse> => {
    const response = await axiosInstance.get(`/requirement-changes/batches/${batchId}/records`);
    return response.data;
  },

  getAffectedTestCases: async (
    recordId: number
  ): Promise<{
    test_cases: AffectedTestCase[];
    total: number;
    change_type: string;
    module_name: string;
  }> => {
    const response = await axiosInstance.get(
      `/requirement-changes/test-cases/affected?record_id=${recordId}`
    );
    return response.data;
  },

  batchUpdateTestCaseStatus: async (
    testCaseIds: number[],
    newStatus: string,
    reason?: string
  ): Promise<{ success: boolean; message: string; updated_count: number }> => {
    const params = new URLSearchParams();
    params.append('new_status', newStatus);
    if (reason) params.append('reason', reason);
    
    const response = await axiosInstance.post(
      `/requirement-changes/test-cases/batch-update-status?${params.toString()}`,
      testCaseIds
    );
    return response.data;
  },

  deleteChangeRecord: async (recordId: number): Promise<void> => {
    await axiosInstance.delete(`/requirement-changes/records/${recordId}`);
  },

  batchDeleteChangeRecords: async (recordIds: number[]): Promise<{ success: boolean; message: string; deleted_count: number; skipped_count: number }> => {
    const response = await axiosInstance.post('/requirement-changes/records/batch-delete', recordIds);
    return response.data;
  },

  deleteChangeBatch: async (batchId: number): Promise<void> => {
    await axiosInstance.delete(`/requirement-changes/batches/${batchId}`);
  },

  deleteAllPendingBatchesByVersion: async (versionId: number): Promise<void> => {
    await axiosInstance.delete(`/requirement-changes/batches/version/${versionId}`);
  }
};

export const CHANGE_TYPES = {
  ADDED: 'added',
  MODIFIED: 'modified',
  DELETED: 'deleted',
  UNCHANGED: 'unchanged'
};

export const CHANGE_ACTIONS = {
  GENERATE_NEW: 'generate_new',
  UPDATE_EXISTING: 'update_existing',
  DEPRECATE: 'deprecate',
  KEEP_OLD: 'keep_old',
  ARCHIVE: 'archive'
};

export const CHANGE_RECORD_STATUS = {
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed'
};

export const IMPACT_LEVELS = {
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low'
};

export const TEST_CASE_STATUS = {
  DRAFT: 'draft',
  PENDING_REVIEW: 'pending_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  DEPRECATED: 'deprecated',
  ARCHIVED: 'archived'
};