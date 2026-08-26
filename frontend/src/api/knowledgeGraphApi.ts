/**
 * 知识图谱API封装
 * 提供：生成触发、进度查询、详情查看、列表查询等接口
 */

import axiosInstance from './axiosConfig';

// ==================== 类型定义 ====================

export interface KnowledgeGraphGenerateRequest {
  version_id?: number | null; // 项目级图谱，版本可空
  project_id: number;
  mode?: 'existing' | 'crawl'; // existing=基于已有探索结果合成（默认，零爬取）；crawl=全站深度爬取
  base_url: string;
  login_username: string;
  login_password: string;
  exploration_strategy?: 'quick' | 'normal' | 'deep';
  skip_tenant?: boolean;
}

export interface KnowledgeGraphResponse {
  id: number;
  project_id: number;
  version_id: number | null; // 最近更新来源版本（项目唯一，可空）
  graph_name: string;
  base_url: string;
  exploration_strategy: string;
  exploration_status: 'pending' | 'running' | 'completed' | 'failed';
  progress_percentage: number;
  current_page: string | null;
  page_count: number;
  menu_count: number;
  element_count: number;
  confidence_score: number;
  error_message?: string | null; // 失败原因（failed 状态时展示）
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string | null;
}

export interface KnowledgeGraphDetailResponse {
  id: number;
  project_id: number;
  version_id: number | null; // 最近更新来源版本（项目唯一，可空）
  graph_name: string;
  base_url: string;
  exploration_strategy: string;
  exploration_status: string;
  progress_percentage: number;
  current_page: string | null;
  error_message: string | null;
  
  // 爬取数据
  pages: any[];
  menus: any[];
  elements: any[];
  forms: any[];
  tables: any[];
  flows: any[];
  api_calls: any[];
  dependencies: any[];
  // 逐页快照（可视化下钻：页面 → 元素归属）
  snapshots: any[];
  
  // 统计信息
  page_count: number;
  menu_count: number;
  element_count: number;
  flow_count: number;
  api_count: number;
  
  // 质量评估
  confidence_score: number;
  locator_validation_rate: number;
  
  // 时间信息
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string | null;
}

export interface KnowledgeGraphProgressResponse {
  graph_id: number;
  exploration_status: string;
  progress_percentage: number;
  current_page: string | null;
  error_message: string | null;
  page_count: number;
  menu_count: number;
  element_count: number;
}

export interface KnowledgeGraphStatsResponse {
  total_graphs: number;
  completed_graphs: number;
  running_graphs: number;
  failed_graphs: number;
  total_pages: number;
  total_elements: number;
  total_apis: number;
}

// ==================== API函数 ====================

/**
 * 触发知识图谱生成（异步）
 */
export const generateKnowledgeGraph = async (request: KnowledgeGraphGenerateRequest) => {
  const response = await axiosInstance.post('/knowledge-graph/generate', request);
  return response.data;
};

/**
 * 触发知识图谱生成（同步，用于测试）
 */
export const generateKnowledgeGraphSync = async (request: KnowledgeGraphGenerateRequest) => {
  const response = await axiosInstance.post('/knowledge-graph/generate-sync', request);
  return response.data;
};

/**
 * 查询知识图谱生成进度
 */
export const getKnowledgeGraphProgress = async (graphId: number): Promise<KnowledgeGraphProgressResponse> => {
  const response = await axiosInstance.get(`/knowledge-graph/progress/${graphId}`);
  return response.data;
};

/**
 * 获取知识图谱详情
 */
export const getKnowledgeGraphDetail = async (graphId: number): Promise<KnowledgeGraphDetailResponse> => {
  const response = await axiosInstance.get(`/knowledge-graph/${graphId}`);
  return response.data;
};

/**
 * 查询版本的知识图谱列表
 */
export const listKnowledgeGraphsByVersion = async (versionId: number): Promise<KnowledgeGraphResponse[]> => {
  const response = await axiosInstance.get(`/knowledge-graph/version/${versionId}`);
  return response.data;
};

/**
 * 查询项目的知识图谱列表
 */
export const listKnowledgeGraphsByProject = async (projectId: number): Promise<KnowledgeGraphResponse[]> => {
  const response = await axiosInstance.get(`/knowledge-graph/project/${projectId}`);
  return response.data;
};

/**
 * 查询正在运行的知识图谱任务
 */
export const getRunningKnowledgeGraphs = async (): Promise<KnowledgeGraphProgressResponse[]> => {
  const response = await axiosInstance.get('/knowledge-graph/running');
  return response.data;
};

/**
 * 获取知识图谱统计信息
 */
export const getKnowledgeGraphStats = async (): Promise<KnowledgeGraphStatsResponse> => {
  const response = await axiosInstance.get('/knowledge-graph/stats');
  return response.data;
};

/**
 * 删除知识图谱
 */
export const deleteKnowledgeGraph = async (graphId: number) => {
  const response = await axiosInstance.delete(`/knowledge-graph/${graphId}`);
  return response.data;
};

/**
 * 轮询知识图谱进度（定时查询，支持取消）
 * @param isActive 每轮请求前检查；返回 false 则立即停止（组件卸载/用户取消）
 */
export const pollKnowledgeGraphProgress = async (
  graphId: number,
  onProgress: (progress: KnowledgeGraphProgressResponse) => void,
  interval: number = 3000, // 3秒间隔
  maxAttempts: number = 100, // 最大查询次数（约5分钟）
  isActive?: () => boolean
): Promise<KnowledgeGraphProgressResponse | null> => {
  let attempts = 0;

  while (true) {
    if (isActive && !isActive()) return null; // 已取消/已卸载

    const progress = await getKnowledgeGraphProgress(graphId);
    onProgress(progress);

    // 检查是否完成或失败
    if (progress.exploration_status === 'completed' || progress.exploration_status === 'failed') {
      return progress;
    }

    // 检查是否超过最大次数
    attempts++;
    if (attempts >= maxAttempts) {
      throw new Error('轮询超时：超过最大查询次数');
    }

    // 继续轮询
    await new Promise(resolve => setTimeout(resolve, interval));
  }
};

// ==================== 导出API对象 ====================

export const knowledgeGraphApi = {
  generate: generateKnowledgeGraph,
  generateSync: generateKnowledgeGraphSync,
  getProgress: getKnowledgeGraphProgress,
  getDetail: getKnowledgeGraphDetail,
  listByVersion: listKnowledgeGraphsByVersion,
  listByProject: listKnowledgeGraphsByProject,
  getRunning: getRunningKnowledgeGraphs,
  getStats: getKnowledgeGraphStats,
  delete: deleteKnowledgeGraph,
  pollProgress: pollKnowledgeGraphProgress,
};

export default knowledgeGraphApi;