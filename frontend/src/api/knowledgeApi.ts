/**
 * 知识管理API服务
 */

import axiosInstance from './axiosConfig';

const API_BASE = '/knowledge';

export interface RagKnowledgeBase {
  id: string;
  name: string;
  description: string;
  project: string;
  version: string;
  documentCount: number;
  chunkCount: number;
  status: 'active' | 'inactive' | 'processing';
  hasGraph: boolean;
  chunkSize?: number;
  chunkMethod?: string;
  embeddingModel?: string;
  createdAt: string;
  updatedAt: string;
  documents?: Document[];
}

export interface Document {
  id: string;
  name: string;
  type: string;
  size: string;
  content?: string;
  status: string;
  uploadTime?: string;
  chunkCount?: number;
}

export interface KnowledgeGraph {
  id: string;
  name: string;
  sourceRag: string;
  entityCount: number;
  relationCount: number;
  tripleCount: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  createdAt: string;
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  color?: string;
  properties?: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  sourceName?: string;
  targetName?: string;
  properties?: Record<string, any>;
}

export interface KnowledgeGraphDetail extends KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CreateKnowledgeBaseRequest {
  name: string;
  description?: string;
  project?: string;
  version?: string;
  chunkSize?: number;
  chunkMethod?: string;
  embeddingModel?: string;
  enableOcr?: boolean;
}

export interface AddDocumentRequest {
  name: string;
  type: string;
  size: string;
  content?: string;
  filePath?: string;
}

const knowledgeApi = {
  listRagBases: async (params?: { skip?: number; limit?: number; search?: string }): Promise<{ items: RagKnowledgeBase[]; total: number }> => {
    const response = await axiosInstance.get(`${API_BASE}/rag`, { params });
    return response.data.data;
  },

  createRagBase: async (data: CreateKnowledgeBaseRequest): Promise<RagKnowledgeBase> => {
    const response = await axiosInstance.post(`${API_BASE}/rag`, data);
    return response.data.data;
  },

  getRagBase: async (id: string): Promise<RagKnowledgeBase> => {
    const response = await axiosInstance.get(`${API_BASE}/rag/${id}`);
    return response.data.data;
  },

  updateRagBase: async (id: string, data: Partial<CreateKnowledgeBaseRequest>): Promise<RagKnowledgeBase> => {
    const response = await axiosInstance.put(`${API_BASE}/rag/${id}`, data);
    return response.data.data;
  },

  deleteRagBase: async (id: string): Promise<void> => {
    await axiosInstance.delete(`${API_BASE}/rag/${id}`);
  },

  addDocument: async (kbId: string, data: AddDocumentRequest): Promise<Document> => {
    const response = await axiosInstance.post(`${API_BASE}/rag/${kbId}/documents`, data);
    return response.data.data;
  },

  deleteDocument: async (kbId: string, docId: string): Promise<void> => {
    await axiosInstance.delete(`${API_BASE}/rag/${kbId}/documents/${docId}`);
  },

  generateGraph: async (kbId: string, payload?: { name?: string; documents?: { content: string }[] }): Promise<{ graphId: number; entityCount: number; relationCount: number; status: string; usedLLM?: boolean }> => {
    const response = await axiosInstance.post(`${API_BASE}/rag/${kbId}/generate-graph`, payload || {});
    return response.data.data;
  },

  listGraphs: async (params?: { skip?: number; limit?: number; search?: string }): Promise<{ items: KnowledgeGraph[]; total: number }> => {
    const response = await axiosInstance.get(`${API_BASE}/graphs`, { params });
    return response.data.data;
  },

  getGraph: async (id: string): Promise<KnowledgeGraphDetail> => {
    const response = await axiosInstance.get(`${API_BASE}/graphs/${id}`);
    return response.data.data;
  },

  deleteGraph: async (id: string): Promise<void> => {
    await axiosInstance.delete(`${API_BASE}/graphs/${id}`);
  },

  getStatistics: async (): Promise<{
    rag: {
      totalKnowledgeBases: number;
      totalDocuments: number;
      totalChunks: number;
    };
    graph: {
      totalGraphs: number;
      totalEntities: number;
      totalRelations: number;
    };
  }> => {
    const response = await axiosInstance.get(`${API_BASE}/statistics`);
    return response.data.data;
  },

  vectorizeChunks: async (kbId: string): Promise<{ success: boolean; message: string; count: number }> => {
    const response = await axiosInstance.post(`${API_BASE}/rag/${kbId}/vectorize`);
    return response.data.data;
  },

  queryRag: async (query: string, knowledgeBaseId?: string, topK?: number): Promise<{
    success: boolean;
    answer?: string;
    sources?: Array<{ content: string; similarity: number }>;
  }> => {
    const response = await axiosInstance.post(`${API_BASE}/rag/query`, {
      query,
      knowledge_base_id: knowledgeBaseId,
      top_k: topK || 5,
    });
    return response.data.data;
  },
};

export default knowledgeApi;