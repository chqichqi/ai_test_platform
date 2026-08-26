import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Card, Row, Col, Statistic, Table, Tag, Progress, Spin, Empty,
  Typography
} from 'antd';
import {
  BugOutlined, WarningOutlined, CheckCircleOutlined,
  RiseOutlined,
  AlertOutlined
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import {
  issueApi, IssueDashboard, IssueTrend, IssueSummary,
  SEVERITY_OPTIONS, STATUS_OPTIONS
} from '../../api/issueApi';

const { Text } = Typography;

interface IssueDashboardPageProps {
  projectId?: number;
}

const IssueDashboardPage: React.FC<IssueDashboardPageProps> = ({ projectId: propProjectId }) => {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = propProjectId ?? (projectIdParam ? Number(projectIdParam) : null);
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<IssueDashboard | null>(null);
  const [summary, setSummary] = useState<IssueSummary | null>(null);
  const [trend, setTrend] = useState<IssueTrend | null>(null);

  const fetchData = async () => {
    if (projectId === null) return;
    setLoading(true);
    try {
      const [dashboardData, summaryData, trendData] = await Promise.all([
        issueApi.getDashboard(projectId),
        issueApi.getSummary(projectId),
        issueApi.getTrend(projectId, 30)
      ]);
      setDashboard(dashboardData);
      setSummary(summaryData);
      setTrend(trendData);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) {
      fetchData();
    }
  }, [projectId]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!dashboard) {
    return <Empty description="暂无数据" />;
  }

  const getStatusOption = (value: string) => {
    return STATUS_OPTIONS.find(o => o.value === value);
  };

  const getSeverityOption = (value: string) => {
    return SEVERITY_OPTIONS.find(o => o.value === value);
  };

  const trendChartOption = {
    title: {
      text: '问题趋势',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['新增问题', '解决问题'],
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trend?.trend.map(t => t.date.slice(5)) || []
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '新增问题',
        type: 'line',
        data: trend?.trend.map(t => t.created) || [],
        itemStyle: { color: '#1890ff' },
        areaStyle: { opacity: 0.3 }
      },
      {
        name: '解决问题',
        type: 'line',
        data: trend?.trend.map(t => t.resolved) || [],
        itemStyle: { color: '#52c41a' },
        areaStyle: { opacity: 0.3 }
      }
    ]
  };

  const statusPieOption = {
    title: {
      text: '状态分布',
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'middle'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['60%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data: Object.entries(summary?.by_status || {}).map(([key, value]) => ({
          value,
          name: getStatusOption(key)?.label || key,
          itemStyle: { color: getStatusOption(key)?.color }
        })).filter(d => d.value > 0)
      }
    ]
  };

  const severityBarOption = {
    title: {
      text: '严重程度分布',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: SEVERITY_OPTIONS.map(o => o.label)
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        type: 'bar',
        data: SEVERITY_OPTIONS.map(o => ({
          value: summary?.by_severity[o.value] || 0,
          itemStyle: { color: o.color }
        })),
        barWidth: '60%'
      }
    ]
  };

  const recentIssuesColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 80,
      render: (severity: string) => {
        const opt = getSeverityOption(severity);
        return <Tag color={opt?.color}>{opt?.label}</Tag>;
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => {
        const opt = getStatusOption(status);
        return <Tag color={opt?.color}>{opt?.label}</Tag>;
      }
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 140,
      render: (date: string) => dayjs(date).format('MM-DD HH:mm')
    }
  ];

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card>
            <Row gutter={16}>
              <Col span={4}>
                <Statistic
                  title="健康评分"
                  value={dashboard.health_score}
                  suffix="分"
                  valueStyle={{ 
                    color: dashboard.health_score >= 80 ? '#52c41a' : 
                           dashboard.health_score >= 60 ? '#faad14' : '#f5222d'
                  }}
                />
                <Progress 
                  percent={dashboard.health_score} 
                  showInfo={false}
                  strokeColor={
                    dashboard.health_score >= 80 ? '#52c41a' :
                    dashboard.health_score >= 60 ? '#faad14' : '#f5222d'
                  }
                />
              </Col>
              <Col span={4}>
                <Statistic
                  title="问题总数"
                  value={dashboard.summary.total}
                  prefix={<BugOutlined />}
                />
              </Col>
              <Col span={4}>
                <Statistic
                  title="待处理"
                  value={dashboard.summary.open}
                  valueStyle={{ color: '#1890ff' }}
                  prefix={<AlertOutlined />}
                />
              </Col>
              <Col span={4}>
                <Statistic
                  title="处理中"
                  value={dashboard.summary.in_progress}
                  valueStyle={{ color: '#722ed1' }}
                />
              </Col>
              <Col span={4}>
                <Statistic
                  title="本周新增"
                  value={dashboard.summary.new_this_week}
                  prefix={<RiseOutlined />}
                  valueStyle={{ color: '#f5222d' }}
                />
              </Col>
              <Col span={4}>
                <Statistic
                  title="本周解决"
                  value={dashboard.summary.resolved_this_week}
                  prefix={<CheckCircleOutlined />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={16}>
          <Card>
            <ReactECharts option={trendChartOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <ReactECharts option={statusPieOption} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card>
            <ReactECharts option={severityBarOption} style={{ height: 250 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="最近问题">
            <Table
              columns={recentIssuesColumns}
              dataSource={dashboard.recent_issues}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="严重问题（待处理）"
              value={dashboard.summary.critical_open}
              valueStyle={{ color: '#f5222d' }}
              prefix={<WarningOutlined />}
            />
            <Text type="secondary">需要立即处理</Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="高优先级（待处理）"
              value={dashboard.summary.high_open}
              valueStyle={{ color: '#fa8c16' }}
            />
            <Text type="secondary">优先安排处理</Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="解决率"
              value={summary?.resolution_rate || 0}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
            />
            <Progress 
              percent={summary?.resolution_rate || 0} 
              showInfo={false}
              strokeColor="#52c41a"
            />
          </Card>
        </Col>
      </Row>

      {summary?.avg_resolution_time_hours && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card>
              <Statistic
                title="平均解决时间"
                value={summary.avg_resolution_time_hours}
                suffix="小时"
              />
              <Text type="secondary">
                基于已解决的 {Object.keys(summary.by_status).reduce((a, b) => 
                  (summary.by_status[a] || 0) + (summary.by_status[b] || 0)
                , 0)} 个问题计算
              </Text>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
};

export default IssueDashboardPage;