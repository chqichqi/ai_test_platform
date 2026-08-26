# 站点地图（已根据 MCP 探索结果更新）

## 模块顶层路由
| # | 模块 | 入口 URL hash | 主要 Tab |
|---|---|---|---|
| 1 | 登录页 | `/login` | - |
| 2 | 工作台 | `/workpanel` | - |
| 3 | 患者档案 | `/patientarchieve` | 全部 / 我的患者 |
| 4 | 设备管理 | `/device` | - |
| 5 | 问卷管理 | `/surveymanage` | - |
| 6 | 账号管理 | `/role` | - |
| 7 | 数据管理 | `/internalreport` | 报告查收 |
| 8 | 运营配置 | `/operatorconfiguration` | - |
| 9 | 操作日志 | `/operatorlog` | - |
| 10 | 随访管理 | `/visitpatientmanage` | 已入组 / 已退组 |

## 工作台卡片跳转路由
| 来源 | 目标 URL hash |
|---|---|
| 患者人数 / SMART报告 / 入组人数 | `/patientarchieve` |
| 任一疾病卡片 | `/patientarchieve?exceptionType=<code>` |
| 周报审核 | `/weeklyapproval` |
| 数据审核 / 报告审核 | `/internalreport` (tab) |
| 待发货 / 预约回收 | `/device` (tab) |
| 随访项目个数 | `/visitmanage` |
| 随访进行中 / 待随访 / 随访延期 / 随访中止 | `/visitpatientmanage` (已入组 tab) |
| 房颤预警列表条目 | `/patientarchieve/detail?id=<id>&type=1&sn=<sn>&date=[start,end]` |
| 佩戴预警列表条目 | `/patientarchieve/detail?id=<id>` |
| 测量预警列表条目 | `/patientarchieve/detail?id=<id>`（同佩戴预警，当前无数据未实测） |

## 直接 fragment 跳转限制
- 系统采用路由守卫；**直接 `goto(/#/xxx)` 在某些情况下会被重定向到 `/#/login`**
- 推荐：登录后通过点击左侧导航或卡片进行跳转
