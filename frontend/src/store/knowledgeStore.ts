import { useState, useEffect, useCallback } from 'react';

export interface Document {
  id: string;
  name: string;
  type: string;
  size: string;
  content: string;
  uploadTime: string;
  status: 'processed' | 'processing' | 'failed';
}

export interface RagKnowledgeBase {
  id: string;
  name: string;
  description: string;
  project: string;
  version: string;
  documentCount: number;
  chunkCount: number;
  status: 'active' | 'inactive' | 'processing';
  createdAt: string;
  updatedAt: string;
  hasGraph: boolean;
  documents?: Document[];
  chunkSize?: number;
  chunkMethod?: string;
  embeddingModel?: string;
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  color: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface KnowledgeGraph {
  id: string;
  name: string;
  sourceRag: string;
  ragId: string;
  entityCount: number;
  relationCount: number;
  tripleCount: number;
  status: 'completed' | 'processing' | 'failed';
  createdAt: string;
  progress: number;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
}

const STORAGE_KEY_RAG = 'knowledge_rag_bases';
const STORAGE_KEY_GRAPHS = 'knowledge_graphs';
const EVENT_UPDATE = 'knowledge_store_update';

const sampleNodes: GraphNode[] = [
  { id: '1', name: '产品', type: '概念', color: '#6366f1' },
  { id: '2', name: '用户', type: '角色', color: '#0891b2' },
  { id: '3', name: '订单', type: '实体', color: '#ea580c' },
  { id: '4', name: '支付', type: '功能', color: '#10b981' },
  { id: '5', name: '库存', type: '实体', color: '#f59e0b' },
  { id: '6', name: '管理员', type: '角色', color: '#8b5cf6' },
  { id: '7', name: '报表', type: '功能', color: '#ec4899' },
  { id: '8', name: '权限', type: '概念', color: '#14b8a6' },
];

const sampleEdges: GraphEdge[] = [
  { source: '1', target: '2', relation: '服务' },
  { source: '2', target: '3', relation: '创建' },
  { source: '3', target: '4', relation: '触发' },
  { source: '3', target: '5', relation: '关联' },
  { source: '6', target: '1', relation: '管理' },
  { source: '6', target: '7', relation: '查看' },
  { source: '8', target: '6', relation: '控制' },
  { source: '8', target: '2', relation: '限制' },
  { source: '1', target: '7', relation: '生成' },
  { source: '5', target: '3', relation: '支持' },
];

const sampleDocuments: Document[] = [
  { id: 'd1', name: '产品需求文档.pdf', type: 'PDF', size: '2.4 MB', content: '# 产品需求文档\n\n## 1. 产品概述\n\n本产品是一款面向企业级用户的知识管理系统，主要功能包括：\n\n- RAG知识库管理\n- 知识图谱生成\n- 智能问答\n- 文档检索\n\n## 2. 功能模块\n\n### 2.1 RAG知识库\n支持文档上传、自动分块、向量化存储和语义检索。\n\n### 2.2 知识图谱\n基于RAG库自动提取实体和关系，构建知识图谱。\n\n### 2.3 智能问答\n结合RAG和知识图谱，提供精准的问答服务。', uploadTime: '2025-03-20 10:30', status: 'processed' },
  { id: 'd2', name: '用户手册.docx', type: 'DOCX', size: '1.8 MB', content: '# 用户手册\n\n## 快速开始\n\n### 1. 创建知识库\n\n点击"创建知识库"按钮，输入知识库名称和描述，系统会自动生成项目标识和初始版本。\n\n### 2. 上传文档\n\n进入知识库详情页面，点击"上传文档"按钮，支持PDF、DOCX、TXT等格式。\n\n### 3. 生成图谱\n\n文档上传完成后，点击"生成图谱"按钮，系统会自动提取实体和关系。\n\n## 常见问题\n\n**Q: 支持哪些文档格式？**\nA: 目前支持PDF、DOCX、TXT、Markdown等格式。\n\n**Q: 知识图谱是如何生成的？**\nA: 系统使用NLP技术自动提取文档中的实体和关系。', uploadTime: '2025-03-19 14:20', status: 'processed' },
  { id: 'd3', name: 'API接口文档.md', type: 'MD', size: '0.5 MB', content: '# API接口文档\n\n## 基础信息\n\n- Base URL: `https://api.example.com/v1`\n- 认证方式: Bearer Token\n\n## 接口列表\n\n### 1. 创建知识库\n\n```\nPOST /knowledge-bases\n```\n\n请求体:\n```json\n{\n  "name": "知识库名称",\n  "description": "描述"\n}\n```\n\n### 2. 上传文档\n\n```\nPOST /knowledge-bases/{id}/documents\n```\n\n### 3. 生成图谱\n\n```\nPOST /knowledge-bases/{id}/graph\n```', uploadTime: '2025-03-18 09:15', status: 'processed' },
];

const defaultRagBases: RagKnowledgeBase[] = [
  { id: '1', name: '产品文档库', description: '产品相关文档', project: 'product-docs', version: 'v1.0.0', documentCount: 24, chunkCount: 156, status: 'active', createdAt: '2025-03-20 10:30', updatedAt: '2025-03-25 14:20', hasGraph: true, documents: sampleDocuments },
  { id: '2', name: 'API文档库', description: 'API接口文档', project: 'api-docs', version: 'v2.1.0', documentCount: 18, chunkCount: 89, status: 'active', createdAt: '2025-03-19 14:20', updatedAt: '2025-03-24 09:15', hasGraph: false, documents: [sampleDocuments[2]] },
  { id: '3', name: '技术规范库', description: '技术规范与标准', project: 'tech-specs', version: 'v1.2.0', documentCount: 12, chunkCount: 67, status: 'processing', createdAt: '2025-03-21 09:15', updatedAt: '2025-03-21 09:15', hasGraph: false, documents: [] },
];

const defaultGraphs: KnowledgeGraph[] = [
  { 
    id: 'graph-1', 
    name: '产品文档图谱', 
    sourceRag: '产品文档库', 
    ragId: '1', 
    entityCount: 256, 
    relationCount: 128, 
    tripleCount: 512, 
    status: 'completed', 
    createdAt: '2025-03-22 15:30', 
    progress: 100,
    nodes: sampleNodes,
    edges: sampleEdges,
  },
];

const getRagBases = (): RagKnowledgeBase[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_RAG);
    return stored ? JSON.parse(stored) : defaultRagBases;
  } catch {
    return defaultRagBases;
  }
};

const getGraphs = (): KnowledgeGraph[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_GRAPHS);
    return stored ? JSON.parse(stored) : defaultGraphs;
  } catch {
    return defaultGraphs;
  }
};

const saveRagBases = (data: RagKnowledgeBase[]) => {
  localStorage.setItem(STORAGE_KEY_RAG, JSON.stringify(data));
  window.dispatchEvent(new CustomEvent(EVENT_UPDATE));
};

const saveGraphs = (data: KnowledgeGraph[]) => {
  localStorage.setItem(STORAGE_KEY_GRAPHS, JSON.stringify(data));
  window.dispatchEvent(new CustomEvent(EVENT_UPDATE));
};

export const useRagBases = () => {
  const [ragBases, setRagBases] = useState<RagKnowledgeBase[]>(getRagBases);

  useEffect(() => {
    const handleUpdate = () => {
      setRagBases(getRagBases());
    };
    window.addEventListener(EVENT_UPDATE, handleUpdate);
    return () => window.removeEventListener(EVENT_UPDATE, handleUpdate);
  }, []);

  const addRagBase = useCallback((rag: RagKnowledgeBase) => {
    const data = [...getRagBases(), rag];
    saveRagBases(data);
    setRagBases(data);
  }, []);

  const updateRagBase = useCallback((id: string, updates: Partial<RagKnowledgeBase>) => {
    const data = getRagBases().map(r => r.id === id ? { ...r, ...updates } : r);
    saveRagBases(data);
    setRagBases(data);
  }, []);

  const deleteRagBase = useCallback((id: string) => {
    const ragBasesData = getRagBases().filter(r => r.id !== id);
    saveRagBases(ragBasesData);
    setRagBases(ragBasesData);
    
    const graphsData = getGraphs().filter(g => g.ragId !== id);
    saveGraphs(graphsData);
  }, []);

  const addDocument = useCallback((ragId: string, doc: Document) => {
    const data = getRagBases().map(r => {
      if (r.id === ragId) {
        const documents = [...(r.documents || []), doc];
        return { 
          ...r, 
          documents, 
          documentCount: documents.length,
          updatedAt: new Date().toLocaleString()
        };
      }
      return r;
    });
    saveRagBases(data);
    setRagBases(data);
  }, []);

  const deleteDocument = useCallback((ragId: string, docId: string) => {
    const data = getRagBases().map(r => {
      if (r.id === ragId) {
        const documents = (r.documents || []).filter(d => d.id !== docId);
        return { 
          ...r, 
          documents, 
          documentCount: documents.length,
          updatedAt: new Date().toLocaleString()
        };
      }
      return r;
    });
    saveRagBases(data);
    setRagBases(data);
  }, []);

  return { ragBases, addRagBase, updateRagBase, deleteRagBase, addDocument, deleteDocument };
};

export const useGraphs = () => {
  const [graphs, setGraphs] = useState<KnowledgeGraph[]>(getGraphs);

  useEffect(() => {
    const handleUpdate = () => {
      setGraphs(getGraphs());
    };
    window.addEventListener(EVENT_UPDATE, handleUpdate);
    return () => window.removeEventListener(EVENT_UPDATE, handleUpdate);
  }, []);

  const addGraph = useCallback((graph: KnowledgeGraph) => {
    const data = [...getGraphs(), graph];
    saveGraphs(data);
    setGraphs(data);
  }, []);

  const deleteGraph = useCallback((id: string) => {
    const data = getGraphs().filter(g => g.id !== id);
    saveGraphs(data);
    setGraphs(data);
  }, []);

  return { graphs, addGraph, deleteGraph };
};

export const generateGraphFromRag = (rag: RagKnowledgeBase): KnowledgeGraph => {
  const docContent = rag.documents?.map(d => d.content).join('\n\n') || '';
  
  let nodes: GraphNode[] = [];
  let edges: GraphEdge[] = [];
  
  const colors: Record<string, string> = {
    '模块': '#6366f1',
    '功能': '#10b981',
    '系统': '#0891b2',
    '技术': '#ea580c',
    '角色': '#8b5cf6',
    '实体': '#ec4899',
  };
  
  if (docContent && docContent.length > 100) {
    const nodeMap = new Map<string, GraphNode>();
    let nodeIndex = 0;
    
    const addNode = (name: string, type: string) => {
      const cleanName = name.trim().substring(0, 12);
      if (cleanName.length >= 2 && !nodeMap.has(cleanName)) {
        nodeMap.set(cleanName, {
          id: `n${nodeIndex++}`,
          name: cleanName,
          type,
          color: colors[type] || '#6366f1',
        });
      }
    };
    
    const sectionPattern = /[一三三四五六七八九十\d]+[、.．]\s*([^\n]{2,12})/g;
    const modulePattern = /([^\n]{2,10})(模块|管理|配置|设置)/g;
    const featurePattern = /功能[：:·\s]*([^\n，。]{2,10})/g;
    const techPattern = /(React|Vue|Python|FastAPI|TypeScript|Node\.?js|LLM|RAG|AI\s*Agent|Embedding|知识图谱|向量数据库)/gi;
    const rolePattern = /(管理员|用户|测试人员|开发者|项目经理|查看者)/g;
    
    const sectionMatches = [...docContent.matchAll(sectionPattern)];
    sectionMatches.slice(0, 10).forEach(match => {
      const name = match[1]?.replace(/[模块功能设置配置]$/g, '').trim();
      if (name && name.length >= 2 && name.length <= 10) {
        addNode(name, '模块');
      }
    });
    
    const moduleMatches = [...docContent.matchAll(modulePattern)];
    moduleMatches.slice(0, 8).forEach(match => {
      const name = match[1]?.trim();
      if (name && name.length >= 2) {
        addNode(name + (match[2] || '模块'), '模块');
      }
    });
    
    const featureMatches = [...docContent.matchAll(featurePattern)];
    featureMatches.slice(0, 8).forEach(match => {
      const name = match[1]?.trim();
      if (name && name.length >= 2) {
        addNode(name, '功能');
      }
    });
    
    const techMatches = [...docContent.matchAll(techPattern)];
    techMatches.slice(0, 6).forEach(match => {
      const name = match[1]?.trim();
      if (name) {
        addNode(name, '技术');
      }
    });
    
    const roleMatches = [...docContent.matchAll(rolePattern)];
    roleMatches.slice(0, 4).forEach(match => {
      const name = match[1]?.trim();
      if (name) {
        addNode(name, '角色');
      }
    });
    
    nodes = Array.from(nodeMap.values()).slice(0, 12);
    
    if (nodes.length < 3) {
      nodes = [
        { id: 'n0', name: '知识管理', type: '模块', color: '#6366f1' },
        { id: 'n1', name: 'RAG检索', type: '功能', color: '#10b981' },
        { id: 'n2', name: '图谱生成', type: '功能', color: '#0891b2' },
        { id: 'n3', name: 'LLM配置', type: '模块', color: '#ea580c' },
        { id: 'n4', name: '测试管理', type: '模块', color: '#8b5cf6' },
      ];
    }
    
    const relationTypes = ['包含', '依赖', '关联', '调用', '生成', '支持', '使用'];
    const nodeList = nodes;
    
    for (let i = 0; i < Math.min(nodeList.length - 1, 10); i++) {
      const sourceType = nodeList[i].type;
      const targetType = nodeList[i + 1].type;
      
      let relation = relationTypes[i % relationTypes.length];
      if (sourceType === '模块' && targetType === '功能') {
        relation = '包含';
      } else if (sourceType === '功能' && targetType === '技术') {
        relation = '使用';
      } else if (sourceType === '模块' && targetType === '模块') {
        relation = '关联';
      }
      
      edges.push({
        source: nodeList[i].id,
        target: nodeList[i + 1].id,
        relation,
      });
    }
    
    if (nodeList.length > 3) {
      edges.push({
        source: nodeList[0].id,
        target: nodeList[nodeList.length - 1].id,
        relation: '关联',
      });
    }
  } else {
    nodes = [
      { id: 'n0', name: '知识库', type: '模块', color: '#6366f1' },
      { id: 'n1', name: '文档管理', type: '功能', color: '#10b981' },
      { id: 'n2', name: '向量检索', type: '功能', color: '#0891b2' },
      { id: 'n3', name: '图谱分析', type: '功能', color: '#ea580c' },
    ];
    edges = [
      { source: 'n0', target: 'n1', relation: '包含' },
      { source: 'n0', target: 'n2', relation: '支持' },
      { source: 'n0', target: 'n3', relation: '生成' },
    ];
  }
  
  return {
    id: `graph-${rag.id}`,
    name: `${rag.name}图谱`,
    sourceRag: rag.name,
    ragId: rag.id,
    entityCount: nodes.length,
    relationCount: edges.length,
    tripleCount: edges.length,
    status: 'completed',
    createdAt: new Date().toLocaleString(),
    progress: 100,
    nodes,
    edges,
  };
};