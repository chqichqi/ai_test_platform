import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type UserRole = 'external' | 'tester' | 'test_engineer' | 'test_manager' | 'admin';

interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  roles: UserRole[];
  permissions: string[];
  is_superuser: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
}

const initialState: AuthState = {
  user: JSON.parse(localStorage.getItem('user') || 'null'),
  token: localStorage.getItem('token'),
  refreshToken: localStorage.getItem('refreshToken'),
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials: (state, action: PayloadAction<{ user: User; token: string; refreshToken?: string }>) => {
      state.user = action.payload.user;
      state.token = action.payload.token;
      state.refreshToken = action.payload.refreshToken || state.refreshToken;
      localStorage.setItem('token', action.payload.token);
      localStorage.setItem('user', JSON.stringify(action.payload.user));
      if (action.payload.refreshToken) {
        localStorage.setItem('refreshToken', action.payload.refreshToken);
      }
    },
    updateToken: (state, action: PayloadAction<{ token: string; refreshToken?: string }>) => {
      state.token = action.payload.token;
      localStorage.setItem('token', action.payload.token);
      if (action.payload.refreshToken) {
        state.refreshToken = action.payload.refreshToken;
        localStorage.setItem('refreshToken', action.payload.refreshToken);
      }
    },
    logout: (state) => {
      state.user = null;
      state.token = null;
      state.refreshToken = null;
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('user');
    },
  },
});

export const { setCredentials, updateToken, logout } = authSlice.actions;
export default authSlice.reducer;

export const selectUser = (state: { auth: AuthState }) => state.auth.user;
export const selectToken = (state: { auth: AuthState }) => state.auth.token;
export const selectPermissions = (state: { auth: AuthState }) => state.auth.user?.permissions || [];
export const selectRoles = (state: { auth: AuthState }) => state.auth.user?.roles || [];
export const selectIsSuperuser = (state: { auth: AuthState }) => state.auth.user?.is_superuser || false;

export const hasPermission = (state: { auth: AuthState }, permission: string): boolean => {
  const user = state.auth.user;
  if (!user) return false;
  if (user.is_superuser) return true;
  return user.permissions.includes(permission);
};

export const hasAnyPermission = (state: { auth: AuthState }, permissions: string[]): boolean => {
  const user = state.auth.user;
  if (!user) return false;
  if (user.is_superuser) return true;
  return permissions.some(p => user.permissions.includes(p));
};

export const hasAllPermissions = (state: { auth: AuthState }, permissions: string[]): boolean => {
  const user = state.auth.user;
  if (!user) return false;
  if (user.is_superuser) return true;
  return permissions.every(p => user.permissions.includes(p));
};

export const hasRole = (state: { auth: AuthState }, role: UserRole): boolean => {
  const user = state.auth.user;
  if (!user) return false;
  if (user.is_superuser) return true;
  return user.roles.includes(role);
};

export const hasAnyRole = (state: { auth: AuthState }, roles: UserRole[]): boolean => {
  const user = state.auth.user;
  if (!user) return false;
  if (user.is_superuser) return true;
  return roles.some(r => user.roles.includes(r));
};