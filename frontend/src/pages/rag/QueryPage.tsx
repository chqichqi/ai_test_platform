import React, { useState } from 'react';
import { Card, Typography, Input, Button, Space, List, Tag, message, Select, Spin } from 'antd';
import { SearchOutlined, CopyOutlined, ThunderboltOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface SearchResult {
  id: string;
  content: string;
  document: string;
  score: number;
  page?: number;
}

const QueryPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results] = useState<SearchResult[]>([
    {
      id: '1',
      content: 'AI Agent测试平台支持多种技能(SKILL)的开发和测试，包括文档分析、代码生成、API测试等功能。',
      document: 'API文档.pdf',
      score: 0.95,
      page: 12,
    },
    {
      id: '2',
      content: '知识库管理功能允许用户上传PDF、DOCX、TXT等格式的文档，系统会自动进行文本提取和向量化处理。',
      document: '用户手册.docx',
      score: 0.87,
      page: 5,
    },
    {
      id: '3',
      content: 'RAG(检索增强生成)查询基于向量相似度搜索，返回最相关的文档片段作为上下文。',
      document: '技术规范.txt',
      score: 0.82,
    },
    {
      id: '4',
      content: '系统使用ChromaDB作为向量数据库，支持多种Embedding模型，包括OpenAI、本地模型等。',
      document: '设计文档.pdf',
      score: 0.78,
      page: 8,
    },
    {
      id: '5',
      content: '查询结果可以用于生成测试用例、编写文档、回答问题等应用场景。',
      document: '应用场景.md',
      score: 0.72,
    },
  ]);
  const [collection, setCollection] = useState('default');
  const [answer, setAnswer] = useState('');

  const handleSearch = () => {
    if (!query.trim()) {
      message.warning('请输入查询问题');
      return;
    }
    
    setLoading(true);
    // 模拟API调用延迟
    setTimeout(() => {
      setLoading(false);
      message.success('查询完成，找到5个相关结果');
      // 模拟生成答案
      setAnswer(`根据知识库内容，${query}的相关信息如下：AI Agent测试平台提供了完整的RAG功能，支持从上传的文档中检索相关信息并生成回答。系统会自动处理文档分块、向量化存储和相似度搜索。`);
    }, 1500);
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('已复制到剪贴板');
  };

  const handleQuickQuery = (text: string) => {
    setQuery(text);
    message.info('已填充查询，点击搜索按钮开始查询');
  };

  const quickQueries = [
    '如何上传文档到知识库？',
    '什么是RAG？',
    '支持哪些文档格式？',
    '如何进行技能测试？',
    '向量数据库是如何工作的？',
  ];

  return (
    <div>
      <Card style={{ marginTop: 0 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div style={{ display: 'flex', gap: 16 }}>
            <Select
              value={collection}
              onChange={setCollection}
              style={{ width: 200 }}
            >
              <Option value="default">默认知识库</Option>
              <Option value="api-docs">API文档库</Option>
              <Option value="user-manuals">用户手册库</Option>
              <Option value="technical">技术文档库</Option>
            </Select>
            <Text type="secondary">当前选择: {collection}</Text>
          </div>
          
          <TextArea
            placeholder="请输入您的问题，例如：如何上传文档？什么是RAG？..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={4}
            style={{ width: '100%' }}
          />
          
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Space>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleSearch}
                loading={loading}
              >
                开始查询
              </Button>
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => handleQuickQuery(quickQueries[0])}
              >
                示例问题
              </Button>
            </Space>
            <Button onClick={() => setQuery('')}>清空</Button>
          </div>
        </Space>
      </Card>
      
      {loading && (
        <Card style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin size="large" />
          <Text style={{ display: 'block', marginTop: 16 }}>正在查询知识库，请稍候...</Text>
        </Card>
      )}
      
      {answer && !loading && (
        <Card style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={4}>AI 回答</Title>
            <Button
              type="text"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(answer)}
            >
              复制
            </Button>
          </div>
          <Card size="small" style={{ backgroundColor: '#fafafa', marginTop: 8 }}>
            <Text>{answer}</Text>
          </Card>
        </Card>
      )}
      
      {results.length > 0 && !loading && (
        <Card style={{ marginTop: 16 }}>
          <Title level={4}>检索结果 ({results.length})</Title>
          <Text type="secondary">根据相似度排序的相关文档片段</Text>
          
          <List
            dataSource={results}
            renderItem={(item) => (
              <List.Item
                key={item.id}
                actions={[
                  <Button
                    type="text"
                    icon={<CopyOutlined />}
                    onClick={() => handleCopy(item.content)}
                    size="small"
                  >
                    复制
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text strong>{item.document}</Text>
                      <Tag color={item.score > 0.9 ? 'green' : item.score > 0.8 ? 'blue' : 'orange'}>
                        相关度: {(item.score * 100).toFixed(1)}%
                      </Tag>
                      {item.page && <Tag color="purple">第 {item.page} 页</Tag>}
                    </Space>
                  }
                  description={item.content}
                />
              </List.Item>
            )}
          />
        </Card>
      )}
      
      <Card style={{ marginTop: 16 }}>
        <Title level={4}>快速查询</Title>
        <Text type="secondary">点击以下问题快速开始查询</Text>
        <Space wrap style={{ marginTop: 12 }}>
          {quickQueries.map((q, index) => (
            <Button
              key={index}
              size="small"
              onClick={() => handleQuickQuery(q)}
            >
              {q}
            </Button>
          ))}
        </Space>
      </Card>
    </div>
  );
};

export default QueryPage;