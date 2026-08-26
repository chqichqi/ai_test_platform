import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Typography, Button, Table, Space, Tag, Select, Input, Modal,
  message, Tabs, InputNumber, Slider, Switch,
  Progress, Badge, Row, Col, Statistic,
  Alert, Empty
} from 'antd';
import {
  PlayCircleOutlined, StopOutlined, ThunderboltOutlined,
  ReloadOutlined, PlusOutlined, SettingOutlined,
  LineChartOutlined, DashboardOutlined, ApiOutlined
} from '@ant-design/icons';
import * as echarts from 'echarts';
import { projectApi } from '../../api/projectApi';
import { performanceApi, ApprovedApiCase, LocustExecution, StepConfig } from '../../api/performanceApi';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

interface ProjectInfo {
  id: number;
  name: string;
  code: string;
}

const PerformanceTestPage: React.FC = () => {
  // 项目和Tab
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<string>('locust');

  // 场景配置
  const [host, setHost] = useState('http://localhost:8000');
  const [numUsers, setNumUsers] = useState(100);
  const [spawnRate, setSpawnRate] = useState(10);
  const [runTime, setRunTime] = useState(60);
  const [stepEnabled, setStepEnabled] = useState(false);
  const [stepCount, setStepCount] = useState(5);
  const [stepDuration, setStepDuration] = useState(60);
  const [stepIncrement, setStepIncrement] = useState(10);

  // 用例选择
  const [approvedCases, setApprovedCases] = useState<ApprovedApiCase[]>([]);
  const [selectedCaseIds, setSelectedCaseIds] = useState<number[]>([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [caseSearch, setCaseSearch] = useState('');
  const [caseMethod, setCaseMethod] = useState<string>('all');
  const [casePagination, setCasePagination] = useState({ page: 1, pageSize: 10, total: 0 });

  // 执行状态
  const [executionId, setExecutionId] = useState<number | null>(null);
  const [execStatus, setExecStatus] = useState<string>('idle');
  const [execProgress, setExecProgress] = useState(0);
  const [startLoading, setStartLoading] = useState(false);

  // 脚本
  const [scripts, setScripts] = useState<any[]>([]);
  const [selectedScriptId, setSelectedScriptId] = useState<number | null>(null);
  const [showCreateScriptModal, setShowCreateScriptModal] = useState(false);
  const [newScriptName, setNewScriptName] = useState('');
  const [createScriptLoading, setCreateScriptLoading] = useState(false);

  // 执行历史
  const [executions, setExecutions] = useState<LocustExecution[]>([]);

  // 图表
  const tpsChartRef = useRef<HTMLDivElement>(null);
  const rtChartRef = useRef<HTMLDivElement>(null);
  const errorChartRef = useRef<HTMLDivElement>(null);
  const usersChartRef = useRef<HTMLDivElement>(null);
  const tpsChartInstance = useRef<echarts.ECharts | null>(null);
  const rtChartInstance = useRef<echarts.ECharts | null>(null);
  const errorChartInstance = useRef<echarts.ECharts | null>(null);
  const usersChartInstance = useRef<echarts.ECharts | null>(null);

  // 指标数据
  const [metricsData, setMetricsData] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // 加载项目
  useEffect(() => {
    loadProjects();
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadApprovedCases();
      loadScripts();
      loadExecutions();
    }
  }, [selectedProjectId]);

  // 初始化图表
  useEffect(() => {
    if (activeTab === 'locust') {
      setTimeout(() => initCharts(), 100);
    }
    return () => {
      disposeCharts();
    };
  }, [activeTab]);

  const loadProjects = async () => {
    try {
      const response = await projectApi.list({ page_size: 100 });
      setProjects(response.items || []);
      if (response.items?.length > 0) {
        setSelectedProjectId(response.items[0].id);
      }
    } catch (error: any) {
      message.error('加载项目列表失败');
    }
  };

  const loadApprovedCases = async () => {
    if (!selectedProjectId) return;
    setLoadingCases(true);
    try {
      const data = await performanceApi.getApprovedApiCases({
        project_id: selectedProjectId,
        page: casePagination.page,
        page_size: casePagination.pageSize,
        search: caseSearch || undefined,
        method: caseMethod !== 'all' ? caseMethod : undefined,
      });
      setApprovedCases(data.items);
      setCasePagination(prev => ({ ...prev, total: data.total }));
    } catch (error: any) {
      console.error('加载已审批用例失败:', error);
    } finally {
      setLoadingCases(false);
    }
  };

  const loadScripts = async () => {
    if (!selectedProjectId) return;
    try {
      const data = await performanceApi.listLocustScripts(selectedProjectId);
      setScripts(data.items);
    } catch (error: any) {
      console.error('加载脚本列表失败:', error);
    }
  };

  const loadExecutions = async () => {
    if (!selectedProjectId) return;
    try {
      const data = await performanceApi.listLocustExecutions({ project_id: selectedProjectId });
      setExecutions(data.items);
    } catch (error: any) {
      console.error('加载执行历史失败:', error);
    }
  };

  // ===== 图表初始化 =====
  const initCharts = () => {
    const chartOption = (title: string, color: string, yName: string): echarts.EChartsOption => ({
      title: { text: title, left: 8, textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 35, bottom: 25 },
      xAxis: { type: 'category', data: [] },
      yAxis: { type: 'value', name: yName },
      series: [{
        type: 'line',
        smooth: true,
        data: [],
        lineStyle: { color },
        areaStyle: { color, opacity: 0.1 },
        symbol: 'none',
      }],
      dataZoom: [{ type: 'inside' }],
    });

    if (tpsChartRef.current && !tpsChartInstance.current) {
      tpsChartInstance.current = echarts.init(tpsChartRef.current);
      tpsChartInstance.current.setOption(chartOption('TPS (每秒事务数)', '#52c41a', 'TPS'));
    }
    if (rtChartRef.current && !rtChartInstance.current) {
      rtChartInstance.current = echarts.init(rtChartRef.current);
      rtChartInstance.current.setOption({
        ...chartOption('响应时间 (ms)', '#1890ff', 'ms'),
        series: [
          { type: 'line', smooth: true, data: [], name: 'Avg RT', lineStyle: { color: '#1890ff' }, symbol: 'none' },
          { type: 'line', smooth: true, data: [], name: 'Max RT', lineStyle: { color: '#ff7a45' }, symbol: 'none' },
        ],
      });
    }
    if (errorChartRef.current && !errorChartInstance.current) {
      errorChartInstance.current = echarts.init(errorChartRef.current);
      errorChartInstance.current.setOption(chartOption('错误率 (%)', '#ff4d4f', '%'));
    }
    if (usersChartRef.current && !usersChartInstance.current) {
      usersChartInstance.current = echarts.init(usersChartRef.current);
      usersChartInstance.current.setOption({
        ...chartOption('活跃用户数', '#722ed1', 'Users'),
        series: [{ type: 'line', smooth: true, data: [], lineStyle: { color: '#722ed1' }, areaStyle: { color: '#722ed1', opacity: 0.15 }, symbol: 'none' }],
      });
    }
  };

  const disposeCharts = () => {
    [tpsChartInstance, rtChartInstance, errorChartInstance, usersChartInstance].forEach(inst => {
      if (inst.current) { inst.current.dispose(); inst.current = null; }
    });
  };

  // ===== 更新图表数据 =====
  const updateCharts = useCallback((metrics: any[]) => {
    const times = metrics.map((_: any, i: number) => `${i * 2}s`);
    const tpsData = metrics.map((m: any) => m.tps || 0);
    const avgRtData = metrics.map((m: any) => m.avg_rt || 0);
    const maxRtData = metrics.map((m: any) => m.max_rt || 0);
    const failData = metrics.map((m: any) => (m.fail_ratio || 0) * 100);
    const userData = metrics.map((m: any) => m.user_count || 0);

    const updateChart = (inst: React.RefObject<echarts.ECharts | null>, data: number[], yMax?: number) => {
      if (inst.current) {
        inst.current.setOption({
          xAxis: { data: times },
          series: [{ data }],
          yAxis: yMax ? { max: Math.ceil(yMax * 1.3) || 1 } : {},
        });
      }
    };

    updateChart(tpsChartInstance, tpsData, Math.max(...tpsData, 1));
    updateChart(rtChartInstance, avgRtData);
    if (rtChartInstance.current) {
      rtChartInstance.current.setOption({
        xAxis: { data: times },
        series: [{ data: avgRtData }, { data: maxRtData }],
      });
    }
    updateChart(errorChartInstance, failData, 100);
    updateChart(usersChartInstance, userData, numUsers);
  }, [numUsers]);

  // ===== 执行控制 =====
  const startPolling = (execId: number) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    const startTime = Date.now();
    pollingRef.current = setInterval(async () => {
      try {
        const data = await performanceApi.getLocustMetrics(execId);
        const elapsed = (Date.now() - startTime) / 1000;
        setExecProgress(Math.min(Math.round((elapsed / runTime) * 100), 99));

        if (data.metrics && data.metrics.length > 0) {
          setMetricsData(prev => {
            const combined = [...prev, ...data.metrics.slice(-3)];
            return combined.slice(-60);
          });
        }

        if (data.summary) {
          setSummary(data.summary);
        }

        if (data.status === 'completed' || data.status === 'stopped' || data.status === 'failed') {
          stopPolling();
          setExecStatus(data.status);
          setExecProgress(100);
          loadExecutions();
        }
      } catch (error) {
        console.error('获取指标失败:', error);
      }
    }, 2000);
  };

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const handleStart = async () => {
    if (selectedCaseIds.length === 0) {
      message.warning('请至少选择一个已审批的API用例');
      return;
    }
    if (!selectedProjectId) {
      message.warning('请先选择项目');
      return;
    }

    setStartLoading(true);
    setMetricsData([]);
    setSummary(null);

    const stepConfig: StepConfig | undefined = stepEnabled ? {
      enabled: true,
      step_count: stepCount,
      step_duration: stepDuration,
      step_thread_increment: stepIncrement,
    } : undefined;

    try {
      const exec = await performanceApi.startLocustExecution({
        project_id: selectedProjectId,
        host,
        num_users: numUsers,
        spawn_rate: spawnRate,
        run_time: runTime,
        step_config: stepConfig,
      });

      setExecutionId(exec.id);
      setExecStatus('running');
      setExecProgress(0);

      startPolling(exec.id);
      message.success(`Locust 执行已启动 (ID: ${exec.id})`);
    } catch (error: any) {
      message.error('启动失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setStartLoading(false);
    }
  };

  const handleStop = async () => {
    if (!executionId) return;
    try {
      await performanceApi.stopLocustExecution(executionId);
      stopPolling();
      setExecStatus('stopped');
      setExecProgress(100);
      message.info('执行已停止');
      loadExecutions();
    } catch (error: any) {
      message.error('停止失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleReset = () => {
    stopPolling();
    setExecutionId(null);
    setExecStatus('idle');
    setExecProgress(0);
    setMetricsData([]);
    setSummary(null);
  };

  // 更新图表当 metricsData 变化
  useEffect(() => {
    if (metricsData.length > 0) {
      updateCharts(metricsData);
    }
  }, [metricsData, updateCharts]);

  // 创建脚本
  const handleCreateScript = async () => {
    if (!selectedProjectId || !newScriptName) return;
    setCreateScriptLoading(true);
    try {
      await performanceApi.createLocustScript({
        project_id: selectedProjectId,
        name: newScriptName,
        host,
        case_ids: selectedCaseIds,
      });
      message.success('脚本创建成功');
      setShowCreateScriptModal(false);
      setNewScriptName('');
      loadScripts();
    } catch (error: any) {
      message.error('创建脚本失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCreateScriptLoading(false);
    }
  };

  // ===== 渲染 =====

  const caseColumns = [
    { title: '', key: 'check', width: 40,
      render: (_: any, record: ApprovedApiCase) => (
        <input type="checkbox" checked={selectedCaseIds.includes(record.id)}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedCaseIds(prev => [...prev, record.id]);
            } else {
              setSelectedCaseIds(prev => prev.filter(id => id !== record.id));
            }
          }} />
      ) },
    { title: '用例名称', dataIndex: 'name', key: 'name', ellipsis: true, width: 200 },
    { title: '方法', dataIndex: 'method', key: 'method', width: 70,
      render: (m: string) => <Tag color="blue">{m}</Tag> },
    { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true, width: 180 },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 60,
      render: (p: string) => <Tag color={p === 'P0' ? 'red' : p === 'P1' ? 'orange' : 'blue'}>{p}</Tag> },
  ];

  const execColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 50 },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true, width: 150 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const colors: Record<string, string> = { running: 'processing', completed: 'success', stopped: 'warning', failed: 'error' };
        const labels: Record<string, string> = { running: '运行中', completed: '已完成', stopped: '已停止', failed: '失败' };
        return <Badge status={colors[s] as any} text={labels[s] || s} />;
      } },
    { title: '用户数', dataIndex: 'num_users', key: 'num_users', width: 60 },
    { title: 'TPS', dataIndex: 'avg_tps', key: 'avg_tps', width: 70,
      render: (v: number) => v != null ? v.toFixed(1) : '-' },
    { title: 'Avg RT', dataIndex: 'avg_rt', key: 'avg_rt', width: 70,
      render: (v: number) => v != null ? `${v.toFixed(0)}ms` : '-' },
    { title: 'P99 RT', dataIndex: 'p99_rt', key: 'p99_rt', width: 70,
      render: (v: number) => v != null ? `${v.toFixed(0)}ms` : '-' },
    { title: '错误率', dataIndex: 'error_rate', key: 'error_rate', width: 70,
      render: (v: number) => v != null ? `${v.toFixed(1)}%` : '-' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 140,
      render: (t: string) => t ? new Date(t).toLocaleString() : '-' },
  ];

  const getStepPreview = () => {
    if (!stepEnabled) return '';
    const steps: number[] = [];
    for (let i = 1; i <= stepCount; i++) {
      steps.push(Math.min(i * stepIncrement, numUsers));
    }
    return steps.join(' → ');
  };

  return (
    <div style={{ padding: 16, background: '#f0f2f5', minHeight: '100vh' }}>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            <ThunderboltOutlined /> 性能/压力测试
          </Title>
          <Select
            value={selectedProjectId}
            onChange={setSelectedProjectId}
            style={{ width: 200 }}
            placeholder="选择项目"
          >
            {projects.map(p => (
              <Option key={p.id} value={p.id}>{p.name}</Option>
            ))}
          </Select>
        </Space>
      </Card>

      <Tabs activeKey={activeTab} onChange={setActiveTab} type="card">
        <Tabs.TabPane tab={<><LineChartOutlined /> Locust 压力测试</>} key="locust">
          {selectedProjectId ? (
            <div style={{ display: 'flex', gap: 12 }}>
              {/* 左侧：配置面板 */}
              <div style={{ width: 360, flexShrink: 0 }}>
                {/* 场景配置 */}
                <Card size="small" title={<><SettingOutlined /> 场景配置</>} style={{ marginBottom: 12 }}>
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <div>
                      <Text type="secondary">目标 Host</Text>
                      <Input value={host} onChange={e => setHost(e.target.value)} />
                    </div>
                    <div>
                      <Text type="secondary">并发用户数: {numUsers}</Text>
                      <Space style={{ width: '100%' }}>
                        <InputNumber min={1} max={10000} value={numUsers}
                          onChange={v => setNumUsers(v || 100)} style={{ width: 100 }} />
                        <Slider min={1} max={500} value={numUsers}
                          onChange={v => setNumUsers(v)} style={{ flex: 1 }} />
                      </Space>
                    </div>
                    <div>
                      <Text type="secondary">孵化率 (用户/秒): {spawnRate}</Text>
                      <InputNumber min={1} max={500} value={spawnRate}
                        onChange={v => setSpawnRate(v || 10)} style={{ width: '100%' }} />
                    </div>
                    <div>
                      <Text type="secondary">运行时长 (秒): {runTime}</Text>
                      <InputNumber min={10} max={3600} step={10} value={runTime}
                        onChange={v => setRunTime(v || 60)} style={{ width: '100%' }} />
                    </div>
                  </Space>
                </Card>

                {/* 梯度配置 */}
                <Card size="small" title="梯度线程控制" style={{ marginBottom: 12 }}>
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <Switch checked={stepEnabled} onChange={setStepEnabled}
                      checkedChildren="启用" unCheckedChildren="禁用" />
                    {stepEnabled && (
                      <>
                        <div>
                          <Text type="secondary">步数</Text>
                          <InputNumber min={1} max={20} value={stepCount}
                            onChange={v => setStepCount(v || 5)} style={{ width: '100%' }} />
                        </div>
                        <div>
                          <Text type="secondary">每步时长 (秒)</Text>
                          <InputNumber min={10} max={600} value={stepDuration}
                            onChange={v => setStepDuration(v || 60)} style={{ width: '100%' }} />
                        </div>
                        <div>
                          <Text type="secondary">每步增加线程数</Text>
                          <InputNumber min={1} max={100} value={stepIncrement}
                            onChange={v => setStepIncrement(v || 10)} style={{ width: '100%' }} />
                        </div>
                        <Alert type="info" message={`梯度预览: ${getStepPreview()}`}
                          style={{ fontSize: 12 }} />
                      </>
                    )}
                  </Space>
                </Card>

                {/* 用例选择 */}
                <Card size="small"
                  title={<><ApiOutlined /> 选择API用例 (已审批)</>}
                  extra={
                    <Space size="small">
                      <Input.Search size="small" placeholder="搜索..."
                        value={caseSearch} onChange={e => setCaseSearch(e.target.value)}
                        onSearch={() => loadApprovedCases()} style={{ width: 120 }} />
                      <Select size="small" value={caseMethod} onChange={setCaseMethod} style={{ width: 70 }}>
                        <Option value="all">全部</Option>
                        <Option value="GET">GET</Option>
                        <Option value="POST">POST</Option>
                        <Option value="PUT">PUT</Option>
                        <Option value="DELETE">DELETE</Option>
                      </Select>
                    </Space>
                  }
                  style={{ marginBottom: 12 }}>
                  <Table
                    dataSource={approvedCases}
                    columns={caseColumns}
                    rowKey="id"
                    size="small"
                    loading={loadingCases}
                    pagination={{
                      current: casePagination.page,
                      pageSize: casePagination.pageSize,
                      total: casePagination.total,
                      onChange: (p, ps) => {
                        setCasePagination({ page: p, pageSize: ps, total: casePagination.total });
                        loadApprovedCases();
                      },
                      size: 'small',
                      showSizeChanger: false,
                    }}
                    scroll={{ y: 300 }}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    已选 {selectedCaseIds.length} 个用例
                  </Text>
                </Card>

                {/* 脚本保存 */}
                <Card size="small">
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Text strong>压测脚本</Text>
                    <Button size="small" icon={<PlusOutlined />}
                      onClick={() => setShowCreateScriptModal(true)}
                      disabled={selectedCaseIds.length === 0}>
                      保存为脚本
                    </Button>
                  </Space>
                  {scripts.length > 0 && (
                    <Select
                      placeholder="选择已有脚本"
                      value={selectedScriptId}
                      onChange={setSelectedScriptId}
                      allowClear
                      style={{ width: '100%', marginTop: 8 }}
                    >
                      {scripts.map(s => (
                        <Option key={s.id} value={s.id}>{s.name} (v{s.version})</Option>
                      ))}
                    </Select>
                  )}
                </Card>
              </div>

              {/* 右侧：执行与监控 */}
              <div style={{ flex: 1 }}>
                {/* 执行控制 */}
                <Card size="small" title="执行控制" style={{ marginBottom: 12 }}>
                  <Space>
                    <Button type="primary" icon={<PlayCircleOutlined />}
                      onClick={handleStart} loading={startLoading}
                      disabled={execStatus === 'running'}
                      danger>
                      开始压测
                    </Button>
                    <Button icon={<StopOutlined />}
                      onClick={handleStop}
                      disabled={execStatus !== 'running'}>
                      停止
                    </Button>
                    <Button icon={<ReloadOutlined />}
                      onClick={handleReset}
                      disabled={execStatus === 'running'}>
                      重置
                    </Button>
                    <Badge
                      status={execStatus === 'running' ? 'processing' : execStatus === 'completed' ? 'success' : execStatus === 'stopped' ? 'warning' : 'default'}
                      text={
                        execStatus === 'running' ? '运行中' :
                        execStatus === 'completed' ? '已完成' :
                        execStatus === 'stopped' ? '已停止' :
                        execStatus === 'failed' ? '失败' : '空闲'
                      }
                    />
                  </Space>
                  {execStatus !== 'idle' && (
                    <Progress percent={execProgress} style={{ marginTop: 8 }}
                      status={execStatus === 'failed' ? 'exception' : execStatus === 'completed' ? 'success' : 'active'} />
                  )}
                </Card>

                {/* 实时图表 */}
                {execStatus === 'idle' ? (
                  <Card style={{ marginBottom: 12 }}>
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <span>
                          尚未启动压测<br />
                          <Text type="secondary">配置左侧参数并选择用例后，点击"开始压测"查看实时指标</Text>
                        </span>
                      }
                    />
                  </Card>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
                    <Card size="small" bodyStyle={{ padding: 4 }}>
                      <div ref={tpsChartRef} style={{ height: 200 }} />
                    </Card>
                    <Card size="small" bodyStyle={{ padding: 4 }}>
                      <div ref={rtChartRef} style={{ height: 200 }} />
                    </Card>
                    <Card size="small" bodyStyle={{ padding: 4 }}>
                      <div ref={errorChartRef} style={{ height: 200 }} />
                    </Card>
                    <Card size="small" bodyStyle={{ padding: 4 }}>
                      <div ref={usersChartRef} style={{ height: 200 }} />
                    </Card>
                  </div>
                )}

                {/* 指标摘要 */}
                <Card size="small" title="指标摘要" style={{ marginBottom: 12 }}>
                  <Row gutter={16}>
                    <Col span={6}>
                      <Statistic title="Avg TPS" value={summary?.avg_tps || 0} precision={1} suffix="TPS"
                        valueStyle={{ color: '#52c41a' }} />
                    </Col>
                    <Col span={6}>
                      <Statistic title="Avg RT" value={summary?.avg_rt || 0} precision={0} suffix="ms"
                        valueStyle={{ color: '#1890ff' }} />
                    </Col>
                    <Col span={6}>
                      <Statistic title="P99 RT" value={summary?.p99_rt || 0} precision={0} suffix="ms"
                        valueStyle={{ color: '#fa8c16' }} />
                    </Col>
                    <Col span={6}>
                      <Statistic title="Error Rate" value={summary?.error_rate || 0} precision={1} suffix="%"
                        valueStyle={{ color: (summary?.error_rate || 0) > 1 ? '#ff4d4f' : '#52c41a' }} />
                    </Col>
                  </Row>
                </Card>

                {/* 执行历史 */}
                <Card size="small" title={`执行历史 (${executions.length})`}>
                  <Table
                    dataSource={executions}
                    columns={execColumns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 10, size: 'small' }}
                    scroll={{ x: 700 }}
                  />
                </Card>
              </div>
            </div>
          ) : (
            <Card><Text type="secondary">请先选择项目</Text></Card>
          )}
        </Tabs.TabPane>

        {/* JMeter Tab (placeholder) */}
        <Tabs.TabPane tab={<><DashboardOutlined /> JMeter 测试</>} key="jmeter">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }} size="large">
              <Alert
                type="info"
                message="JMeter 压测"
                description="JMeter 脚本管理、场景配置和执行功能已就绪。请使用左侧 Locust 标签进行基于 API 用例的压力测试，或直接上传 JMeter JMX 脚本进行测试。"
              />
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <DashboardOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
                <Paragraph type="secondary" style={{ marginTop: 16 }}>
                  JMeter 模块可通过后端 /api/v1/performance/ 接口进行脚本上传、场景配置和执行。
                  <br />这里主要展示基于 API 用例的 Locust 压测能力。
                </Paragraph>
              </div>
            </Space>
          </Card>
        </Tabs.TabPane>
      </Tabs>

      {/* 创建脚本弹窗 */}
      <Modal
        title="保存为 Locust 脚本"
        open={showCreateScriptModal}
        onOk={handleCreateScript}
        onCancel={() => setShowCreateScriptModal(false)}
        confirmLoading={createScriptLoading}
        okText="创建"
      maskClosable={false}      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>脚本名称</Text>
          <Input value={newScriptName} onChange={e => setNewScriptName(e.target.value)}
            placeholder="输入脚本名称..." />
          <Text type="secondary" style={{ fontSize: 12 }}>
            将从选中的 {selectedCaseIds.length} 个已审批API用例生成 locustfile.py
          </Text>
        </Space>
      </Modal>
    </div>
  );
};

export default PerformanceTestPage;
