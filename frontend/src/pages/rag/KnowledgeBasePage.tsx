import React, { useState } from 'react';
import { Table, Card, Typography, Button, Space, Input, Tag, message, Popconfirm } from 'antd';
import { SearchOutlined, PlusOutlined, DeleteOutlined, EyeOutlined, DownloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;
const { Search } = Input;

interface Document {
  id: string;
  name: string;
  type: string;
  size: string;
  uploadTime: string;
  status: 'processed' | 'processing' | 'failed';
  chunks: number;
}

const KnowledgeBasePage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([
    { id: '1', name: 'API文档.pdf', type: 'PDF', size: '2.4 MB', uploadTime: '2025-03-20 10:30', status: 'processed', chunks: 24 },
    { id: '2', name: '用户手册.docx', type: 'DOCX', size: '1.8 MB', uploadTime: '2025-03-19 14:20', status: 'processed', chunks: 18 },
    { id: '3', name: '技术规范.txt', type: 'TXT', size: '0.5 MB', uploadTime: '2025-03-21 09:15', status: 'processing', chunks: 0 },
    { id: '4', name: '设计图.png', type: 'IMAGE', size: '5.2 MB', uploadTime: '2025-03-18 16:45', status: 'failed', chunks: 0 },
    { id: '5', name: '需求文档.pdf', type: 'PDF', size: '3.1 MB', uploadTime: '2025-03-17 11:10', status: 'processed', chunks: 31 },
  ]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');

  const columns: ColumnsType<Document> = [
    {
      title: '文档名称',
      dataIndex: 'name',
      key: 'name',
      render: (text) => <Text strong>{text}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const statusMap = {
          processed: { color: 'green', text: '已处理' },
          processing: { color: 'orange', text: '处理中' },
          failed: { color: 'red', text: '失败' },
        };
        const config = statusMap[status as keyof typeof statusMap];
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '分块数量',
      dataIndex: 'chunks',
      key: 'chunks',
      render: (chunks) => chunks > 0 ? <Tag color="cyan">{chunks} 块</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: '上传时间',
      dataIndex: 'uploadTime',
      key: 'uploadTime',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" icon={<EyeOutlined />} size="small">查看</Button>
          <Button type="link" icon={<DownloadOutlined />} size="small">下载</Button>
          <Popconfirm
            title="确定要删除此文档吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />} size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleDelete = (id: string) => {
    setDocuments(documents.filter(doc => doc.id !== id));
    message.success('文档已删除');
  };

  const handleSearch = (value: string) => {
    setSearchText(value);
  };

  const filteredDocuments = documents.filter(doc =>
    doc.name.toLowerCase().includes(searchText.toLowerCase()) ||
    doc.type.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div>
      <Card style={{ marginTop: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Search
            placeholder="搜索文档名称或类型"
            allowClear
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            onSearch={handleSearch}
          />
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => message.info('上传功能待实现')}>
              上传文档
            </Button>
            <Button onClick={() => setLoading(!loading)}>刷新</Button>
          </Space>
        </div>
        
        <Table
          columns={columns}
          dataSource={filteredDocuments}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>
      
      <Card style={{ marginTop: 16 }}>
        <Title level={4}>知识库统计</Title>
        <Space size="large">
          <div>
            <Text type="secondary">总文档数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{documents.length}</Title>
          </div>
          <div>
            <Text type="secondary">已处理文档</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{documents.filter(d => d.status === 'processed').length}</Title>
          </div>
          <div>
            <Text type="secondary">总数据块</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{documents.reduce((sum, d) => sum + d.chunks, 0)}</Title>
          </div>
          <div>
            <Text type="secondary">存储空间</Text>
            <Title level={3} style={{ margin: '8px 0' }}>12.3 MB</Title>
          </div>
        </Space>
      </Card>
    </div>
  );
};

export default KnowledgeBasePage;