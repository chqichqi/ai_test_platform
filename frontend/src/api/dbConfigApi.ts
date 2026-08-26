import axios from 'axios';

const API_BASE = '/api/v1/system';

export interface DbConfigStatus {
  configured: boolean;
  db_type: string | null;
  message: string;
}

export interface MySQLConfig {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  version?: string;
  db_exists?: boolean;
  existing_tables?: string[];
  is_initialized?: boolean;
}

export interface InitStep {
  name: string;
  status: 'running' | 'success' | 'error';
  error?: string;
}

export interface InitDatabaseResult {
  success: boolean;
  message: string;
  steps?: InitStep[];
}

export const dbConfigApi = {
  // 检查数据库配置状态
  checkStatus: async (): Promise<DbConfigStatus> => {
    const response = await axios.get(`${API_BASE}/db-config/status`);
    return response.data.data;
  },

  // 测试MySQL连接
  testMySQLConnection: async (config: MySQLConfig): Promise<TestConnectionResult> => {
    const response = await axios.post(`${API_BASE}/db-config/test`, config);
    return response.data.data;
  },

  // 初始化数据库
  initDatabase: async (params: {
    db_type: string;
    host?: string;
    port?: number;
    database?: string;
    username?: string;
    password?: string;
    init_data?: boolean;
  }): Promise<InitDatabaseResult> => {
    const response = await axios.post(`${API_BASE}/db-config/init`, params);
    return response.data.data || response.data;
  },

  // 快速SQLite配置
  quickSQLite: async (): Promise<{ success: boolean; message: string; db_path?: string }> => {
    const response = await axios.post(`${API_BASE}/db-config/quick-sqlite`);
    return response.data.data;
  },

  // 获取配置信息
  getConfigInfo: async (): Promise<Partial<MySQLConfig> & { db_type?: string }> => {
    const response = await axios.get(`${API_BASE}/db-config/info`);
    return response.data.data;
  },
};

export default dbConfigApi;
