/**
 * 生成知识图谱配置弹窗
 * 默认模式：基于已有探索结果合成（零爬取）
 *   探索结果来自：登录模块导入 / 功能用例转 UI 用例 / 审批增量探索，
 *   已由探索链路自动累积进项目知识图谱（KGPopulator.populate）。
 * 高级模式：无探索结果时可选择全站深度爬取（登录 + BFS 探索，较慢）
 */

import React, { useState, useEffect } from 'react';
import {
  Modal, Form, Input, Select, Switch, message, Space, Alert, Collapse, Divider,
} from 'antd';
import {
  ApiOutlined, UserOutlined, LockOutlined, SafetyCertificateOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { KnowledgeGraphGenerateRequest } from '../../api/knowledgeGraphApi';
import { projectSettingApi } from '../../api/projectExtApi';

interface GenerateKnowledgeGraphModalProps {
  visible: boolean;
  projectId: number;
  versionId?: number | null; // 项目级图谱：版本可空（不传则只生成项目级图谱）
  onCancel: () => void;
  /** 返回 Promise：resolve=成功，reject=失败（失败不弹成功提示、不清空表单） */
  onGenerate: (request: KnowledgeGraphGenerateRequest) => Promise<void>;
}

const GenerateKnowledgeGraphModal: React.FC<GenerateKnowledgeGraphModalProps> = ({
  visible,
  projectId,
  versionId,
  onCancel,
  onGenerate,
}) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  // 是否使用全站深度爬取（高级模式）：默认基于已有探索结果合成，零爬取
  const [useCrawl, setUseCrawl] = useState(false);

  // 打开弹窗时从项目配置预填 URL 和账号密码（crawl 模式备用）
  useEffect(() => {
    if (visible) {
      (async () => {
        try {
          const settings = await projectSettingApi.get(projectId);
          const web = settings.exploration_config?.web || {};
          form.setFieldsValue({
            base_url: web.base_url || '',
            login_username: web.username || '',
            login_password: web.password || '',
          });
        } catch {
          // 获取失败则使用默认值
        }
      })();
    }
  }, [visible, projectId, form]);

  const handleOk = async () => {
    try {
      // 仅 crawl 模式校验 URL/账号/密码（existing 模式由后端从已有数据合成）
      const values = await form.validateFields(
        useCrawl ? undefined : (['base_url', 'login_username', 'login_password'] as any),
      );

      setLoading(true);

      const request: KnowledgeGraphGenerateRequest = {
        // versionId 为 0/null/undefined 时统一转 undefined：
        // 后端 Optional 语义，传 0 会触发 MySQL FK IntegrityError（无 id=0 的版本行）
        version_id: versionId || undefined,
        project_id: projectId,
        mode: useCrawl ? 'crawl' : 'existing',
        base_url: values.base_url || '',
        login_username: values.login_username || '',
        login_password: values.login_password || '',
        exploration_strategy: values.exploration_strategy || 'normal',
        skip_tenant: values.skip_tenant !== false, // 默认跳过租户
      };

      await onGenerate(request); // 失败会 reject（父组件已提示），不弹成功、不清表单
      if (!useCrawl) {
        message.success('知识图谱已基于已有探索结果生成');
      } else {
        message.success('全站爬取任务已启动');
      }
      form.resetFields();
      setUseCrawl(false);
    } catch (error) {
      // 配置校验失败 or 生成触发失败（提示已由对应方处理）
      if (error && (error as any)?.errorFields) {
        message.error('配置验证失败，请检查输入');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setUseCrawl(false);
    onCancel();
  };

  return (
    <Modal
      title={
        <Space>
          <ApiOutlined />
          <span>生成知识图谱</span>
        </Space>
      }
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      width={600}
      confirmLoading={loading}
      okText={useCrawl ? '开始全站爬取' : '基于探索结果生成'}
      cancelText="取消"
    >
      <Alert
        message="基于已有探索结果生成（推荐）"
        description="不重复登录、不重复爬取网页。系统将直接使用项目中已累积的探索结果合成知识图谱，并整理各模块/功能之间的内在联系与跳转关系。"
        type="success"
        showIcon
        icon={<SafetyCertificateOutlined />}
        style={{ marginBottom: 12 }}
      />

      <Alert
        message="探索结果从哪来？"
        description="登录模块导入、功能用例转 UI 用例、需求审批增量探索——这些流程对页面的探索结果会自动累积到项目知识图谱中。只要做过其中任一步，即可直接生成图谱。"
        type="info"
        showIcon
        style={{ marginBottom: 8 }}
      />

      <Divider plain style={{ margin: '12px 0' }}>
        <Space size={4}>
          <GlobalOutlined />
          <span style={{ fontSize: 12, color: '#999' }}>高级：全站深度爬取</span>
        </Space>
      </Divider>

      <Collapse
        ghost
        style={{ marginBottom: 4 }}
        activeKey={useCrawl ? ['crawl'] : []}
        onChange={(keys) => setUseCrawl(keys.includes('crawl'))}
        items={[
          {
            key: 'crawl',
            label: '项目完全没有探索结果时，可展开此选项，由系统登录并爬取所有页面、元素、API调用等，构建完整知识图谱',
            children: (
              <>
                <Alert
                  message="仅当项目尚无任何探索结果时才需要爬取"
                  description="登录后如果出现机构选择页面，会自动选择非租户机构。爬取耗时较长（5-30分钟），通常不需要使用。"
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                />
                <Form
                  form={form}
                  layout="vertical"
                  initialValues={{
                    exploration_strategy: 'normal',
                    skip_tenant: true,
                  }}
                >
                  {/* 项目URL */}
                  <Form.Item
                    label="项目基础URL"
                    name="base_url"
                    rules={
                      useCrawl
                        ? [
                            { required: true, message: '请输入项目URL' },
                            { type: 'url', message: '请输入有效的URL' },
                          ]
                        : []
                    }
                    extra="例如：http://localhost:3000 或 https://example.com"
                  >
                    <Input
                      prefix={<ApiOutlined />}
                      placeholder="http://localhost:3000"
                      autoComplete="off"
                    />
                  </Form.Item>

                  {/* 登录用户名 */}
                  <Form.Item
                    label="登录用户名"
                    name="login_username"
                    rules={useCrawl ? [{ required: true, message: '请输入登录用户名' }] : []}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder="输入登录用户名"
                      autoComplete="new-password"
                    />
                  </Form.Item>

                  {/* 登录密码 */}
                  <Form.Item
                    label="登录密码"
                    name="login_password"
                    rules={useCrawl ? [{ required: true, message: '请输入登录密码' }] : []}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder="输入登录密码"
                      autoComplete="new-password"
                    />
                  </Form.Item>

                  {/* 爬取策略 */}
                  <Form.Item
                    label="爬取策略"
                    name="exploration_strategy"
                    extra="选择爬取深度：quick最快，deep最完整"
                  >
                    <Select>
                      <Select.Option value="quick">
                        <Space>
                          <span style={{ fontWeight: 'bold', color: '#52c41a' }}>Quick</span>
                          <span style={{ color: '#999' }}>（2分钟，主页+登录）</span>
                        </Space>
                      </Select.Option>
                      <Select.Option value="normal">
                        <Space>
                          <span style={{ fontWeight: 'bold', color: '#1890ff' }}>Normal</span>
                          <span style={{ color: '#999' }}>（5-10分钟，主页+二级菜单）</span>
                        </Space>
                      </Select.Option>
                      <Select.Option value="deep">
                        <Space>
                          <span style={{ fontWeight: 'bold', color: '#ff4d4f' }}>Deep</span>
                          <span style={{ color: '#999' }}>（10-30分钟，所有可达页面）</span>
                        </Space>
                      </Select.Option>
                    </Select>
                  </Form.Item>

                  {/* 是否跳过租户机构 */}
                  <Form.Item
                    label="跳过租户机构"
                    name="skip_tenant"
                    valuePropName="checked"
                    extra="如果登录后出现机构选择页面，自动跳过包含'租户'标签的机构"
                  >
                    <Switch checkedChildren="是" unCheckedChildren="否" />
                  </Form.Item>
                </Form>
              </>
            ),
          },
        ]}
      />
    </Modal>
  );
};

export default GenerateKnowledgeGraphModal;
