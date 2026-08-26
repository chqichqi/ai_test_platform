import axiosInstance from './axiosConfig';

export interface LLMConfig {
  id: string;
  name: string;
  provider: string;
  api_key_masked: string;
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
  status: 'pending' | 'success' | 'failed';
  last_test_at: string | null;
  last_test_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface LLMConfigCreate {
  name: string;
  provider: string;
  api_key: string;
  base_url?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface LLMConfigUpdate {
  name?: string;
  provider?: string;
  api_key?: string;
  base_url?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface ActiveLLMConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
}

export const llmConfigApi = {
  list: async (): Promise<LLMConfig[]> => {
    const response = await axiosInstance.get('/llm-configs');
    return response.data;
  },

  get: async (id: string): Promise<LLMConfig> => {
    const response = await axiosInstance.get(`/llm-configs/${id}`);
    return response.data;
  },

  create: async (data: LLMConfigCreate): Promise<LLMConfig> => {
    const response = await axiosInstance.post('/llm-configs', data);
    return response.data;
  },

  update: async (id: string, data: LLMConfigUpdate): Promise<LLMConfig> => {
    const response = await axiosInstance.put(`/llm-configs/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await axiosInstance.delete(`/llm-configs/${id}`);
  },

  test: async (id: string): Promise<{ success: boolean; message: string; response?: string }> => {
    const response = await axiosInstance.post(`/llm-configs/${id}/test`);
    return response.data;
  },

  activate: async (id: string): Promise<{ success: boolean; message: string }> => {
    const response = await axiosInstance.post(`/llm-configs/${id}/activate`);
    return response.data;
  },

  getActive: async (): Promise<ActiveLLMConfig | null> => {
    const response = await axiosInstance.get('/llm-configs/active/current');
    return response.data?.data || null;
  },
};

export default llmConfigApi;