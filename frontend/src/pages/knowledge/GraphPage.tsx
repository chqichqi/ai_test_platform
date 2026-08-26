import React, { useState, useEffect, useCallback } from 'react';
import { Table, Card, Typography, Button, Space, Input, Tag, Modal, Descriptions, Progress, Empty, Spin, message, Tooltip } from 'antd';
import { SearchOutlined, EyeOutlined, BranchesOutlined, NodeIndexOutlined, SyncOutlined, CheckCircleOutlined, ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  Handle,
} from 'reactflow';
import 'reactflow/dist/style.css';
import knowledgeApi, { KnowledgeGraph, GraphNode, GraphEdge } from '../../api/knowledgeApi';

const { Title, Text } = Typography;
const { Search } = Input;

const NODE_COLORS: Record<string, string> = {
  '模块': '#6366f1',
  '功能': '#10b981',
  '页面': '#0891b2',
};

const EDGE_COLORS: Record<string, string> = {
  '前置条件': '#ef4444',
  '包含': '#22c55e',
  '依赖': '#3b82f6',
  '顺序': '#f59e0b',
  '关联': '#64748b',
};

const CustomNode: React.FC<{ data: { label: string; type: string; requiresLogin?: boolean; color: string } }> = ({ data }) => {
  const isPublic = data.requiresLogin === false;
  
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ background: '#555', width: 8, height: 8 }} />
      <div
        style={{
          padding: '12px 20px',
          borderRadius: 8,
          background: data.color,
          color: '#fff',
          fontSize: 14,
          fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          border: isPublic 
            ? '3px dashed #fbbf24' 
            : '3px solid #1e293b',
          minWidth: 80,
          textAlign: 'center',
        }}
      >
        <div>{data.label}</div>
        <div style={{ fontSize: 10, opacity: 0.8, marginTop: 4 }}>{data.type}</div>
        {isPublic && (
          <div style={{ fontSize: 9, opacity: 0.7, marginTop: 2 }}>公开访问</div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ background: '#555', width: 8, height: 8 }} />
    </>
  );
};

const nodeTypes = { custom: CustomNode };

const GraphPage: React.FC = () => {
  const [graphs, setGraphs] = useState<KnowledgeGraph[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedGraph, setSelectedGraph] = useState<KnowledgeGraph | null>(null);
  const [visualVisible, setVisualVisible] = useState(false);
  const [visualGraph, setVisualGraph] = useState<KnowledgeGraphDetail | null>(null);
  const [visualLoading, setVisualLoading] = useState(false);
  
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  interface KnowledgeGraphDetail extends KnowledgeGraph {
    nodes: GraphNode[];
    edges: GraphEdge[];
  }

  const loadGraphs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await knowledgeApi.listGraphs();
      setGraphs(result.items);
    } catch (error) {
      message.error('加载图谱列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraphs();
  }, [loadGraphs]);

  const handleVisualize = async (record: KnowledgeGraph) => {
    setVisualLoading(true);
    setVisualVisible(true);
    
    try {
      const graphDetail = await knowledgeApi.getGraph(record.id);
      
      const graphWithNodes: KnowledgeGraphDetail = {
        ...record,
        nodes: graphDetail.nodes.map((n) => ({
          id: n.id,
          name: n.name,
          type: n.type,
          color: n.color,
          properties: n.properties || {},
        })),
        edges: graphDetail.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          relation: e.relation,
          sourceName: e.sourceName,
          targetName: e.targetName,
        })),
      };
      
      setVisualGraph(graphWithNodes);
    } catch (error) {
      console.error('获取图谱详情失败:', error);
      message.error('获取图谱详情失败');
      setVisualVisible(false);
    } finally {
      setVisualLoading(false);
    }
  };
  
  useEffect(() => {
    if (!visualGraph?.nodes || visualGraph.nodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }
    
    const centerX = 400;
    const centerY = 300;
    const radius = 250;
    const nodeCount = visualGraph.nodes.length;
    
    const nodeIdSet = new Set(visualGraph.nodes.map(n => String(n.id)));
    
    const flowNodes: Node[] = visualGraph.nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / nodeCount - Math.PI / 2;
      return {
        id: String(node.id),
        type: 'custom',
        position: {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        },
        data: {
          label: node.name,
          type: node.type,
          requiresLogin: (node as any).properties?.requires_login,
          color: node.color || NODE_COLORS[node.type] || '#6366f1',
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });
    
    const flowEdges: Edge[] = [];
    
    if (visualGraph.edges && visualGraph.edges.length > 0) {
      for (let i = 0; i < visualGraph.edges.length; i++) {
        const edge = visualGraph.edges[i];
        const sourceId = String(edge.source);
        const targetId = String(edge.target);
        
        if (edge.source === undefined || edge.target === undefined) {
          continue;
        }
        
        if (!nodeIdSet.has(sourceId) || !nodeIdSet.has(targetId)) {
          continue;
        }
        
        const isPrecondition = edge.relation === '前置条件';
        const edgeColor = EDGE_COLORS[edge.relation] || '#64748b';
        
        flowEdges.push({
          id: `e${i}`,
          source: sourceId,
          target: targetId,
          label: edge.relation,
          animated: isPrecondition,
          style: { stroke: edgeColor, strokeWidth: isPrecondition ? 3 : 2 },
          labelStyle: { fill: edgeColor, fontWeight: 600, fontSize: 12 },
          labelBgStyle: { fill: '#fff', fillOpacity: 0.9 },
          labelBgPadding: [8, 4] as [number, number],
          labelBgBorderRadius: 4,
          markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
        });
      }
    }
    
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [visualGraph]);

  const columns: ColumnsType<KnowledgeGraph> = [
    {
      title: '图谱名称',
      dataIndex: 'name',
      key: 'name',
      render: (text) => (
        <Space>
          <BranchesOutlined style={{ color: '#0891b2' }} />
          <Text strong>{text}</Text>
        </Space>
      ),
    },
    {
      title: '来源RAG库',
      dataIndex: 'sourceRag',
      key: 'sourceRag',
      render: (text) => <Tag color="purple">{text}</Tag>,
    },
    {
      title: '实体数量',
      dataIndex: 'entityCount',
      key: 'entityCount',
      render: (count) => <Tag color="cyan">{count} 个</Tag>,
    },
    {
      title: '关系数量',
      dataIndex: 'relationCount',
      key: 'relationCount',
      render: (count) => <Tag color="orange">{count} 个</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status, record) => {
        if (status === 'completed') {
          return <Tag color="green" icon={<CheckCircleOutlined />}>已完成</Tag>;
        } else if (status === 'processing') {
          return (
            <Space direction="vertical" size={0} style={{ width: 100 }}>
              <Tag color="processing" icon={<SyncOutlined spin />}>处理中</Tag>
              <Progress percent={record.progress} size="small" />
            </Space>
          );
        }
        return <Tag color="default">待处理</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      render: (text) => (
        <Space>
          <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
          <Text type="secondary">{text}</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Tooltip title="查看详情">
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => {
                setSelectedGraph(record);
                setDetailVisible(true);
              }}
            />
          </Tooltip>
          <Tooltip title="可视化查看">
            <Button
              type="text"
              icon={<NodeIndexOutlined />}
              onClick={() => handleVisualize(record)}
              disabled={record.status !== 'completed'}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const filteredData = graphs.filter(g =>
    g.name.toLowerCase().includes(searchText.toLowerCase()) ||
    g.sourceRag.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div>
      <Card style={{ marginTop: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Search
            placeholder="搜索图谱名称"
            allowClear
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <Button icon={<ReloadOutlined />} onClick={loadGraphs} loading={loading}>
            刷新
          </Button>
        </div>
        
        <Spin spinning={loading}>
          {filteredData.length > 0 ? (
            <Table
              columns={columns}
              dataSource={filteredData}
              rowKey="id"
              pagination={{ pageSize: 10 }}
            />
          ) : (
            <Empty
              description="暂无知识图谱"
              style={{ padding: '40px 0' }}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Text type="secondary">
                请先在 RAG库 中创建知识库并生成图谱
              </Text>
            </Empty>
          )}
        </Spin>
      </Card>
      
      <Card style={{ marginTop: 16 }}>
        <Title level={4}>图谱统计</Title>
        <Space size="large">
          <div>
            <Text type="secondary">图谱总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{graphs.length}</Title>
          </div>
          <div>
            <Text type="secondary">实体总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{graphs.reduce((sum, g) => sum + g.entityCount, 0)}</Title>
          </div>
          <div>
            <Text type="secondary">关系总数</Text>
            <Title level={3} style={{ margin: '8px 0' }}>{graphs.reduce((sum, g) => sum + g.relationCount, 0)}</Title>
          </div>
        </Space>
      </Card>

      <Modal
        maskClosable={false}
        title="图谱详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
          <Button 
            key="visualize" 
            type="primary" 
            icon={<NodeIndexOutlined />}
            disabled={selectedGraph?.status !== 'completed'}
            onClick={() => {
              if (selectedGraph) {
                handleVisualize(selectedGraph);
                setDetailVisible(false);
              }
            }}
          >
            可视化查看
          </Button>,
        ]}
        width={600}
      >
        {selectedGraph && (
          <Descriptions column={2} bordered>
            <Descriptions.Item label="图谱名称">{selectedGraph.name}</Descriptions.Item>
            <Descriptions.Item label="来源RAG">{selectedGraph.sourceRag}</Descriptions.Item>
            <Descriptions.Item label="实体数量">{selectedGraph.entityCount} 个</Descriptions.Item>
            <Descriptions.Item label="关系数量">{selectedGraph.relationCount} 个</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color="green">已完成</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{selectedGraph.createdAt}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      <Modal
        maskClosable={false}
        title={
          <Space>
            <BranchesOutlined style={{ color: '#0891b2' }} />
            <span>知识图谱可视化</span>
            {visualGraph && <Tag color="purple">{visualGraph.name}</Tag>}
          </Space>
        }
        open={visualVisible}
        onCancel={() => setVisualVisible(false)}
        footer={[
          <Button key="close" onClick={() => setVisualVisible(false)}>
            关闭
          </Button>,
        ]}
        width={1000}
        centered
      >
        {visualLoading ? (
          <div style={{ textAlign: 'center', padding: '80px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>
              <Text type="secondary">正在加载图谱数据...</Text>
            </div>
          </div>
        ) : visualGraph && nodes.length > 0 ? (
          <>
            <div style={{ marginBottom: 12 }}>
              <Title level={5}>图例说明</Title>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 8 }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>实体类型：</Text>
                  <Space size={4} style={{ marginLeft: 8 }}>
                    <Tag color="#6366f1">模块</Tag>
                    <Tag color="#10b981">功能</Tag>
                    <Tag color="#0891b2">页面</Tag>
                  </Space>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>关系类型：</Text>
                  <Space size={4} style={{ marginLeft: 8 }}>
                    <Tag color="red">前置条件</Tag>
                    <Tag color="green">包含</Tag>
                    <Tag color="blue">依赖</Tag>
                    <Tag>关联</Tag>
                  </Space>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>登录要求：</Text>
                  <Space size={8} style={{ marginLeft: 8 }}>
                    <span style={{ 
                      display: 'inline-flex', 
                      alignItems: 'center', 
                      gap: 4,
                      fontSize: 11 
                    }}>
                      <span style={{ 
                        width: 24, 
                        height: 3, 
                        background: '#1e293b',
                        borderRadius: 1
                      }}></span>
                      需登录
                    </span>
                    <span style={{ 
                      display: 'inline-flex', 
                      alignItems: 'center', 
                      gap: 4,
                      fontSize: 11 
                    }}>
                      <span style={{ 
                        width: 24, 
                        height: 3, 
                        background: 'repeating-linear-gradient(90deg, #fbbf24 0, #fbbf24 4px, transparent 4px, transparent 8px)',
                        borderRadius: 1
                      }}></span>
                      公开访问
                    </span>
                  </Space>
                </div>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                提示：可拖拽节点调整位置，滚轮缩放，拖拽画布平移
              </Text>
            </div>
            <div style={{ height: 500, width: '100%', border: '1px solid #e5e7eb', borderRadius: 8 }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.3}
                maxZoom={2}
                attributionPosition="bottom-left"
              >
                <Background color="#e5e7eb" gap={16} />
                <Controls showInteractive={false} />
                <MiniMap 
                  nodeColor={(node) => node.data?.color || '#6366f1'}
                  maskColor="rgba(0,0,0,0.1)"
                />
              </ReactFlow>
            </div>
          </>
        ) : (
          <Empty description="暂无图谱数据" style={{ padding: '40px 0' }} />
        )}
      </Modal>
    </div>
  );
};

export default GraphPage;