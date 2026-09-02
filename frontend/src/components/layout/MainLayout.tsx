import React, { useState, useMemo, useEffect } from 'react';
import { Layout, Menu, Button, Dropdown, Typography, Badge, Tooltip, ConfigProvider, theme, Modal, Spin } from 'antd';
import { 
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  BarChartOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  // SearchOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  BulbOutlined,
  SyncOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { logout } from '../../store/slices/authSlice';
import { openProgressModal } from '../../store/slices/taskProgressSlice';
import { RootState } from '../../store';
import type { MenuProps } from 'antd';
import { generationTaskApi, GenerationTask } from '../../api/generationTaskApi';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { colors } = useSelector((state: RootState) => state.theme);
  const [notifications] = useState(3);
  const [runningTasks, setRunningTasks] = useState<GenerationTask[]>([]);
  const [taskModalVisible, setTaskModalVisible] = useState(false);

  // 轮询运行中的任务
  useEffect(() => {
    const fetchRunningTasks = async () => {
      try {
        const taskList = await generationTaskApi.listTasks({
          status: 'running',
          limit: 5
        });
        setRunningTasks(taskList.tasks);
      } catch (error) {
        console.error('获取运行任务失败', error);
      }
    };

    fetchRunningTasks();
    const interval = setInterval(fetchRunningTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  // 页面标题映射
  const getPageTitle = () => {
    const path = location.pathname;
    const titles: Record<string, string> = {
      '/dashboard': '仪表板',
      '/projects': '项目版本',
      '/git': 'Git管理',
      '/testcases/functional': '功能用例',
      '/tests/functional': '功能用例',
      '/tests/api': 'API用例 / API测试',
      '/tests/web-ui': 'UI用例 / UI测试',
      '/tests/web-ui-chat': 'UI用例 AI 生成',
      '/tests/performance': '压力测试',
      '/tests/app': 'APP测试',
      '/issues': '问题管理',
      '/reports': '测试报告',
      '/cicd': 'CI/CD集成',
      '/notifications': '通知告警',
      '/skills': 'SKILL管理',
      '/settings': '系统设置',
      '/knowledge': '知识库管理',
      '/knowledge/graph': '知识图谱',
      '/rag': 'RAG知识库',
      '/rag/upload': '文档上传',
      '/rag/query': 'RAG 查询',
      '/requirements': '需求管理',
    };
    // 精确匹配
    if (titles[path]) return titles[path];
    // 前缀匹配（如 /projects/1/versions/2 → 项目及版本）
    if (path.startsWith('/projects/')) return '项目及版本';
    if (path.startsWith('/testcases/')) return '用例管理';
    if (path.startsWith('/tests/')) return '用例管理 / 执行中心';
    return 'AI Agent 测试平台';
  };

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '仪表板',
    },
    {
      key: '/projects',
      icon: <DatabaseOutlined />,
      label: '项目版本',
    },
    {
      key: 'testcases',
      icon: <FileTextOutlined />,
      label: '用例管理',
      children: [
        { key: '/testcases/functional', label: '功能用例' },
        { key: '/tests/web-ui', label: 'UI用例' },
        { key: '/tests/api', label: 'API用例' },
      ],
    },
    {
      key: 'execution',
      icon: <ThunderboltOutlined />,
      label: '执行中心',
      children: [
        { key: '/tests/execution?type=ui', label: 'UI测试' },
        { key: '/tests/execution?type=api', label: 'API测试' },
        { key: '/tests/execution?type=app', label: 'APP测试' },
        { key: '/tests/execution?type=performance', label: '压力测试' },
      ],
    },
    {
      key: '/reports',
      icon: <BarChartOutlined />,
      label: '测试报告',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '系统设置',
    },
  ];

  const handleMenuClick = (e: any) => {
    navigate(e.key);
  };

  const handleLogout = () => {
    dispatch(logout());
    navigate('/auth/login');
  };

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '账号设置',
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: handleLogout,
    },
  ];

  const selectedKeys = [location.pathname];
  const openKeys = collapsed ? [] : (
    location.pathname.startsWith('/tests/') || location.pathname.startsWith('/testcases/')
      ? ['testcases', 'execution']
      : [location.pathname.split('/')[1]]
  );

const menuStyles = useMemo(() => `
    .custom-theme-menu .ant-menu-item-selected {
      background: ${colors.menuSelectedBg} !important;
      border-radius: 8px;
      margin: 4px 8px;
      box-shadow: 0 0 20px ${colors.colorPrimary}40;
    }
    .custom-theme-menu .ant-menu-item-selected::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 4px;
      height: 70%;
      background: ${colors.gradientPrimary};
      border-radius: 0 2px 2px 0;
      box-shadow: 0 0 8px ${colors.colorPrimary};
    }
    .custom-theme-menu .ant-menu-item-selected .ant-menu-title-content {
      background: ${colors.gradientPrimary};
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 700;
      text-shadow: none;
      filter: drop-shadow(0 0 12px ${colors.colorPrimary}) drop-shadow(0 0 4px ${colors.colorPrimary}80);
    }
    .custom-theme-menu .ant-menu-item {
      margin: 4px 8px;
      border-radius: 8px;
    }
    .custom-theme-menu .ant-menu-item:not(.ant-menu-item-selected) .ant-menu-title-content {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 500;
    }
    .custom-theme-menu .ant-menu-item:hover {
      background: ${colors.siderHoverBg} !important;
      border-radius: 8px;
    }
    .custom-theme-menu .ant-menu-item:hover .ant-menu-title-content {
      background: ${colors.gradientPrimary};
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 600;
      filter: drop-shadow(0 0 6px ${colors.colorPrimary}60);
    }
    .custom-theme-menu .ant-menu-submenu-selected > .ant-menu-submenu-title .ant-menu-title-content {
      background: ${colors.gradientPrimary};
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 600;
      filter: drop-shadow(0 0 8px ${colors.colorPrimary}60);
    }
    .custom-theme-menu .ant-menu-submenu-title {
      margin: 4px 8px;
      border-radius: 8px;
    }
    .custom-theme-menu .ant-menu-submenu-title .ant-menu-title-content {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 500;
    }
    .custom-theme-menu .ant-menu-submenu-title:hover {
      background: ${colors.siderHoverBg} !important;
      border-radius: 8px;
    }
    .custom-theme-menu .ant-menu-submenu-title:hover .ant-menu-title-content {
      background: ${colors.gradientPrimary};
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      filter: drop-shadow(0 0 6px ${colors.colorPrimary}60);
    }
    .custom-theme-menu .ant-menu-sub {
      background: rgba(255, 255, 255, 0.05) !important;
      border-radius: 8px;
      margin: 4px 8px;
    }
    .custom-theme-menu .ant-menu-sub .ant-menu-item-selected .ant-menu-title-content {
      background: ${colors.gradientPrimary};
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 700;
      filter: drop-shadow(0 0 10px ${colors.colorPrimary});
    }
    .custom-theme-menu .ant-menu-sub .ant-menu-item .ant-menu-title-content {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .custom-theme-menu .ant-menu-item-selected .ant-menu-item-icon {
      color: ${colors.colorPrimary} !important;
      filter: drop-shadow(0 0 6px ${colors.colorPrimary});
    }
    .custom-theme-menu .ant-menu-item:hover .ant-menu-item-icon {
      color: ${colors.colorPrimary} !important;
    }
    .custom-theme-menu .ant-menu-item-icon {
      color: #a78bfa;
    }
  `, [colors]);

  return (
    <>
      <style>{menuStyles}</style>
      <Layout style={{ minHeight: '100vh', background: `linear-gradient(135deg, ${colors.colorBgLayout} 0%, ${colors.pageBgTint} 100%)` }}>
      <ConfigProvider
        theme={{
          algorithm: theme.darkAlgorithm,
          components: {
            Menu: {
              itemColor: colors.siderTextSecondary,
              itemHoverColor: '#ffffff',
              itemSelectedColor: '#ffffff',
              itemBg: 'transparent',
              itemHoverBg: colors.siderHoverBg,
              itemSelectedBg: 'transparent',
              subMenuItemBg: 'transparent',
            },
          },
        }}
      >
        <Sider 
          trigger={null} 
          collapsible 
          collapsed={collapsed}
          width={240}
          style={{
            background: colors.siderBg,
            position: 'relative',
          }}
        >
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: colors.siderBgTint,
            pointerEvents: 'none',
            zIndex: 0,
          }} />
          <div style={{
            position: 'relative',
            zIndex: 1,
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
          }}>
            <div style={{ 
              height: 64, 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? 0 : '0 20px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
              flexShrink: 0,
            }}>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 10,
              }}>
                <div style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: colors.gradientPrimary,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                }}>
                  <RobotOutlined style={{ fontSize: 18, color: '#fff' }} />
                </div>
                {!collapsed && (
                  <div>
                    <Text style={{ 
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      backgroundClip: 'text',
                      fontSize: 16, 
                      fontWeight: 700, 
                      display: 'block',
                    }}>
                      AI Agent
                    </Text>
                    <Text style={{ 
                      background: 'linear-gradient(135deg, #5ee7df 0%, #b490ca 50%, #d789d7 100%)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      backgroundClip: 'text',
                      fontSize: 15,
                      fontWeight: 600,
                    }}>
                      测试平台
                    </Text>
                  </div>
                )}
              </div>
            </div>
            
            <div style={{ 
              flex: 1, 
              overflow: 'auto', 
              paddingBottom: collapsed ? 0 : 100,
            }}>
              <Menu
                mode="inline"
                selectedKeys={selectedKeys}
                defaultOpenKeys={openKeys}
                items={menuItems}
                onClick={handleMenuClick}
                style={{ 
                  background: 'transparent',
                  marginTop: 12,
                  border: 'none',
                }}
                className="custom-theme-menu"
              />
            </div>
          </div>
          
          {!collapsed && (
            <div style={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              width: 240,
              padding: '4px 12px 6px',
              background: `linear-gradient(to top, ${colors.siderBg} 60%, transparent 100%)`,
              zIndex: 10,
            }}>
              <div style={{
                padding: 12,
                borderRadius: 10,
                background: 'rgba(255, 255, 255, 0.15)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                backdropFilter: 'blur(4px)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <BulbOutlined style={{ color: '#fbbf24', fontSize: 16 }} />
                  <Text style={{ 
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                    fontSize: 14, 
                    fontWeight: 700,
                  }}>
                    快速提示
                  </Text>
                </div>
                <Text style={{ 
                  background: 'linear-gradient(135deg, #5ee7df 0%, #b490ca 50%, #d789d7 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                  fontSize: 12,
                  fontWeight: 600,
                  display: 'block',
                  marginBottom: 8,
                }}>
                  使用 AI 助手可快速生成测试用例
                </Text>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={() => navigate('/tests/web-ui-chat')}
                  style={{
                    width: '100%',
                    borderRadius: 8,
                    background: colors.gradientPrimary,
                    border: 'none',
                    fontWeight: 600,
                  }}
                >
                  AI助手生成
                </Button>
              </div>
            </div>
          )}
          {collapsed && (
            <Tooltip title="AI助手生成" placement="right">
              <Button
                type="primary"
                icon={<ThunderboltOutlined style={{ fontSize: 14 }} />}
                onClick={() => navigate('/tests/web-ui-chat')}
                style={{
                  position: 'fixed',
                  bottom: 12,
                  left: 20,
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  background: colors.gradientPrimary,
                  border: 'none',
                  zIndex: 10,
                }}
              />
            </Tooltip>
          )}
        </Sider>
      </ConfigProvider>
      
      <Layout style={{ background: `linear-gradient(180deg, ${colors.colorBgLayout} 0%, ${colors.pageBgTint} 100%)` }}>
        <Header style={{ 
          padding: '0 24px', 
          background: colors.headerBg,
          backdropFilter: 'blur(12px)',
          display: 'flex', 
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)',
          borderBottom: `1px solid ${colors.colorBorder}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined style={{ fontSize: 16 }} /> : <MenuFoldOutlined style={{ fontSize: 16 }} />}
              onClick={() => setCollapsed(!collapsed)}
              style={{ 
                color: colors.colorTextSecondary,
                width: 40,
                height: 40,
                borderRadius: 10,
              }}
            />
            
            {/* 页面标题 */}
            <Text style={{
              fontSize: 18,
              fontWeight: 600,
              color: colors.colorText,
            }}>
              {getPageTitle()}
            </Text>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Tooltip title="SKILL管理">
              <Button 
                type="text" 
                icon={<RobotOutlined style={{ fontSize: 16 }} />}
                onClick={() => navigate('/skills')}
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: colors.menuSelectedBg,
                  color: colors.colorPrimary,
                }}
              />
            </Tooltip>
            
            <Tooltip title="AI 助手">
              <Button 
                type="text" 
                icon={<ThunderboltOutlined style={{ fontSize: 16 }} />}
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: colors.menuSelectedBg,
                  color: colors.colorPrimary,
                }}
              />
            </Tooltip>
            
            <Tooltip title="API 状态">
              <Button 
                type="text" 
                icon={<ApiOutlined style={{ fontSize: 16 }} />}
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: `rgba(16, 185, 129, 0.1)`,
                  color: colors.colorSuccess,
                }}
              />
            </Tooltip>
            
            {/* 任务状态指示器 */}
            {runningTasks.length > 0 && (
              <Tooltip title={`${runningTasks.length}个任务正在执行`}>
                <Badge count={runningTasks.length} size="small" offset={[-2, 2]}>
                  <Button 
                    type="text" 
                    icon={<SyncOutlined spin style={{ fontSize: 16 }} />}
                    onClick={() => setTaskModalVisible(true)}
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 10,
                      background: colors.menuSelectedBg,
                      color: colors.colorPrimary,
                    }}
                  />
                </Badge>
              </Tooltip>
            )}
            
            <Badge count={notifications} size="small" offset={[-2, 2]}>
              <Tooltip title="通知">
                <Button 
                  type="text" 
                  icon={<BellOutlined style={{ fontSize: 16 }} />}
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 10,
                    color: colors.colorTextSecondary,
                  }}
                />
              </Tooltip>
            </Badge>
            
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" trigger={['click']}>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                cursor: 'pointer',
                padding: '4px 8px',
                borderRadius: 10,
                transition: 'all 0.2s',
              }}>
                <div style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: colors.gradientPrimary,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: colors.glowShadow,
                }}>
                  <Text style={{ color: '#fff', fontWeight: 600, fontSize: 14 }}>
                    {user?.username?.charAt(0)?.toUpperCase() || 'U'}
                  </Text>
                </div>
                {!collapsed && (
                  <div style={{ marginLeft: 10 }}>
                    <Text strong style={{ display: 'block', fontSize: 13, color: colors.colorText }}>
                      {user?.username || '用户'}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {user?.role === 'admin' ? '系统管理员' : '普通用户'}
                    </Text>
                  </div>
                )}
              </div>
            </Dropdown>
          </div>
        </Header>
        
        <Content style={{ 
          margin: 16, 
          padding: 0,
          background: 'transparent',
          minHeight: 'calc(100vh - 96px)',
        }}>
          <div style={{
            background: colors.cardBg,
            borderRadius: 12,
            padding: 20,
            minHeight: 'calc(100vh - 132px)',
            boxShadow: `0 1px 3px ${colors.pageBgTint}`,
            border: `1px solid ${colors.cardBorder}`,
          }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
    
    {/* 任务状态弹窗 */}
    <Modal
      title={<span><SyncOutlined spin style={{ marginRight: 8, color: colors.colorPrimary }} />正在执行的任务</span>}
      open={taskModalVisible}
      onCancel={() => setTaskModalVisible(false)}
      footer={null}
      width={500}
    >
      {runningTasks.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 48, color: colors.colorSuccess }} />
          <p style={{ marginTop: 16, color: colors.colorTextSecondary }}>暂无正在执行的任务</p>
        </div>
      ) : (
        <div>
          {runningTasks.map(task => (
            <div 
              key={task.id}
              style={{
                padding: '16px',
                marginBottom: '12px',
                borderRadius: '8px',
                background: colors.colorBgContainer,
                border: `1px solid ${colors.colorBorder}`,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>
                    任务 #{task.display_id} - 测试用例生成
                  </div>
                  <div style={{ fontSize: 12, color: colors.colorTextSecondary }}>
                    {task.current_step || '正在处理...'}
                  </div>
                </div>
                <Spin />
              </div>
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, color: colors.colorTextSecondary, marginBottom: 4 }}>
                  进度: {task.progress}% | 已生成: {task.generated_count}条
                  {task.current_batch > 0 && task.total_batches > 0 && ` | 批次: ${task.current_batch}/${task.total_batches}`}
                </div>
              </div>
              <Button 
                type="link" 
                size="small"
                onClick={() => {
                  setTaskModalVisible(false);
                  // 项目详情页已取消：统一回项目列表打开进度弹窗（进度弹窗为全局状态）
                  navigate('/projects');
                  dispatch(openProgressModal(task.id));
                }}
              >
                查看生成进度
              </Button>
            </div>
          ))}
        </div>
      )}
    </Modal>
    </>
  );
};

export default MainLayout;