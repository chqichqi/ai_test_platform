import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Card, Typography, Button, Space, Tag, Descriptions, Tabs, List, message, 
  Divider, Form, Input, Select, Alert
} from 'antd';
import { 
  ArrowLeftOutlined, CopyOutlined, EditOutlined, PlusOutlined, 
  DeleteOutlined, SaveOutlined, CloseOutlined 
} from '@ant-design/icons';
import { skillApi } from '../../api/skillApi';
import { SkillDetailResponse } from '../../types/skill';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
const { Option } = Select;
const { TextArea } = Input;

// 将转义的换行符转换回真正的换行符
const unescapeNewlines = (text: string | undefined): string => {
  if (!text) return '';
  return text.replace(/\\n/g, '\n').replace(/\\t/g, '\t');
};

const SkillDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [skill, setSkill] = useState<SkillDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingTab, setEditingTab] = useState<string | null>(null);
  const [editForm] = Form.useForm();

  useEffect(() => {
    fetchSkillDetail();
  }, [id]);

  const fetchSkillDetail = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const response = await skillApi.get(Number(id));
      setSkill(response);
    } catch (error) {
      console.error('获取SKILL详情失败:', error);
      message.error('获取SKILL详情失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!skill) return;
    try {
      await skillApi.copy(skill.id);
      message.success('复制成功');
      navigate('/skills');
    } catch (error) {
      console.error('复制失败:', error);
      message.error('复制失败');
    }
  };

  const handleSaveContent = async (tabKey: string, values: any) => {
    if (!skill) return;
    try {
      const updatedContent = { ...skill.content };
      
      switch (tabKey) {
        case 'role':
          updatedContent.role = values;
          break;
        case 'io':
          // 验证JSON格式
          let parsedSchema;
          try {
            parsedSchema = JSON.parse(values.output.schema);
          } catch (e: any) {
            // 尝试定位错误位置
            const errorMsg = e.message;
            const positionMatch = errorMsg.match(/position (\d+)/);
            const lineMatch = errorMsg.match(/line (\d+)/);
            
            let detailedError = 'JSON格式错误';
            if (lineMatch) {
              detailedError += `，第${lineMatch[1]}行`;
            }
            if (positionMatch) {
              const position = parseInt(positionMatch[1]);
              const lines = values.output.schema.substring(0, position).split('\n');
              const lineNumber = lines.length;
              const columnNumber = lines[lines.length - 1].length + 1;
              detailedError += `，第${lineNumber}行第${columnNumber}列`;
            }
            detailedError += `：${errorMsg}`;
            
            message.error(detailedError);
            return;
          }
          
          updatedContent.input = values.input;
          updatedContent.output = {
            format: values.output.format,
            schema: parsedSchema
          };
          break;
        case 'methods':
          updatedContent.methods = values.methods;
          break;
        case 'domain_rules':
          updatedContent.domain_rules = values.domain_rules;
          break;
        case 'quality_checks':
          updatedContent.quality_checks = values.quality_checks;
          break;
        case 'prompt':
          // 对于预设SKILL，只更新用户提示词，保留系统提示词
          if (skill.is_default && typeof skill.content.prompt_template === 'object') {
            updatedContent.prompt_template = {
              ...skill.content.prompt_template,  // 保留原有的system_prompt和variables
              user_prompt: values.prompt_template?.user_prompt || values.prompt_template
            };
          } else {
            updatedContent.prompt_template = values.prompt_template;
          }
          break;
      }

      console.log('发送更新的content:', JSON.stringify(updatedContent, null, 2));
      
      await skillApi.update(skill.id, { content: updatedContent });
      message.success('保存成功');
      setEditingTab(null);
      fetchSkillDetail();
    } catch (error: any) {
      console.error('保存失败:', error);
      console.error('错误详情:', error.response?.data);
      message.error('保存失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const startEditing = (tabKey: string) => {
    if (!skill) return;
    
    // 权限检查：
    // - 非预设SKILL：可编辑所有Tab
    // - 预设SKILL：只能编辑prompt tab（用户提示词部分）
    const isPreset = skill.is_default;
    const isObjTemplate = typeof skill.content?.prompt_template === 'object';
    
    if (isPreset) {
      if (tabKey !== 'prompt') {
        message.warning('预设SKILL的其他内容不可编辑，只能编辑用户提示词模板');
        return;
      }
      if (!isObjTemplate) {
        message.warning('旧格式预设SKILL不可编辑，请复制后修改');
        return;
      }
    }
    
    setEditingTab(tabKey);
    
    // 初始化表单值
    const content = skill.content;
    switch (tabKey) {
      case 'role':
        editForm.setFieldsValue({ ...content.role });
        break;
      case 'io':
        editForm.setFieldsValue({ 
          input: content.input,
          output: {
            format: content.output.format,
            schema: JSON.stringify(content.output.schema, null, 2)
          }
        });
        break;
      case 'methods':
        editForm.setFieldsValue({ methods: content.methods });
        break;
      case 'domain_rules':
        editForm.setFieldsValue({ domain_rules: content.domain_rules });
        break;
      case 'quality_checks':
        editForm.setFieldsValue({ quality_checks: content.quality_checks });
        break;
      case 'prompt':
        if (typeof content.prompt_template === 'object') {
          editForm.setFieldsValue({ 
            prompt_template: {
              system_prompt: unescapeNewlines(content.prompt_template.system_prompt),
              user_prompt: unescapeNewlines(content.prompt_template.user_prompt)
            }
          });
        } else {
          editForm.setFieldsValue({ prompt_template: unescapeNewlines(content.prompt_template) });
        }
        break;
    }
  };

  const cancelEditing = () => {
    setEditingTab(null);
    editForm.resetFields();
  };

  if (!skill && !loading) {
    return (
      <Card>
        <Title level={4}>SKILL不存在</Title>
        <Button onClick={() => navigate('/skills')}>返回SKILL列表</Button>
      </Card>
    );
  }

  const content = skill?.content;
  const isPreset = skill?.is_default;  // 是否为预设SKILL
  const isObjTemplate = typeof content?.prompt_template === 'object' && content?.prompt_template !== null;
  
  // 编辑权限：
  // - 非预设SKILL：可编辑所有内容
  // - 预设SKILL + 新格式prompt_template：只能编辑user_prompt
  // - 预设SKILL + 旧格式：不可编辑
  const canEditAll = !isPreset;
  const canEditUserPrompt = isPreset && isObjTemplate;
  const canEditPrompt = canEditAll || canEditUserPrompt;
  // 渲染角色设定Tab
  const renderRoleTab = () => {
    if (!content) return null;
    
    if (editingTab === 'role') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('role', values)}>
          <Form.Item name="name" label="角色名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="角色描述">
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="expertise" label="专业知识领域">
            <Select mode="tags" placeholder="输入专业知识领域后按回车" />
          </Form.Item>
          <Form.Item name="behavior_rules" label="行为准则">
            <Select mode="tags" placeholder="输入行为准则后按回车" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4}>{content.role.name}</Title>
          {canEditAll && (
            <Button icon={<EditOutlined />} onClick={() => startEditing('role')}>编辑</Button>
          )}
        </div>
        <Paragraph>{content.role.description}</Paragraph>
        
        <Divider orientation="left">专业知识领域</Divider>
        <List
          dataSource={content.role.expertise}
          renderItem={(item) => (
            <List.Item>
              <Text>• {item}</Text>
            </List.Item>
          )}
        />
        
        <Divider orientation="left">行为准则</Divider>
        <List
          dataSource={content.role.behavior_rules}
          renderItem={(item) => (
            <List.Item>
              <Text>• {item}</Text>
            </List.Item>
          )}
        />
      </Space>
    );
  };

  // 渲染输入/输出Tab
  const renderIOTab = () => {
    if (!content) return null;

    if (editingTab === 'io') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('io', values)}>
          <Title level={5}>输入字段</Title>
          <Form.Item name={['input', 'required_fields']} label="必填字段">
            <Select mode="tags" placeholder="输入必填字段后按回车" />
          </Form.Item>
          <Form.Item name={['input', 'optional_fields']} label="可选字段">
            <Select mode="tags" placeholder="输入可选字段后按回车" />
          </Form.Item>
          
          <Divider />
          
          <Title level={5}>输出格式</Title>
          <Form.Item name={['output', 'format']} label="格式">
            <Select>
              <Option value="json">JSON</Option>
              <Option value="xml">XML</Option>
              <Option value="yaml">YAML</Option>
              <Option value="text">纯文本</Option>
            </Select>
          </Form.Item>
          <Form.Item name={['output', 'schema']} label="Schema (JSON)">
            <TextArea rows={6} placeholder='{"type": "object", "properties": {...}}' />
          </Form.Item>
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4}>输入/输出配置</Title>
          {canEditAll && (
            <Button icon={<EditOutlined />} onClick={() => startEditing('io')}>编辑</Button>
          )}
        </div>
        
        <Title level={5}>输入字段</Title>
        <Descriptions bordered column={1}>
          <Descriptions.Item label="必填字段">
            {content.input.required_fields.map(f => <Tag key={f}>{f}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="可选字段">
            {content.input.optional_fields.map(f => <Tag key={f}>{f}</Tag>)}
          </Descriptions.Item>
        </Descriptions>
        
        <Divider />
        
        <Title level={5}>输出格式</Title>
        <Descriptions bordered column={1}>
          <Descriptions.Item label="格式">{content.output.format}</Descriptions.Item>
          <Descriptions.Item label="Schema">
            <pre style={{ backgroundColor: '#f6f8fa', padding: 16, borderRadius: 4, overflow: 'auto' }}>
              {JSON.stringify(content.output.schema, null, 2)}
            </pre>
          </Descriptions.Item>
        </Descriptions>
      </Space>
    );
  };

  // 渲染测试方法Tab
  const renderMethodsTab = () => {
    if (!content) return null;

    if (editingTab === 'methods') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('methods', values)}>
          <Form.List name="methods">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Card 
                    key={key} 
                    size="small" 
                    style={{ marginBottom: 16 }}
                    extra={
                      <Button 
                        type="text" 
                        danger 
                        icon={<DeleteOutlined />} 
                        onClick={() => remove(name)}
                      >
                        删除
                      </Button>
                    }
                  >
                    <Form.Item {...restField} name={[name, 'name']} label="方法名称" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'description']} label="方法描述">
                      <TextArea rows={2} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'applicable_scenarios']} label="适用场景">
                      <Select mode="tags" placeholder="输入适用场景后按回车" />
                    </Form.Item>
                  </Card>
                ))}
                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                  添加测试方法
                </Button>
              </>
            )}
          </Form.List>
          
          <Form.Item style={{ marginTop: 16 }}>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>测试方法列表</Title>
          {canEditAll && (
            <Button icon={<EditOutlined />} onClick={() => startEditing('methods')}>编辑</Button>
          )}
        </div>
        <List
          dataSource={content.methods}
          renderItem={(method) => (
            <List.Item>
              <List.Item.Meta
                title={<Text strong>{method.name}</Text>}
                description={
                  <Space direction="vertical" size={2}>
                    <Text>{method.description}</Text>
                    <Text type="secondary">
                      适用场景: {method.applicable_scenarios.join('、')}
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Space>
    );
  };

  // 渲染领域规则Tab
  const renderDomainRulesTab = () => {
    if (!content) return null;

    if (editingTab === 'domain_rules') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('domain_rules', values)}>
          <Form.List name="domain_rules">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Card 
                    key={key} 
                    size="small" 
                    style={{ marginBottom: 16 }}
                    extra={
                      <Button 
                        type="text" 
                        danger 
                        icon={<DeleteOutlined />} 
                        onClick={() => remove(name)}
                      >
                        删除
                      </Button>
                    }
                  >
                    <Form.Item {...restField} name={[name, 'domain']} label="领域名称" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'must_test']} label="必须测试">
                      <Select mode="tags" placeholder="输入必须测试项后按回车" />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, 'security_focus']} label="安全关注点">
                      <Select mode="tags" placeholder="输入安全关注点后按回车" />
                    </Form.Item>
                  </Card>
                ))}
                <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                  添加领域规则
                </Button>
              </>
            )}
          </Form.List>
          
          <Form.Item style={{ marginTop: 16 }}>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>领域规则列表</Title>
          {canEditAll && (
            <Button icon={<EditOutlined />} onClick={() => startEditing('domain_rules')}>编辑</Button>
          )}
        </div>
        <List
          dataSource={content.domain_rules}
          renderItem={(rule) => (
            <List.Item>
              <List.Item.Meta
                title={<Tag color="blue">{rule.domain}</Tag>}
                description={
                  <Space direction="vertical" size={4}>
                    <div>
                      <Text strong>必须测试: </Text>
                      {rule.must_test.map((item, idx) => (
                        <span key={idx}>• {item} </span>
                      ))}
                    </div>
                    <div>
                      <Text strong type="danger">安全关注点: </Text>
                      {rule.security_focus.map((item, idx) => (
                        <span key={idx}>• {item} </span>
                      ))}
                    </div>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Space>
    );
  };

  // 渲染质量检查Tab
  const renderQualityChecksTab = () => {
    if (!content) return null;

    if (editingTab === 'quality_checks') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('quality_checks', values)}>
          <Form.Item name="quality_checks" label="质量检查项">
            <Select mode="tags" placeholder="输入质量检查项后按回车" style={{ width: '100%' }} />
          </Form.Item>
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>质量检查清单</Title>
          {canEditAll && (
            <Button icon={<EditOutlined />} onClick={() => startEditing('quality_checks')}>编辑</Button>
          )}
        </div>
        <List
          dataSource={content.quality_checks}
          renderItem={(check, index) => (
            <List.Item>
              <Text>{index + 1}. {check}</Text>
            </List.Item>
          )}
        />
      </Space>
    );
  };

  // 渲染提示词模板Tab
  const renderPromptTab = () => {
    if (!content) return null;

    const promptTemplate = content.prompt_template;
    const isObjTemplate = typeof promptTemplate === 'object' && promptTemplate !== null;

    if (editingTab === 'prompt') {
      return (
        <Form form={editForm} layout="vertical" onFinish={(values) => handleSaveContent('prompt', values)}>
          {isObjTemplate ? (
            <>
              <Title level={5}>系统提示词 (System Prompt)</Title>
              {isPreset ? (
                <Alert type="warning" showIcon message="预设SKILL的系统提示词不可修改" style={{ marginBottom: 8 }} />
              ) : (
                <Paragraph type="secondary" style={{ fontSize: '12px' }}>
                  定义AI的角色、专业知识和行为准则，在所有生成请求中保持不变
                </Paragraph>
              )}
              <Form.Item name={['prompt_template', 'system_prompt']} label="系统提示词" rules={[{ required: true }]}>
                <TextArea 
                  rows={12} 
                  placeholder="定义AI角色和行为准则..." 
                  disabled={isPreset}
                  style={{ 
                    fontFamily: 'Consolas, "Courier New", monospace',
                    fontSize: '13px',
                    lineHeight: '1.6',
                    backgroundColor: isPreset ? '#f5f5f5' : undefined
                  }}
                />
              </Form.Item>
              
              <Divider />
              
              <Title level={5}>用户提示词模板 (User Prompt Template)</Title>
              <Paragraph type="secondary" style={{ fontSize: '12px' }}>
                定义具体的生成任务，包含可替换的变量占位符。可用变量：
              </Paragraph>
              <Space wrap style={{ marginBottom: 8 }}>
                <Tag color="blue">{'{{project_name}}'}</Tag>
                <Tag color="blue">{'{{version_number}}'}</Tag>
                <Tag color="blue">{'{{requirement_content}}'}</Tag>
                <Tag color="blue">{'{{modules_list}}'}</Tag>
                <Tag color="blue">{'{{estimated_cases}}'}</Tag>
              </Space>
              <Form.Item name={['prompt_template', 'user_prompt']} label="用户提示词模板" rules={[{ required: true }]}>
                <TextArea 
                  rows={20} 
                  placeholder="定义生成任务和变量占位符..." 
                  style={{ 
                    fontFamily: 'Consolas, "Courier New", monospace',
                    fontSize: '13px',
                    lineHeight: '1.6'
                  }}
                />
              </Form.Item>
            </>
          ) : (
            <>
              {isPreset && (
                <Alert type="info" showIcon message="旧格式预设SKILL不可编辑，请复制后修改" style={{ marginBottom: 16 }} />
              )}
              <Form.Item name="prompt_template" label="提示词模板" rules={[{ required: true }]}>
                <TextArea 
                  rows={25} 
                  placeholder="输入提示词模板..." 
                  disabled={isPreset}
                  style={{ 
                    fontFamily: 'Consolas, "Courier New", monospace',
                    fontSize: '13px',
                    lineHeight: '1.6',
                    backgroundColor: isPreset ? '#f5f5f5' : undefined
                  }}
                />
              </Form.Item>
            </>
          )}
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存</Button>
              <Button onClick={cancelEditing} icon={<CloseOutlined />}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      );
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>提示词模板</Title>
          {canEditPrompt ? (
            <Button icon={<EditOutlined />} onClick={() => startEditing('prompt')}>
              {isPreset ? '编辑用户提示词' : '编辑'}
            </Button>
          ) : (
            <Space>
              <Tag color="orange">预设模板不可编辑</Tag>
              <Button type="primary" icon={<CopyOutlined />} onClick={handleCopy}>
                复制后编辑
              </Button>
            </Space>
          )}
        </div>
        
        {isPreset && canEditUserPrompt && (
          <Alert 
            type="info" 
            showIcon 
            message="预设SKILL可编辑用户提示词模板"
            description="您可以修改用户提示词模板，调整任务描述格式以适应项目需求。系统提示词和其他内容保持不变。"
            style={{ marginBottom: 16 }}
          />
        )}
        
        {isObjTemplate ? (
          <>
            <Card 
              title={<Text strong>系统提示词 (System Prompt)</Text>}
              size="small" 
              style={{ marginBottom: 16 }}
              extra={isPreset ? <Tag color="purple">预设固定</Tag> : <Tag color="green">可编辑</Tag>}
            >
              <Paragraph type="secondary" style={{ fontSize: '12px', marginBottom: 8 }}>
                定义AI的角色和专业能力，在每次生成时都会使用
              </Paragraph>
              <pre style={{ 
                margin: 0, 
                padding: '12px',
                backgroundColor: '#f5f5f5',
                borderRadius: '4px',
                fontFamily: 'Consolas, "Courier New", monospace',
                fontSize: '13px',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                maxHeight: '400px',
                overflow: 'auto'
              }}>
                {unescapeNewlines(promptTemplate.system_prompt)}
              </pre>
            </Card>
            
            <Card 
              title={<Text strong>用户提示词模板 (User Prompt Template)</Text>}
              size="small"
              extra={canEditUserPrompt ? <Tag color="cyan">可编辑</Tag> : <Tag color="orange">需复制</Tag>}
            >
              <Paragraph type="secondary" style={{ fontSize: '12px', marginBottom: 8 }}>
                定义生成任务，以下变量会自动替换为实际值：
              </Paragraph>
              <Space wrap style={{ marginBottom: 12 }}>
                {promptTemplate.variables?.map((v: any) => (
                  <Tag key={v.name} color={v.required ? 'blue' : 'default'}>
                    {`{{${v.name}}}`} - {v.description}
                  </Tag>
                ))}
              </Space>
              <pre style={{ 
                margin: 0, 
                padding: '12px',
                backgroundColor: canEditUserPrompt ? '#e6f7ff' : '#f5f5f5',
                borderRadius: '4px',
                fontFamily: 'Consolas, "Courier New", monospace',
                fontSize: '13px',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                maxHeight: '500px',
                overflow: 'auto',
                border: canEditUserPrompt ? '1px solid #91d5ff' : '1px solid #d9d9d9'
              }}>
                {unescapeNewlines(promptTemplate.user_prompt)}
              </pre>
            </Card>
          </>
        ) : (
          <Card 
            size="small" 
            style={{
              backgroundColor: '#fafafa',
              border: '1px solid #e8e8e8'
            }}
          >
            <pre style={{ 
              margin: 0, 
              padding: '16px',
              backgroundColor: '#ffffff',
              borderRadius: '4px',
              fontFamily: 'Consolas, "Courier New", monospace',
              fontSize: '13px',
              lineHeight: '1.6',
              whiteSpace: 'pre-wrap',
              wordWrap: 'break-word',
              maxHeight: '600px',
              overflow: 'auto'
            }}>
              {unescapeNewlines(promptTemplate)}
            </pre>
          </Card>
        )}
      </Space>
    );
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/skills')}>
          返回
        </Button>
        <Title level={2} style={{ margin: 0 }}>{skill?.name}</Title>
        <Tag color={skill?.status === 'active' ? 'green' : skill?.status === 'draft' ? 'orange' : 'gray'}>
          {skill?.status === 'active' ? '已启用' : skill?.status === 'draft' ? '草稿' : '已弃用'}
        </Tag>
        {skill?.is_default && <Tag color="blue">默认</Tag>}
        <Tag color="cyan">v{skill?.version}</Tag>
      </Space>
      
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        {skill?.description}
      </Text>
      
      <Card loading={loading}>
        <Descriptions bordered column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="SKILL编码">{skill?.code}</Descriptions.Item>
          <Descriptions.Item label="类型">
            <Tag color="blue">{skill?.skill_type}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="标签">
            {skill?.tags?.map(tag => <Tag key={tag}>{tag}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="使用次数">{skill?.usage_count || 0}</Descriptions.Item>
          <Descriptions.Item label="生成次数">{skill?.generation_count || 0}</Descriptions.Item>
          <Descriptions.Item label="平均质量评分">
            {skill?.avg_quality_score ? skill.avg_quality_score.toFixed(1) : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{skill?.created_at ? new Date(skill.created_at).toLocaleString() : '-'}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{skill?.updated_at ? new Date(skill.updated_at).toLocaleString() : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>
      
      {content && (
        <Card style={{ marginTop: 16 }}>
          <Tabs defaultActiveKey="1" onChange={() => setEditingTab(null)}>
            <TabPane tab="角色设定" key="1">
              {renderRoleTab()}
            </TabPane>
            
            <TabPane tab="输入/输出" key="2">
              {renderIOTab()}
            </TabPane>
            
            <TabPane tab="测试方法" key="3">
              {renderMethodsTab()}
            </TabPane>
            
            <TabPane tab="领域规则" key="4">
              {renderDomainRulesTab()}
            </TabPane>
            
            <TabPane tab="质量检查" key="5">
              {renderQualityChecksTab()}
            </TabPane>
            
            <TabPane tab="提示词模板" key="6">
              {renderPromptTab()}
            </TabPane>
          </Tabs>
        </Card>
      )}
      
      <Card style={{ marginTop: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/skills')}>
            返回列表
          </Button>
          <Button type="primary" icon={<CopyOutlined />} onClick={handleCopy}>
            复制此SKILL
          </Button>
        </Space>
      </Card>
    </div>
  );
};

export default SkillDetailPage;
