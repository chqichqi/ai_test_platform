import axiosInstance from './axiosConfig';

export type UserRole = 'external' | 'tester' | 'test_engineer' | 'test_manager' | 'admin';

export interface LoginResponse {
  user: {
    id: string;
    username: string;
    email: string;
    role: UserRole;
    roles: UserRole[];
    permissions: string[];
    is_superuser: boolean;
  };
  token: string;
  refreshToken: string;
}

export const login = async (username: string, password: string): Promise<LoginResponse> => {
  const params = new URLSearchParams();
  params.append('username', username);
  params.append('password', password);
  const response = await axiosInstance.post('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  });
  const responseData = response.data;
  if (!responseData.success) {
    throw new Error(responseData.message || '登录失败');
  }
  const backendUser = responseData.data.user;
  const backendRoles: UserRole[] = backendUser.roles && backendUser.roles.length > 0 ? backendUser.roles : [];
  const user: LoginResponse['user'] = {
    id: backendUser.id,
    username: backendUser.username,
    email: backendUser.email,
    role: backendRoles.length > 0 ? backendRoles[0] : 'external',
    roles: backendRoles,
    permissions: backendUser.permissions || [],
    is_superuser: backendUser.is_superuser || false,
  };
  return {
    user,
    token: responseData.data.access_token,
    refreshToken: responseData.data.refresh_token
  };
};

export const register = async (username: string, email: string, password: string): Promise<LoginResponse> => {
  const response = await axiosInstance.post('/auth/register', { username, email, password });
  return response.data;
};

export const refreshToken = async (refreshToken: string): Promise<{ token: string; refreshToken: string }> => {
  const response = await axiosInstance.post('/auth/refresh', { refresh_token: refreshToken });
  const responseData = response.data;
  if (!responseData.success) {
    throw new Error(responseData.message || 'Token刷新失败');
  }
  return {
    token: responseData.data.access_token,
    refreshToken: responseData.data.refresh_token
  };
};

export const logout = async (): Promise<void> => {
  const token = localStorage.getItem('token');
  if (token) {
    try {
      await axiosInstance.post('/auth/logout', { token });
    } catch {
      // ignore logout errors
    }
  }
};

export const getCurrentUser = async (): Promise<LoginResponse['user']> => {
  const response = await axiosInstance.get('/auth/me');
  return response.data;
};