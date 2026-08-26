import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider, theme, Spin } from 'antd';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider, useSelector } from 'react-redux';
import { store } from './store';
import { RootState } from './store';
import { useState, useEffect } from 'react';
import AuthLayout from './components/layout/AuthLayout';
import MainLayout from './components/layout/MainLayout';
import ProtectedRoute from './components/auth/ProtectedRoute';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import FunctionalTestPage from './pages/tests/FunctionalTestPage';
import PerformanceTestPage from './pages/tests/PerformanceTestPage';
import WebUIChatPage from './pages/tests/WebUIChatPage';
import ExecutionCenterPage from './pages/tests/ExecutionCenterPage';
import ReportsPage from './pages/reports/ReportsPage';
import SettingsPage from './pages/settings/SettingsPage';
import ProjectListPage from './pages/projects/ProjectListPage';
import ProjectDetailPage from './pages/projects/ProjectDetailPage';
import VersionDetailPage from './pages/versions/VersionDetailPage';
import GitRepositoryPage from './pages/git/GitRepositoryPage';
import IssueListPage from './pages/issues/IssueListPage';
import IssueDashboardPage from './pages/issues/IssueDashboardPage';
import NotificationPage from './pages/notifications/NotificationPage';
import CICDPage from './pages/cicd/CICDPage';
import SkillsPage from './pages/skills/SkillsPage';
import SkillDetailPage from './pages/skills/SkillDetailPage';
import RequirementChangeReviewPage from './pages/requirement_changes/RequirementChangeReviewPage';
import KnowledgeGraphVisualizationPage from './pages/knowledgeGraph/KnowledgeGraphVisualizationPage';
import DatabaseConfigWizard from './pages/db-config';
import dbConfigApi from './api/dbConfigApi';
import GenerationTaskNotifier from './components/common/GenerationTaskNotifier';

const queryClient = new QueryClient();

// 数据库配置守卫组件
const DbConfigGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [checking, setChecking] = useState(true);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const location = useLocation();

  useEffect(() => {
    const checkDbConfig = async () => {
      try {
        const status = await dbConfigApi.checkStatus();
        setConfigured(status.configured);
      } catch (error: any) {
        console.error('检查数据库配置失败:', error);
        setConfigured(true);
      } finally {
        setChecking(false);
      }
    };
    checkDbConfig();
  }, []);

  if (checking) {
    return (
      <div style={{ 
        height: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center' 
      }}>
        <Spin size="large" tip="正在检查系统配置..." />
      </div>
    );
  }

  if (configured === false && location.pathname !== '/db-config') {
    return <Navigate to="/db-config" replace />;
  }

  if (configured === true && location.pathname === '/db-config') {
    return <Navigate to="/auth/login" replace />;
  }

  return <>{children}</>;
};

const AppContent: React.FC = () => {
  const { colors } = useSelector((state: RootState) => state.theme);

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: colors.colorPrimary,
          colorSuccess: colors.colorSuccess,
          colorWarning: colors.colorWarning,
          colorError: colors.colorError,
          colorInfo: colors.colorInfo,
          borderRadius: 8,
          colorBgContainer: colors.colorBgContainer,
          colorBgLayout: colors.colorBgLayout,
          colorBgElevated: colors.colorBgElevated,
          colorText: colors.colorText,
          colorTextSecondary: colors.colorTextSecondary,
          colorBorder: colors.colorBorder,
        },
        algorithm: theme.defaultAlgorithm,
        components: {
          Menu: {
            itemBg: 'transparent',
            itemSelectedBg: `${colors.colorPrimary}15`,
            itemSelectedColor: colors.colorPrimary,
          },
          Card: {
            colorBgContainer: colors.cardBg,
          },
          Table: {
            headerBg: colors.colorPrimary,
            headerColor: '#ffffff',
            headerSortActiveBg: colors.colorPrimary,
            headerSortHoverBg: colors.colorPrimary,
            rowHoverBg: `${colors.colorPrimary}08`,
          },
          Tabs: {
            inkBarColor: colors.colorPrimary,
            itemActiveColor: colors.colorPrimary,
            itemSelectedColor: colors.colorPrimary,
            itemHoverColor: colors.colorPrimary,
            cardBg: colors.colorBgContainer,
          },
        },
      }}
    >
      <Router>
        <GenerationTaskNotifier />
        <DbConfigGuard>
          <Routes>
            {/* 数据库配置向导 */}
            <Route path="/db-config" element={<DatabaseConfigWizard />} />
            
            {/* 认证路由 */}
            <Route path="/auth" element={<AuthLayout />}>
              <Route path="login" element={<LoginPage />} />
              <Route path="register" element={<RegisterPage />} />
              <Route index element={<Navigate to="login" />} />
            </Route>
            
            {/* 主布局 - 包含左侧导航菜单 */}
            <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
              <Route index element={<Navigate to="/dashboard" />} />
              <Route path="dashboard" element={<DashboardPage />} />
              
              {/* 项目管理 */}
              <Route path="projects">
                <Route index element={<ProjectListPage />} />
                <Route path=":id" element={<ProjectDetailPage />} />
                <Route path=":projectId/versions/:id" element={<VersionDetailPage />} />
                <Route path=":projectId/versions/:versionId/change-review" element={<RequirementChangeReviewPage />} />
              </Route>
              
              {/* Git管理 */}
              <Route path="git">
                <Route index element={<GitRepositoryPage />} />
                <Route path="project/:projectId" element={<GitRepositoryPage />} />
              </Route>
              
              {/* 测试 / 用例管理 / 执行中心 */}
              <Route path="tests">
                <Route path="functional" element={<FunctionalTestPage />} />
                <Route path="api" element={<FunctionalTestPage />} />
                <Route path="performance" element={<PerformanceTestPage />} />
                <Route path="web-ui" element={<FunctionalTestPage />} />
                <Route path="web-ui-chat" element={<WebUIChatPage />} />
                <Route path="app" element={<FunctionalTestPage />} />
                <Route path="execution" element={<ExecutionCenterPage />} />
                <Route index element={<Navigate to="functional" />} />
              </Route>
              <Route path="testcases">
                <Route path="functional" element={<FunctionalTestPage />} />
                <Route index element={<Navigate to="functional" />} />
              </Route>
              
              {/* 知识图谱 */}
              <Route path="knowledge-graph">
                <Route path=":graphId" element={<KnowledgeGraphVisualizationPage />} />
              </Route>
              
              {/* 问题管理 */}
              <Route path="issues">
                <Route index element={<IssueListPage />} />
                <Route path="project/:projectId" element={<IssueListPage />} />
                <Route path="dashboard/:projectId" element={<IssueDashboardPage />} />
              </Route>
              
              {/* CI/CD */}
              <Route path="cicd">
                <Route index element={<CICDPage />} />
                <Route path="project/:projectId" element={<CICDPage />} />
              </Route>
              
              {/* 通知 */}
              <Route path="notifications">
                <Route index element={<NotificationPage />} />
                <Route path="project/:projectId" element={<NotificationPage />} />
              </Route>
              
              {/* 报表 */}
              <Route path="reports" element={<ReportsPage />} />
              
              {/* SKILL管理 */}
              <Route path="skills">
                <Route index element={<SkillsPage />} />
                <Route path=":id" element={<SkillDetailPage />} />
              </Route>
              
              {/* 设置 */}
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            
            {/* 兜底路由 */}
            <Route path="*" element={<Navigate to="/dashboard" />} />
          </Routes>
        </DbConfigGuard>
      </Router>
    </ConfigProvider>
  );
};

function App() {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <AppContent />
      </QueryClientProvider>
    </Provider>
  );
}

export default App;
