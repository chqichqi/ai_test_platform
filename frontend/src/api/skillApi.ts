import axiosInstance from './axiosConfig';
import {
  Skill,
  SkillCreate,
  SkillUpdate,
  SkillListResponse,
  SkillDetailResponse,
  SkillExample,
  SkillExampleCreate,
  SkillTestRequest,
  SkillTestResponse,
  SkillQueryParams,
} from '../types/skill';

export const skillApi = {
  // 获取SKILL列表
  list: async (params: SkillQueryParams): Promise<SkillListResponse> => {
    const response = await axiosInstance.get('/skills/', { params });
    return response.data;
  },

  // 获取SKILL详情
  get: async (id: number): Promise<SkillDetailResponse> => {
    const response = await axiosInstance.get(`/skills/${id}`);
    return response.data;
  },

  // 创建SKILL
  create: async (data: SkillCreate): Promise<Skill> => {
    const response = await axiosInstance.post('/skills/', data);
    return response.data;
  },

  // 更新SKILL
  update: async (id: number, data: SkillUpdate): Promise<Skill> => {
    const response = await axiosInstance.put(`/skills/${id}`, data);
    return response.data;
  },

  // 删除SKILL
  delete: async (id: number): Promise<void> => {
    await axiosInstance.delete(`/skills/${id}`);
  },

  // 复制SKILL
  copy: async (id: number): Promise<Skill> => {
    const response = await axiosInstance.post(`/skills/${id}/copy`);
    return response.data;
  },

  // 获取SKILL示例列表
  listExamples: async (skillId: number): Promise<SkillExample[]> => {
    const response = await axiosInstance.get(`/skills/${skillId}/examples`);
    return response.data;
  },

  // 创建SKILL示例
  createExample: async (skillId: number, data: SkillExampleCreate): Promise<SkillExample> => {
    const response = await axiosInstance.post(`/skills/${skillId}/examples`, data);
    return response.data;
  },

  // 获取SKILL统计
  getStats: async (id: number): Promise<any> => {
    const response = await axiosInstance.get(`/skills/${id}/stats`);
    return response.data;
  },

  // 导出SKILL
  export: async (id: number): Promise<any> => {
    const response = await axiosInstance.get(`/skills/${id}/export`);
    return response.data;
  },

  // 导入SKILL
  import: async (data: { skill_data: any; project_id?: number }): Promise<Skill> => {
    const response = await axiosInstance.post('/skills/import', data);
    return response.data;
  },

  // 测试SKILL
  test: async (id: number, data: SkillTestRequest): Promise<SkillTestResponse> => {
    const response = await axiosInstance.post(`/skills/${id}/test`, data);
    return response.data;
  },
};

export default skillApi;
