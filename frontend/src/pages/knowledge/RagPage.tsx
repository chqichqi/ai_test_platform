import React, { useState, useEffect, useCallback } from 'react';
import { Table, Card, Typography, Button, Space, Input, Tag, message, Modal, Form, Popconfirm, Tooltip, Descriptions, Tabs, List, Upload, Select, Slider, Switch, Divider, Alert, Spin } from 'antd';
import { SearchOutlined, PlusOutlined, DeleteOutlined, EyeOutlined, FolderOutlined, FileTextOutlined, BranchesOutlined, ClockCircleOutlined, UploadOutlined, FilePdfOutlined, FileWordOutlined, FileMarkdownOutlined, InboxOutlined, SettingOutlined, FileOutlined, InfoCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import knowledgeApi, { RagKnowledgeBase, Document } from '../../api/knowledgeApi';

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;
const { Dragger } = Upload;
const { TabPane } = Tabs;
const { Option } = Select;

const getFileIcon = (type: string) => {
  switch (type.toUpperCase()) {
    case 'PDF':
      return <FilePdfOutlined style={{ color: '#ef4444', fontSize: 20 }} />;
    case 'DOC':
    case 'DOCX':
      return <FileWordOutlined style={{ color: '#3b82f6', fontSize: 20 }} />;
    case 'MD':
    case 'TXT':
      return <FileMarkdownOutlined style={{ color: '#0891b2', fontSize: 20 }} />;
    default:
      return <FileTextOutlined style={{ color: '#6b7280', fontSize: 20 }} />;
  }
};

const DEFAULT_SETTINGS = {
  chunkSize: 500,
  chunkMethod: 'auto',
  embeddingModel: 'text-embedding-3-small',
  enableOcr: true,
};

const RagPage: React.FC = () => {
  const [ragBases, setRagBases] = useState<RagKnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedRag, setSelectedRag] = useState<RagKnowledgeBase | null>(null);
  const [form] = Form.useForm();
  const [settingsForm] = Form.useForm();
  const [docContentVisible, setDocContentVisible] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [settingsModalVisible, setSettingsModalVisible] = useState(false);
  const [tempSettings, setTempSettings] = useState(DEFAULT_SETTINGS);

  const loadRagBases = useCallback(async () => {
    setLoading(true);
    try {
      const result = await knowledgeApi.listRagBases();
      setRagBases(result.items);
    } catch (error) {
      message.error('加载知识库列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRagBases();
  }, [loadRagBases]);

  const columns: ColumnsType<RagKnowledgeBase> = [
    {
      title: '知识库名称',
      dataIndex: 'name',
      key: 'name',
      render: (text) => (
        <Space>
          <FolderOutlined style={{ color: '#6366f1' }} />
          <Text strong>{text}</Text>
        </Space>
      ),
    },
    {
      title: '项目/版本',
      key: 'project',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text code>{record.project}</Text>
          <Tag color="blue">{record.version}</Tag>
        </Space>
      ),
    },
    {
      title: '文档/分块',
      key: 'counts',
      width: 120,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text><FileTextOutlined /> {record.documentCount} 文档</Text>
          <Text type="secondary">{record.chunkCount} 分块</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: 'active' | 'inactive' | 'processing') => {
        const statusMap = {
          active: { color: 'green', text: '已激活' },
          inactive: { color: 'default', text: '未激活' },
          processing: { color: 'orange', text: '处理中' },
        };
        const config = statusMap[status];
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '图谱',
      dataIndex: 'hasGraph',
      key: 'hasGraph',
      width: 80,
      render: (hasGraph) => 
        hasGraph ? 
          <Tag color="cyan" icon={<BranchesOutlined />}>已生成</Tag> : 
          <Tag>未生成</Tag>,
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      render: (text) => (
        <Space>
          <ClockCircleOutlined />
          <Text>{text}</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_, record) => (
        <Space size="small">
          <Button 
            type="link" 
            icon={<EyeOutlined />} 
            size="small"
            onClick={async () => {
              try {
                const detail = await knowledgeApi.getRagBase(record.id);
                setSelectedRag(detail);
                setDetailVisible(true);
              } catch (error) {
                message.error('获取详情失败');
              }
            }}
          >
            详情
          </Button>
          <Tooltip title="生成知识图谱">
            <Button 
              type="link" 
              icon={<BranchesOutlined />} 
              size="small"
              disabled={record.hasGraph || record.status === 'processing'}
              onClick={() => handleGenerateGraph(record)}
            >
              生成图谱
            </Button>
          </Tooltip>
          <Popconfirm
            title="确定要删除此知识库吗？关联的知识图谱也会被删除"
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

  const handleDelete = async (id: string) => {
    try {
      await knowledgeApi.deleteRagBase(id);
      message.success('知识库及关联图谱已删除');
      loadRagBases();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleGenerateGraph = async (record: RagKnowledgeBase) => {
    const hideLoading = message.loading({ content: `正在为 "${record.name}" 生成知识图谱...`, key: 'generateGraph', duration: 0 });
    
    try {
      const ragDetail = await knowledgeApi.getRagBase(record.id);
      const documents = (ragDetail.documents || []).map(doc => ({
        content: doc.content || ''
      }));
      
      if (documents.length === 0 || documents.every(d => d.content.length < 50)) {
        hideLoading();
        message.error({ content: '文档内容不足，请重新上传文档', key: 'generateGraph' });
        return;
      }
      
      const result = await knowledgeApi.generateGraph(record.id, {
        name: record.name,
        documents
      });
      
      hideLoading();
      const method = result.usedLLM ? 'LLM智能提取' : '正则表达式提取';
      message.success({ content: `知识图谱生成成功！使用${method}，提取了 ${result.entityCount} 个实体，${result.relationCount} 个关系`, key: 'generateGraph', duration: 4 });
      loadRagBases();
    } catch (error: any) {
      hideLoading();
      message.error({ content: error.response?.data?.message || '图谱生成失败，请检查LLM配置', key: 'generateGraph' });
    }
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields(['name']);
      
      if (fileList.length === 0) {
        message.warning('请上传至少一个文档');
        return;
      }

      const hideLoading = message.loading({ content: '正在创建知识库...', duration: 0 });

      try {
        const kb = await knowledgeApi.createRagBase({
          name: values.name,
          description: values.description || '',
          chunkSize: tempSettings.chunkSize,
          chunkMethod: tempSettings.chunkMethod,
          embeddingModel: tempSettings.embeddingModel,
        });

        let successCount = 0;
        for (const uploadFile of fileList) {
          const file = (uploadFile.originFileObj || uploadFile) as File;
          const fileSize = (file as any).size || uploadFile.size || 0;
          const ext = uploadFile.name.split('.').pop()?.toLowerCase() || '';
          
          let content = '';
          try {
            if (ext === 'txt' || ext === 'md') {
              content = await new Promise<string>((resolve) => {
                const reader = new FileReader();
                reader.onload = (e) => resolve(e.target?.result as string || '');
                reader.onerror = () => resolve('');
                reader.readAsText(file);
              });
            } else if (ext === 'pdf' || ext === 'docx' || ext === 'doc') {
              const arrayBuffer = await file.arrayBuffer();
              const uint8Array = new Uint8Array(arrayBuffer);
              let binary = '';
              for (let j = 0; j < uint8Array.length; j++) {
                binary += String.fromCharCode(uint8Array[j]);
              }
              content = btoa(binary);
            }
          } catch (err) {
            console.error(`解析文件 ${uploadFile.name} 异常:`, err);
          }

          try {
            await knowledgeApi.addDocument(kb.id, {
              name: uploadFile.name,
              type: ext.toUpperCase(),
              size: `${(fileSize / 1024 / 1024).toFixed(2)} MB`,
              content: content || `# ${uploadFile.name}\n\n文档内容`,
            });
            successCount++;
          } catch (docError) {
            console.error(`上传文档 ${uploadFile.name} 失败:`, docError);
          }
        }

        hideLoading();
        setModalVisible(false);
        form.resetFields();
        setFileList([]);
        setTempSettings(DEFAULT_SETTINGS);
        
        if (successCount > 0) {
          message.success(`知识库创建成功！已上传 ${successCount} 个文档`);
          loadRagBases();
        } else {
          message.error('文档上传失败，请重试');
        }
      } catch (createError) {
        hideLoading();
        message.error('知识库创建失败');
      }
    } catch (error) {
      console.error('Create knowledge base error:', error);
    }
  };

  const handleViewDocument = async (doc: Document) => {
    setSelectedDoc(doc);
    setDocContentVisible(true);
  };

  const handleUploadDocument = async () => {
    if (!selectedRag) return;
    message.info('请在创建知识库时上传文档');
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!selectedRag) return;
    try {
      await knowledgeApi.deleteDocument(selectedRag.id, docId);
      message.success('文档已删除');
      const updatedRag = await knowledgeApi.getRagBase(selectedRag.id);
      setSelectedRag(updatedRag);
      loadRagBases();
    } catch (error) {
      message.error('删除文档失败');
    }
  };

  const handleOpenSettings = () => {
    settingsForm.setFieldsValue(tempSettings);
    setSettingsModalVisible(true);
  };

  const handleSaveSettings = () => {
    settingsForm.validateFields().then(values => {
      setTempSettings(values);
      setSettingsModalVisible(false);
    });
  };

  const filteredData = ragBases.filter(kb =>
    kb.name.toLowerCase().includes(searchText.toLowerCase()) ||
    kb.project.toLowerCase().includes(searchText.toLowerCase())
  );

  const uploadProps = {
    multiple: true,
    fileList,
    beforeUpload: (file: UploadFile) => {
      const ext = file.name.split('.').pop()?.toLowerCase() || '';
      const isValidType = ['pdf', 'doc', 'docx', 'txt', 'md'].includes(ext);
      
      if (!isValidType) {
        message.error(`不支持 ${ext} 格式，只支持 PDF、DOC、DOCX、TXT、MD`);
        return Upload.LIST_IGNORE;
      }
      const isLt50M = (file.size as number) / 1024 / 1024 < 50;
      if (!isLt50M) {
        message.error('文件大小不能超过 50MB');
        return Upload.LIST_IGNORE;
      }
      
      setFileList([...fileList, file]);
      return false;
    },
    onRemove: (file: UploadFile) => {
      const index = fileList.indexOf(file);
      const newFileList = fileList.slice();
      newFileList.splice(index, 1);
      setFileList(newFileList);
    },
  };

  return (
    <div>
      <Card style={{ marginTop: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Search
            placeholder="搜索知识库名称或项目"
            allowClear
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            onSearch={setSearchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadRagBases} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
              创建知识库
            </Button>
          </Space>
        </div>
        
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={filteredData}
            rowKey="id"
            pagination={{ pageSize: 10 }}
          />
        </Spin>
      </Card>
      
      <Card style={{ marginTop: 16 }}>
        <Title level={4}>统计概览</Title>
        <Space size="large">
          <div>
            <Text type="secondary">知识库总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{ragBases.length}</Title>
          </div>
          <div>
            <Text type="secondary">文档总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{ragBases.reduce((sum, kb) => sum + kb.documentCount, 0)}</Title>
          </div>
          <div>
            <Text type="secondary">分块总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{ragBases.reduce((sum, kb) => sum + kb.chunkCount, 0)}</Title>
          </div>
          <div>
            <Text type="secondary">图谱覆盖率</Text>
            <Title level={3} style={{ margin: '8px 0' }}>
              {ragBases.length > 0 
                ? Math.round(ragBases.filter(kb => kb.hasGraph).length / ragBases.length * 100) 
                : 0}%
            </Title>
          </div>
        </Space>
      </Card>

      <Modal
        maskClosable={false}
        title="创建RAG知识库"
        open={modalVisible}
        onOk={handleCreate}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
          setFileList([]);
          setTempSettings(DEFAULT_SETTINGS);
        }}
        okText="创建"
        cancelText="取消"
        width={700}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="知识库名称"
            rules={[{ required: true, message: '请输入知识库名称' }]}
          >
            <Input placeholder="请输入知识库名称，如：产品文档库" />
          </Form.Item>
          
          <Form.Item
            label={
              <Space>
                <span>上传文档</span>
                <Tag color="red">必填</Tag>
              </Space>
            }
            required
          >
            <Dragger {...uploadProps} style={{ padding: '12px 0' }}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined style={{ color: '#6366f1' }} />
              </p>
              <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
              <p className="ant-upload-hint">
                支持 PDF、DOC、DOCX、TXT、MD 格式，单个文件不超过 50MB
              </p>
            </Dragger>
            {fileList.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary">已选择 {fileList.length} 个文件：</Text>
                <div style={{ marginTop: 8 }}>
                  {fileList.slice(0, 5).map(file => (
                    <Tag key={file.uid} icon={<FileOutlined />} style={{ marginBottom: 4 }}>
                      {file.name}
                    </Tag>
                  ))}
                  {fileList.length > 5 && (
                    <Tag>+{fileList.length - 5} 更多文件</Tag>
                  )}
                </div>
              </div>
            )}
          </Form.Item>
          
          <Form.Item
            name="description"
            label="描述"
          >
            <Input.TextArea rows={2} placeholder="请输入知识库描述（可选）" />
          </Form.Item>
          
          <Form.Item>
            <Button 
              icon={<SettingOutlined />} 
              onClick={handleOpenSettings}
            >
              高级设置
            </Button>
            <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
              覆盖系统默认值 | 当前: {tempSettings.embeddingModel}，{tempSettings.chunkSize}字符，{tempSettings.chunkMethod === 'auto' ? '自动分块' : tempSettings.chunkMethod}
            </Text>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        maskClosable={false}
        title="高级设置"
        open={settingsModalVisible}
        onOk={handleSaveSettings}
        onCancel={() => setSettingsModalVisible(false)}
        okText="确定"
        cancelText="取消"
        width={520}
      >
        <Alert
          message="提示"
          description={
            <div style={{ fontSize: 12 }}>
              <p style={{ margin: '0 0 8px 0' }}>此处设置将覆盖系统默认配置。如需修改全局默认值，请前往「系统设置 → 知识库配置」。</p>
              <p style={{ margin: 0 }}><InfoCircleOutlined style={{ marginRight: 4 }} />向量数据库连接由系统设置统一配置，Embedding模型创建后不可更改。</p>
            </div>
          }
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form form={settingsForm} layout="vertical" initialValues={DEFAULT_SETTINGS}>
          <Form.Item
            name="embeddingModel"
            label={
              <Space>
                <span>Embedding模型</span>
                <Tag color="orange" style={{ fontSize: 11 }}>创建后不可更改</Tag>
              </Space>
            }
            tooltip="用于将文本转换为向量，仅用于检索阶段，与LLM无关"
          >
            <Select placeholder="选择Embedding模型">
              <Option value="text-embedding-3-small">text-embedding-3-small（推荐，1536维）</Option>
              <Option value="text-embedding-3-large">text-embedding-3-large（更精确，3072维）</Option>
              <Option value="text-embedding-ada-002">text-embedding-ada-002（经典，1536维）</Option>
            </Select>
          </Form.Item>
          
          <Divider orientation="left" style={{ margin: '12px 0' }}>分块设置</Divider>
          <Form.Item
            name="chunkSize"
            label="分块大小"
            tooltip="每个文本块的最大字符数"
          >
            <Slider
              min={100}
              max={2000}
              marks={{ 100: '100', 500: '500', 1000: '1000', 1500: '1500', 2000: '2000' }}
            />
          </Form.Item>
          <Form.Item
            name="chunkMethod"
            label="分块方式"
            tooltip="选择文本分块的策略"
          >
            <Select placeholder="选择分块方式">
              <Option value="auto">自动分块（推荐）</Option>
              <Option value="paragraph">按段落分块</Option>
              <Option value="sentence">按句子分块</Option>
              <Option value="fixed">固定长度分块</Option>
              <Option value="semantic">语义分块</Option>
            </Select>
          </Form.Item>
          
          <Divider orientation="left" style={{ margin: '12px 0' }}>其他设置</Divider>
          <Form.Item
            name="enableOcr"
            label="启用 OCR"
            valuePropName="checked"
            tooltip="对图片类型的文档启用文字识别"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        maskClosable={false}
        title={
          <Space>
            <FolderOutlined style={{ color: '#6366f1' }} />
            <span>{selectedRag?.name}</span>
          </Space>
        }
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
        ]}
        width={900}
      >
        <Tabs defaultActiveKey="info">
          <TabPane tab="基本信息" key="info">
            {selectedRag && (
              <Descriptions column={2} bordered>
                <Descriptions.Item label="知识库名称">{selectedRag.name}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={selectedRag.status === 'active' ? 'green' : 'orange'}>
                    {selectedRag.status === 'active' ? '已激活' : '处理中'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="项目标识">
                  <Text code>{selectedRag.project}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="版本">
                  <Tag color="blue">{selectedRag.version}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="文档数量">{selectedRag.documentCount} 个</Descriptions.Item>
                <Descriptions.Item label="分块数量">{selectedRag.chunkCount} 个</Descriptions.Item>
                <Descriptions.Item label="分块大小">{selectedRag.chunkSize || 500} 字符</Descriptions.Item>
                <Descriptions.Item label="分块方式">{selectedRag.chunkMethod || '自动分块'}</Descriptions.Item>
                <Descriptions.Item label="Embedding模型">{selectedRag.embeddingModel || 'text-embedding-3-small'}</Descriptions.Item>
                <Descriptions.Item label="图谱状态">
                  {selectedRag.hasGraph ? 
                    <Tag color="cyan">已生成</Tag> : 
                    <Tag>未生成</Tag>
                  }
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">{selectedRag.createdAt}</Descriptions.Item>
                <Descriptions.Item label="更新时间">{selectedRag.updatedAt}</Descriptions.Item>
                <Descriptions.Item label="描述" span={2}>
                  {selectedRag.description || '暂无描述'}
                </Descriptions.Item>
              </Descriptions>
            )}
          </TabPane>
          <TabPane 
            tab={
              <Space>
                <FileTextOutlined />
                <span>文档列表 ({selectedRag?.documents?.length || 0})</span>
              </Space>
            } 
            key="documents"
          >
            <div style={{ marginBottom: 16 }}>
              <Button type="primary" icon={<UploadOutlined />} onClick={handleUploadDocument}>
                上传文档
              </Button>
            </div>
            <List
              dataSource={selectedRag?.documents || []}
              locale={{ emptyText: '暂无文档' }}
              renderItem={(doc) => (
                <List.Item
                  actions={[
                    <Button 
                      type="link" 
                      icon={<EyeOutlined />} 
                      size="small"
                      onClick={() => handleViewDocument(doc)}
                    >
                      查看内容
                    </Button>,
                    <Popconfirm
                      title="确定要删除此文档吗？"
                      onConfirm={() => handleDeleteDocument(doc.id)}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" danger icon={<DeleteOutlined />} size="small">删除</Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={getFileIcon(doc.type)}
                    title={
                      <Space>
                        <Text strong>{doc.name}</Text>
                        <Tag>{doc.type}</Tag>
                        <Tag color={doc.status === 'processed' ? 'green' : 'orange'}>
                          {doc.status === 'processed' ? '已处理' : '处理中'}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space size="large">
                        <Text type="secondary">大小: {doc.size}</Text>
                        <Text type="secondary">上传时间: {doc.uploadTime}</Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </TabPane>
        </Tabs>
      </Modal>

      <Modal
        maskClosable={false}
        title={
          <Space>
            {selectedDoc && getFileIcon(selectedDoc.type)}
            <span>{selectedDoc?.name}</span>
          </Space>
        }
        open={docContentVisible}
        onCancel={() => setDocContentVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDocContentVisible(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {selectedDoc && (
          <div>
            <Space style={{ marginBottom: 16 }}>
              <Tag>{selectedDoc.type}</Tag>
              <Tag color="green">{selectedDoc.status === 'processed' ? '已处理' : '处理中'}</Tag>
              <Text type="secondary">大小: {selectedDoc.size}</Text>
              <Text type="secondary">上传: {selectedDoc.uploadTime}</Text>
            </Space>
            <Card 
              style={{ 
                background: '#fafafa', 
                maxHeight: 500, 
                overflow: 'auto',
                border: '1px solid #e8e8e8',
              }}
            >
              <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                {selectedDoc.content}
              </Paragraph>
            </Card>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default RagPage;