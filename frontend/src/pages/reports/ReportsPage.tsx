import React, { useState, useEffect } from 'react';
import {
  Card, Typography, Table, Space, Tag, Button, Modal, message, Input, Popconfirm,
  Tooltip, Row, Col, Statistic, Empty, Divider
} from 'antd';
import {
  DownloadOutlined, EyeOutlined, DeleteOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined,
  MinusCircleOutlined, FileTextOutlined, BarChartOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import axiosInstance from '../../api/axiosConfig';

const { Title, Text } = Typography;

interface ReportItem {
  project: string;
  version: string;
  run_id: string;
  run_ts: string;
  has_html: boolean;
  has_results: boolean;
  summary: {
    total?: number; passed?: number; failed?: number;
    broken?: number; skipped?: number;
  };
}

const ReportsPage: React.FC = () => {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewingReport, setViewingReport] = useState<ReportItem | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailData, setDetailData] = useState<any>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  useEffect(() => { loadReports(); }, []);

  const loadReports = async () => {
    setLoading(true);
    try {
      const { data } = await axiosInstance.get('/test-reports/list');
      setReports(data.items || []);
    } catch (e: any) {
      message.error('加载报告列表失败');
      setReports([]);
    } finally { setLoading(false); }
  };

  // ─── 查看报告 ───
  const handleView = async (record: ReportItem) => {
    if (record.has_html) {
      // 在新窗口打开 Allure HTML 报告
      window.open(
        `${axiosInstance.defaults.baseURL}/test-reports/serve/${record.project}/${record.version}/${record.run_id}`,
        '_blank'
      );
    } else {
      message.info('HTML 报告未生成，请在服务器运行 allure generate');
    }
  };

  const handleViewDetail = async (record: ReportItem) => {
    try {
      const { data } = await axiosInstance.get(
        `/test-reports/detail/${record.project}/${record.version}/${record.run_id}`
      );
      setDetailData(data);
      setViewingReport(record);
      setDetailVisible(true);
    } catch {
      message.error('加载报告详情失败');
    }
  };

  // ─── 下载 ───
  const handleDownload = (record: ReportItem) => {
    window.open(
      `${axiosInstance.defaults.baseURL}/test-reports/download/${record.project}/${record.version}/${record.run_id}`,
      '_blank'
    );
  };

  // ─── 删除（三重确认） ───
  const handleDelete = async (record: ReportItem) => {
    // 第一重：Popconfirm
    Modal.confirm({
      title: <span style={{ color: '#ff4d4f' }}>⚠️ 确认删除测试报告</span>,
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>即将删除以下报告：</p>
          <p><strong>项目：</strong>{record.project}</p>
          <p><strong>版本：</strong>{record.version}</p>
          <p><strong>时间：</strong>{record.run_ts}</p>
          <Divider />
          <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
            ⚠️ 此操作仅删除测试报告文件，不会影响项目源代码和测试用例！
          </p>
          <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
            ⚠️ 删除后无法恢复！请确认您要删除的是报告文件，而非项目文件！
          </p>
          <p style={{ color: '#ff4d4f', fontWeight: 'bold' }}>
            ⚠️ 第三次提醒：确认删除的是 TEST-REPORTS 目录下的报告，不是项目源文件！
          </p>
          <Divider />
          <p>请输入 <code>DELETE</code> 以确认：</p>
          <Input
            placeholder="输入 DELETE"
            onChange={e => setDeleteConfirmText(e.target.value)}
            style={{ marginTop: 8 }}
          />
        </div>
      ),
      okText: '确认删除报告',
      okButtonProps: {
        danger: true,
        disabled: deleteConfirmText !== 'DELETE',
      },
      cancelText: '取消',
      onOk: async () => {
        try {
          await axiosInstance.delete(
            `/test-reports/delete/${record.project}/${record.version}/${record.run_id}?confirm=DELETE`
          );
          message.success('报告已删除（源文件未受影响）');
          loadReports();
        } catch (e: any) {
          message.error(e.response?.data?.message || '删除失败');
        }
      },
      onCancel: () => setDeleteConfirmText(''),
    });
  };

  const columns: ColumnsType<ReportItem> = [
    { title: '项目', dataIndex: 'project', key: 'project', width: 120 },
    { title: '版本', dataIndex: 'version', key: 'version', width: 100 },
    {
      title: '时间', dataIndex: 'run_ts', key: 'run_ts', width: 160,
      render: (ts: string) => <Text style={{ fontSize: 12 }}>{ts}</Text>,
    },
    {
      title: '结果统计', key: 'summary', width: 280,
      render: (_, r) => {
        const s = r.summary || {};
        return (
          <Space size={4}>
            <Tag color="green">通过 {s.passed ?? '-'}</Tag>
            <Tag color="red">失败 {s.failed ?? '-'}</Tag>
            <Tag color="orange">异常 {s.broken ?? '-'}</Tag>
            <Tag color="default">跳过 {s.skipped ?? '-'}</Tag>
          </Space>
        );
      },
    },
    {
      title: '格式', key: 'format', width: 80,
      render: (_, r) => (
        r.has_html
          ? <Tag color="blue">HTML</Tag>
          : <Tag>JSON</Tag>
      ),
    },
    {
      title: '操作', key: 'action', width: 220,
      render: (_, r) => (
        <Space>
          <Tooltip title={r.has_html ? '查看 HTML 报告' : 'HTML 未生成'}>
            <Button size="small" icon={<EyeOutlined />}
              disabled={!r.has_html} onClick={() => handleView(r)}>
              查看
            </Button>
          </Tooltip>
          <Button size="small" icon={<BarChartOutlined />}
            onClick={() => handleViewDetail(r)}>
            详情
          </Button>
          <Button size="small" icon={<DownloadOutlined />}
            onClick={() => handleDownload(r)}>
            下载
          </Button>
          <Popconfirm
            title="确定删除此报告？源文件不受影响。"
            onConfirm={() => handleDelete(r)}
            okText="去确认" okButtonProps={{ danger: true }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ─── 汇总统计 ───
  const totalPassed = reports.reduce((s, r) => s + (r.summary?.passed || 0), 0);
  const totalFailed = reports.reduce((s, r) => s + (r.summary?.failed || 0) + (r.summary?.broken || 0), 0);
  const totalSkipped = reports.reduce((s, r) => s + (r.summary?.skipped || 0), 0);

  return (
    <div style={{ padding: 16 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <FileTextOutlined /> 测试报告
          </Title>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={loadReports} loading={loading}>
            刷新
          </Button>
        </Col>
      </Row>

      {/* 汇总卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Statistic title="报告总数" value={reports.length} prefix={<FileTextOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="通过" value={totalPassed} valueStyle={{ color: '#3f8600' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="失败/异常" value={totalFailed} valueStyle={{ color: '#cf1322' }} prefix={<CloseCircleOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="跳过" value={totalSkipped} prefix={<MinusCircleOutlined />} /></Card>
        </Col>
      </Row>

      <Card>
        <Table
          columns={columns}
          dataSource={reports}
          rowKey={r => `${r.project}/${r.version}/${r.run_id}`}
          loading={loading}
          locale={{ emptyText: <Empty description="暂无测试报告。执行测试后将自动生成。" /> }}
        />
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="报告详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        width={800}
        footer={null}
      >
        {detailData && (
          <div>
            {viewingReport && (
              <p>
                <strong>项目：</strong>{viewingReport.project} &nbsp;
                <strong>版本：</strong>{viewingReport.version} &nbsp;
                <strong>时间：</strong>{viewingReport.run_ts}
              </p>
            )}
            {(detailData.results || []).map((r: any, i: number) => {
              const statusIcon = r.status === 'passed' ? '✅' :
                r.status === 'failed' ? '❌' : r.status === 'broken' ? '💥' : '⏭️';
              return (
                <Card key={i} size="small" style={{ marginBottom: 8 }}
                  title={<span>{statusIcon} {r.name}</span>}
                >
                  <Space>
                    <Tag color={r.status === 'passed' ? 'green' : 'red'}>{r.status}</Tag>
                    {(r.steps || []).map((s: any, j: number) => (
                      <Tag key={j}>{s.name}</Tag>
                    ))}
                  </Space>
                  {r.statusDetails?.message && (
                    <p style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
                      {r.statusDetails.message}
                    </p>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ReportsPage;
