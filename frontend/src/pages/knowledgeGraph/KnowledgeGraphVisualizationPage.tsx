/**
 * 知识图谱可视化页面（纯关系图 + 逐级下钻）
 *
 * 三级下钻：
 *   L0 总览   —— 模块节点（menus ∪ pages ∪ flows.module）+ 模块间关联
 *                （依赖边命中模块名 + 前置条件边：登录流程 → 其余模块）
 *   L1 模块   —— 该模块页面节点（快照 page_name 命中）+ 页面跳转边
 *                （访问序相邻连边 + 依赖边）；二/三级页面按 URL 深度着色标注
 *   L2 页面   —— 快照元素节点 + 步骤流转边（flows.steps 相邻序列）
 *
 * 数据不足回退：总览无模块数据 → 原有元素级视图
 */

import React, { useEffect, useState, useRef } from 'react';
import { Card, Input, Button, Space, Statistic, Tag, Alert, Typography, Spin, Empty, message } from 'antd';
import {
  ArrowLeftOutlined,
  SearchOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  ReloadOutlined,
  FileTextOutlined,
  ApartmentOutlined,
  DatabaseOutlined,
  LinkOutlined
} from '@ant-design/icons';
import * as d3 from 'd3';
import { useParams, useNavigate } from 'react-router-dom';
import { getKnowledgeGraphDetail, KnowledgeGraphDetailResponse } from '../../api/knowledgeGraphApi';

const { Title, Text } = Typography;

// 边类型 → 颜色
const LINK_COLORS: Record<string, string> = {
  '前置条件': '#f5222d',
  '跳转': '#bfbfbf',
  '导航': '#bfbfbf',
  '菜单入口': '#1890ff',
  '步骤流转': '#722ed1',
};

// URL 深度：hash 路由 #/a/b/c → 3；pathname /a/b/c → 3
const urlDepth = (url: string): number => {
  try {
    const u = new URL(url);
    const hashSegs = (u.hash.split('/').filter(Boolean).length);
    const pathSegs = (u.pathname || '').split('/').filter(Boolean).length;
    return hashSegs || pathSegs;
  } catch {
    return 0;
  }
};

// 短路径（显示用）：hash 最后一段或 pathname 最后一段
const shortPath = (url: string): string => {
  try {
    const u = new URL(url);
    const segs = (u.hash || u.pathname || '').split('/').filter(Boolean);
    return segs.length ? '/' + segs[segs.length - 1] : '';
  } catch {
    return '';
  }
};

// 模块名模糊匹配（与后端 _query_existing_kg 同语义：双向包含）
const moduleMatch = (name: string, module: string): boolean => {
  const n = (name || '').trim();
  return !!n && (n.includes(module) || module.includes(n));
};

// 摊平快照元素（兼容 role-grouped {role: [...]} 与 flat 两种结构）
const flattenElements = (els: any[]): any[] => {
  const out: any[] = [];
  (els || []).forEach((el: any) => {
    if (el && typeof el === 'object' && Array.isArray(el.items)) {
      (el.items || []).forEach((it: any) => out.push({ ...it, role: el.role || el.type || it.role || '' }));
    } else if (el && typeof el === 'object') {
      out.push(el);
    }
  });
  return out;
};

const elemName = (el: any, i: number): string => {
  return (el?.name || el?.element_name || el?.text || el?.label || '').toString().trim()
    || `元素${i + 1}`;
};

const KnowledgeGraphVisualizationPage: React.FC = () => {
  const { graphId } = useParams<{ graphId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState<KnowledgeGraphDetailResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedNode, setSelectedNode] = useState<any>(null);

  // 逐级下钻状态
  const [level, setLevel] = useState<0 | 1 | 2>(0);
  const [activeModule, setActiveModule] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 加载知识图谱数据
  useEffect(() => {
    if (graphId) {
      loadGraphData(parseInt(graphId));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId]);

  // 绘制D3力导向图
  useEffect(() => {
    if (graphData && svgRef.current && containerRef.current) {
      drawKnowledgeGraph();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, level, activeModule, activePage]);

  const loadGraphData = async (id: number, silent = false) => {
    setLoading(true);
    try {
      const data = await getKnowledgeGraphDetail(id);
      setGraphData(data);
      if (!silent) {
        message.success('知识图谱数据加载成功');
      }
    } catch (error) {
      if (!silent) {
        message.error('加载知识图谱数据失败');
      }
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 生成中自动刷新：直接进入本页（running 状态）时每 3 秒拉详情，
  // 完成后自动展示最新数据（对应 Alert 文案「生成完成后自动刷新」）
  useEffect(() => {
    if (!graphData || graphData.exploration_status !== 'running' || !graphId) return;
    const timer = setInterval(() => loadGraphData(parseInt(graphId), true), 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData?.exploration_status, graphId]);

  // ═══════════════════════════════════════════════════════
  // 数据预处理
  // ═══════════════════════════════════════════════════════

  const buildModules = (): { name: string; pageCount: number }[] => {
    if (!graphData) return [];
    const names = new Map<string, number>();
    // 模块名可靠来源：menus.name / flows.module / 模块级依赖边 from
    // （pages[].page_name 是 URL 派生的页面名如 "login"，不是模块名，不入模块集）
    (graphData.menus || []).forEach((m: any) => {
      const n = (m.name || '').trim();
      if (n && !names.has(n)) names.set(n, 0);
    });
    (graphData.flows || []).forEach((f: any) => {
      const n = (f.module || '').trim();
      if (n && !names.has(n)) names.set(n, 0);
    });
    (graphData.dependencies || []).forEach((d: any) => {
      const t = (d.type || '') as string;
      if (!['导航', '菜单入口', '模块归属', '前置条件'].includes(t)) return;
      const n = (d.from || '').trim();
      if (n && !names.has(n)) names.set(n, 0);
    });
    // 页面归属统计：快照 page_name（存模块名）逐页计数
    (graphData.snapshots || []).forEach((s: any) => {
      const n = (s.page_name || '').trim();
      if (n) names.set(n, (names.get(n) || 0) + 1);
    });
    return Array.from(names.entries()).map(([name, pageCount]) => ({ name, pageCount }));
  };

  // 模块下页面（快照 page_name 模糊命中，快照 page_name 存模块名；
  // 回退 pages 列：module 键命中 或 模块级依赖边 to 反查页面名）
  const buildModulePages = (module: string): any[] => {
    if (!graphData) return [];
    const snaps = (graphData.snapshots || []).filter((s: any) => moduleMatch(s.page_name, module));
    if (snaps.length > 0) {
      const minDepth = Math.min(...snaps.map((s: any) => urlDepth(s.page_url || '')));
      return snaps.map((s: any) => ({
        page_url: s.page_url,
        page_name: s.page_name || '',
        depth: urlDepth(s.page_url || '') - minDepth,
        visit_order: s.visit_order || 0,
      }));
    }
    // 模块级依赖边（导航/菜单入口/模块归属）to 反查：模块 → 其下页面
    const depTos = new Set(
      (graphData.dependencies || [])
        .filter((d: any) =>
          moduleMatch(d.from, module) && ['导航', '菜单入口', '模块归属'].includes(d.type || ''))
        .map((d: any) => (d.to || '').trim())
    );
    return (graphData.pages || [])
      .filter((p: any) =>
        moduleMatch(p.module, module) || depTos.has((p.page_name || '').trim()))
      .map((p: any) => {
        const d = urlDepth(p.page_url || '');
        return { page_url: p.page_url, page_name: p.page_name || '', depth: d, visit_order: 0 };
      });
  };

  // 页面元素（快照匹配；快照元素缺失时回退 elements 列全量展示）
  const buildPageElements = (pageUrl: string): any[] => {
    if (!graphData) return [];
    const snap = (graphData.snapshots || []).find(
      (s: any) => s.page_url && (s.page_url === pageUrl || pageUrl.includes(s.page_url) || s.page_url.includes(pageUrl))
    );
    const snapEls = snap ? flattenElements(snap.elements || []) : [];
    if (snapEls.length > 0) return snapEls;
    // 回退：elements 列（无页面归属信息，全量展示，步骤流转边仍可连）
    if ((graphData.elements || []).length > 0) return flattenElements(graphData.elements);
    return [];
  };

  // 模块相关流程（步骤流转边素材）
  const buildModuleFlows = (module: string): any[] => {
    if (!graphData) return [];
    return (graphData.flows || []).filter((f: any) => moduleMatch(f.module, module));
  };

  // ═══════════════════════════════════════════════════════
  // 绘制
  // ═══════════════════════════════════════════════════════

  const drawKnowledgeGraph = () => {
    if (!graphData || !svgRef.current || !containerRef.current) return;

    // 清除旧图
    d3.select(svgRef.current).selectAll('*').remove();

    const nodes: any[] = [];
    const links: any[] = [];
    const nodeIds = new Set<string>();

    const addNode = (id: string, name: string, type: string, color: string, extra: any = {}) => {
      if (!id || nodeIds.has(id)) return;
      nodeIds.add(id);
      nodes.push({ id, name, type, color, ...extra });
    };

    // 关键稳健性：源/目标必须已存在于节点集，否则丢弃（防 d3 forceLink NaN）
    const addLink = (source: string, target: string, type: string) => {
      if (!source || !target) return;
      if (!nodeIds.has(source) || !nodeIds.has(target)) return;
      links.push({ source, target, type });
    };

    // ── L0 总览：模块级 ──
    if (level === 0) {
      const modules = buildModules();
      if (modules.length === 0) {
        drawLegacyGraph(); // 无模块数据 → 回退原有元素级视图
        return;
      }
      modules.forEach((m) => {
        // 节点半径按页面数缩放（10 ~ 26）
        const r = 10 + Math.min(16, (m.pageCount || 0) * 6);
        addNode(`mod_${m.name}`, m.name, 'module', '#1890ff', { pageCount: m.pageCount, radius: r });
      });

      // 依赖边命中模块名（精确匹配，模块名去重后同名即同一节点）
      (graphData.dependencies || []).forEach((dep: any) => {
        if (dep.from && dep.to && nodeIds.has(`mod_${dep.from}`) && nodeIds.has(`mod_${dep.to}`)) {
          addLink(`mod_${dep.from}`, `mod_${dep.to}`, dep.type || '依赖');
        }
      });

      // 前置条件边：登录流程 → 其余模块（如「工作台的前置条件=登录」）。
      // 优先取 flow_type='login' 流程的 module；无登录流程时按平台内部约定名
      // （'登录模块'/'系统登录'）识别含「登录」的模块（CLAUDE.md 例外：内部约定名不参数化）
      let loginModule = '';
      const loginFlow = (graphData.flows || []).find((f: any) => f.flow_type === 'login');
      if (loginFlow?.module && nodeIds.has(`mod_${loginFlow.module}`)) {
        loginModule = loginFlow.module;
      } else {
        const hit = modules.find((m) => /登录|login/i.test(m.name));
        if (hit) loginModule = hit.name;
      }
      if (loginModule && nodeIds.has(`mod_${loginModule}`)) {
        modules.forEach((m) => {
          if (m.name !== loginModule) {
            addLink(`mod_${loginModule}`, `mod_${m.name}`, '前置条件');
          }
        });
      }
    }

    // ── L1 模块下钻：页面节点 + 页面间跳转 ──
    else if (level === 1 && activeModule) {
      const pages = buildModulePages(activeModule);
      if (pages.length === 0) {
        drawLegacyGraph();
        return;
      }
      pages.forEach((p: any) => {
        const depthColor = p.depth === 0 ? '#1890ff' : p.depth === 1 ? '#52c41a' : '#fa8c16';
        addNode(`pg_${p.page_url}`, `${p.page_name || ''}${shortPath(p.page_url)}`.trim(), 'page', depthColor, {
          url: p.page_url,
          depth: p.depth,
        });
      });

      // 页面间跳转边：同模块内按访问序相邻连边（访问序=逻辑流转序）
      const sorted = [...pages].sort((a: any, b: any) => (a.visit_order || 0) - (b.visit_order || 0));
      for (let i = 1; i < sorted.length; i++) {
        const from = sorted[i - 1].page_url;
        const to = sorted[i].page_url;
        if (from && to && from !== to) addLink(`pg_${from}`, `pg_${to}`, '跳转');
      }

      // 依赖「跳转/导航/菜单入口」边（两端都是本模块页面节点才加）
      (graphData.dependencies || []).forEach((dep: any) => {
        if (dep.from && dep.to && nodeIds.has(`pg_${dep.from}`) && nodeIds.has(`pg_${dep.to}`)) {
          addLink(`pg_${dep.from}`, `pg_${dep.to}`, dep.type || '依赖');
        }
      });
    }

    // ── L2 页面下钻：元素节点 + 步骤流转边 ──
    else if (level === 2 && activePage) {
      const elements = buildPageElements(activePage);
      if (elements.length === 0) {
        drawLegacyGraph();
        return;
      }
      elements.forEach((el: any, i: number) => {
        const name = elemName(el, i);
        const elType = el.role || el.type || '';
        addNode(`el_${activePage}_${i}`, name, 'element', '#722ed1', { elementType: elType });
      });

      // 步骤流转边（元素→元素）：目标文本/依赖端点匹配元素节点才连
      const match = (t: string) => {
        if (!t) return -1;
        return elements.findIndex((el: any, j: number) => {
          const n = elemName(el, j);
          return n && (n.includes(t) || t.includes(n));
        });
      };
      // 来源 1：dependencies「步骤流转」边（探索管线产物，真机数据的主要来源）
      (graphData.dependencies || []).forEach((dep: any) => {
        if (dep.type !== '步骤流转') return;
        const fromIdx = match((dep.from || '').toString());
        const toIdx = match((dep.to || '').toString());
        if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
          addLink(`el_${activePage}_${fromIdx}`, `el_${activePage}_${toIdx}`, '步骤流转');
        }
      });
      // 来源 2：flows（模块命中）steps 相邻序列
      const flows = buildModuleFlows(activeModule || '');
      flows.forEach((f: any) => {
        const steps = (f.steps || []) as any[];
        for (let i = 1; i < steps.length; i++) {
          const prevTarget = (steps[i - 1].target || steps[i - 1].locator_text || '').toString().trim();
          const curTarget = (steps[i].target || steps[i].locator_text || '').toString().trim();
          if (!prevTarget || !curTarget) continue;
          const fromIdx = match(prevTarget);
          const toIdx = match(curTarget);
          if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
            addLink(`el_${activePage}_${fromIdx}`, `el_${activePage}_${toIdx}`, '步骤流转');
          }
        }
      });
    }

    if (nodes.length === 0) {
      d3.select(svgRef.current).selectAll('*').remove();
      message.info('知识图谱数据为空——请在项目列表卡片点击「知识图谱」按钮生成图谱数据');
      setLoading(false);
      return;
    }

    renderGraph(nodes, links);
  };

  // 回退视图：原有元素级力导向图（无模块数据时）
  const drawLegacyGraph = () => {
    if (!graphData || !svgRef.current || !containerRef.current) return;
    const nodes: any[] = [];
    const links: any[] = [];
    const nodeIds = new Set<string>();
    const addNode = (id: string, name: string, type: string, color: string, extra: any = {}) => {
      if (!id || nodeIds.has(id)) return;
      nodeIds.add(id);
      nodes.push({ id, name, type, color, ...extra });
    };
    const addLink = (source: string, target: string, type: string) => {
      if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) return;
      links.push({ source, target, type });
    };

    const sampledElements = (graphData.elements || []).slice(0, 50);
    sampledElements.forEach((elem: any, i: number) => {
      addNode(`elem_${i}`, elemName(elem, i), 'element', '#722ed1', { elementType: elem.type });
    });
    if (sampledElements.length === 0) {
      d3.select(svgRef.current).selectAll('*').remove();
      message.info('暂无知识图谱数据，请先在项目列表生成图谱');
      setLoading(false);
      return;
    }
    if (graphData.base_url) {
      addNode('page_synthetic', '探索页面', 'page', '#faad14', { url: graphData.base_url });
      sampledElements.forEach((_: any, i: number) => {
        addLink('page_synthetic', `elem_${i}`, '包含');
      });
    }
    // 步骤流转边（元素级依赖）
    (graphData.dependencies || []).forEach((dep: any) => {
      const fromIdx = sampledElements.findIndex((el: any, j: number) => {
        const n = elemName(el, j);
        return n && (dep.from || '').includes(n);
      });
      const toIdx = sampledElements.findIndex((el: any, j: number) => {
        const n = elemName(el, j);
        return n && (dep.to || '').includes(n);
      });
      if (fromIdx >= 0 && toIdx >= 0 && fromIdx !== toIdx) {
        addLink(`elem_${fromIdx}`, `elem_${toIdx}`, dep.type || '依赖');
      }
    });
    renderGraph(nodes, links);
  };

  // 公共渲染：力导向图（缩放/拖拽/点击）
  const renderGraph = (nodes: any[], links: any[]) => {
    if (!svgRef.current || !containerRef.current) return;
    const width = containerRef.current.clientWidth;
    const height = 600;

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg.append('g');

    const zoom = d3.zoom<SVGSVGElement, any>()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance(110))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => (d.radius || 22) + 8));

    // 连线（按类型着色）
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .enter().append('line')
      .attr('stroke', (d: any) => LINK_COLORS[d.type] || '#ccc')
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.6);

    // 连线标签
    const linkLabel = g.append('g')
      .selectAll('text')
      .data(links)
      .enter().append('text')
      .text((d: any) => d.type)
      .attr('font-size', '10px')
      .attr('fill', '#999')
      .attr('text-anchor', 'middle');

    // 节点
    const node = g.append('g')
      .selectAll('g')
      .data(nodes)
      .enter().append('g')
      .call(d3.drag<SVGGElement, any>()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended)
      );

    node.append('circle')
      .attr('r', (d: any) => d.radius || 20)
      .attr('fill', (d: any) => d.color)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('cursor', 'pointer');

    node.append('text')
      .text((d: any) => d.name)
      .attr('x', (d: any) => (d.radius || 20) + 5)
      .attr('y', 5)
      .attr('font-size', '12px')
      .attr('fill', '#333')
      .attr('cursor', 'pointer');

    node.on('click', (event: any, d: any) => {
      event.stopPropagation();
      // 逐级下钻：总览点模块 → L1；L1 点页面 → L2；其余 → 详情面板
      if (level === 0 && d.type === 'module') {
        setSelectedNode(null);
        setActiveModule(d.name);
        setLevel(1);
        return;
      }
      if (level === 1 && d.type === 'page') {
        setSelectedNode(null);
        setActivePage(d.url);
        setLevel(2);
        return;
      }
      setSelectedNode(d);
    });

    // 搜索高亮
    if (searchTerm) {
      node.selectAll('circle')
        .attr('stroke', (d: any) =>
          d.name.toLowerCase().includes(searchTerm.toLowerCase()) ? '#ff4d4f' : '#fff'
        )
        .attr('stroke-width', (d: any) =>
          d.name.toLowerCase().includes(searchTerm.toLowerCase()) ? 4 : 2
        );
    }

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      linkLabel
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2 - 5);
      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }

    function dragged(event: any) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }

    function dragended(event: any) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }
  };

  const handleSearch = () => {
    drawKnowledgeGraph();
  };

  const handleZoomIn = () => {
    if (svgRef.current) {
      d3.select(svgRef.current).transition().call(
        d3.zoom<SVGSVGElement, any>().scaleBy as any, 1.3
      );
    }
  };

  const handleZoomOut = () => {
    if (svgRef.current) {
      d3.select(svgRef.current).transition().call(
        d3.zoom<SVGSVGElement, any>().scaleBy as any, 0.7
      );
    }
  };

  const handleReload = () => {
    drawKnowledgeGraph();
  };

  const goBack = () => {
    setSelectedNode(null);
    if (level === 2) {
      setActivePage(null);
      setLevel(1);
    } else if (level === 1) {
      setActiveModule(null);
      setLevel(0);
    }
  };

  // ═══════════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════════

  if (loading) {
    return (
      <Card style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="正在加载知识图谱数据..." />
      </Card>
    );
  }

  if (!graphData) {
    return (
      <Card>
        <Empty description="知识图谱数据不存在" />
      </Card>
    );
  }

  const levelTitle =
    level === 0 ? '模块总览（点击模块下钻）'
    : level === 1 ? `模块「${activeModule}」页面（点击页面下钻，二/三级页面按颜色区分）`
    : `页面元素`;

  return (
    <div style={{ padding: '20px' }}>
      {/* 返回栏：知识图谱是项目级资产，入口在项目列表卡片（项目详情页已取消） */}
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/projects')}>
          返回项目列表
        </Button>
        {level > 0 && (
          <Button onClick={goBack}>← 返回{level === 2 ? `模块 ${activeModule}` : '总览'}</Button>
        )}
        {graphData.exploration_status === 'running' && (
          <Tag color="blue">生成中 {graphData.progress_percentage}%</Tag>
        )}
      </Space>

      {graphData.exploration_status === 'running' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`知识图谱生成中：${graphData.progress_percentage}%（${graphData.current_page || '探索中'}），生成完成后自动刷新`}
        />
      )}
      {graphData.exploration_status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="知识图谱生成失败"
          description={graphData.error_message || '未知错误，请前往项目列表重新生成'}
        />
      )}

      {/* 顶部工具栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Title level={4}>知识图谱可视化 — {levelTitle}</Title>

          <Space>
            {/* 搜索框 */}
            <Input
              placeholder="搜索节点..."
              prefix={<SearchOutlined />}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onPressEnter={handleSearch}
              style={{ width: 300 }}
            />

            {/* 操作按钮 */}
            <Button icon={<SearchOutlined />} onClick={handleSearch}>搜索</Button>
            <Button icon={<ZoomInOutlined />} onClick={handleZoomIn}>放大</Button>
            <Button icon={<ZoomOutOutlined />} onClick={handleZoomOut}>缩小</Button>
            <Button icon={<ReloadOutlined />} onClick={handleReload}>重置布局</Button>
          </Space>

          {/* 统计信息（按层适配） */}
          <Space size="large">
            {level === 0 && (
              <>
                <Statistic title="模块数" value={buildModules().length} prefix={<ApartmentOutlined />} />
                <Statistic title="页面数" value={graphData.page_count} prefix={<FileTextOutlined />} />
                <Statistic title="元素数" value={graphData.element_count} prefix={<DatabaseOutlined />} />
              </>
            )}
            {level === 1 && activeModule && (
              <>
                <Statistic title="页面数" value={buildModulePages(activeModule).length} prefix={<FileTextOutlined />} />
                <Statistic title="流程数" value={buildModuleFlows(activeModule).length} prefix={<LinkOutlined />} />
              </>
            )}
            {level === 2 && activePage && (
              <Statistic title="元素数" value={buildPageElements(activePage).length} prefix={<DatabaseOutlined />} />
            )}
          </Space>
        </Space>
      </Card>

      {/* 主内容区：图谱 + 图例 */}
      <div style={{ display: 'flex', gap: '16px' }}>
        {/* 知识图谱 */}
        <Card style={{ flex: 1 }}>
          <div ref={containerRef} style={{ width: '100%', height: '600px', border: '1px solid #e8e8e8' }}>
            <svg ref={svgRef}></svg>
          </div>
        </Card>

        {/* 右侧：图例 + 选中的节点详情 */}
        <Card style={{ width: 300 }}>
          <Title level={5}>节点图例</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            {level === 0 && (
              <>
                <Tag color="#1890ff">模块节点</Tag>
                <Tag color="#f5222d">前置条件边（登录 → 模块）</Tag>
                <Tag color="#1890ff">菜单入口 / 依赖边</Tag>
                <Tag color="#bfbfbf">跳转 / 导航边</Tag>
              </>
            )}
            {level === 1 && (
              <>
                <Tag color="#1890ff">一级页面</Tag>
                <Tag color="#52c41a">二级页面（子功能）</Tag>
                <Tag color="#fa8c16">三级页面</Tag>
                <Tag color="#bfbfbf">页面跳转边</Tag>
              </>
            )}
            {level === 2 && (
              <>
                <Tag color="#722ed1">元素节点</Tag>
                <Tag color="#722ed1">步骤流转边</Tag>
              </>
            )}
            {level === 0 && <Text type="secondary">提示：点击模块节点下钻查看页面；点击页面节点查看元素</Text>}
            {level === 1 && <Text type="secondary">提示：二/三级页面为模块下的子功能，点击页面节点查看元素与步骤流转</Text>}
          </Space>

          {/* 选中节点详情 */}
          {selectedNode && (
            <div style={{ marginTop: 16 }}>
              <Title level={5}>节点详情</Title>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text strong>名称：{selectedNode.name}</Text>
                <Text>类型：{selectedNode.type}</Text>
                {selectedNode.url && <Text>URL：{selectedNode.url}</Text>}
                {selectedNode.depth !== undefined && <Text>页面层级：{selectedNode.depth === 0 ? '一级' : selectedNode.depth === 1 ? '二级' : `三级+`}</Text>}
                {selectedNode.elementType && <Text>元素类型：{selectedNode.elementType}</Text>}
                {selectedNode.pageCount !== undefined && <Text>关联页面数：{selectedNode.pageCount}</Text>}
              </Space>
            </div>
          )}
        </Card>
      </div>

      {/* 爬取配置信息 */}
      <Card style={{ marginTop: 16 }}>
        <Alert
          message="知识图谱生成信息"
          description={
            <Space direction="vertical">
              <Text>图谱名称：{graphData.graph_name}</Text>
              <Text>项目URL：{graphData.base_url}</Text>
              <Text>爬取策略：{graphData.exploration_strategy}</Text>
              <Text>准确性评分：{graphData.confidence_score.toFixed(2)}</Text>
              <Text>定位器验证率：{graphData.locator_validation_rate.toFixed(2)}</Text>
              <Text>耗时：{graphData.duration_seconds}秒</Text>
            </Space>
          }
          type="info"
          showIcon
        />
      </Card>
    </div>
  );
};

export default KnowledgeGraphVisualizationPage;
