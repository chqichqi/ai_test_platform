import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type ThemeMode = 'tech-color' | 'ocean-breeze' | 'sunset-glow';

export interface ThemeColors {
  colorPrimary: string;
  colorSuccess: string;
  colorWarning: string;
  colorError: string;
  colorInfo: string;
  colorBgContainer: string;
  colorBgLayout: string;
  colorBgElevated: string;
  colorText: string;
  colorTextSecondary: string;
  colorBorder: string;
  gradientPrimary: string;
  gradientSecondary: string;
  siderBg: string;
  siderBorder: string;
  siderText: string;
  siderTextSecondary: string;
  siderHoverBg: string;
  headerBg: string;
  cardBg: string;
  cardBorder: string;
  menuSelectedBg: string;
  menuSelectedColor: string;
  glowShadow: string;
  siderBgTint: string;
  pageBgTint: string;
}

export const THEMES: Record<ThemeMode, { name: string; nameEn: string; description: string; icon: string; colors: ThemeColors }> = {
  'tech-color': {
    name: '炫彩科技',
    nameEn: 'Tech Color',
    description: '明亮炫彩，充满科技感',
    icon: 'ThunderboltOutlined',
    colors: {
      colorPrimary: '#6366f1',
      colorSuccess: '#10b981',
      colorWarning: '#f59e0b',
      colorError: '#ef4444',
      colorInfo: '#3b82f6',
      colorBgContainer: '#ffffff',
      colorBgLayout: '#f8f7ff',
      colorBgElevated: '#ffffff',
      colorText: '#1e293b',
      colorTextSecondary: '#64748b',
      colorBorder: 'rgba(99, 102, 241, 0.12)',
      gradientPrimary: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)',
      gradientSecondary: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
      siderBg: 'linear-gradient(180deg, #3730a3 0%, #312e81 100%)',
      siderBorder: 'rgba(99, 102, 241, 0.3)',
      siderText: '#ffffff',
      siderTextSecondary: '#e0e7ff',
      siderHoverBg: 'rgba(99, 102, 241, 0.2)',
      headerBg: 'rgba(255, 255, 255, 0.95)',
      cardBg: 'rgba(255, 255, 255, 0.98)',
      cardBorder: 'rgba(99, 102, 241, 0.08)',
      menuSelectedBg: 'linear-gradient(90deg, rgba(99, 102, 241, 0.35) 0%, rgba(139, 92, 246, 0.25) 100%)',
      menuSelectedColor: '#ffffff',
      glowShadow: '0 4px 20px rgba(99, 102, 241, 0.15)',
      siderBgTint: 'rgba(99, 102, 241, 0.08)',
      pageBgTint: 'rgba(99, 102, 241, 0.03)',
    },
  },
  'ocean-breeze': {
    name: '海洋微风',
    nameEn: 'Ocean Breeze',
    description: '清新淡雅，宁静致远',
    icon: 'CloudOutlined',
    colors: {
      colorPrimary: '#0891b2',
      colorSuccess: '#059669',
      colorWarning: '#d97706',
      colorError: '#dc2626',
      colorInfo: '#0284c7',
      colorBgContainer: '#ffffff',
      colorBgLayout: '#f0fdff',
      colorBgElevated: '#ffffff',
      colorText: '#0f172a',
      colorTextSecondary: '#475569',
      colorBorder: 'rgba(8, 145, 178, 0.15)',
      gradientPrimary: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 50%, #0e7490 100%)',
      gradientSecondary: 'linear-gradient(135deg, #22d3ee 0%, #06b6d4 100%)',
      siderBg: 'linear-gradient(180deg, #155e75 0%, #134e4a 100%)',
      siderBorder: 'rgba(8, 145, 178, 0.3)',
      siderText: '#ffffff',
      siderTextSecondary: '#cffafe',
      siderHoverBg: 'rgba(8, 145, 178, 0.25)',
      headerBg: 'rgba(255, 255, 255, 0.95)',
      cardBg: 'rgba(255, 255, 255, 0.98)',
      cardBorder: 'rgba(8, 145, 178, 0.1)',
      menuSelectedBg: 'linear-gradient(90deg, rgba(6, 182, 212, 0.35) 0%, rgba(8, 145, 178, 0.25) 100%)',
      menuSelectedColor: '#ffffff',
      glowShadow: '0 4px 20px rgba(8, 145, 178, 0.15)',
      siderBgTint: 'rgba(8, 145, 178, 0.08)',
      pageBgTint: 'rgba(8, 145, 178, 0.03)',
    },
  },
  'sunset-glow': {
    name: '暮光暖阳',
    nameEn: 'Sunset Glow',
    description: '温暖柔和，舒适惬意',
    icon: 'SunOutlined',
    colors: {
      colorPrimary: '#ea580c',
      colorSuccess: '#16a34a',
      colorWarning: '#ca8a04',
      colorError: '#dc2626',
      colorInfo: '#c2410c',
      colorBgContainer: '#ffffff',
      colorBgLayout: '#fffbf5',
      colorBgElevated: '#ffffff',
      colorText: '#1c1917',
      colorTextSecondary: '#57534e',
      colorBorder: 'rgba(234, 88, 12, 0.15)',
      gradientPrimary: 'linear-gradient(135deg, #f97316 0%, #ea580c 50%, #c2410c 100%)',
      gradientSecondary: 'linear-gradient(135deg, #fb923c 0%, #f97316 100%)',
      siderBg: 'linear-gradient(180deg, #9a3412 0%, #7c2d12 100%)',
      siderBorder: 'rgba(234, 88, 12, 0.3)',
      siderText: '#ffffff',
      siderTextSecondary: '#ffedd5',
      siderHoverBg: 'rgba(234, 88, 12, 0.25)',
      headerBg: 'rgba(255, 255, 255, 0.95)',
      cardBg: 'rgba(255, 255, 255, 0.98)',
      cardBorder: 'rgba(234, 88, 12, 0.1)',
      menuSelectedBg: 'linear-gradient(90deg, rgba(249, 115, 22, 0.35) 0%, rgba(234, 88, 12, 0.25) 100%)',
      menuSelectedColor: '#ffffff',
      glowShadow: '0 4px 20px rgba(234, 88, 12, 0.15)',
      siderBgTint: 'rgba(234, 88, 12, 0.08)',
      pageBgTint: 'rgba(234, 88, 12, 0.03)',
    },
  },
};

interface ThemeState {
  mode: ThemeMode;
  colors: ThemeColors;
}

const getStoredTheme = (): ThemeMode => {
  const stored = localStorage.getItem('theme-mode');
  if (stored && (stored === 'tech-color' || stored === 'ocean-breeze' || stored === 'sunset-glow')) {
    return stored;
  }
  return 'tech-color';
};

const initialState: ThemeState = {
  mode: getStoredTheme(),
  colors: THEMES[getStoredTheme()].colors,
};

const themeSlice = createSlice({
  name: 'theme',
  initialState,
  reducers: {
    setTheme: (state, action: PayloadAction<ThemeMode>) => {
      state.mode = action.payload;
      state.colors = THEMES[action.payload].colors;
      localStorage.setItem('theme-mode', action.payload);
    },
  },
});

export const { setTheme } = themeSlice.actions;
export default themeSlice.reducer;