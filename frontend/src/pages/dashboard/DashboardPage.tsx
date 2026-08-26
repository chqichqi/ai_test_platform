import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Card, Typography, Progress, List, Tag, Select, DatePicker, Button, Badge, Empty, Space, message } from 'antd';
import { 
  ProjectOutlined, 
  FileTextOutlined, 
  CheckCircleOutlined,
  PlayCircleOutlined,
  BugOutlined,
  ClockCircleOutlined,
  BarChartOutlined,
  ReloadOutlined,
  FireOutlined,
  PieChartOutlined,
  LineChartOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { dashboardApi, SystemStats, ProjectDashboardStats } from '../../api/dashboardApi';
import { projectApi } from '../../api/projectApi';
import dayjs from 'dayjs';
import type { EChartsOption } from 'echarts';

const { Text } = Typography;
const { RangePicker } = DatePicker;

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [, setLoading] = useState(true);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [projectStats, setProjectStats] = useState<ProjectDashboardStats | null>(null);
  const [timeRange, setTimeRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(7, 'days'),
    dayjs()
  ]);

  useEffect(() => {
    fetchData();
    fetchProjects();
  }, []);

  useEffect(() => {
    if (selectedProject) {
      fetchProjectDashboard(selectedProject);
    }
  }, [selectedProject, timeRange]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await dashboardApi.getSystemStats();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch dashboard stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchProjects = async () => {
    try {
      const data = await projectApi.list({ page_size: 100 });
      console.log('Projects API response:', data);
      setProjects(data.items || []);
      if (data.items && data.items.length > 0 && !selectedProject) {
        setSelectedProject(data.items[0].id);
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
      message.error('获取项目列表失败');
    }
  };

  const fetchProjectDashboard = async (projectId: number) => {
    try {
      const data = await dashboardApi.getProjectDashboard(projectId);
      setProjectStats(data);
    } catch (error) {
      console.error('Failed to fetch project dashboard:', error);
    }
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      passed: '#52c41a',
      failed: '#f5222d',
      skipped: '#faad14',
      running: '#1890ff',
      pending: '#d9d9d9',
      completed: '#52c41a',
      success: '#52c41a',
      error: '#f5222d',
    };
    return colors[status] || '#d9d9d9';
  };

  const getStatusText = (status: string) => {
    const texts: Record<string, string> = {
      passed: '通过',
      failed: '失败',
      skipped: '跳过',
      running: '运行中',
      pending: '待执行',
      completed: '已完成',
      success: '成功',
      error: '错误',
    };
    return texts[status] || status;
  };

  // ECharts options
  const trendOption: EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['通过', '失败', '跳过'], top: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '15%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false,
      data: projectStats?.test_execution_trend?.map(d => d.date) || []
    },
    yAxis: { type: 'value', name: '次数' },
    series: [
      {
        name: '通过',
        type: 'line',
        smooth: true,
        data: projectStats?.test_execution_trend?.map(d => d.passed || 0) || [],
        itemStyle: { color: '#52c41a' },
        areaStyle: { opacity: 0.1 }
      },
      {
        name: '失败',
        type: 'line',
        smooth: true,
        data: projectStats?.test_execution_trend?.map(d => d.failed || 0) || [],
        itemStyle: { color: '#f5222d' },
        areaStyle: { opacity: 0.1 }
      },
      {
        name: '跳过',
        type: 'line',
        smooth: true,
        data: projectStats?.test_execution_trend?.map(d => d.skipped || 0) || [],
        itemStyle: { color: '#faad14' },
        areaStyle: { opacity: 0.1 }
      }
    ]
  };

  const pieOption: EChartsOption = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left', top: 'center' },
    series: [
      {
        name: '状态',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['60%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: {
          label: { show: true, fontSize: 20, fontWeight: 'bold' }
        },
        labelLine: { show: false },
        data: Object.entries(projectStats?.test_case_status_distribution || {}).map(([key, value]) => ({
          name: getStatusText(key),
          value
        }))
      }
    ]
  };

  const versionPieOption: EChartsOption = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left', top: 'center' },
    series: [
      {
        name: '版本状态',
        type: 'pie',
        radius: '60%',
        center: ['60%', '50%'],
        data: Object.entries(projectStats?.version_status_distribution || {}).map(([key, value]) => ({
          name: key,
          value
        })),
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
        }
      }
    ]
  };

  const barOption: EChartsOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: Object.keys(projectStats?.issue_stats?.by_priority || {}) },
    yAxis: { type: 'value', name: '数量' },
    series: [{
      data: Object.values(projectStats?.issue_stats?.by_priority || {}),
      type: 'bar',
      itemStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: '#f5222d' },
            { offset: 1, color: '#ff7875' }
          ]
        }
      }
    }]
  };

  const statCards = [
    { 
      title: '项目总数', 
      value: stats?.total_projects || 0, 
      suffix: '个',
      icon: <ProjectOutlined />, 
      color: '#667eea',
      bgColor: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    },
    { 
      title: '测试用例', 
      value: stats?.total_test_cases || 0, 
      suffix: '条',
      icon: <FileTextOutlined />, 
      color: '#52c41a',
      bgColor: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
    },
    { 
      title: '执行次数', 
      value: stats?.total_executions || 0, 
      suffix: '次',
      icon: <PlayCircleOutlined />, 
      color: '#faad14',
      bgColor: 'linear-gradient(135deg, #faad14 0%, #ffd666 100%)',
    },
    { 
      title: '通过率', 
      value: stats?.pass_rate || 0, 
      suffix: '%',
      icon: <CheckCircleOutlined />, 
      color: '#f5222d',
      bgColor: 'linear-gradient(135deg, #f5222d 0%, #ff7875 100%)',
    },
    { 
      title: '问题总数', 
      value: stats?.total_issues || 0, 
      suffix: '个',
      icon: <BugOutlined />, 
      color: '#722ed1',
      bgColor: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)',
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Text type="secondary" style={{ fontSize: 14 }}>
              实时监控测试执行情况与项目状态
            </Text>
          </div>
          <Space>
            <RangePicker
              value={timeRange}
              onChange={(dates) => dates && setTimeRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              style={{ width: 240 }}
            />
            <Select
              placeholder="选择项目"
              value={selectedProject}
              onChange={setSelectedProject}
              style={{ width: 200 }}
              allowClear
            >
              {projects.map(project => (
                <Select.Option key={project.id} value={project.id}>
                  {project.name}
                </Select.Option>
              ))}
            </Select>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>
              刷新
            </Button>
          </Space>
        </div>
      </div>

      {/* Stat Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((stat, index) => (
          <Col xs={24} sm={12} md={8} lg={4} key={index}>
            <Card 
              className="stat-card"
              style={{ borderRadius: 12, border: 'none', overflow: 'hidden' }}
              styles={{ body: { padding: 20 } }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 48,
                  height: 48,
                  borderRadius: 12,
                  background: stat.bgColor,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: `0 4px 12px ${stat.color}40`,
                }}>
                  {React.cloneElement(stat.icon, { style: { fontSize: 24, color: '#fff' } })}
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{stat.title}</Text>
                  <br />
                  <Text style={{ fontSize: 24, fontWeight: 700, color: '#1f2937' }}>
                    {stat.value}<span style={{ fontSize: 14, fontWeight: 400 }}>{stat.suffix}</span>
                  </Text>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {!selectedProject && (
        <Card style={{ textAlign: 'center', padding: 40 }}>
          <Empty
            description={
              <Space direction="vertical" size="large">
                {projects.length === 0 ? (
                  <>
                    <Text type="secondary" style={{ fontSize: 16 }}>
                      系统中暂无项目，请先创建项目
                    </Text>
                    <Button type="primary" onClick={() => navigate('/projects')}>
                      创建项目
                    </Button>
                  </>
                ) : (
                  <>
                    <Text type="secondary" style={{ fontSize: 16 }}>
                      请从上方下拉菜单选择一个项目查看详细统计
                    </Text>
                    <Button type="primary" onClick={() => fetchData()}>
                      刷新数据
                    </Button>
                  </>
                )}
              </Space>
            }
          />
        </Card>
      )}

      {selectedProject && projectStats && (
        <>
          {/* Project Overview */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={8}>
              <Card 
                title={<><PieChartOutlined /> 版本状态分布</>}
                style={{ borderRadius: 12 }}
                styles={{ body: { padding: '12px 24px' } }}
              >
              {Object.keys(projectStats.version_status_distribution || {}).length > 0 ? (
                <ReactECharts option={versionPieOption} style={{ height: 250 }} />
              ) : (
                <Empty description="暂无数据" />
              )}
              </Card>
            </Col>
            <Col xs={24} lg={8}>
              <Card 
                title={<><PieChartOutlined /> 测试用例状态</>}
                style={{ borderRadius: 12 }}
                styles={{ body: { padding: '12px 24px' } }}
              >
              {Object.keys(projectStats.test_case_status_distribution || {}).length > 0 ? (
                <ReactECharts option={pieOption} style={{ height: 250 }} />
              ) : (
                <Empty description="暂无数据" />
              )}
              </Card>
            </Col>
            <Col xs={24} lg={8}>
              <Card 
                title={<><FireOutlined /> 项目概览</>}
                style={{ borderRadius: 12 }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 0' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text>版本进度</Text>
                      <Text strong>{projectStats.total_versions} 个版本</Text>
                    </div>
                    <Progress 
                      percent={Math.round((projectStats.total_versions > 0 ? 
                        (projectStats.version_status_distribution?.released || 0) / projectStats.total_versions * 100 : 0))} 
                      strokeColor={{ from: '#667eea', to: '#764ba2' }}
                    />
                  </div>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text>测试覆盖率</Text>
                      <Text strong>{projectStats.total_test_cases} 个用例</Text>
                    </div>
                    <Progress 
                      percent={Math.round(projectStats.pass_rate || 0)} 
                      strokeColor={{ from: '#52c41a', to: '#95de64' }}
                    />
                  </div>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text>问题解决率</Text>
                      <Text strong>
                        {projectStats.issue_stats?.total > 0 ? 
                          Math.round((projectStats.issue_stats.resolved / projectStats.issue_stats.total) * 100) : 0}%
                      </Text>
                    </div>
                    <Progress 
                      percent={projectStats.issue_stats?.total > 0 ? 
                        Math.round((projectStats.issue_stats.resolved / projectStats.issue_stats.total) * 100) : 0} 
                      strokeColor={{ from: '#722ed1', to: '#b37feb' }}
                    />
                  </div>
                </div>
              </Card>
            </Col>
          </Row>

          {/* Trend Charts */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} lg={12}>
              <Card 
                title={<><LineChartOutlined /> 测试执行趋势</>}
                style={{ borderRadius: 12 }}
                styles={{ body: { padding: '12px 24px' } }}
              >
              {projectStats.test_execution_trend?.length > 0 ? (
                <ReactECharts option={trendOption} style={{ height: 250 }} />
              ) : (
                <Empty description="暂无数据" />
              )}
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card 
                title={<><BarChartOutlined /> 问题优先级分布</>}
                style={{ borderRadius: 12 }}
                styles={{ body: { padding: '12px 24px' } }}
              >
              {Object.keys(projectStats.issue_stats?.by_priority || {}).length > 0 ? (
                <ReactECharts option={barOption} style={{ height: 250 }} />
              ) : (
                <Empty description="暂无数据" />
              )}
              </Card>
            </Col>
          </Row>
        </>
      )}

      {/* Recent Activities */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card 
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <PlayCircleOutlined style={{ color: '#667eea' }} />
                <span>最近执行</span>
                <Badge count={projectStats?.recent_executions?.length || 0} style={{ backgroundColor: '#52c41a' }} />
              </div>
            }
            style={{ borderRadius: 12 }}
          >
            <List
              dataSource={projectStats?.recent_executions || []}
              renderItem={(item) => (
                <List.Item>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                    <Badge 
                      color={getStatusColor(item.status)} 
                      style={{ width: 8, height: 8 }}
                    />
                    <div style={{ flex: 1 }}>
                      <Text strong style={{ fontSize: 14 }}>{item.name}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />
                        {dayjs(item.start_time).format('YYYY-MM-DD HH:mm')}
                      </Text>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <Tag color={getStatusColor(item.status)}>
                        {getStatusText(item.status)}
                      </Tag>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {item.passed}/{item.total} 通过
                      </Text>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        
        <Col xs={24} lg={12}>
          <Card 
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <BugOutlined style={{ color: '#f5222d' }} />
                <span>最近问题</span>
                <Badge count={projectStats?.issue_stats?.total || 0} style={{ backgroundColor: '#f5222d' }} />
              </div>
            }
            style={{ borderRadius: 12 }}
          >
            <List
              dataSource={stats?.recent_issues || []}
              renderItem={(item) => (
                <List.Item>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                    <div style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: getStatusColor(item.status),
                    }} />
                    <div style={{ flex: 1 }}>
                      <Text strong style={{ fontSize: 14 }}>{item.title}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />
                        {dayjs(item.created_at).format('YYYY-MM-DD HH:mm')}
                      </Text>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <Tag color={item.priority === 'high' ? 'red' : item.priority === 'medium' ? 'orange' : 'blue'}>
                        {item.priority}
                      </Tag>
                      <br />
                      {item.assignee && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          指派给: {item.assignee}
                        </Text>
                      )}
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DashboardPage;
