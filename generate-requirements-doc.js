const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel, AlignmentType, WidthType, BorderStyle, ShadingType, PageBreak, Header, Footer, PageNumber, LevelFormat, TabStopType, TabStopPosition } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

const createTableCell = (text, options = {}) => {
  const { bold = false, width = 2000, fill = null, align = AlignmentType.LEFT } = options;
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [
      new Paragraph({
        alignment: align,
        children: [new TextRun({ text, bold, font: "微软雅黑", size: 21 })]
      })
    ]
  });
};

const createHeading1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 400, after: 200 },
  children: [new TextRun({ text, bold: true, font: "微软雅黑", size: 32, color: "2E75B6" })]
});

const createHeading2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 300, after: 150 },
  children: [new TextRun({ text, bold: true, font: "微软雅黑", size: 28, color: "2E75B6" })]
});

const createHeading3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 200, after: 100 },
  children: [new TextRun({ text, bold: true, font: "微软雅黑", size: 24, color: "404040" })]
});

const createParagraph = (text, options = {}) => {
  const { bold = false, indent = 0, color = "333333" } = options;
  return new Paragraph({
    spacing: { after: 120 },
    indent: indent > 0 ? { left: indent * 360 } : undefined,
    children: [new TextRun({ text, bold, font: "微软雅黑", size: 21, color })]
  });
};

const doc = new Document({
  styles: {
    default: { document: { run: { font: "微软雅黑", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "微软雅黑", color: "2E75B6" },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "微软雅黑", color: "2E75B6" },
        paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "微软雅黑", color: "404040" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } }
    },
    headers: {
      default: new Header({ children: [new Paragraph({ children: [new TextRun({ text: "AI Agent测试平台 V1.0 需求文档", font: "微软雅黑", size: 18, color: "666666" })] })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "第 ", font: "微软雅黑", size: 18 }), new TextRun({ children: [PageNumber.CURRENT], font: "微软雅黑", size: 18 }), new TextRun({ text: " 页", font: "微软雅黑", size: 18 })] })] })
    },
    children: [
      // ========== 封面 ==========
      new Paragraph({ spacing: { before: 2000 } }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "AI Agent测试平台", bold: true, font: "微软雅黑", size: 56, color: "2E75B6" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 }, children: [new TextRun({ text: "V1.0版本详细需求文档", bold: true, font: "微软雅黑", size: 44, color: "404040" })] }),
      new Paragraph({ spacing: { before: 800 } }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "版本号：V1.0", font: "微软雅黑", size: 24 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100 }, children: [new TextRun({ text: "文档状态：正式发布", font: "微软雅黑", size: 24 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100 }, children: [new TextRun({ text: "编制日期：2026年3月", font: "微软雅黑", size: 24 })] }),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 文档修订记录 ==========
      createHeading1("文档修订记录"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1500, 1500, 2000, 4360],
        rows: [
          new TableRow({ children: [createTableCell("版本号", { bold: true, width: 1500, fill: "E8F4FC" }), createTableCell("日期", { bold: true, width: 1500, fill: "E8F4FC" }), createTableCell("修订人", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("修订内容", { bold: true, width: 4360, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("V1.0", { width: 1500 }), createTableCell("2026-03-28", { width: 1500 }), createTableCell("开发团队", { width: 2000 }), createTableCell("初始版本，包含V1.0全部功能需求", { width: 4360 })] }),
        ]
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 目录 ==========
      createHeading1("目  录"),
      createParagraph("一、项目概述 ......................................................... 3"),
      createParagraph("二、用户角色与权限 .................................................. 4"),
      createParagraph("三、功能模块详细需求 ............................................... 5"),
      createParagraph("    3.1 用户认证模块 ................................................. 5"),
      createParagraph("    3.2 仪表板模块 ..................................................... 6"),
      createParagraph("    3.3 知识管理模块 ................................................. 7"),
      createParagraph("    3.4 技能管理模块 ................................................ 10"),
      createParagraph("    3.5 测试管理模块 ................................................ 12"),
      createParagraph("    3.6 测试报告模块 ................................................ 15"),
      createParagraph("    3.7 系统设置模块 ................................................ 16"),
      createParagraph("四、非功能性需求 .................................................. 19"),
      createParagraph("五、技术架构要求 .................................................. 20"),
      createParagraph("六、数据库设计 ..................................................... 21"),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 一、项目概述 ==========
      createHeading1("一、项目概述"),
      createHeading2("1.1 项目背景"),
      createParagraph("AI Agent测试平台是一个基于人工智能技术的自动化测试平台，旨在帮助测试人员快速构建、执行和管理各类测试任务。平台集成了RAG（检索增强生成）知识库、技能管理系统、知识图谱等核心功能，能够显著提升测试效率和质量。"),
      createHeading2("1.2 项目目标"),
      createParagraph("• 构建统一的AI驱动测试平台，整合知识管理、技能管理、测试执行等功能"),
      createParagraph("• 支持多种LLM（大语言模型）接入，包括OpenAI、DeepSeek、智谱AI等"),
      createParagraph("• 实现基于RAG的智能测试用例生成和知识检索"),
      createParagraph("• 提供可视化的知识图谱展示和测试报告分析"),
      createParagraph("• 支持功能测试、API测试、Web UI测试等多种测试类型"),
      createHeading2("1.3 适用范围"),
      createParagraph("本文档适用于AI Agent测试平台V1.0版本的所有开发、测试和运维人员，作为系统设计和开发的依据。"),
      createHeading2("1.4 术语定义"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 7360],
        rows: [
          new TableRow({ children: [createTableCell("术语", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("定义说明", { bold: true, width: 7360, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("RAG", { width: 2000 }), createTableCell("Retrieval-Augmented Generation，检索增强生成，一种结合检索和生成的AI技术", { width: 7360 })] }),
          new TableRow({ children: [createTableCell("LLM", { width: 2000 }), createTableCell("Large Language Model，大语言模型，如GPT、Claude等", { width: 7360 })] }),
          new TableRow({ children: [createTableCell("Embedding", { width: 2000 }), createTableCell("向量化嵌入，将文本转换为向量表示的过程", { width: 7360 })] }),
          new TableRow({ children: [createTableCell("SKILL", { width: 2000 }), createTableCell("技能，平台中可复用的测试能力单元", { width: 7360 })] }),
          new TableRow({ children: [createTableCell("知识图谱", { width: 2000 }), createTableCell("以图结构形式存储和展示知识实体及其关系的技术", { width: 7360 })] }),
        ]
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 二、用户角色与权限 ==========
      createHeading1("二、用户角色与权限"),
      createHeading2("2.1 角色定义"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1800, 3780, 3780],
        rows: [
          new TableRow({ children: [createTableCell("角色名称", { bold: true, width: 1800, fill: "E8F4FC" }), createTableCell("角色描述", { bold: true, width: 3780, fill: "E8F4FC" }), createTableCell("主要职责", { bold: true, width: 3780, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("系统管理员", { width: 1800 }), createTableCell("拥有系统全部权限的管理者", { width: 3780 }), createTableCell("用户管理、系统配置、全局设置", { width: 3780 })] }),
          new TableRow({ children: [createTableCell("项目经理", { width: 1800 }), createTableCell("负责项目整体管理和协调", { width: 3780 }), createTableCell("项目创建、测试审批、报告查看", { width: 3780 })] }),
          new TableRow({ children: [createTableCell("测试人员", { width: 1800 }), createTableCell("执行测试任务的一线人员", { width: 3780 }), createTableCell("测试执行、用例编写、技能使用", { width: 3780 })] }),
          new TableRow({ children: [createTableCell("查看者", { width: 1800 }), createTableCell("仅有查看权限的只读用户", { width: 3780 }), createTableCell("查看报告、浏览知识库", { width: 3780 })] }),
        ]
      }),
      createHeading2("2.2 权限矩阵"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2800, 1640, 1640, 1640, 1640],
        rows: [
          new TableRow({ children: [createTableCell("功能模块", { bold: true, width: 2800, fill: "E8F4FC" }), createTableCell("管理员", { bold: true, width: 1640, fill: "E8F4FC" }), createTableCell("项目经理", { bold: true, width: 1640, fill: "E8F4FC" }), createTableCell("测试人员", { bold: true, width: 1640, fill: "E8F4FC" }), createTableCell("查看者", { bold: true, width: 1640, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("用户管理", { width: 2800 }), createTableCell("全部", { width: 1640 }), createTableCell("-", { width: 1640 }), createTableCell("-", { width: 1640 }), createTableCell("-", { width: 1640 })] }),
          new TableRow({ children: [createTableCell("知识库管理", { width: 2800 }), createTableCell("全部", { width: 1640 }), createTableCell("增删改查", { width: 1640 }), createTableCell("查、上传", { width: 1640 }), createTableCell("查", { width: 1640 })] }),
          new TableRow({ children: [createTableCell("技能管理", { width: 2800 }), createTableCell("全部", { width: 1640 }), createTableCell("增删改查", { width: 1640 }), createTableCell("查、使用", { width: 1640 }), createTableCell("查", { width: 1640 })] }),
          new TableRow({ children: [createTableCell("测试执行", { width: 2800 }), createTableCell("全部", { width: 1640 }), createTableCell("全部", { width: 1640 }), createTableCell("执行、查看", { width: 1640 }), createTableCell("查看", { width: 1640 })] }),
          new TableRow({ children: [createTableCell("系统设置", { width: 2800 }), createTableCell("全部", { width: 1640 }), createTableCell("-", { width: 1640 }), createTableCell("-", { width: 1640 }), createTableCell("-", { width: 1640 })] }),
        ]
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 三、功能模块详细需求 ==========
      createHeading1("三、功能模块详细需求"),
      
      // 3.1 用户认证模块
      createHeading2("3.1 用户认证模块"),
      createHeading3("3.1.1 功能概述"),
      createParagraph("用户认证模块负责系统的登录、注册、权限验证等核心安全功能，采用JWT（JSON Web Token）机制实现无状态认证。"),
      createHeading3("3.1.2 功能列表"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1200, 2000, 4160, 2000],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1200, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 4160, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 2000, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("AUTH-001", { width: 1200 }), createTableCell("用户登录", { width: 2000 }), createTableCell("支持用户名密码登录，返回Access Token和Refresh Token", { width: 4160 }), createTableCell("高", { width: 2000 })] }),
          new TableRow({ children: [createTableCell("AUTH-002", { width: 1200 }), createTableCell("用户注册", { width: 2000 }), createTableCell("新用户注册，需验证用户名和邮箱唯一性", { width: 4160 }), createTableCell("高", { width: 2000 })] }),
          new TableRow({ children: [createTableCell("AUTH-003", { width: 1200 }), createTableCell("Token刷新", { width: 2000 }), createTableCell("使用Refresh Token自动刷新Access Token，无需重新登录", { width: 4160 }), createTableCell("高", { width: 2000 })] }),
          new TableRow({ children: [createTableCell("AUTH-004", { width: 1200 }), createTableCell("退出登录", { width: 2000 }), createTableCell("清除用户会话，Token加入黑名单", { width: 4160 }), createTableCell("中", { width: 2000 })] }),
          new TableRow({ children: [createTableCell("AUTH-005", { width: 1200 }), createTableCell("密码重置", { width: 2000 }), createTableCell("通过邮箱发送重置链接，支持密码找回", { width: 4160 }), createTableCell("中", { width: 2000 })] }),
        ]
      }),
      createHeading3("3.1.3 Token机制说明"),
      createParagraph("• Access Token：有效期30分钟，用于API请求认证"),
      createParagraph("• Refresh Token：有效期7天，用于刷新Access Token"),
      createParagraph("• 前端自动处理Token刷新，用户无感知"),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.2 仪表板模块
      createHeading2("3.2 仪表板模块"),
      createHeading3("3.2.1 功能概述"),
      createParagraph("仪表板是系统的首页入口，展示系统整体运行状态、关键指标统计、最近活动和快速操作入口，帮助用户快速了解系统状态。"),
      createHeading3("3.2.2 页面布局"),
      createParagraph("仪表板页面分为四个主要区域："),
      createParagraph("1. 统计卡片区：展示知识库文档数、技能数量、测试用例数、测试通过率四项核心指标，每个卡片显示数值和变化趋势"),
      createParagraph("2. 最近活动区：展示最近5条系统活动记录，包括用户操作、测试执行、系统事件等"),
      createParagraph("3. 快速操作区：提供上传文档、创建技能、API测试、查看报告四个快捷入口"),
      createParagraph("4. 系统状态区：展示CPU使用率、内存使用率、磁盘空间三项系统资源状态"),
      createHeading3("3.2.3 数据展示要求"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2200, 3580, 3580],
        rows: [
          new TableRow({ children: [createTableCell("统计项", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("数据来源", { bold: true, width: 3580, fill: "E8F4FC" }), createTableCell("展示要求", { bold: true, width: 3580, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("知识库文档", { width: 2200 }), createTableCell("统计所有知识库中的文档总数", { width: 3580 }), createTableCell("数字+单位'个'，显示增长百分比", { width: 3580 })] }),
          new TableRow({ children: [createTableCell("技能数量", { width: 2200 }), createTableCell("统计已创建的技能总数", { width: 3580 }), createTableCell("数字+单位'个'，显示增长百分比", { width: 3580 })] }),
          new TableRow({ children: [createTableCell("测试用例", { width: 2200 }), createTableCell("统计所有测试用例数量", { width: 3580 }), createTableCell("数字+单位'条'，显示增长百分比", { width: 3580 })] }),
          new TableRow({ children: [createTableCell("测试通过率", { width: 2200 }), createTableCell("已通过测试/总测试数", { width: 3580 }), createTableCell("百分比数值，精确到小数点后1位", { width: 3580 })] }),
        ]
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.3 知识管理模块
      createHeading2("3.3 知识管理模块"),
      createHeading3("3.3.1 功能概述"),
      createParagraph("知识管理模块是平台的核心功能，包含RAG知识库和知识图谱两个子模块，支持文档上传、向量化处理、语义检索和图谱可视化。"),
      createHeading3("3.3.2 RAG知识库"),
      createParagraph("RAG知识库提供知识的存储、管理和检索功能，支持多种文档格式的上传和处理。"),
      createParagraph("功能列表：", { bold: true }),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("RAG-001", { width: 1400 }), createTableCell("创建知识库", { width: 2200 }), createTableCell("创建新知识库，设置名称、描述、上传文档", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-002", { width: 1400 }), createTableCell("文档上传", { width: 2200 }), createTableCell("支持PDF、DOC、DOCX、TXT、MD格式，单个文件≤50MB", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-003", { width: 1400 }), createTableCell("文档分块", { width: 2200 }), createTableCell("支持自动、段落、句子、固定长度、语义五种分块方式", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-004", { width: 1400 }), createTableCell("向量化处理", { width: 2200 }), createTableCell("使用Embedding模型将文本转换为向量存储", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-005", { width: 1400 }), createTableCell("语义检索", { width: 2200 }), createTableCell("基于向量相似度的语义搜索功能", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-006", { width: 1400 }), createTableCell("知识库详情", { width: 2200 }), createTableCell("查看知识库基本信息、文档列表、统计数据", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RAG-007", { width: 1400 }), createTableCell("生成知识图谱", { width: 2200 }), createTableCell("从知识库自动生成知识图谱", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.3.3 创建知识库流程"),
      createParagraph("创建知识库采用表单式交互，包含以下必填项和可选项："),
      createParagraph("必填项：", { bold: true }),
      createParagraph("• 知识库名称：最多255字符，不能为空"),
      createParagraph("• 上传文档：至少上传1个文档文件"),
      createParagraph("可选项：", { bold: true }),
      createParagraph("• 描述：知识库的文字描述"),
      createParagraph("• 高级设置（点击按钮弹出配置窗口）："),
      createParagraph("  - 分块大小：100-2000字符，默认500"),
      createParagraph("  - 分块方式：自动/段落/句子/固定长度/语义，默认自动"),
      createParagraph("  - Embedding模型：text-embedding-3-small（推荐）/text-embedding-3-large/text-embedding-ada-002"),
      createParagraph("  - OCR开关：默认开启"),
      createHeading3("3.3.4 Embedding模型与LLM关系说明"),
      createParagraph("重要提示：Embedding模型用于文本向量化检索，LLM用于生成回答，两者独立使用，无需匹配。"),
      createParagraph("• 同一知识库必须使用相同的Embedding模型，创建后不可更改"),
      createParagraph("• 不同的LLM可以与任意Embedding模型配合使用"),
      createParagraph("• 检索阶段使用Embedding模型，生成阶段使用LLM"),
      new Paragraph({ children: [new PageBreak()] }),

      createHeading3("3.3.5 知识图谱"),
      createParagraph("知识图谱模块提供图谱的展示、浏览和管理功能，以可视化方式呈现知识实体及其关系。"),
      createParagraph("功能列表：", { bold: true }),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("GRAPH-001", { width: 1400 }), createTableCell("图谱列表", { width: 2200 }), createTableCell("展示所有知识图谱，含名称、来源RAG、实体数、关系数、状态", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("GRAPH-002", { width: 1400 }), createTableCell("图谱可视化", { width: 2200 }), createTableCell("Canvas绘图实现，圆形节点+连线展示实体关系", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("GRAPH-003", { width: 1400 }), createTableCell("缩放控制", { width: 2200 }), createTableCell("支持放大、缩小、重置视图功能", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("GRAPH-004", { width: 1400 }), createTableCell("图例说明", { width: 2200 }), createTableCell("显示不同类型节点的颜色说明", { width: 3960 }), createTableCell("低", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("GRAPH-005", { width: 1400 }), createTableCell("删除图谱", { width: 2200 }), createTableCell("删除知识图谱，不影响原知识库", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.3.6 图谱可视化规格"),
      createParagraph("• 节点样式：圆形，直径28px，不同类型使用不同颜色"),
      createParagraph("• 连线样式：灰色直线，宽度1.5px，中间标注关系名称"),
      createParagraph("• 节点布局：圆形布局，节点均匀分布在圆周上"),
      createParagraph("• 缩放范围：支持0.5x-2x缩放"),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.4 技能管理模块
      createHeading2("3.4 技能管理模块"),
      createHeading3("3.4.1 功能概述"),
      createParagraph("技能管理模块负责测试技能的全生命周期管理，包括技能的创建、配置、执行和日志记录。技能是平台中可复用的测试能力单元。"),
      createHeading3("3.4.2 功能列表"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("SKILL-001", { width: 1400 }), createTableCell("技能列表", { width: 2200 }), createTableCell("展示所有技能，含名称、类型、状态、使用次数、成功率", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("SKILL-002", { width: 1400 }), createTableCell("创建技能", { width: 2200 }), createTableCell("创建新技能，设置名称、描述、类型、参数配置", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("SKILL-003", { width: 1400 }), createTableCell("编辑技能", { width: 2200 }), createTableCell("修改技能配置，包括参数、超时时间、重试次数等", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("SKILL-004", { width: 1400 }), createTableCell("运行测试", { width: 2200 }), createTableCell("选择LLM配置和参数，执行技能测试", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("SKILL-005", { width: 1400 }), createTableCell("查看日志", { width: 2200 }), createTableCell("展示技能执行历史，含输入输出、耗时、状态", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("SKILL-006", { width: 1400 }), createTableCell("删除技能", { width: 2200 }), createTableCell("删除技能及其相关执行记录", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.4.3 技能属性"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 2000, 5360],
        rows: [
          new TableRow({ children: [createTableCell("属性名称", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("数据类型", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("说明", { bold: true, width: 5360, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("技能名称", { width: 2000 }), createTableCell("String", { width: 2000 }), createTableCell("唯一标识，最多255字符", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("显示名称", { width: 2000 }), createTableCell("String", { width: 2000 }), createTableCell("友好显示名称", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("描述", { width: 2000 }), createTableCell("Text", { width: 2000 }), createTableCell("技能功能描述", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("类型", { width: 2000 }), createTableCell("Enum", { width: 2000 }), createTableCell("功能测试/API测试/Web测试/数据生成/验证/转换/自定义", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("状态", { width: 2000 }), createTableCell("Enum", { width: 2000 }), createTableCell("草稿/审核中/已批准/已废弃/已归档", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("超时时间", { width: 2000 }), createTableCell("Integer", { width: 2000 }), createTableCell("执行超时时间，单位秒，默认300", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("最大重试次数", { width: 2000 }), createTableCell("Integer", { width: 2000 }), createTableCell("执行失败重试次数，默认3", { width: 5360 })] }),
          new TableRow({ children: [createTableCell("版本", { width: 2000 }), createTableCell("String", { width: 2000 }), createTableCell("版本号，如1.0.0", { width: 5360 })] }),
        ]
      }),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.5 测试管理模块
      createHeading2("3.5 测试管理模块"),
      createHeading3("3.5.1 功能概述"),
      createParagraph("测试管理模块提供功能测试、API测试、Web UI测试三种测试类型的创建、执行和管理功能，支持AI辅助生成测试用例。"),
      createHeading3("3.5.2 功能测试"),
      createParagraph("功能测试用于验证系统功能是否符合预期，支持测试用例的管理和批量执行。"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("FUNC-001", { width: 1400 }), createTableCell("用例列表", { width: 2200 }), createTableCell("展示测试用例，含名称、描述、关联技能、状态、优先级", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("FUNC-002", { width: 1400 }), createTableCell("创建用例", { width: 2200 }), createTableCell("创建测试用例，设置测试步骤和预期结果", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("FUNC-003", { width: 1400 }), createTableCell("执行测试", { width: 2200 }), createTableCell("单个执行或批量执行选中的测试用例", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("FUNC-004", { width: 1400 }), createTableCell("筛选过滤", { width: 2200 }), createTableCell("按技能、状态、优先级筛选测试用例", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("FUNC-005", { width: 1400 }), createTableCell("查看结果", { width: 2200 }), createTableCell("查看测试执行结果和详细日志", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.5.3 API测试"),
      createParagraph("API测试用于验证接口的正确性和性能，支持RESTful API的测试。"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("API-001", { width: 1400 }), createTableCell("接口列表", { width: 2200 }), createTableCell("展示API测试用例，含名称、方法、端点、状态、响应时间", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("API-002", { width: 1400 }), createTableCell("创建测试", { width: 2200 }), createTableCell("创建API测试，设置请求方法、URL、Headers、Body", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("API-003", { width: 1400 }), createTableCell("执行请求", { width: 2200 }), createTableCell("发送HTTP请求并获取响应", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("API-004", { width: 1400 }), createTableCell("响应分析", { width: 2200 }), createTableCell("展示响应状态码、响应时间、响应体", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("API-005", { width: 1400 }), createTableCell("成功率统计", { width: 2200 }), createTableCell("统计API调用的成功率", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.5.4 Web UI测试"),
      createParagraph("Web UI测试用于自动化测试Web应用的前端功能，支持多种浏览器和设备模拟。"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("WEB-001", { width: 1400 }), createTableCell("测试列表", { width: 2200 }), createTableCell("展示Web UI测试用例，含名称、脚本类型、浏览器、状态", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("WEB-002", { width: 1400 }), createTableCell("创建测试", { width: 2200 }), createTableCell("创建Web UI测试，编写或录制测试脚本", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("WEB-003", { width: 1400 }), createTableCell("浏览器选择", { width: 2200 }), createTableCell("支持Chrome、Firefox、Safari、Edge", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("WEB-004", { width: 1400 }), createTableCell("设备模拟", { width: 2200 }), createTableCell("支持桌面、平板、手机三种视图模式", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("WEB-005", { width: 1400 }), createTableCell("用例转换", { width: 2200 }), createTableCell("将Web UI测试转换为功能测试用例", { width: 3960 }), createTableCell("低", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.5.5 AI聊天生成"),
      createParagraph("AI聊天生成功能允许用户通过与AI对话的方式快速生成测试用例。"),
      createParagraph("• 支持多轮对话，逐步细化测试需求"),
      createParagraph("• AI根据对话内容自动生成测试脚本"),
      createParagraph("• 支持生成结果的预览和编辑"),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.6 测试报告模块
      createHeading2("3.6 测试报告模块"),
      createHeading3("3.6.1 功能概述"),
      createParagraph("测试报告模块提供测试执行结果的可视化展示和导出功能，支持多种报告类型的生成和管理。"),
      createHeading3("3.6.2 功能列表"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2200, 3960, 1800],
        rows: [
          new TableRow({ children: [createTableCell("编号", { bold: true, width: 1400, fill: "E8F4FC" }), createTableCell("功能名称", { bold: true, width: 2200, fill: "E8F4FC" }), createTableCell("功能描述", { bold: true, width: 3960, fill: "E8F4FC" }), createTableCell("优先级", { bold: true, width: 1800, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("RPT-001", { width: 1400 }), createTableCell("报告列表", { width: 2200 }), createTableCell("展示所有报告，含名称、类型、时间范围、状态、大小", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RPT-002", { width: 1400 }), createTableCell("生成报告", { width: 2200 }), createTableCell("按时间范围和类型生成测试报告", { width: 3960 }), createTableCell("高", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RPT-003", { width: 1400 }), createTableCell("报告预览", { width: 2200 }), createTableCell("在线预览报告内容", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RPT-004", { width: 1400 }), createTableCell("报告下载", { width: 2200 }), createTableCell("下载PDF或HTML格式的报告", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
          new TableRow({ children: [createTableCell("RPT-005", { width: 1400 }), createTableCell("统计概览", { width: 2200 }), createTableCell("展示测试通过率、用例数量等统计数据", { width: 3960 }), createTableCell("中", { width: 1800 })] }),
        ]
      }),
      createHeading3("3.6.3 报告类型"),
      createParagraph("• 测试报告：功能测试的执行结果汇总"),
      createParagraph("• API报告：API测试的性能和正确性分析"),
      createParagraph("• 性能报告：系统性能指标统计"),
      createParagraph("• 系统报告：系统运行状态和错误汇总"),
      new Paragraph({ children: [new PageBreak()] }),

      // 3.7 系统设置模块
      createHeading2("3.7 系统设置模块"),
      createHeading3("3.7.1 功能概述"),
      createParagraph("系统设置模块提供平台的配置管理功能，包括基本设置、LLM配置、数据库设置、安全设置和通知设置。"),
      createHeading3("3.7.2 基本设置"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 6960],
        rows: [
          new TableRow({ children: [createTableCell("配置项", { bold: true, width: 2400, fill: "E8F4FC" }), createTableCell("说明", { bold: true, width: 6960, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("平台名称", { width: 2400 }), createTableCell("系统显示名称，默认'AI Agent测试平台'", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("系统语言", { width: 2400 }), createTableCell("支持简体中文、English、日本語", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("时区", { width: 2400 }), createTableCell("系统时区设置，如Asia/Shanghai", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("主题设置", { width: 2400 }), createTableCell("炫彩科技/海洋微风/暮光暖阳三种主题", { width: 6960 })] }),
        ]
      }),
      createHeading3("3.7.3 LLM配置"),
      createParagraph("支持配置多个LLM提供商，每个配置包含以下信息："),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 6960],
        rows: [
          new TableRow({ children: [createTableCell("配置项", { bold: true, width: 2400, fill: "E8F4FC" }), createTableCell("说明", { bold: true, width: 6960, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("配置名称", { width: 2400 }), createTableCell("用户自定义的配置名称", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("提供商", { width: 2400 }), createTableCell("OpenAI/DeepSeek/智谱AI/Moonshot/通义千问/自定义", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("API Key", { width: 2400 }), createTableCell("LLM服务的API密钥", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Base URL", { width: 2400 }), createTableCell("API服务地址，自定义时可修改", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("模型", { width: 2400 }), createTableCell("使用的模型名称，如gpt-4、deepseek-chat", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Temperature", { width: 2400 }), createTableCell("生成温度，范围0-2，默认0.7", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Max Tokens", { width: 2400 }), createTableCell("最大生成长度，默认4000", { width: 6960 })] }),
        ]
      }),
      createParagraph("LLM配置支持连接测试功能，验证配置的有效性。"),
      createHeading3("3.7.4 数据库设置"),
      createParagraph("配置向量数据库连接参数："),
      createParagraph("• 向量数据库类型：ChromaDB/Pinecone/Weaviate/Qdrant"),
      createParagraph("• 连接参数：主机地址、端口、集合名称"),
      createParagraph("• 向量参数：向量维度、相似度度量方式"),
      createParagraph("• 缓存设置：是否启用缓存、缓存TTL"),
      createHeading3("3.7.5 安全设置"),
      createParagraph("• 会话超时：设置用户会话超时时间"),
      createParagraph("• 密码策略：弱/中/强三种密码复杂度要求"),
      createParagraph("• 登录限制：最大登录尝试次数"),
      createParagraph("• 双因素认证：是否启用2FA"),
      createParagraph("• 注册控制：是否允许用户自主注册"),
      createHeading3("3.7.6 通知设置"),
      createParagraph("配置系统通知方式和触发条件："),
      createParagraph("• 邮件通知：SMTP服务器配置"),
      createParagraph("• 通知类型：测试完成、系统错误、API限流、文档处理、技能运行结果"),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 四、非功能性需求 ==========
      createHeading1("四、非功能性需求"),
      createHeading2("4.1 性能需求"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3000, 6360],
        rows: [
          new TableRow({ children: [createTableCell("指标项", { bold: true, width: 3000, fill: "E8F4FC" }), createTableCell("要求", { bold: true, width: 6360, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("页面加载时间", { width: 3000 }), createTableCell("首屏加载≤3秒，后续页面切换≤1秒", { width: 6360 })] }),
          new TableRow({ children: [createTableCell("API响应时间", { width: 3000 }), createTableCell("普通接口≤500ms，复杂查询≤2秒", { width: 6360 })] }),
          new TableRow({ children: [createTableCell("并发用户数", { width: 3000 }), createTableCell("支持≥100个并发用户同时在线", { width: 6360 })] }),
          new TableRow({ children: [createTableCell("文档上传", { width: 3000 }), createTableCell("支持单文件≤50MB，总上传≤500MB", { width: 6360 })] }),
        ]
      }),
      createHeading2("4.2 安全需求"),
      createParagraph("• 用户密码使用bcrypt加密存储"),
      createParagraph("• API请求需携带有效Token"),
      createParagraph("• 敏感操作需二次确认"),
      createParagraph("• API Key等敏感信息不在日志中明文记录"),
      createParagraph("• 支持HTTPS加密传输"),
      createHeading2("4.3 可用性需求"),
      createParagraph("• 系统可用性≥99.5%"),
      createParagraph("• 支持数据备份和恢复"),
      createParagraph("• 提供友好的错误提示和操作引导"),
      createHeading2("4.4 兼容性需求"),
      createParagraph("• 浏览器：Chrome 90+、Firefox 88+、Safari 14+、Edge 90+"),
      createParagraph("• 分辨率：最小支持1366×768，推荐1920×1080"),
      createParagraph("• 移动端：支持响应式布局"),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 五、技术架构要求 ==========
      createHeading1("五、技术架构要求"),
      createHeading2("5.1 前端技术栈"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 6960],
        rows: [
          new TableRow({ children: [createTableCell("技术", { bold: true, width: 2400, fill: "E8F4FC" }), createTableCell("版本/说明", { bold: true, width: 6960, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("React", { width: 2400 }), createTableCell("18.x，前端框架", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("TypeScript", { width: 2400 }), createTableCell("5.x，类型安全", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Ant Design", { width: 2400 }), createTableCell("5.x，UI组件库", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Redux Toolkit", { width: 2400 }), createTableCell("状态管理", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("React Router", { width: 2400 }), createTableCell("6.x，路由管理", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Vite", { width: 2400 }), createTableCell("构建工具", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Axios", { width: 2400 }), createTableCell("HTTP请求库", { width: 6960 })] }),
        ]
      }),
      createHeading2("5.2 后端技术栈"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 6960],
        rows: [
          new TableRow({ children: [createTableCell("技术", { bold: true, width: 2400, fill: "E8F4FC" }), createTableCell("版本/说明", { bold: true, width: 6960, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("Python", { width: 2400 }), createTableCell("3.9+", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("FastAPI", { width: 2400 }), createTableCell("Web框架", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("SQLAlchemy", { width: 2400 }), createTableCell("ORM框架", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("Pydantic", { width: 2400 }), createTableCell("数据验证", { width: 6960 })] }),
          new TableRow({ children: [createTableCell("SQLite/PostgreSQL", { width: 2400 }), createTableCell("数据库", { width: 6960 })] }),
        ]
      }),
      createHeading2("5.3 API设计规范"),
      createParagraph("• RESTful API设计风格"),
      createParagraph("• 统一的响应格式：{ success, code, message, data }"),
      createParagraph("• API路径：/api/v1/{module}/{resource}"),
      createParagraph("• 版本控制：通过URL路径区分版本"),
      new Paragraph({ children: [new PageBreak()] }),

      // ========== 六、数据库设计 ==========
      createHeading1("六、数据库设计"),
      createHeading2("6.1 核心数据表"),
      createParagraph("技能相关表：", { bold: true }),
      createParagraph("• skills - 技能主表"),
      createParagraph("• skill_parameters - 技能参数表"),
      createParagraph("• skill_usages - 执行记录表"),
      createParagraph("• skill_test_cases - 测试用例表"),
      createParagraph("• skill_templates - 技能模板表"),
      createParagraph("知识管理相关表：", { bold: true }),
      createParagraph("• rag_knowledge_bases_new - RAG知识库表"),
      createParagraph("• rag_documents_new - 文档表"),
      createParagraph("• rag_chunks_new - 文档分块表"),
      createParagraph("• knowledge_graphs - 知识图谱表"),
      createParagraph("• graph_entities - 图谱实体表"),
      createParagraph("• graph_relations - 图谱关系表"),
      createParagraph("系统管理相关表：", { bold: true }),
      createParagraph("• user - 用户表"),
      createParagraph("• llm_configs - LLM配置表"),
      createParagraph("• tests - 测试记录表"),
      createParagraph("• reports - 报告表"),
      createHeading2("6.2 用户表结构（user）"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 2000, 2000, 2960],
        rows: [
          new TableRow({ children: [createTableCell("字段名", { bold: true, width: 2400, fill: "E8F4FC" }), createTableCell("类型", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("约束", { bold: true, width: 2000, fill: "E8F4FC" }), createTableCell("说明", { bold: true, width: 2960, fill: "E8F4FC" })] }),
          new TableRow({ children: [createTableCell("id", { width: 2400 }), createTableCell("Integer", { width: 2000 }), createTableCell("PK", { width: 2000 }), createTableCell("主键", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("username", { width: 2400 }), createTableCell("String(50)", { width: 2000 }), createTableCell("Unique, Not Null", { width: 2000 }), createTableCell("用户名", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("email", { width: 2400 }), createTableCell("String(100)", { width: 2000 }), createTableCell("Unique, Not Null", { width: 2000 }), createTableCell("邮箱", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("hashed_password", { width: 2400 }), createTableCell("String(255)", { width: 2000 }), createTableCell("Not Null", { width: 2000 }), createTableCell("加密密码", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("role", { width: 2400 }), createTableCell("String(20)", { width: 2000 }), createTableCell("Default 'user'", { width: 2000 }), createTableCell("角色", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("is_active", { width: 2400 }), createTableCell("Boolean", { width: 2000 }), createTableCell("Default True", { width: 2000 }), createTableCell("是否激活", { width: 2960 })] }),
          new TableRow({ children: [createTableCell("created_at", { width: 2400 }), createTableCell("DateTime", { width: 2000 }), createTableCell("-", { width: 2000 }), createTableCell("创建时间", { width: 2960 })] }),
        ]
      }),
      new Paragraph({ spacing: { after: 400 } }),
      createParagraph("—— 文档结束 ——", { align: AlignmentType.CENTER }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("AI Agent-V1版本详细需求文档.docx", buffer);
  console.log("需求文档生成成功：AI Agent-V1版本详细需求文档.docx");
});