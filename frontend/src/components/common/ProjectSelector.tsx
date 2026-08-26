import React, { useState, useEffect } from 'react';
import { Card, List, Typography, Spin, Empty, Input } from 'antd';
import { FolderOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { projectApi } from '../../api/projectApi';

const { Title, Text } = Typography;
const { Search } = Input;

interface ProjectSelectorProps {
  onSelect: (projectId: number) => void;
  basePath: string;
  title?: string;
}

interface Project {
  id: number;
  name: string;
  code: string;
  description: string | null;
  status: string;
}

const ProjectSelector: React.FC<ProjectSelectorProps> = ({ onSelect, basePath, title }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      const response = await projectApi.list({ page: 1, page_size: 100 });
      setProjects(response.items || []);
    } catch (error) {
      console.error('获取项目列表失败', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (projectId: number) => {
    onSelect(projectId);
    navigate(`${basePath}/${projectId}`);
  };

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchText.toLowerCase()) ||
    p.code.toLowerCase().includes(searchText.toLowerCase())
  );

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      {title && (
        <Title level={4} style={{ marginBottom: 16 }}>{title}</Title>
      )}
      
      <Search
        placeholder="搜索项目名称或编码"
        allowClear
        onChange={e => setSearchText(e.target.value)}
        style={{ marginBottom: 16, maxWidth: 400 }}
        prefix={<SearchOutlined />}
      />

      {filteredProjects.length === 0 ? (
        <Empty description="暂无项目，请先创建项目" />
      ) : (
        <List
          grid={{ gutter: 16, xs: 1, sm: 2, md: 3, lg: 3, xl: 4, xxl: 4 }}
          dataSource={filteredProjects}
          renderItem={(item) => (
            <List.Item>
              <Card
                hoverable
                onClick={() => handleSelect(item.id)}
                style={{ cursor: 'pointer' }}
              >
                <Card.Meta
                  avatar={<FolderOutlined style={{ fontSize: 32, color: '#1890ff' }} />}
                  title={item.name}
                  description={
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>{item.code}</Text>
                      <br />
                      <Text ellipsis style={{ fontSize: 12 }}>{item.description || '暂无描述'}</Text>
                    </div>
                  }
                />
              </Card>
            </List.Item>
          )}
        />
      )}
    </div>
  );
};

export default ProjectSelector;