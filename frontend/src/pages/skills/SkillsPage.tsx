import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Card, Button, Space, Tag, Input, Modal, Form, Select, message, Tooltip, Upload, Typography, Steps, Row, Col, Collapse
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, CopyOutlined, EyeOutlined, ImportOutlined, ExportOutlined, UploadOutlined,
  UserOutlined, FileTextOutlined, ToolOutlined, CodeOutlined, MinusCircleOutlined, PlusCircleOutlined, ReloadOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { skillApi } from '../../api/skillApi';
import { projectApi } from '../../api/projectApi';
import { Skill, SkillType } from '../../types/skill';
import { Project } from '../../types/project';

const { Search } = Input;
const { Option } = Select;
const { Text } = Typography;
const { Step } = Steps;
const { TextArea } = Input;
const { Panel } = Collapse;

// SKILL类型选项
const SKILL_TYPE_OPTIONS = [
  { value: 'functional', label: '功能测试', color: 'blue' },
  { value: 'api', label: 'API测试', color: 'green' },
  { value: 'ui', label: 'UI测试', color: 'purple' },
  { value: 'performance', label: '性能测试', color: 'orange' },
  { value: 'security', label: '安全测试', color: 'red' },
];

const SkillsPage: React.FC = () => {
  const navigate = useNavigate();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [filterType, setFilterType] = useState<SkillType | null>(null);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  // 项目列表（用于导入时选择）
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  // 弹窗状态
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [quickCopyModalVisible, setQuickCopyModalVisible] = useState(false);
  const [currentSkill, setCurrentSkill] = useState<Skill | null>(null);
  const [importFile, setImportFile] = useState<any>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [quickCopyLoading, setQuickCopyLoading] = useState(false);

  // 快速复制表单
  const [quickCopyForm] = Form.useForm();

  // 创建步骤状态
  const [createStep, setCreateStep] = useState(0);
  const [createLoading, setCreateLoading] = useState(false);

  // 表单
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [importForm] = Form.useForm();

  // 加载SKILL列表
  const loadSkills = async (page = 1, pageSize = 10, force = false) => {
    console.log('>>> loadSkills called:', { page, pageSize, filterType, searchText, force });
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (filterType) {
        console.log('>>> Adding filterType:', filterType);
        params.skill_type = filterType;
      }
      if (searchText) {
        console.log('>>> Adding searchText:', searchText);
        params.search = searchText;
      }

      console.log('>>> API params:', JSON.stringify(params));
      const response = await skillApi.list(params);
      console.log('>>> API response:', response);
      
      // 防御性检查
      if (response && Array.isArray(response.items)) {
        console.log(`>>> Loaded ${response.items.length} skills, total: ${response.total}`);
        console.log('>>> Skills data:', response.items.map((s: any) => ({id: s.id, name: s.name, code: s.code})));
        setSkills(response.items);
        setPagination({
          current: response.page || 1,
          pageSize: response.page_size || 10,
          total: response.total || 0
        });
      } else {
        console.warn('>>> Invalid response format:', response);
        setSkills([]);
        setPagination({ current: 1, pageSize: 10, total: 0 });
      }
    } catch (error: any) {
      console.error('>>> 加载SKILL列表失败:', error);
      message.error('加载SKILL列表失败: ' + (error.response?.data?.message || error.message || '未知错误'));
      setSkills([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSkills();
    loadProjects();
  }, [filterType, searchText]);

  // 加载项目列表（用于导入时选择）
  const loadProjects = async () => {
    setProjectsLoading(true);
    try {
      const response = await projectApi.list({ page_size: 100 });
      if (response && Array.isArray(response.items)) {
        setProjects(response.items);
      } else {
        setProjects([]);
      }
    } catch (error) {
      console.error('加载项目列表失败:', error);
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  };

  // 表格列定义
  const columns: ColumnsType<Skill> = [
    {
      title: 'SKILL名称',
      dataIndex: 'name',
      key: 'name',
      width: 240,
      render: (text: string, record: Skill) => (
        <Space direction="vertical" size={0}>
          <span style={{ fontWeight: 'bold' }}>{text}</span>
          <span style={{ fontSize: '12px', color: '#666' }}>{record.code}</span>
          {record.is_default && <Tag color="blue">默认</Tag>}
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'skill_type',
      key: 'skill_type',
      width: 100,
      render: (type: SkillType) => {
        const option = SKILL_TYPE_OPTIONS.find(o => o.value === type);
        return <Tag color={option?.color || 'default'}>{option?.label || type}</Tag>;
      },
    },
    {
      title: '使用统计',
      key: 'stats',
      width: 160,
      render: (_, record: Skill) => (
        <Space>
          <Tooltip title="使用次数">
            <span>👤 {record.usage_count}</span>
          </Tooltip>
          <Tooltip title="生成次数">
            <span>📝 {record.generation_count}</span>
          </Tooltip>
          {record.avg_quality_score && (
            <Tooltip title="平均质量评分">
              <span>⭐ {record.avg_quality_score.toFixed(1)}</span>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 200,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {tags?.map(tag => <Tag key={tag}>{tag}</Tag>)}
        </Space>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record: Skill) => (
        <Space>
          <Tooltip title="查看详情">
            <Button
              type="link"
              icon={<EyeOutlined />}
              onClick={() => handleViewDetail(record)}
            />
          </Tooltip>
          {!record.is_default && (
            <Tooltip title="编辑">
              <Button
                type="link"
                icon={<EditOutlined />}
                onClick={() => handleEdit(record)}
              />
            </Tooltip>
          )}
          <Tooltip title="复制">
            <Button
              type="link"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(record)}
            />
          </Tooltip>
          {!record.is_default && (
            <Tooltip title="删除">
              <Button
                type="link"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record)}
              />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  // 查看详情
  const handleViewDetail = (skill: Skill) => {
    navigate(`/skills/${skill.id}`);
  };

  // 编辑
  const handleEdit = (skill: Skill) => {
    if (skill.is_default) {
      message.warning('预设SKILL不能编辑，请使用复制功能创建副本');
      return;
    }
    setCurrentSkill(skill);
    editForm.setFieldsValue({
      name: skill.name,
      description: skill.description,
      tags: skill.tags,
      is_default: skill.is_default,
    });
    setEditModalVisible(true);
  };

  // 复制（快速复制 - 打开创建弹窗并预填充数据）
  const handleCopy = async (skill: Skill) => {
    try {
      // 获取完整的SKILL详情
      const skillDetail = await skillApi.get(skill.id);
      
      // 清理和转换content数据，确保所有字段符合后端schema要求
      const sanitizeContent = (content: any) => {
        if (!content) return {
          role: { name: '', description: '', expertise: [], behavior_rules: [] },
          input: { required_fields: [], optional_fields: [] },
          output: { format: 'json', schema: {} },
          methods: [],
          domain_rules: [],
          quality_checks: [],
          prompt_template: ''
        };
        
        return {
          role: {
            name: content.role?.name || '',
            description: content.role?.description || '',
            expertise: Array.isArray(content.role?.expertise) ? content.role.expertise : [],
            behavior_rules: Array.isArray(content.role?.behavior_rules) ? content.role.behavior_rules : []
          },
          input: {
            required_fields: Array.isArray(content.input?.required_fields) ? content.input.required_fields : [],
            optional_fields: Array.isArray(content.input?.optional_fields) ? content.input.optional_fields : []
          },
          output: {
            format: content.output?.format || 'json',
            schema: content.output?.schema || {}
          },
          methods: Array.isArray(content.methods) ? content.methods.map((m: any) => ({
            name: m.name || '',
            description: m.description || '',
            applicable_scenarios: Array.isArray(m.applicable_scenarios) ? m.applicable_scenarios : []
          })) : [],
          domain_rules: Array.isArray(content.domain_rules) ? content.domain_rules : [],
          quality_checks: Array.isArray(content.quality_checks) ? content.quality_checks : [],
          prompt_template: content.prompt_template || ''
        };
      };
      
      const sanitizedContent = sanitizeContent(skillDetail.content);
      
      // 打开创建弹窗
      setCreateModalVisible(true);
      setCreateStep(0);
      
      // 使用 setTimeout 确保表单已渲染后再设置值
      setTimeout(() => {
        createForm.resetFields();
        createForm.setFieldsValue({
          name: `${skillDetail.name}（副本）`,
          code: `${skillDetail.code}_copy`,
          skill_type: skillDetail.skill_type,
          description: skillDetail.description || '',
          tags: Array.isArray(skillDetail.tags) ? skillDetail.tags : [],
          is_global: skillDetail.is_global ?? false,
          is_default: false,
          content: sanitizedContent
        });
        console.log('表单已填充:', createForm.getFieldsValue());
      }, 100);
      
      message.info('已加载SKILL数据，请修改信息后点击完成创建');
    } catch (error: any) {
      console.error('复制失败:', error);
      const errorMsg = error.response?.data?.detail || error.message || '无法获取SKILL详情';
      message.error('复制失败：' + errorMsg);
    }
  };

  // 提交快速复制
  const handleQuickCopySubmit = async () => {
    if (!currentSkill) return;
    
    setQuickCopyLoading(true);
    try {
      const values = await quickCopyForm.validateFields();
      
      // 获取原SKILL详情
      const originalSkill = await skillApi.get(currentSkill.id);
      
      // 创建新的SKILL数据，只修改名称和编码
      const newSkillData = {
        name: values.name,
        code: values.code,
        skill_type: originalSkill.skill_type,
        description: originalSkill.description || undefined,
        tags: originalSkill.tags || [],
        is_global: originalSkill.is_global,
        is_default: false, // 复制的不设为默认
        content: originalSkill.content,
      };
      
      await skillApi.create(newSkillData);
      message.success('快速复制成功');
      setQuickCopyModalVisible(false);
      quickCopyForm.resetFields();
      loadSkills();
    } catch (error) {
      console.error('快速复制失败:', error);
      message.error('快速复制失败');
    } finally {
      setQuickCopyLoading(false);
    }
  };

  // 删除
  const handleDelete = async (skill: Skill) => {
    if (skill.is_default) {
      message.warning('预设SKILL不能删除');
      return;
    }
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除SKILL "${skill.name}" 吗？`,
      onOk: async () => {
        try {
          await skillApi.delete(skill.id);
          message.success('删除成功');
          loadSkills();
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  // 创建提交
  const handleCreateSubmit = async () => {
    setCreateLoading(true);
    try {
      // 先验证所有步骤的必填字段
      const validationErrors: string[] = [];
      
      // 获取所有表单值
      const allValues = createForm.getFieldsValue(true);
      console.log('所有表单值:', allValues);
      
      // 验证第1步：基本信息
      if (!allValues.name?.trim()) {
        validationErrors.push('第1步【基本信息】- SKILL名称不能为空');
      }
      if (!allValues.code?.trim()) {
        validationErrors.push('第1步【基本信息】- SKILL编码不能为空');
      }
      if (!allValues.skill_type) {
        validationErrors.push('第1步【基本信息】- 请选择SKILL类型');
      }
      
      // 验证第2步：角色定义
      if (!allValues.content?.role?.name?.trim()) {
        validationErrors.push('第2步【角色定义】- 角色名称不能为空');
      }
      if (!allValues.content?.role?.description?.trim()) {
        validationErrors.push('第2步【角色定义】- 角色描述不能为空');
      }
      
      // 验证第4步：提示词模板
      if (!allValues.content?.prompt_template?.trim()) {
        validationErrors.push('第4步【提示词模板】- 提示词模板不能为空');
      }
      
      // 如果有验证错误，显示错误并停止提交
      if (validationErrors.length > 0) {
        message.error({
          content: (
            <div style={{ maxHeight: '300px', overflow: 'auto' }}>
              <div style={{ fontWeight: 'bold', marginBottom: '8px', color: '#ff4d4f' }}>
                请完善以下必填项：
              </div>
              {validationErrors.map((error, index) => (
                <div key={index} style={{ marginBottom: '4px', color: '#595959' }}>
                  {index + 1}. {error}
                </div>
              ))}
              <div style={{ marginTop: '12px', color: '#8c8c8c', fontSize: '12px' }}>
                点击"上一步"返回相应步骤填写
              </div>
            </div>
          ),
          duration: 8
        });
        setCreateLoading(false);
        return;
      }
      
      const values = await createForm.validateFields();
      console.log('表单值:', values);
      
      // 解析output schema
      let outputSchema = {};
      if (values.content?.output?.schema) {
        try {
          outputSchema = typeof values.content.output.schema === 'string' 
            ? JSON.parse(values.content.output.schema) 
            : values.content.output.schema;
        } catch (e) {
          message.error('输出Schema JSON格式错误: ' + (e as Error).message);
          setCreateLoading(false);
          return;
        }
      }
      
      // 构建完整的SKILL数据
      const skillData = {
        name: values.name,
        code: values.code,
        skill_type: values.skill_type,
        description: values.description,
        tags: values.tags || [],
        is_global: values.is_global || false,
        is_default: values.is_default || false,
        content: {
          role: {
            name: values.content?.role?.name || '',
            description: values.content?.role?.description || '',
            expertise: values.content?.role?.expertise || [],
            behavior_rules: values.content?.role?.behavior_rules || []
          },
          input: {
            required_fields: values.content?.input?.required_fields || [],
            optional_fields: values.content?.input?.optional_fields || []
          },
          output: {
            format: values.content?.output?.format || 'json',
            schema: outputSchema
          },
          methods: values.content?.methods?.map((method: any) => ({
            name: method.name,
            description: method.description,
            applicable_scenarios: method.applicable_scenarios || []
          })) || [],
          domain_rules: values.content?.domain_rules || [],
          quality_checks: values.content?.quality_checks || [],
          prompt_template: values.content?.prompt_template || ''
        }
      };
      
      console.log('提交数据:', skillData);
      const response = await skillApi.create(skillData);
      console.log('创建成功:', response);
      message.success('创建成功');
      setCreateModalVisible(false);
      setCreateStep(0);
      createForm.resetFields();
      loadSkills();
    } catch (error: any) {
      console.error('创建失败:', error);
      console.error('错误详情:', error.response?.data);
      
      // 处理验证错误
      if (error.response?.status === 422) {
        const errorData = error.response?.data;
        if (errorData?.detail && Array.isArray(errorData.detail)) {
          // Pydantic验证错误格式
          const errorMessages = errorData.detail.map((err: any) => {
            const loc = err.loc?.join('.') || '';
            const fieldName = getFieldNameFromPath(loc);
            return `${fieldName}: ${err.msg}`;
          }).join('\n');
          message.error({
            content: (
              <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>数据验证失败，请检查以下字段：</div>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{errorMessages}</pre>
              </div>
            ),
            duration: 5
          });
        } else if (errorData?.detail) {
          message.error('创建失败: ' + errorData.detail);
        } else {
          message.error('创建失败: 数据格式不正确，请检查所有必填项');
        }
      } else if (error.errorFields) {
        // Ant Design 表单验证错误
        const errorMessages = error.errorFields.map((field: any) => {
          const fieldName = getFieldNameFromPath(field.name.join('.'));
          return `${fieldName}: ${field.errors.join(', ')}`;
        }).join('\n');
        message.error({
          content: (
            <div style={{ maxHeight: '200px', overflow: 'auto' }}>
              <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>请检查以下字段：</div>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{errorMessages}</pre>
            </div>
          ),
          duration: 5
        });
      } else {
        const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '创建失败';
        message.error('创建失败: ' + errorMsg);
      }
    } finally {
      setCreateLoading(false);
    }
  };

  // 辅助函数：将字段路径转换为中文名称
  const getFieldNameFromPath = (path: string): string => {
    const fieldMap: Record<string, string> = {
      'name': 'SKILL名称',
      'code': 'SKILL编码',
      'skill_type': 'SKILL类型',
      'description': '描述',
      'content': '内容',
      'content.role': '角色设定',
      'content.role.name': '角色名称',
      'content.role.description': '角色描述',
      'content.role.expertise': '专业知识',
      'content.role.behavior_rules': '行为准则',
      'content.input': '输入配置',
      'content.input.required_fields': '必填字段',
      'content.input.optional_fields': '可选字段',
      'content.output': '输出配置',
      'content.output.format': '输出格式',
      'content.output.schema': '输出Schema',
      'content.methods': '测试方法',
      'content.domain_rules': '领域规则',
      'content.quality_checks': '质量检查',
      'content.prompt_template': '提示词模板'
    };
    return fieldMap[path] || path;
  };

  // 编辑提交
  const handleEditSubmit = async () => {
    if (!currentSkill) return;
    try {
      const values = await editForm.validateFields();
      await skillApi.update(currentSkill.id, values);
      message.success('更新成功');
      setEditModalVisible(false);
      loadSkills();
    } catch (error: any) {
      console.error('更新失败:', error);
      const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message || '更新失败';
      message.error('更新失败: ' + errorMsg);
    }
  };

  // 导出多条SKILL
  const handleExportMultiple = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要导出的SKILL');
      return;
    }

    try {
      const selectedSkills = skills.filter(skill => selectedRowKeys.includes(skill.id));
      
      for (const skill of selectedSkills) {
        const response = await skillApi.export(skill.id);
        const dataStr = JSON.stringify(response, null, 2);
        const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
        const exportFileDefaultName = `${skill.code}_export.json`;
        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportFileDefaultName);
        linkElement.click();
        // 添加短暂延迟避免浏览器阻塞
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      message.success(`成功导出 ${selectedRowKeys.length} 个SKILL`);
      setSelectedRowKeys([]);
    } catch (error) {
      message.error('导出失败');
    }
  };

  // 行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
  };

  return (
    <div style={{ padding: 6 }}>
      <Card
        extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadSkills(1, 10)}>刷新</Button>
          <Button icon={<ImportOutlined />} onClick={() => setImportModalVisible(true)}>导入</Button>
            <Button 
              icon={<ExportOutlined />} 
              onClick={handleExportMultiple}
              disabled={selectedRowKeys.length === 0}
            >
              导出{selectedRowKeys.length > 0 ? `(${selectedRowKeys.length})` : ''}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
              创建SKILL
            </Button>
          </Space>
        }
      >
      {/* 筛选栏 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Search
          placeholder="搜索SKILL名称/编码"
          allowClear
          onSearch={setSearchText}
          style={{ width: 250 }}
        />
        <Select
          placeholder="类型筛选"
          allowClear
          style={{ width: 150 }}
          onChange={setFilterType}
        >
          {SKILL_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
        </Select>
        {selectedRowKeys.length > 0 && (
          <Text type="secondary">已选择 {selectedRowKeys.length} 项</Text>
        )}
      </Space>

      {/* 表格 */}
      <Table
        columns={columns}
        dataSource={skills}
        loading={loading}
        rowKey="id"
        rowSelection={rowSelection}
        pagination={{
          ...pagination,
          onChange: (page, pageSize) => loadSkills(page, pageSize),
        }}
      />

      {/* 创建弹窗 - 分步骤向导 */}
      <Modal
        title="创建SKILL"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          setCreateStep(0);
          createForm.resetFields();
        }}
        width={900}
        footer={null}
        destroyOnClose={false}
        forceRender
      >
        <Steps current={createStep} style={{ marginBottom: 24 }}>
          <Step title="基本信息" icon={<FileTextOutlined />} />
          <Step title="角色定义" icon={<UserOutlined />} />
          <Step title="测试方法" icon={<ToolOutlined />} />
          <Step title="提示词模板" icon={<CodeOutlined />} />
        </Steps>

        <Form form={createForm} layout="vertical" preserve>
          {/* 步骤1：基本信息 */}
          <div style={{ display: createStep === 0 ? 'block' : 'none' }}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="name"
                  label="SKILL名称"
                  rules={[{ required: true, message: '请输入SKILL名称' }]}
                >
                  <Input placeholder="如：功能测试用例生成专家" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="code"
                  label="SKILL编码"
                  rules={[{ required: true, message: '请输入SKILL编码' }]}
                >
                  <Input placeholder="如：functional_test_v1" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="skill_type"
              label="SKILL类型"
              rules={[{ required: true, message: '请选择SKILL类型' }]}
            >
              <Select placeholder="请选择SKILL类型">
                {SKILL_TYPE_OPTIONS.map(o => <Option key={o.value} value={o.value}>{o.label}</Option>)}
              </Select>
            </Form.Item>
            <Form.Item name="description" label="描述">
              <TextArea rows={3} placeholder="描述这个SKILL的用途和特点（可选）" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="tags" label="标签">
                  <Select mode="tags" placeholder="添加标签（可选）" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="is_global" label="全局SKILL" initialValue={false}>
                  <Select>
                    <Option value={true}>是（所有项目可用）</Option>
                    <Option value={false}>否（仅指定项目可用）</Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
          </div>

          {/* 步骤2：角色定义 */}
          <div style={{ display: createStep === 1 ? 'block' : 'none' }}>
            <Form.Item
              name={['content', 'role', 'name']}
              label="角色名称"
              rules={[{ required: true, message: '请输入角色名称' }]}
            >
              <Input placeholder="如：功能测试专家" />
            </Form.Item>
            <Form.Item
              name={['content', 'role', 'description']}
              label="角色描述"
              rules={[{ required: true, message: '请输入角色描述' }]}
            >
              <TextArea rows={3} placeholder="描述这个角色的定位和能力" />
            </Form.Item>
            <Form.Item name={['content', 'role', 'expertise']} label="专业知识">
              <Select mode="tags" placeholder="添加专业知识领域（可选，如：功能测试、边界值分析）" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name={['content', 'role', 'behavior_rules']} label="行为规则">
              <Select mode="tags" placeholder="添加行为规则（可选，如：生成用例必须包含前置条件）" style={{ width: '100%' }} />
            </Form.Item>
          </div>

          {/* 步骤3：测试方法 */}
          <div style={{ display: createStep === 2 ? 'block' : 'none' }}>
            <Form.List name={['content', 'methods']}>
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Card 
                      key={key} 
                      size="small" 
                      style={{ marginBottom: 16 }}
                      title={`测试方法 ${name + 1}`}
                      extra={
                        <Button 
                          type="link" 
                          danger 
                          icon={<MinusCircleOutlined />} 
                          onClick={() => remove(name)}
                        >
                          删除
                        </Button>
                      }
                    >
                      <Form.Item
                        {...restField}
                        name={[name, 'name']}
                        label="方法名称"
                        rules={[{ required: true, message: '请输入方法名称' }]}
                      >
                        <Input placeholder="如：等价类划分法" />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, 'description']}
                        label="方法描述"
                        rules={[{ required: true, message: '请输入方法描述' }]}
                      >
                        <TextArea rows={2} placeholder="描述这个方法的使用方式" />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, 'applicable_scenarios']}
                        label="适用场景"
                      >
                        <Select mode="tags" placeholder="添加适用场景（可选）" style={{ width: '100%' }} />
                      </Form.Item>
                    </Card>
                  ))}
                  <Button 
                    type="dashed" 
                    onClick={() => add()} 
                    block 
                    icon={<PlusCircleOutlined />}
                  >
                    添加测试方法
                  </Button>
                  {fields.length === 0 && (
                    <Text type="secondary" style={{ display: 'block', marginTop: 8, textAlign: 'center' }}>
                      测试方法可选，可以创建后再添加
                    </Text>
                  )}
                </>
              )}
            </Form.List>
          </div>

          {/* 步骤 4：提示词模板 */}
          <div style={{ display: createStep === 3 ? 'block' : 'none' }}>
            <Form.Item
              name={['content', 'prompt_template']}
              label="提示词模板"
              rules={[{ required: true, message: '请输入提示词模板' }]}
              tooltip="AI 生成测试用例的核心指令，支持 {{variable}} 变量语法"
            >
              <TextArea 
                rows={12} 
                placeholder="请输入提示词模板..."
              />
            </Form.Item>
            
            <Form.Item label="输出配置" tooltip="定义 AI 输出的格式规范">
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item 
                    name={['content', 'output', 'format']} 
                    label="输出格式" 
                    initialValue="json"
                    style={{ marginBottom: 0 }}
                  >
                    <Select>
                      <Option value="json">JSON</Option>
                      <Option value="markdown">Markdown</Option>
                      <Option value="xml">XML</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item 
                name={['content', 'output', 'schema']} 
                label="输出 Schema (可选)"
                tooltip="定义输出 JSON 的结构，不填写则使用默认格式"
              >
                <TextArea rows={6} placeholder="请输入 JSON Schema..." />
              </Form.Item>
            </Form.Item>
            
            <Form.Item label="高级配置（可选）" tooltip="可选配置，创建后可以继续编辑">
              <Collapse accordion>
                <Panel header="输入配置" key="input-config" forceRender>
                  <Form.Item 
                    name={['content', 'input', 'required_fields']} 
                    label="必填字段"
                  >
                    <Select mode="tags" placeholder="添加必填字段" style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item 
                    name={['content', 'input', 'optional_fields']} 
                    label="可选字段"
                  >
                    <Select mode="tags" placeholder="添加可选字段" style={{ width: '100%' }} />
                  </Form.Item>
                </Panel>
                
                <Panel header="领域规则" key="domain-rules" forceRender>
                  <Form.List name={['content', 'domain_rules']}>
                    {(fields, { add }) => (
                      <>
                        {fields.map(({ key, name, ...restField }) => (
                          <Card key={key} size="small" style={{ marginBottom: 12 }}>
                            <Form.Item {...restField} name={[name, 'domain']} label="领域名称">
                              <Input placeholder="如：输入验证" />
                            </Form.Item>
                            <Form.Item {...restField} name={[name, 'must_test']} label="必须测试">
                              <Select mode="tags" placeholder="添加必测项" />
                            </Form.Item>
                          </Card>
                        ))}
                        <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                          添加领域规则
                        </Button>
                      </>
                    )}
                  </Form.List>
                </Panel>
                
                <Panel header="质量检查" key="quality-checks" forceRender>
                  <Form.Item 
                    name={['content', 'quality_checks']} 
                    label="质量检查规则"
                  >
                    <Select mode="tags" placeholder="添加质量检查规则" style={{ width: '100%' }} />
                  </Form.Item>
                </Panel>
              </Collapse>
            </Form.Item>
          </div>

        </Form>

        {/* 步骤导航按钮 */}
        <div style={{ marginTop: 24, textAlign: 'right' }}>
          {createStep > 0 && (
            <Button style={{ marginRight: 8 }} onClick={() => setCreateStep(createStep - 1)}>
              上一步
            </Button>
          )}
          {createStep < 3 && (
            <Button 
              type="primary" 
              onClick={async () => {
                try {
                  // 只验证当前步骤的字段
                  let fieldNamesToValidate: string[][] = [];
                  
                  if (createStep === 0) {
                    // 第1步：基本信息
                    fieldNamesToValidate = [['name'], ['code'], ['skill_type']];
                  } else if (createStep === 1) {
                    // 第2步：角色定义
                    fieldNamesToValidate = [['content', 'role', 'name'], ['content', 'role', 'description']];
                  } else if (createStep === 2) {
                    // 第3步：测试方法（可选，不验证）
                    fieldNamesToValidate = [];
                  }
                  
                  if (fieldNamesToValidate.length > 0) {
                    await createForm.validateFields(fieldNamesToValidate);
                  }
                  console.log(`步骤${createStep + 1}验证通过`);
                  setCreateStep(createStep + 1);
                } catch (error: any) {
                  console.error('验证失败:', error);
                  if (error.errorFields) {
                    const errorMsg = error.errorFields.map((f: any) => f.errors.join(', ')).join('; ');
                    message.error('请填写必填项: ' + errorMsg);
                  } else {
                    message.error('请填写必填项');
                  }
                }
              }}
            >
              下一步
            </Button>
          )}
          {createStep === 3 && (
            <Button 
              type="primary" 
              loading={createLoading}
              onClick={handleCreateSubmit}
            >
              完成创建
            </Button>
          )}
        </div>
      </Modal>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑SKILL"
        open={editModalVisible}
        onOk={handleEditSubmit}
        onCancel={() => setEditModalVisible(false)}
        width={600}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="SKILL名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认" valuePropName="checked">
            <Select>
              <Option value={true}>是</Option>
              <Option value={false}>否</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 导入弹窗 */}
      <Modal
        title="导入SKILL"
        open={importModalVisible}
        onOk={async () => {
          if (!importFile) {
            message.error('请选择要导入的文件');
            return;
          }
          
          const values = await importForm.validateFields().catch(() => null);
          if (!values) return;
          
          setImportLoading(true);
          try {
            const fileContent = await importFile.text();
            console.log('>>> 导入文件内容:', fileContent.substring(0, 500));
            
            let skillData;
            try {
              skillData = JSON.parse(fileContent);
            } catch (parseError) {
              message.error('文件格式错误：不是有效的JSON文件');
              console.error('>>> JSON解析错误:', parseError);
              return;
            }
            
            console.log('>>> 解析后的数据:', skillData);
            
            // 验证必需字段
            if (!skillData.name) {
              message.error('导入失败：JSON文件缺少name字段');
              return;
            }
            if (!skillData.code) {
              message.error('导入失败：JSON文件缺少code字段');
              return;
            }
            if (!skillData.skill_type) {
              message.error('导入失败：JSON文件缺少skill_type字段');
              return;
            }
            
            const response = await skillApi.import({ 
              skill_data: skillData,
              project_id: values.project_id 
            });
            console.log('>>> 导入API响应:', response);
            console.log('>>> 导入成功，准备刷新列表...');
            message.success('导入成功');
            setImportModalVisible(false);
            importForm.resetFields();
            
            // 立即刷新列表 - 强制重新加载
            console.log('>>> 开始强制刷新列表');
            // 清除可能的缓存
            setSkills([]);
            setPagination({ current: 1, pageSize: 10, total: 0 });
            // 延迟一下确保状态更新
            await new Promise(resolve => setTimeout(resolve, 100));
            await loadSkills(1, 10);
            console.log('>>> 列表刷新完成');
          } catch (error: any) {
            console.error('>>> 导入失败:', error);
            const errorMsg = error.response?.data?.detail || error.message || '未知错误';
            message.error('导入失败：' + errorMsg);
          } finally {
            setImportLoading(false);
            setImportFile(null);
          }
        }}
        onCancel={() => {
          setImportModalVisible(false);
          setImportFile(null);
          importForm.resetFields();
        }}
        confirmLoading={importLoading}
        width={500}
        okText="导入"
        cancelText="取消"
      >
        <Form 
          form={importForm}
          layout="vertical"
        >
          <Form.Item
            label="选择SKILL文件"
            required
          >
            <Upload
              accept=".json"
              beforeUpload={(file) => {
                console.log('>>> 选择文件:', file.name);
                setImportFile(file);
                return false;
              }}
              maxCount={1}
              onRemove={() => {
                console.log('>>> 移除文件');
                setImportFile(null);
              }}
              fileList={importFile ? [{ uid: '-1', name: importFile.name, status: 'done' }] : []}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
            {!importFile && (
              <div style={{ color: '#ff4d4f', fontSize: '14px', marginTop: '8px' }}>
                请选择要导入的JSON文件
              </div>
            )}
          </Form.Item>
          <Form.Item
            name="project_id"
            label="所属项目"
          >
            <Select 
              placeholder="选择项目（可选，不选则创建为全局SKILL）" 
              allowClear
              loading={projectsLoading}
              notFoundContent={projectsLoading ? '加载中...' : '暂无项目'}
            >
              {projects.map(project => (
                <Option key={project.id} value={project.id}>
                  {project.name} ({project.code})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item>
            <Text type="secondary">
              支持导入之前导出的SKILL JSON文件
            </Text>
          </Form.Item>
        </Form>
      </Modal>

      {/* 快速复制弹窗 */}
      <Modal
        title="快速复制SKILL"
        open={quickCopyModalVisible}
        onOk={handleQuickCopySubmit}
        onCancel={() => {
          setQuickCopyModalVisible(false);
          quickCopyForm.resetFields();
        }}
        confirmLoading={quickCopyLoading}
        width={500}
      >
        <Form form={quickCopyForm} layout="vertical">
          <Form.Item
            name="name"
            label="SKILL名称"
            rules={[{ required: true, message: '请输入新的SKILL名称' }]}
          >
            <Input placeholder="如：用户管理功能测试专家" />
          </Form.Item>
          <Form.Item
            name="code"
            label="SKILL编码"
            rules={[{ required: true, message: '请输入新的SKILL编码' }]}
          >
            <Input placeholder="如：user_management_test_v1" />
          </Form.Item>
          <Form.Item>
            <Text type="secondary">
              快速复制将保留原SKILL的所有内容（角色定义、测试方法、提示词模板等），
              只需修改名称和编码即可使用。
            </Text>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
    </div>
  );
};

export default SkillsPage;
