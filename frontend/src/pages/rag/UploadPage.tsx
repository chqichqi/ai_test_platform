import React, { useState } from 'react';
import { Upload, Card, Typography, Button, Form, Select, Input, message, Progress, Space, Tag } from 'antd';
import { InboxOutlined, UploadOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const { Dragger } = Upload;
const { Option } = Select;
const { TextArea } = Input;

const UploadPage: React.FC = () => {
  const [form] = Form.useForm();
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fileList, setFileList] = useState<any[]>([]);

  const uploadProps = {
    name: 'file',
    multiple: true,
    fileList,
    beforeUpload: (file: any) => {
      const isLt100M = file.size / 1024 / 1024 < 100;
      if (!isLt100M) {
        message.error('文件大小不能超过100MB');
        return false;
      }
      setFileList([...fileList, file]);
      return false;
    },
    onChange(info: any) {
      const { status } = info.file;
      if (status === 'removed') {
        setFileList(info.fileList);
      }
    },
  };

  const handleUpload = async () => {
    if (fileList.length === 0) {
      message.warning('请先选择要上传的文件');
      return;
    }
    
    setUploading(true);
    setProgress(0);
    
    // 模拟上传进度
    const interval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 10;
      });
    }, 300);
    
    // 模拟上传API调用
    setTimeout(() => {
      clearInterval(interval);
      setProgress(100);
      setUploading(false);
      message.success('文件上传成功！');
      setFileList([]);
      form.resetFields();
    }, 3000);
  };

  const onFinish = (values: any) => {
    console.log('表单数据:', values);
    handleUpload();
  };

  return (
    <div>
      <Card style={{ marginTop: 0 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
        >
          <Form.Item
            name="files"
            label="选择文件"
            rules={[{ required: true, message: '请选择要上传的文件' }]}
          >
            <Dragger {...uploadProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
              <p className="ant-upload-hint">
                支持 PDF, DOCX, TXT, PNG, JPG 等格式，单个文件不超过100MB
              </p>
            </Dragger>
          </Form.Item>
          
          {fileList.length > 0 && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Title level={5}>已选择文件 ({fileList.length})</Title>
              <ul>
                {fileList.map((file, index) => (
                  <li key={index}>
                    <Text>{file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)</Text>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          
          <Form.Item
            name="collection"
            label="知识库集合"
            initialValue="default"
            rules={[{ required: true, message: '请选择知识库集合' }]}
          >
            <Select placeholder="选择知识库集合">
              <Option value="default">默认集合</Option>
              <Option value="api-docs">API文档</Option>
              <Option value="user-manuals">用户手册</Option>
              <Option value="technical">技术文档</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="chunkSize"
            label="分块大小"
            initialValue="1000"
            rules={[{ required: true, message: '请选择分块大小' }]}
          >
            <Select placeholder="选择分块大小">
              <Option value="500">500 字符</Option>
              <Option value="1000">1000 字符</Option>
              <Option value="1500">1500 字符</Option>
              <Option value="2000">2000 字符</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="description"
            label="描述"
          >
            <TextArea
              placeholder="请输入文档描述（可选）"
              rows={3}
            />
          </Form.Item>
          
          {uploading && (
            <Form.Item>
              <Card size="small">
                <Text>上传进度</Text>
                <Progress percent={progress} />
              </Card>
            </Form.Item>
          )}
          
          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                loading={uploading}
                icon={<UploadOutlined />}
                disabled={fileList.length === 0}
              >
                {uploading ? '上传中...' : '开始上传'}
              </Button>
              <Button onClick={() => {
                setFileList([]);
                form.resetFields();
              }}>
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
      
      <Card style={{ marginTop: 16 }}>
        <Title level={4}>支持格式</Title>
        <Space wrap>
          <Tag color="blue">PDF (.pdf)</Tag>
          <Tag color="blue">Word (.docx, .doc)</Tag>
          <Tag color="blue">文本 (.txt)</Tag>
          <Tag color="blue">Markdown (.md)</Tag>
          <Tag color="blue">图片 (.png, .jpg, .jpeg)</Tag>
          <Tag color="blue">Excel (.xlsx, .xls)</Tag>
          <Tag color="blue">PowerPoint (.pptx)</Tag>
        </Space>
        
        <Title level={4} style={{ marginTop: 16 }}>处理流程</Title>
        <ol>
          <li><Text>文件上传到服务器</Text></li>
          <li><Text>文档解析和文本提取</Text></li>
          <li><Text>文本分块（根据设置的大小）</Text></li>
          <li><Text>向量化处理（生成Embedding）</Text></li>
          <li><Text>存储到向量数据库</Text></li>
          <li><Text>可用于RAG查询</Text></li>
        </ol>
      </Card>
    </div>
  );
};

export default UploadPage;