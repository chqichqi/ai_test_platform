import axiosInstance from './axiosConfig';

export interface NotificationChannel {
  id: number;
  project_id?: number;
  name: string;
  type: string;
  enabled: boolean;
  test_status?: string;
  created_at?: string;
}

export interface NotificationChannelDetail {
  id: number;
  project_id?: number;
  name: string;
  type: string;
  webhook_url?: string;
  secret?: string;
  email_config?: Record<string, any>;
  enabled: boolean;
  test_status?: string;
  test_message?: string;
  last_test_at?: string;
  created_at?: string;
}

export interface AlertRule {
  id: number;
  name: string;
  condition_type: string;
  enabled: boolean;
  trigger_count?: number;
  last_triggered_at?: string;
}

export interface NotificationHistory {
  id: number;
  channel_id: number;
  recipient?: string;
  subject: string;
  status: string;
  error_message?: string;
  sent_at?: string;
  created_at?: string;
}

export interface ChannelCreate {
  project_id?: number;
  name: string;
  type: string;
  webhook_url?: string;
  secret?: string;
  email_config?: Record<string, any>;
  enabled?: boolean;
}

export interface ChannelUpdate {
  name?: string;
  webhook_url?: string;
  secret?: string;
  email_config?: Record<string, any>;
  enabled?: boolean;
}

export interface AlertRuleCreate {
  project_id: number;
  name: string;
  description?: string;
  condition_type: string;
  condition_config?: Record<string, any>;
  channel_ids?: number[];
  receivers?: string[];
  custom_template?: string;
  enabled?: boolean;
}

export interface AlertRuleUpdate {
  name?: string;
  description?: string;
  condition_type?: string;
  condition_config?: Record<string, any>;
  channel_ids?: number[];
  receivers?: string[];
  custom_template?: string;
  enabled?: boolean;
}

export interface SendNotificationRequest {
  channel_id: number;
  title: string;
  content: string;
  recipients?: string[];
}

export interface NotificationOptions {
  channel_types: Array<{ value: string; label: string; icon: string }>;
  condition_types: Array<{ value: string; label: string }>;
}

export const notificationApi = {
  listChannels: async (projectId?: number, page = 1, pageSize = 20) => {
    const response = await axiosInstance.get('/notifications/channels', {
      params: { project_id: projectId, page, page_size: pageSize }
    });
    return response.data;
  },

  getChannel: async (id: number): Promise<NotificationChannelDetail> => {
    const response = await axiosInstance.get(`/notifications/channels/${id}`);
    return response.data;
  },

  createChannel: async (data: ChannelCreate): Promise<{ id: number; message: string }> => {
    const response = await axiosInstance.post('/notifications/channels', data);
    return response.data;
  },

  updateChannel: async (id: number, data: ChannelUpdate): Promise<{ message: string }> => {
    const response = await axiosInstance.put(`/notifications/channels/${id}`, data);
    return response.data;
  },

  deleteChannel: async (id: number): Promise<{ message: string }> => {
    const response = await axiosInstance.delete(`/notifications/channels/${id}`);
    return response.data;
  },

  testChannel: async (id: number): Promise<{ success: boolean; message: string }> => {
    const response = await axiosInstance.post(`/notifications/channels/${id}/test`);
    return response.data;
  },

  listRules: async (projectId: number, page = 1, pageSize = 20) => {
    const response = await axiosInstance.get('/notifications/rules', {
      params: { project_id: projectId, page, page_size: pageSize }
    });
    return response.data;
  },

  createRule: async (data: AlertRuleCreate): Promise<{ id: number; message: string }> => {
    const response = await axiosInstance.post('/notifications/rules', data);
    return response.data;
  },

  updateRule: async (id: number, data: AlertRuleUpdate): Promise<{ message: string }> => {
    const response = await axiosInstance.put(`/notifications/rules/${id}`, data);
    return response.data;
  },

  deleteRule: async (id: number): Promise<{ message: string }> => {
    const response = await axiosInstance.delete(`/notifications/rules/${id}`);
    return response.data;
  },

  sendNotification: async (data: SendNotificationRequest): Promise<{ success: boolean; message: string }> => {
    const response = await axiosInstance.post('/notifications/send', data);
    return response.data;
  },

  listHistory: async (
    projectId: number,
    channelId?: number,
    status?: string,
    page = 1,
    pageSize = 20
  ) => {
    const response = await axiosInstance.get('/notifications/history', {
      params: { project_id: projectId, channel_id: channelId, status, page, page_size: pageSize }
    });
    return response.data;
  },

  getOptions: async (): Promise<NotificationOptions> => {
    const response = await axiosInstance.get('/notifications/options');
    return response.data;
  }
};

export const CHANNEL_TYPE_OPTIONS = [
  { value: 'feishu', label: '飞书', icon: '📨' },
  { value: 'dingtalk', label: '钉钉', icon: '📱' },
  { value: 'wechat', label: '企业微信', icon: '💬' },
  { value: 'email', label: '邮件', icon: '📧' }
];

export const CONDITION_TYPE_OPTIONS = [
  { value: 'execution_failed', label: '测试执行失败' },
  { value: 'pass_rate_low', label: '通过率过低' },
  { value: 'performance_abnormal', label: '性能异常' },
  { value: 'ci_failed', label: 'CI构建失败' },
  { value: 'issue_created', label: '问题创建' },
  { value: 'issue_unresolved', label: '问题未解决' }
];

export const STATUS_OPTIONS = [
  { value: 'success', label: '成功', color: '#52c41a' },
  { value: 'failed', label: '失败', color: '#f5222d' },
  { value: 'pending', label: '等待', color: '#faad14' }
];