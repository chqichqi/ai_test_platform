"""
需求变更分析服务
用于对比分析新旧需求文档，识别变更并生成处理建议
"""

# 强制打印确认代码已加载 - 19:45版本
print("=" * 60)
print("requirement_change_service.py LOADED - VERSION 19:45")
print("=" * 60)

import json
import re
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.services.llm_service import LLMService
from app.core.models.requirement import TestCase, TestCaseStatus, TestCaseType, TestCasePriority, ExecutionType, TestPoint
from app.core.models.requirement_change import (
    RequirementChangeRecord, RequirementChangeBatch,
    ChangeType, ChangeImpactLevel, ChangeRecordStatus, ChangeAction
)

# 审批后增量探索任务集合：持引用防 GC，done 后 discard
_EXPLORATION_TASKS: set = set()


def _spawn_kg_exploration(version_id: int, module_names: List[str]):
    """审批 commit 后 fire-and-forget 触发知识图谱增量探索（失败不影响审批）。"""
    if not module_names:
        return

    async def _run():
        from app.core.services.kg_incremental_explorer import explore_affected_modules
        try:
            await explore_affected_modules(version_id, module_names)
        except Exception as _e:
            logger.warning(f"[KGIncremental] 增量探索任务异常: {_e}")

    try:
        _task = asyncio.get_running_loop().create_task(_run())
        _EXPLORATION_TASKS.add(_task)
        _task.add_done_callback(_EXPLORATION_TASKS.discard)
        logger.info(f"[KGIncremental] 已触发审批后增量探索：版本{version_id}，"
                    f"模块 {module_names}")
    except Exception as _e:
        logger.warning(f"[KGIncremental] 无法触发增量探索任务: {_e}")


class RequirementChangeAnalyzer:
    """需求变更分析服务"""
    
    CHANGE_ANALYSIS_PROMPT = """你是一个专业的测试用例管理专家，正在分析需求文档的变更。

## 任务说明
请对比以下两个需求文档版本，识别所有的变更点，并分析对测试用例的影响。

## 原需求文档
{original_doc}

## 补充需求文档（新版本）
{supplement_doc}

## 分析要求

### 1. 变更类型分类
请将每个变更归类为以下类型之一：
- **新增功能**：新需求中出现原需求没有的功能模块
- **修改功能**：功能名称相同，但描述/逻辑发生变化（包括功能被删除/废弃）
- **删除功能**：原需求有，新需求明确标注"删除"、"废弃"、"不再支持"
- **无变化**：功能描述完全一致

### 2. 影响级别评估
请评估每个变更的影响级别：
- **高影响**：核心功能变更，需全面重新测试
- **中影响**：部分功能变更，需局部重新测试
- **低影响**：边缘功能变更，可选择性测试

### 3. 处理建议
请为每个变更提供处理建议：
- 新增功能 → generate_new：生成新测试用例
- 修改功能 → update_existing：标记旧用例待更新，生成新用例
- 删除功能 → deprecate：标记旧用例为已废弃
- 无变化 → keep_old：保持不变

### 4. 关键识别点
- 如果新需求中出现"已废弃"、"不再支持"、"删除"、"下线"等关键词，应归类为删除功能
- 如果功能名称相同但描述不同，应归类为修改功能
- 新增的功能模块，即使名称略有不同，也应识别为新增功能

请以JSON格式返回分析结果，格式如下：
```json
{{"change_summary": {{
  "added_modules": ["新功能模块1", "新功能模块2"],
  "modified_modules": ["修改的功能模块1"],
  "deleted_modules": ["被删除的功能模块1"],
  "unchanged_modules": ["无变化的功能模块1"]
}},
"detail_analysis": [
  {{
    "module_name": "登录模块",
    "change_type": "modified",
    "old_description": "原功能描述...",
    "new_description": "新功能描述...",
    "impact_level": "high",
    "suggested_action": "update_existing",
    "suggested_reason": "登录方式从单一变为多种，核心功能变更"
  }},
  {{
    "module_name": "积分系统",
    "change_type": "deleted",
    "old_description": "积分兑换商品功能...",
    "new_description": "已废弃，不再支持",
    "impact_level": "high",
    "suggested_action": "deprecate",
    "suggested_reason": "功能明确标注废弃，相关测试用例应标记为已废弃"
  }}
]
}}
```

只返回JSON，不要包含其他内容。"""

    MODULE_EXTRACTION_PROMPT = """请从以下需求文档中提取所有功能模块名称。

需求文档内容：
{content}

提取规则：
1. 提取所有主要功能模块（通常是 ## 标题或明确的模块名称）
2. 忽略：概述、背景、简介、附录、目录、说明、规则、字典、术语、前言、文档、版本、修订、变更、范围、目的等非功能性章节
3. 模块名称应简洁明了（不超过15个字符）

请以JSON数组格式返回：
```json
["模块1", "模块2", "模块3"]
```

只返回JSON数组，不要包含其他内容。"""

    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    async def analyze_change(
        self,
        version_id: int,
        original_doc: str,
        supplement_doc: str,
        user_id: Optional[int] = None,
        supplement_doc_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        分析需求变更

        supplement_doc_id: 补充文档已保存的RequirementDocument ID
        """
        # 强制打印确认代码已加载
        print("=" * 50)
        print("NEW CODE VERSION - 2024-04-19 19:40")
        print("=" * 50)
        
        logger.info(f"开始分析需求变更，版本ID：{version_id}")

        # ── Phase 1: 结构化 diff（机器驱动，不依赖 LLM）──
        from app.core.services.two_step_generator import extract_features, diff_features
        from app.core.models.requirement import TestPoint
        from app.core.services.version_generator_utils import clean_module_name

        # Step1 提取新旧功能点
        old_features_result = await extract_features(self.llm_service, original_doc) if original_doc else {"features": []}
        new_features_result = await extract_features(self.llm_service, supplement_doc) if supplement_doc else {"features": []}
        old_features = old_features_result.get("features", [])
        new_features = new_features_result.get("features", [])
        logger.info(f"[变更分析] Step1 完成: 旧 {len(old_features)} 个功能点, 新 {len(new_features)} 个功能点")

        # 结构化 key diff
        diff = diff_features(old_features, new_features)
        logger.info(f"[变更分析] 结构化 diff: +{len(diff['added'])} 新增, -{len(diff['removed'])} 删除, ={len(diff['unchanged'])} 不变")

        # 查询 DB 中已有的 TestPoint（关联到 TestCase）
        old_test_points = self.db.query(TestPoint).filter(
            TestPoint.version_id == version_id
        ).all()
        tp_by_key = {tp.feature_key: tp for tp in old_test_points if tp.feature_key}
        # 兜底索引：按 name + category 匹配（兼容旧 TestPoint 用 _source_feature 作 key 的情况）
        tp_by_name = {}
        for tp in old_test_points:
            _nm = (tp.name or '').strip()
            _cat = (tp.category or '').strip()
            if _nm and _cat:
                tp_by_name[(_nm, _cat)] = tp
            elif _nm:
                tp_by_name[(_nm, '')] = tp

        # ── Phase 2: 影响分析（基于 TestPoint 关系）──
        detail_analysis = []
        affected_case_ids = set()

        # 新增功能 → 生成新用例
        for f in diff["added"]:
            detail_analysis.append({
                "module_name": f.get("name", ""), "change_type": "added",
                "old_description": "", "new_description": f.get("detail", ""),
                "impact_level": "medium", "suggested_action": "generate_new",
                "affected_test_cases": [],
            })

        # 删除功能 → 标记旧用例 DEPRECATED（方案B：影响范围按【逻辑用例 id】）
        for f in diff["removed"]:
            tp = tp_by_key.get(f.get("key", ""))
            if not tp:  # 兜底：按 name + category 匹配
                tp = tp_by_name.get((f.get("name", ""), f.get("category", ""))) or tp_by_name.get((f.get("name", ""), ''))
            affected = []
            if tp and tp.test_case_id:
                _row = self.db.query(TestCase).filter(TestCase.id == int(tp.test_case_id)).first()
                if _row:
                    _lid = self._logical_id_of(_row)
                    affected.append(_lid)
                    affected_case_ids.add(_lid)
            if not affected:
                # 兜底：TestPoint 缺失/未绑定 → 模块名模糊匹配
                affected = self._find_impacted_logical_cases(version_id, f.get("name", ""))
                affected_case_ids.update(affected)
            detail_analysis.append({
                "module_name": f.get("name", ""), "change_type": "deleted",
                "old_description": f.get("detail", ""), "new_description": "",
                "impact_level": "high", "suggested_action": "deprecate",
                "affected_test_cases": affected,
            })

        # 不变功能 → 保留
        for pair in diff.get("unchanged", []):
            old_f = pair["old"]
            tp = tp_by_key.get(old_f.get("key", ""))
            if not tp:
                tp = tp_by_name.get((old_f.get("name", ""), old_f.get("category", ""))) or tp_by_name.get((old_f.get("name", ""), ''))
            affected = []
            if tp and tp.test_case_id:
                affected.append(tp.test_case_id)
            detail_analysis.append({
                "module_name": pair["new"].get("name", ""), "change_type": "unchanged",
                "old_description": pair["old"].get("detail", ""),
                "new_description": pair["new"].get("detail", ""),
                "impact_level": "low", "suggested_action": "keep_old",
                "affected_test_cases": affected,
            })

        # ── Phase 3: LLM 仅用于语义理解（匹配 key 不同但语义相同的功能点）──
        if diff["removed"] and diff["added"]:
            # 有删除也有新增 → LLM 判断是否语义相同
            try:
                semantic_matches = await self._llm_semantic_match_features(diff["removed"], diff["added"])
                for match in semantic_matches:
                    old_f = match.get("old")
                    new_f = match.get("new")
                    if old_f and new_f:
                        tp = tp_by_key.get(old_f.get("key", ""))
                        if not tp:
                            tp = tp_by_name.get((old_f.get("name", ""), old_f.get("category", ""))) or tp_by_name.get((old_f.get("name", ""), ''))
                        affected = []
                        if tp and tp.test_case_id:
                            _row = self.db.query(TestCase).filter(TestCase.id == int(tp.test_case_id)).first()
                            if _row:
                                _lid = self._logical_id_of(_row)
                                affected.append(_lid)
                                affected_case_ids.add(_lid)
                        if not affected:
                            # 兜底：TestPoint 缺失/未绑定 → 模块名模糊匹配
                            affected = self._find_impacted_logical_cases(version_id, old_f.get("name", ""))
                            affected_case_ids.update(affected)
                        # 修正：原"删除"改为"修改"
                        for item in detail_analysis:
                            if item.get("module_name") == old_f.get("name", "") and item["change_type"] == "deleted":
                                item["change_type"] = "modified"
                                item["new_description"] = new_f.get("detail", "")
                                item["suggested_action"] = "update_existing"
                                item["impact_level"] = "medium"
                                item["affected_test_cases"] = affected
                                break
                        # 移除对应新增项
                        detail_analysis = [d for d in detail_analysis
                                          if not (d["change_type"] == "added" and d["module_name"] == new_f.get("name", ""))]
                logger.info(f"[变更分析] LLM 语义匹配: {len(semantic_matches)} 对")
            except Exception as e:
                logger.warning(f"[变更分析] LLM 语义匹配失败: {e}")

        # ── Phase 4: 汇总 ──
        added_modules = [d["module_name"] for d in detail_analysis if d["change_type"] == "added"]
        modified_modules = [d["module_name"] for d in detail_analysis if d["change_type"] == "modified"]
        removed_modules = [d["module_name"] for d in detail_analysis if d["change_type"] == "deleted"]
        change_summary = {
            "added_count": len(diff["added"]),
            "modified_count": len(modified_modules),
            "deleted_count": len(removed_modules),
            "unchanged_count": len(diff["unchanged"]),
            "added_modules": added_modules,
            "modified_modules": modified_modules,
            "removed_modules": removed_modules,
        }
        total_affected = len(affected_case_ids)
        logger.info(f"[变更分析] 完成: {change_summary}, 影响 {total_affected} 条用例")

        logger.info(f"[变更分析] 汇总: {change_summary}")

        # 5. 创建变更批次记录
        batch = self._create_change_batch(
            version_id=version_id,
            original_doc=original_doc,
            supplement_doc=supplement_doc,
            change_summary=change_summary,
            user_id=user_id
        )

        # 6. 创建变更记录（每个受影响的功能点一条记录）
        change_records = self._create_change_records(
            batch_id=batch.id,
            version_id=version_id,
            detail_analysis=detail_analysis,
            user_id=user_id
        )

        # 7. 汇总
        total_affected_cases = len(affected_case_ids)
        total_related_cases = sum(len(item.get("affected_test_cases", [])) for item in detail_analysis)
        estimated_new_cases = change_summary.get("added_count", 0) + change_summary.get("modified_count", 0)

        if change_summary["added_count"] + change_summary["modified_count"] + change_summary["deleted_count"] == 0:
            message = f"需求文档无变化, {change_summary['unchanged_count']} 个功能模块保持不变"
        else:
            message = f"分析完成：{change_summary['added_count']}个新增, {change_summary['modified_count']}个修改, {change_summary['deleted_count']}个删除, {total_affected_cases}条用例受影响"

        return {
            "success": True,
            "batch_id": batch.id,
            "change_summary": change_summary,
            "detail_analysis": detail_analysis,
            "change_records": [
                {
                    "id": record.id,
                    "module_name": record.module_name,
                    "change_type": record.change_type,
                    "status": record.status
                }
                for record in change_records
            ],
            "total_affected_cases": total_affected_cases,
            "total_related_cases": total_related_cases,
            "estimated_new_cases": estimated_new_cases,
            "message": message
        }
    
    async def _extract_modules(self, doc_content: str) -> List[str]:
        """提取文档中的模块名称"""
        if not doc_content:
            return []
        
        # 首先尝试正则提取
        regex_modules = self._extract_modules_regex(doc_content)
        
        # 获取LLM配置的max_tokens
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        # 模块提取需要较小输出空间，取配置值的10%作为上限
        extraction_max_tokens = min(int(config_max_tokens * 0.1), 2000)
        
        # 如果提取结果太少，调用LLM辅助
        if len(regex_modules) < 3 and len(doc_content) > 500:
            truncated_content = self._truncate_document(doc_content, 5000)
            llm_result = await self.llm_service.async_call_llm(
                prompt=self.MODULE_EXTRACTION_PROMPT.format(content=truncated_content),
                temperature=0.3,
                max_tokens=extraction_max_tokens
            )
            
            if llm_result:
                try:
                    json_match = re.search(r'\[.*?\]', llm_result, re.DOTALL)
                    if json_match:
                        modules = json.loads(json_match.group())
                        if isinstance(modules, list):
                            logger.info(f"LLM提取模块：{modules}")
                            return modules
                except json.JSONDecodeError:
                    pass
        
        logger.info(f"正则提取模块：{regex_modules}")
        return regex_modules
    
    def _extract_modules_regex(self, content: str) -> List[str]:
        """使用正则表达式提取模块"""
        modules = []
        seen = set()
        
        # ## 标题匹配
        pattern1 = r'##\s+([^\n#]{2,20})'
        for match in re.finditer(pattern1, content):
            module_name = match.group(1).strip()
            if self._is_valid_module(module_name) and module_name not in seen:
                seen.add(module_name)
                modules.append(module_name)
        
        # 数字编号匹配（如：一、登录模块）
        pattern2 = r'[一二三四五六七八九十\d]+[、.．]\s*([^\n]{2,15})(模块|功能|管理|配置|设置|系统)'
        for match in re.finditer(pattern2, content):
            module_name = match.group(1).strip() + match.group(2).strip()
            if self._is_valid_module(module_name) and module_name not in seen:
                seen.add(module_name)
                modules.append(module_name)
        
        return modules[:30]  # 限制数量
    
    def _is_valid_module(self, module_name: str) -> bool:
        """检查是否是有效的模块名称"""
        ignore_keywords = [
            '概述', '背景', '简介', '附录', '目录', '说明', '规则', '字典',
            '术语', '前言', '文档', '版本', '修订', '变更', '范围', '目的',
            '测试', '用例', '需求', '分析', '设计', '开发', '部署'
        ]
        
        module_lower = module_name.lower()
        for keyword in ignore_keywords:
            if keyword in module_lower:
                return False
        
        return True
    
    def _truncate_document(self, content: str, max_length: int) -> str:
        """截断文档内容"""
        if len(content) <= max_length:
            return content
        
        # 尝试保留关键部分（模块标题和前几行描述）
        lines = content.split('\n')
        result_lines = []
        current_length = 0
        
        for line in lines:
            if current_length + len(line) + 1 > max_length:
                break
            
            # 保留标题行和重要描述
            if line.strip().startswith('#') or len(line.strip()) > 20:
                result_lines.append(line)
                current_length += len(line) + 1
        
        return '\n'.join(result_lines)[:max_length]
    
    def _parse_analysis_result(self, llm_response: Optional[str]) -> Optional[Dict]:
        """解析LLM分析结果"""
        if not llm_response:
            return None
        
        try:
            # 清理响应内容
            cleaned_response = llm_response.strip()
            
            # 移除可能的markdown代码块标记
            if '```json' in cleaned_response:
                cleaned_response = cleaned_response.split('```json')[1]
                if '```' in cleaned_response:
                    cleaned_response = cleaned_response.split('```')[0]
            elif '```' in cleaned_response:
                parts = cleaned_response.split('```')
                if len(parts) >= 2:
                    cleaned_response = parts[1]
            
            cleaned_response = cleaned_response.strip()
            
            # 方法1：尝试直接解析
            try:
                result = json.loads(cleaned_response)
                if isinstance(result, dict):
                    return self._normalize_result(result)
                else:
                    logger.warning(f"JSON解析结果不是字典类型: {type(result)}")
            except json.JSONDecodeError:
                pass
            
            # 方法2：添加缺失的开头{
            if cleaned_response.startswith('"change_summary"') or cleaned_response.startswith('"detail_analysis"'):
                test_json = '{' + cleaned_response
                # 计算需要添加多少个}
                open_braces = test_json.count('{')
                close_braces = test_json.count('}')
                needed_braces = open_braces - close_braces
                if needed_braces > 0:
                    test_json = test_json + '}' * needed_braces
                
                try:
                    result = json.loads(test_json)
                    if isinstance(result, dict):
                        return self._normalize_result(result)
                except json.JSONDecodeError:
                    pass
            
            # 方法3：使用正则提取完整JSON
            json_match = re.search(r'\{[\s\S]*\}', cleaned_response)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    if isinstance(result, dict):
                        return self._normalize_result(result)
                except json.JSONDecodeError:
                    pass
            
            # 方法4：尝试构建最小有效JSON
            if 'change_summary' in cleaned_response:
                try:
                    # 提取change_summary部分
                    summary_match = re.search(r'"change_summary"\s*:\s*\{[^}]*\}', cleaned_response)
                    if summary_match:
                        summary_json = summary_match.group()
                        result = json.loads('{' + summary_json + '}')
                        if isinstance(result, dict):
                            return self._normalize_result(result)
                except json.JSONDecodeError:
                    pass
            
            logger.error(f"无法从响应中提取有效JSON")
            logger.debug(f"原始响应：{cleaned_response[:300]}")
            return None
            
        except Exception as e:
            logger.error(f"解析过程发生异常：{e}")
            logger.debug(f"原始响应：{llm_response[:300] if llm_response else 'None'}")
            return None
    
    def _normalize_result(self, result: Dict) -> Dict:
        """规范化分析结果"""
        # 确保result是字典类型
        if not isinstance(result, dict):
            logger.error(f"_normalize_result收到非字典类型: {type(result)}")
            return {
                "change_summary": {
                    "added_modules": [],
                    "modified_modules": [],
                    "deleted_modules": [],
                    "unchanged_modules": [],
                    "added_count": 0,
                    "modified_count": 0,
                    "deleted_count": 0,
                    "unchanged_count": 0
                },
                "detail_analysis": []
            }
        
        # 验证并补充统计信息
        summary = result.get("change_summary", {})
        if not summary:
            summary = {
                "added_modules": [],
                "modified_modules": [],
                "deleted_modules": [],
                "unchanged_modules": []
            }
        
        summary["added_count"] = len(summary.get("added_modules", []))
        summary["modified_count"] = len(summary.get("modified_modules", []))
        summary["deleted_count"] = len(summary.get("deleted_modules", []))
        summary["unchanged_count"] = len(summary.get("unchanged_modules", []))
        # 键名统一：analyze_change 产出 removed_modules；兼容 LLM 返回的 deleted_modules
        summary["removed_modules"] = summary.get("removed_modules", summary.get("deleted_modules", []))
        
        result["change_summary"] = summary
        
        # 确保detail_analysis存在
        if "detail_analysis" not in result:
            result["detail_analysis"] = []
        
        return result
    
    def _fallback_analysis(
        self,
        original_modules: List[str],
        supplement_modules: List[str]
    ) -> Dict:
        """备选方案：基于模块列表进行简单对比"""
        original_set = set(original_modules)
        supplement_set = set(supplement_modules)
        
        added_modules = list(supplement_set - original_set)
        deleted_modules = list(original_set - supplement_set)
        unchanged_modules = list(original_set & supplement_set)
        
        detail_analysis = []
        
        for module in added_modules:
            detail_analysis.append({
                "module_name": module,
                "change_type": ChangeType.ADDED.value,
                "old_description": None,
                "new_description": "新增功能",
                "impact_level": ChangeImpactLevel.MEDIUM.value,
                "suggested_action": ChangeAction.GENERATE_NEW.value,
                "suggested_reason": "新需求中出现的新功能模块"
            })
        
        for module in deleted_modules:
            detail_analysis.append({
                "module_name": module,
                "change_type": ChangeType.DELETED.value,
                "old_description": "原有功能",
                "new_description": "需求中已移除",
                "impact_level": ChangeImpactLevel.HIGH.value,
                "suggested_action": ChangeAction.DEPRECATE.value,
                "suggested_reason": "功能已从需求中移除"
            })
        
        for module in unchanged_modules:
            detail_analysis.append({
                "module_name": module,
                "change_type": ChangeType.UNCHANGED.value,
                "old_description": "原有功能",
                "new_description": "功能描述无变化",
                "impact_level": ChangeImpactLevel.LOW.value,
                "suggested_action": ChangeAction.KEEP_OLD.value,
                "suggested_reason": "功能无变化，保持原有测试用例"
            })
        
        return {
            "change_summary": {
                "added_modules": added_modules,
                "modified_modules": [],
                "deleted_modules": deleted_modules,
                "removed_modules": deleted_modules,
                "unchanged_modules": unchanged_modules,
                "added_count": len(added_modules),
                "modified_count": 0,
                "deleted_count": len(deleted_modules),
                "unchanged_count": len(unchanged_modules)
            },
            "detail_analysis": detail_analysis
        }
    
    async def _llm_semantic_match_features(self, removed: list, added: list) -> list:
        """LLM 语义匹配：判断删除和新增的功能点是否实际是同一功能的修改。"""
        if not removed or not added:
            return []

        llm_config = self.llm_service.get_active_config()
        if not llm_config:
            return []

        removed_lines = [f"  [{i+1}] [{f.get('category','')}] {f.get('name','')}: {f.get('detail','')[:60]}"
                        for i, f in enumerate(removed)]
        added_lines = [f"  [{i+1}] [{f.get('category','')}] {f.get('name','')}: {f.get('detail','')[:60]}"
                      for i, f in enumerate(added)]

        prompt = f"""你是需求变更分析专家。判断以下"删除"和"新增"的功能点中，哪些实际是**同一功能的修改**（名称变化但测试同一功能）。

删除的功能点:
{chr(10).join(removed_lines) if removed_lines else '(无)'}

新增的功能点:
{chr(10).join(added_lines) if added_lines else '(无)'}

判断标准: 两个功能点覆盖相同的 UI 操作或业务规则 → 同一功能的修改。
输出 JSON: [{{"old": 1, "new": 3}}, {{"old": 2, "new": 5}}]  (数字是上面列表的编号)
无匹配: []
直接输出 JSON, 不要 markdown。"""

        try:
            response = await self.llm_service.async_call_llm(
                prompt=prompt, temperature=0, max_tokens=self.llm_service.get_scaled_max_tokens(0.05, 2000), json_mode=False,
            )
            if not response:
                return []
            import json as _json
            json_match = re.search(r'\[.*?\]', response.strip(), re.DOTALL)
            if not json_match:
                return []
            pairs = _json.loads(json_match.group(0))
            result = []
            for pair in pairs:
                old_idx = pair.get('old', 0) - 1
                new_idx = pair.get('new', 0) - 1
                if 0 <= old_idx < len(removed) and 0 <= new_idx < len(added):
                    result.append({"old": removed[old_idx], "new": added[new_idx]})
            return result
        except Exception as e:
            logger.warning(f"LLM 语义匹配失败: {e}")
            return []

    @staticmethod
    def _logical_id_of(row) -> int:
        """物理行 → 逻辑用例 id（方案B：影响范围按逻辑维度，派生后不换键）"""
        return row.logical_case_id or row.id

    def _find_impacted_logical_cases(self, version_id: int, module_name: str) -> List[int]:
        """查找受影响模块的【逻辑用例】id 列表（方案B，模块名模糊兜底）。

        主路径是 analyze_change 的 per-feature TestPoint 精确匹配（affected_test_cases 存逻辑 id）；
        本方法覆盖 TestPoint 缺失/模块改名场景：该版本项目下 module 模糊匹配的非冻结用例
        （含用例名称兜底），映射到逻辑 id（派生后同一逻辑 id 去重不重复影响）。
        """
        from app.core.models.project import Version
        version = self.db.query(Version).filter(Version.id == version_id).first()
        if not version:
            return []

        from app.core.services.version_generator_utils import clean_module_name
        clean_name = clean_module_name(module_name)

        seen = set()
        result = []

        def _add(row):
            _lid = self._logical_id_of(row)
            if _lid not in seen:
                seen.add(_lid)
                result.append(_lid)

        base_q = self.db.query(TestCase).filter(
            TestCase.project_id == version.project_id,
            or_(TestCase.status.is_(None), ~TestCase.status.in_(("deprecated", "archived"))),
        )
        if clean_name:
            # 模块名模糊匹配
            rows = base_q.filter(TestCase.module.ilike(f"%{clean_name}%")).all()
            for row in rows:
                _add(row)
            # 用例名称兜底（模块全改名仍命中）
            if not result:
                rows = base_q.filter(TestCase.name.ilike(f"%{clean_name}%")).limit(20).all()
                for row in rows:
                    _add(row)
        else:
            for row in base_q.all():
                _add(row)

        logger.info(f"模块 '{module_name}' 模糊兜底找到 {len(result)} 个受影响逻辑用例")
        return result

    def _create_change_batch(
        self,
        version_id: int,
        original_doc: str,
        supplement_doc: str,
        change_summary: Dict,
        user_id: Optional[int] = None
    ) -> RequirementChangeBatch:
        """创建变更批次记录"""
        added_count = change_summary.get("added_count", 0)
        modified_count = change_summary.get("modified_count", 0)
        deleted_count = change_summary.get("deleted_count", 0)
        
        # 如果没有实际变更，批次状态为已完成，否则为待审核
        has_changes = added_count + modified_count + deleted_count > 0
        batch_status = ChangeRecordStatus.COMPLETED.value if not has_changes else ChangeRecordStatus.PENDING.value
        
        batch = RequirementChangeBatch(
            version_id=version_id,
            original_requirement_doc=original_doc[:5000] if original_doc else None,
            supplement_requirement_doc=supplement_doc[:5000] if supplement_doc else None,
            change_summary=change_summary,
            added_count=added_count,
            modified_count=modified_count,
            deleted_count=deleted_count,
            unchanged_count=change_summary.get("unchanged_count", 0),
            status=batch_status,
            created_by=user_id,
            completed_at=datetime.utcnow() if not has_changes else None
        )
        
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        
        logger.info(f"创建变更批次：ID={batch.id}, 状态={batch_status} (有变更: {has_changes})")
        return batch
    
    def _create_change_records(
        self,
        batch_id: int,
        version_id: int,
        detail_analysis: List[Dict],
        user_id: Optional[int] = None
    ) -> List[RequirementChangeRecord]:
        """创建变更记录 - 只为有实际变更的模块创建记录（added/modified/deleted），跳过unchanged"""
        records = []
        
        for item in detail_analysis:
            change_type = item.get("change_type", ChangeType.UNCHANGED.value)
            
            # 跳过"无变化"的模块，不需要审核
            if change_type == ChangeType.UNCHANGED.value:
                logger.info(f"跳过无变化模块: {item.get('module_name', '未知模块')}")
                continue
            
            record = RequirementChangeRecord(
                version_id=version_id,
                change_type=change_type,
                module_name=item.get("module_name", "未知模块"),
                old_description=item.get("old_description"),
                new_description=item.get("new_description"),
                impact_level=item.get("impact_level", ChangeImpactLevel.MEDIUM.value),
                affected_test_cases=item.get("affected_test_cases", []),
                affected_test_cases_count=len(item.get("affected_test_cases", [])),
                suggested_action=item.get("suggested_action", ChangeAction.KEEP_OLD.value),
                suggested_reason=item.get("suggested_reason", ""),
                status=ChangeRecordStatus.PENDING.value,
                created_by=user_id
            )
            
            self.db.add(record)
            records.append(record)
        
        self.db.commit()
        
        for record in records:
            self.db.refresh(record)
        
        logger.info(f"创建变更记录：{len(records)}条（跳过了{len(detail_analysis) - len(records)}条无变化模块）")
        return records
    
    def _estimate_new_cases(self, parsed_result: Dict) -> int:
        """预估新生成的测试用例数量"""
        added_count = parsed_result.get("change_summary", {}).get("added_count", 0)
        modified_count = parsed_result.get("change_summary", {}).get("modified_count", 0)
        
        # 每个新增模块预计8个用例，每个修改模块预计4个新用例
        return added_count * 8 + modified_count * 4
    
    async def process_approved_change(
        self,
        change_record_id: int,
        action: str,
        keep_old_cases: bool = False,
        reviewer_id: Optional[int] = None,
        review_comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理已批准的变更
        
        Args:
            change_record_id: 变更记录ID
            action: 处理动作
            keep_old_cases: 是否保留旧测试用例
            reviewer_id: 审核人ID
            review_comment: 审核意见
        
        Returns:
            处理结果
        """
        record = self.db.query(RequirementChangeRecord).filter(
            RequirementChangeRecord.id == change_record_id
        ).first()
        
        if not record:
            return {"success": False, "message": "变更记录不存在"}
        
        if record.status != ChangeRecordStatus.PENDING.value:
            return {"success": False, "message": f"变更记录状态为{record.status}，无法处理"}
        
        # 更新审核信息
        record.reviewed_by = reviewer_id
        record.reviewed_at = datetime.utcnow()
        record.review_comment = review_comment
        
        result = {"success": True, "action_taken": action}
        
        try:
            if action == ChangeAction.GENERATE_NEW.value:
                # 生成新测试用例
                new_cases = await self._generate_new_test_cases(record)
                record.new_test_cases = new_cases
                record.new_test_cases_count = len(new_cases)
                result["new_test_cases_count"] = len(new_cases)
                
            elif action == ChangeAction.UPDATE_EXISTING.value:
                # 变更即派生（方案B）：旧行归档冻结 + 新修订 draft + AI 重写 + 旧 WUI 软删
                # （keep_old_cases 已废弃——派生行从不继承旧状态，无「保留」语义）
                derive = await self._derive_cases_for_change(record)
                record.new_test_cases = derive.get("new_test_case_ids", [])
                record.new_test_cases_count = derive.get("new_test_cases_count", 0)
                result["new_test_cases_count"] = derive.get("new_test_cases_count", 0)
                result["derived_count"] = derive.get("derived_count", 0)
                result["ui_soft_deleted"] = derive.get("ui_soft_deleted", 0)
                result["rewritten"] = derive.get("rewritten", 0)

            elif action == ChangeAction.DEPRECATE.value:
                # 功能删除：全部修订按逻辑 id 标记废弃 + 级联移除 UI 用例和执行中心条目
                self._mark_cases_deprecated(record.affected_test_cases)
                result["deprecated_count"] = record.affected_test_cases_count
                cascade = self._remove_affected_ui_and_scene(record.affected_test_cases)
                result.update(cascade)

            elif action == ChangeAction.ARCHIVE.value:
                # 归档现有测试用例（冻结保留，不删 UI）
                self._mark_cases_archived(record.affected_test_cases)
                result["archived_count"] = record.affected_test_cases_count
                
            elif action == ChangeAction.KEEP_OLD.value:
                # 保持不变
                result["unchanged_count"] = record.affected_test_cases_count
            
            # 更新记录状态
            record.action_taken = action
            record.keep_old_cases = keep_old_cases
            record.status = ChangeRecordStatus.COMPLETED.value
            record.processed_by = reviewer_id
            record.processed_at = datetime.utcnow()
            
            self.db.commit()

            # 变更已提交：后台增量探索受影响模块（知识图谱项目级实时更新）
            if (record.change_type in ('added', 'modified') and
                    action in (ChangeAction.GENERATE_NEW.value, ChangeAction.UPDATE_EXISTING.value)):
                _spawn_kg_exploration(record.version_id, [record.module_name])

            logger.info(f"变更记录{change_record_id}处理完成，动作：{action}")
            
        except Exception as e:
            logger.error(f"处理变更记录失败：{e}")
            record.status = ChangeRecordStatus.FAILED.value
            record.error_message = str(e)
            self.db.commit()
            
            return {"success": False, "message": f"处理失败：{str(e)}"}
        
        return result
    
    async def _generate_new_test_cases(self, record: RequirementChangeRecord) -> List[int]:
        """为变更记录生成新的测试用例
        
        Args:
            record: 变更记录
            
        Returns:
            新生成的测试用例ID列表
        """
        from app.core.models.project import Version, Project
        
        # 获取版本信息
        version = self.db.query(Version).filter(Version.id == record.version_id).first()
        if not version:
            logger.error(f"版本不存在：{record.version_id}")
            return []
        
        # 获取项目信息
        project = self.db.query(Project).filter(Project.id == version.project_id).first()
        if not project:
            logger.error(f"项目不存在：{version.project_id}")
            return []
        
        # 构建生成提示词
        module_desc = record.new_description or record.old_description or ""
        
        if not module_desc:
            logger.warning(f"模块 {record.module_name} 没有描述信息，无法生成测试用例")
            return []
        
        generate_prompt = self._build_generate_prompt(
            module_name=record.module_name,
            module_description=module_desc,
            project_name=project.name,
            version_number=version.version_number
        )
        
        logger.info(f"为模块 {record.module_name} 调用LLM生成测试用例...")
        
        # 获取LLM配置的max_tokens
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        # 测试用例生成需要较大输出空间，取配置值的30%作为上限
        generation_max_tokens = min(int(config_max_tokens * 0.3), 8000)
        logger.info(f"测试用例生成max_tokens: 配置值{config_max_tokens}, 实际使用{generation_max_tokens}")
        
        try:
            llm_response = await self.llm_service.async_call_llm(
                prompt=generate_prompt,
                system_prompt="你是一位专业的测试用例生成专家，请根据模块描述生成详细的测试用例。",
                temperature=0.3,
                max_tokens=generation_max_tokens
            )
            
            if not llm_response:
                logger.error(f"LLM调用失败，返回为空")
                return []
            
            # 解析LLM响应
            test_cases_data = self._parse_test_cases_response(llm_response)
            
            if not test_cases_data:
                logger.warning(f"LLM响应解析失败，无法提取测试用例")
                return []
            
            # 保存测试用例到数据库
            new_case_ids = await self._save_generated_test_cases(
                test_cases_data=test_cases_data,
                project_id=project.id,
                version_id=version.id,
                module_name=record.module_name,
                generated_by="ai_change"
            )
            
            logger.info(f"为模块 {record.module_name} 成功生成 {len(new_case_ids)} 个测试用例")
            
            return new_case_ids
            
        except Exception as e:
            logger.error(f"生成测试用例失败：{str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _build_generate_prompt(
        self,
        module_name: str,
        module_description: str,
        project_name: str,
        version_number: str
    ) -> str:
        """构建测试用例生成提示词"""
        json_example = '''
{
  "test_cases": [
    {
      "title": "用例标题",
      "description": "用例描述",
      "preconditions": "前置条件",
      "test_steps": [
        {"step_no": 1, "action": "点击「新增」按钮，在「患者姓名」输入框中填写\"张三\"", "expected_result": "页面显示新增成功"}
      ],
      "priority": "P1",
      "test_type": "positive"
    }
  ]
}
'''
        
        return f"""# 项目信息
- 项目名称：{project_name}
- 版本号：{version_number}
- 模块名称：{module_name}

# 模块功能描述
{module_description}

# 任务要求
请根据上述模块功能描述，生成详细的测试用例。

## 用例要求
1. 每个测试用例需包含完整的测试步骤和预期结果
2. 覆盖正常场景、异常场景、边界场景
3. 标注优先级：P0（核心）、P1（重要）、P2（一般）、P3（次要）
4. 每个模块生成 3-8 个测试用例

## UI 元素命名约定（关键！影响后续自动化转化）
test_steps 中的 action 必须遵循以下约定，以便后续自动化工具能精确识别页面元素：
1. 用「」标记真正的 UI 元素名（描述词如"卡片""按钮"放在「」外面）：点击「新增」按钮
2. 用""标记操作值：在「患者姓名」输入框中填写"张三"
3. 纯验证步骤用"验证："开头，不需要「」标记：验证：页面显示所有当天预警

## 输出格式
请以JSON格式输出，格式如下：
```json
{json_example}
```

请开始生成测试用例，只返回JSON，不要包含其他内容。"""
    
    def _parse_test_cases_response(self, llm_response: str) -> Optional[List[Dict]]:
        """解析LLM返回的测试用例数据"""
        import re
        import json
        
        try:
            # 提取JSON代码块
            pattern = r'```json\s*(.*?)\s*```'
            match = re.search(pattern, llm_response, re.DOTALL | re.IGNORECASE)
            
            if match:
                json_str = match.group(1)
            else:
                # 尝试提取花括号包围的内容
                pattern = r'\{.*\}'
                match = re.search(pattern, llm_response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                else:
                    return None
            
            # 解析JSON
            data = json.loads(json_str.strip())
            
            if isinstance(data, dict) and "test_cases" in data:
                return data.get("test_cases", [])
            elif isinstance(data, list):
                return data
            
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败：{e}")
            
            # 尝试修复并重新解析
            try:
                fixed_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                data = json.loads(fixed_str)
                
                if isinstance(data, dict) and "test_cases" in data:
                    return data.get("test_cases", [])
                elif isinstance(data, list):
                    return data
                
            except Exception:
                pass
            
            return None
    
    async def _save_generated_test_cases(
        self,
        test_cases_data: List[Dict],
        project_id: int,
        version_id: int,
        module_name: str,
        generated_by: str = "ai_change"
    ) -> List[int]:
        """保存生成的测试用例到数据库
        
        Args:
            test_cases_data: 测试用例数据列表
            project_id: 项目ID
            version_id: 版本ID
            module_name: 模块名称
            generated_by: 生成方式
            
        Returns:
            新生成的测试用例ID列表
        """
        new_case_ids = []
        
        for tc_data in test_cases_data:
            try:
                # 构建测试步骤JSON
                test_steps = tc_data.get("test_steps", [])
                if isinstance(test_steps, list):
                    test_steps_json = test_steps
                elif isinstance(test_steps, str):
                    test_steps_json = [{"step_no": 1, "action": test_steps, "expected_result": ""}]
                else:
                    test_steps_json = []
                
                # 创建测试用例
                test_case = TestCase(
                    project_id=project_id,
                    version_id=version_id,
                    module=module_name,
                    name=tc_data.get("title", f"{module_name}-测试用例"),
                    description=tc_data.get("description", ""),
                    preconditions=tc_data.get("preconditions", ""),
                    test_steps=test_steps_json,
                    expected_result=tc_data.get("expected_result", ""),
                    priority=tc_data.get("priority", "P2"),
                    case_type=TestCaseType.FUNCTIONAL.value,
                    execution_type=ExecutionType.MANUAL.value,
                    status=TestCaseStatus.DRAFT.value,
                    generated_by=generated_by,
                    tags=[module_name, generated_by]
                )
                
                self.db.add(test_case)
                self.db.flush()

                # 方案B：新建用例逻辑=物理（logical_case_id=自身id）
                test_case.logical_case_id = test_case.id

                # 补建 TestPoint（变更影响范围按 TestPoint 匹配，缺失则新模块用例不可见）
                _title = tc_data.get("title", f"{module_name}-测试用例")
                _tp = TestPoint(
                    version_id=version_id,
                    feature_key=tc_data.get("key") or re.sub(r"\s+", "", _title)[:200],
                    name=_title,
                    category=(tc_data.get("category") or "")[:50],
                    detail=tc_data.get("description"),
                    status="active",
                    test_case_id=test_case.id,
                )
                self.db.add(_tp)

                new_case_ids.append(test_case.id)
                
            except Exception as e:
                logger.error(f"保存测试用例失败：{e}")
                continue
        
        self.db.commit()
        
        return new_case_ids
    
    async def _derive_cases_for_change(self, record: RequirementChangeRecord) -> Dict[str, Any]:
        """变更即派生（方案B）：受影响逻辑用例派生新修订，旧行冻结归档。

        对每个受影响逻辑用例（record.affected_test_cases = 逻辑 id 列表）：
        1. 生效行 → status=archived（冻结；不删除，执行记录/历史引用不破坏）
        2. 新行：logical_case_id=同逻辑 id、revision_no=next、derived_from_id=旧行 id、
           version_id=record.version_id、status=draft（从不继承旧状态）、内容=旧行副本
        3. AI 按新需求重写新行内容（失败 → 保留副本，draft 供人工修改后审核）
        4. 旧 WUI 软删（is_deleted=1，从 UI 用例列表隐藏；执行中心条目保留，执行时重解析）
        5. TestPoint.test_case_id 改绑新行

        Returns:
            {"derived_count": n, "ui_soft_deleted": m, "rewritten": k}
        """
        from app.core.models.project import Version
        from app.core.models.web_ui_test import WebUITestCase as WebUI
        from app.core.models.requirement import TestPoint
        from app.core.services.case_versioning import resolve_case_by_logical_id, next_revision_no

        affected_logical_ids = list(dict.fromkeys(record.affected_test_cases or []))
        # 兜底：记录中无受影响用例 → 模块名模糊匹配（TestPoint 缺失场景）
        if not affected_logical_ids:
            affected_logical_ids = self._find_impacted_logical_cases(record.version_id, record.module_name)

        version = self.db.query(Version).filter(Version.id == record.version_id).first()
        if not version:
            return {"derived_count": 0, "ui_soft_deleted": 0, "rewritten": 0}

        derived_count = 0
        ui_soft_deleted = 0
        rewritten_count = 0
        new_row_ids = []
        from datetime import datetime as _dt

        for lid in affected_logical_ids:
            eff = resolve_case_by_logical_id(self.db, version.project_id, lid)
            if eff is None:
                logger.warning(f"[派生] 逻辑用例 {lid} 无生效行，跳过")
                continue

            # 2) 派生新行（先复制旧行内容，AI 重写后覆盖）
            # JSON 列：旧行 str（历史数据）解析为 list/dict，否则 None（避免 JSON 字符串嵌套）
            def _as_list(_v):
                if isinstance(_v, list):
                    return _v
                if isinstance(_v, str):
                    try:
                        return json.loads(_v)
                    except Exception:
                        return None
                return None

            def _as_dict(_v):
                if isinstance(_v, dict):
                    return _v
                if isinstance(_v, str):
                    try:
                        return json.loads(_v)
                    except Exception:
                        return None
                return None

            new_row = TestCase(
                project_id=eff.project_id,
                version_id=record.version_id,
                module=eff.module,
                name=eff.name,
                description=eff.description,
                preconditions=eff.preconditions,
                test_steps=_as_list(eff.test_steps),
                expected_result=eff.expected_result,
                test_data=_as_dict(eff.test_data),
                priority=eff.priority,
                case_type=eff.case_type,
                execution_type=eff.execution_type,
                tags=_as_list(eff.tags),
                generated_by="ai_change",
                status="draft",  # 派生行从不继承旧状态，回草稿待审核
                logical_case_id=lid,
                revision_no=next_revision_no(self.db, lid),
                derived_from_id=eff.id,
                created_by=record.created_by,
            )
            self.db.add(new_row)
            self.db.flush()

            # 3) AI 按新需求重写（失败 → 保留副本）
            rewritten = await self._rewrite_case_content(record, eff)
            if rewritten:
                for _k, _v in rewritten.items():
                    if _k == "test_steps" and isinstance(_v, list):
                        setattr(new_row, _k, _v)
                    elif _v is not None:
                        setattr(new_row, _k, _v)
                rewritten_count += 1

            # 1) 旧行冻结
            eff.status = "archived"
            eff.updated_at = _dt.utcnow()

            # 4) 旧 WUI 软删（逻辑 id + 历史物理 id 候选）
            _phys_ids = [str(r.id) for r in self.db.query(TestCase).filter(
                TestCase.logical_case_id == lid
            ).all()]
            _candidates = list(dict.fromkeys([str(lid)] + _phys_ids))
            _wuis = self.db.query(WebUI).filter(
                WebUI.test_case_id.in_(_candidates),
                WebUI.deleted_at.is_(None),
            ).all()
            for _w in _wuis:
                _w.is_deleted = True
                _w.deleted_at = _dt.utcnow()
            ui_soft_deleted += len(_wuis)

            # 5) TestPoint 改绑新行
            _tps = self.db.query(TestPoint).filter(TestPoint.test_case_id == eff.id).all()
            for _tp in _tps:
                _tp.test_case_id = new_row.id

            new_row_ids.append(new_row.id)
            derived_count += 1

        self.db.flush()
        logger.info(
            f"[派生] 逻辑用例 {derived_count} 个: 新行 {new_row_ids}, "
            f"旧 WUI 软删 {ui_soft_deleted}, AI 重写 {rewritten_count}"
        )
        return {
            "derived_count": derived_count,
            "new_test_cases_count": derived_count,
            "new_test_case_ids": new_row_ids,
            "ui_soft_deleted": ui_soft_deleted,
            "rewritten": rewritten_count,
        }

    async def _rewrite_case_content(self, record: RequirementChangeRecord, old_case) -> Optional[Dict]:
        """按新需求重写单条用例内容（AI；失败返回 None → 派生行保留旧内容副本）"""
        import json as _j
        try:
            _steps = old_case.test_steps
            if isinstance(_steps, list):
                _steps_str = _j.dumps(_steps, ensure_ascii=False)
            else:
                _steps_str = _j.dumps(_steps, ensure_ascii=False) if _steps else '(无)'
            prompt = f"""# 需求变更
模块「{record.module_name}」需求已变更（类型: {record.change_type}）：
【旧需求】{record.old_description or '(无)'}
【新需求】{record.new_description or '(无)'}

# 旧测试用例
标题: {old_case.name}
前置条件: {old_case.preconditions or '(无)'}
测试步骤: {_steps_str}
预期结果: {old_case.expected_result or '(无)'}

# 任务
按【新需求】重写此测试用例。只修改受需求变更影响的步骤，其余保留原内容。
test_steps 中的 action 保持 UI 元素命名约定：用「」标记 UI 元素名、用""标记操作值（如"点击「新增」按钮，在「患者姓名」输入框中填写\"张三\""），纯验证步骤以"验证："开头。
直接输出 JSON（不要 markdown）：
{{"name": "用例标题", "description": "用例描述", "preconditions": "前置条件", "test_steps": [{{"step_no": 1, "action": "操作描述", "expected_result": "预期结果"}}], "expected_result": "整体预期", "priority": "P1"}}"""
            resp = await self.llm_service.async_call_llm(
                prompt=prompt, system_prompt="你是测试用例重写专家，输出 JSON。", temperature=0.2,
                max_tokens=self.llm_service.get_scaled_max_tokens(0.1, 8000),
            )
            if not resp:
                return None
            _m = re.search(r'\{.*\}', resp, re.DOTALL)
            if not _m:
                return None
            data = _j.loads(_m.group(0))
            if not isinstance(data, dict) or "name" not in data:
                return None
            steps = data.get("test_steps")
            if not isinstance(steps, list):
                steps = None
            return {
                "name": str(data.get("name", old_case.name)),
                "description": data.get("description"),
                "preconditions": data.get("preconditions"),
                "test_steps": steps,
                "expected_result": data.get("expected_result"),
                "priority": data.get("priority"),
            }
        except Exception as e:
            logger.warning(f"[派生] 用例重写失败，保留旧内容副本: {e}")
            return None
    
    def _mark_cases_deprecated(self, logical_case_ids: List[int]):
        """标记【逻辑用例】的全部修订为已废弃（方案B：参数为逻辑 id）"""
        if not logical_case_ids:
            return

        rows = self.db.query(TestCase).filter(
            TestCase.logical_case_id.in_(logical_case_ids)
        ).all()
        for r in rows:
            r.status = TestCaseStatus.DEPRECATED.value

        logger.info(f"标记{len(rows)}个用例行为已废弃（逻辑用例 {len(logical_case_ids)} 个）")

    def _mark_cases_archived(self, logical_case_ids: List[int]):
        """标记【逻辑用例】的全部修订为已归档（方案B：参数为逻辑 id）"""
        if not logical_case_ids:
            return

        rows = self.db.query(TestCase).filter(
            TestCase.logical_case_id.in_(logical_case_ids)
        ).all()
        for r in rows:
            r.status = TestCaseStatus.ARCHIVED.value

        logger.info(f"标记{len(rows)}个用例行为已归档（逻辑用例 {len(logical_case_ids)} 个）")

    def _remove_affected_ui_and_scene(self, logical_case_ids: List[int]) -> Dict[str, int]:
        """
        功能删除（REMOVE/DEPRECATE）时移除受影响逻辑用例关联的 UI 用例和执行中心条目。
        方案B 语义：
        - 仅 REMOVE 调用（修改走派生：WUI 软删保留，执行中心条目重解析）
        - WUI 按逻辑 id 匹配（兼容历史物理 id 绑定）
        - SceneItem.case_id 存功能用例逻辑 id，按逻辑 id 匹配
        - 执行记录永不改变（历史快照），不删除
        """
        result = {"ui_removed": 0, "scene_removed": 0}
        if not logical_case_ids:
            return result

        try:
            from app.core.models.web_ui_test import WebUITestCase as WebUI
            # WUI 绑定逻辑 id（新）+ 各逻辑用例全部物理行 id（历史物理绑定兼容）
            _phys_rows = self.db.query(TestCase).filter(
                TestCase.logical_case_id.in_(logical_case_ids)
            ).all()
            candidates = list(dict.fromkeys(
                [str(lid) for lid in logical_case_ids] + [str(r.id) for r in _phys_rows]
            ))

            # 1) 移除 UI 用例
            affected_ui = self.db.query(WebUI).filter(
                WebUI.test_case_id.in_(candidates)
            ).all()
            for ui_case in affected_ui:
                self.db.delete(ui_case)
            result["ui_removed"] = len(affected_ui)

            # 2) 移除执行中心（场景）中的条目（case_id 存功能用例逻辑 id）
            try:
                from app.core.models.scene import SceneItem
                scene_items = self.db.query(SceneItem).filter(
                    SceneItem.case_id.in_(logical_case_ids),
                    SceneItem.case_type == "ui"
                ).all()
                for item in scene_items:
                    self.db.delete(item)
                result["scene_removed"] = len(scene_items)
            except Exception:
                pass  # scene 表可能不存在

            if result["ui_removed"] > 0 or result["scene_removed"] > 0:
                self.db.flush()
                logger.info(
                    f"变更回退(REMOVE): 移除UI用例{result['ui_removed']}条, "
                    f"执行中心{result['scene_removed']}条（执行记录保留，历史快照不改）"
                )
        except Exception as e:
            logger.warning(f"UI/Scene回退跳过: {str(e)}")

        return result

    async def batch_approve_changes(
        self,
        version_id: int,
        approve_all: bool = False,
        actions: List[Dict] = None,
        reviewer_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        批量批准变更 - 汇总后一次性生成测试用例
        
        使用事务保护，确保失败时回滚所有操作
        
        Args:
            version_id: 版本ID
            approve_all: 是否一键批准所有变更
            actions: 批量操作列表（如果不一键批准）
            reviewer_id: 审核人ID
        
        Returns:
            批量处理结果
        """
        from app.core.models.project import Version, Project
        
        # 查询该版本下所有待审核的变更记录
        pending_records = self.db.query(RequirementChangeRecord).filter(
            RequirementChangeRecord.version_id == version_id,
            RequirementChangeRecord.status == ChangeRecordStatus.PENDING.value
        ).all()
        
        if not pending_records:
            return {"success": True, "message": "没有待审核的变更记录"}
        
        results = {
            "total": len(pending_records),
            "processed": 0,
            "failed": 0,
            "generated_cases_count": 0,
            "derived_cases_count": 0,  # 方案B：变更即派生统计（旧版归档待审核）
            "details": []
        }
        
        # 1. 分类处理：新增生成 / 修改派生（方案B） / 其他操作（废弃、归档、保持）
        generate_records = []  # 新增模块：批量生成新用例
        derive_records = []    # 修改模块：变更即派生（逐条 AI 重写，不走批量生成）
        other_records = []     # 其他操作（废弃、归档、保持）

        for record in pending_records:
            action = None
            keep_old = False

            if approve_all:
                action = record.suggested_action
                keep_old = False
            else:
                for act in actions or []:
                    if act.get("module") == record.module_name:
                        action = act.get("action")
                        keep_old = act.get("keep_old", False)
                        break

            if not action:
                continue

            # 使用字典存储action信息，避免动态设置ORM属性
            record_info = {
                "record": record,
                "action": action,
                "keep_old": keep_old
            }

            # 分类（方案B：UPDATE_EXISTING=派生，不进批量生成）
            if action == ChangeAction.GENERATE_NEW.value:
                generate_records.append(record_info)
            elif action == ChangeAction.UPDATE_EXISTING.value:
                derive_records.append(record_info)
            else:
                other_records.append(record_info)
        
        # 开始事务
        try:
            # 2. 先生成新测试用例（如果失败，可以回滚）
            if generate_records:
                # 获取版本和项目信息
                version = self.db.query(Version).filter(Version.id == version_id).first()
                if not version:
                    return {"success": False, "message": "版本不存在"}
                
                project = self.db.query(Project).filter(Project.id == version.project_id).first()
                if not project:
                    return {"success": False, "message": "项目不存在"}
                
                # 获取LLM配置
                llm_config = self.llm_service.get_active_config()
                if not llm_config:
                    logger.error("批量批准变更失败：没有活跃的LLM配置")
                    return {"success": False, "message": "没有活跃的LLM配置，请在系统设置中配置LLM服务"}
                config_max_tokens = llm_config.max_tokens
                
                # 判断是否需要分批
                module_count = len(generate_records)
                estimated_tokens = module_count * 500
                generation_max_tokens = min(int(config_max_tokens * 0.4), 12000)
                
                needs_batch = estimated_tokens > generation_max_tokens * 0.6
                max_modules_per_batch = max(1, int(generation_max_tokens * 0.6 / 500))
                
                logger.info(f"批量生成: {module_count}个模块, 预估{estimated_tokens}tokens, max={generation_max_tokens}, 需分批={needs_batch}")
                
                all_new_case_ids: Dict[str, List[int]] = {}

                if needs_batch:
                    batch_count = (module_count + max_modules_per_batch - 1) // max_modules_per_batch
                    logger.info(f"分批策略: {module_count}个模块分{batch_count}批，每批最多{max_modules_per_batch}个")

                    for batch_idx in range(batch_count):
                        batch_records_info = generate_records[batch_idx * max_modules_per_batch : (batch_idx + 1) * max_modules_per_batch]
                        batch_records = [info["record"] for info in batch_records_info]
                        logger.info(f"处理第{batch_idx + 1}/{batch_count}批，包含{len(batch_records)}个模块")

                        batch_case_ids = await self._batch_generate_test_cases(
                            records=batch_records,
                            project=project,
                            version=version,
                            max_tokens=generation_max_tokens
                        )

                        for _m, _ids in batch_case_ids.items():
                            all_new_case_ids.setdefault(_m, []).extend(_ids)
                        logger.info(f"第{batch_idx + 1}批生成{sum(len(v) for v in batch_case_ids.values())}个测试用例")
                else:
                    logger.info(f"一次性生成: {module_count}个模块")
                    batch_records = [info["record"] for info in generate_records]
                    all_new_case_ids = await self._batch_generate_test_cases(
                        records=batch_records,
                        project=project,
                        version=version,
                        max_tokens=generation_max_tokens
                    )

                results["generated_cases_count"] = sum(len(v) for v in all_new_case_ids.values())
                logger.info(f"批量生成完成，共{results['generated_cases_count']}个测试用例")
                
                # 3. 更新生成记录的状态和关联新用例
                for record_info in generate_records:
                    record = record_info["record"]
                    action = record_info["action"]

                    # 更新记录状态
                    record.status = ChangeRecordStatus.COMPLETED.value
                    record.reviewed_by = reviewer_id
                    record.reviewed_at = datetime.utcnow()
                    record.action_taken = action
                    record.new_test_cases_count = len(all_new_case_ids.get(record.module_name, []))

                    results["processed"] += 1
                    results["details"].append({
                        "module": record.module_name,
                        "action": action,
                        "success": True,
                        "message": f"已生成{record.new_test_cases_count}个新用例"
                    })

                # 3.5 修改模块：变更即派生（方案B）
                for record_info in derive_records:
                    record = record_info["record"]
                    action = record_info["action"]

                    derive = await self._derive_cases_for_change(record)
                    record.new_test_cases = derive.get("new_test_case_ids", [])
                    record.new_test_cases_count = derive.get("new_test_cases_count", 0)
                    results["derived_cases_count"] += derive.get("derived_count", 0)

                    record.status = ChangeRecordStatus.COMPLETED.value
                    record.reviewed_by = reviewer_id
                    record.reviewed_at = datetime.utcnow()
                    record.action_taken = action

                    results["processed"] += 1
                    results["details"].append({
                        "module": record.module_name,
                        "action": action,
                        "success": True,
                        "derived_count": derive.get("derived_count", 0),
                        "message": f"已派生{derive.get('derived_count', 0)}个修订（旧版归档，待审核）",
                    })
            
            # 4. 处理其他操作（废弃、归档、保持）- 只在生成成功后执行
            for record_info in other_records:
                record = record_info["record"]
                action = record_info["action"]
                
                if action == ChangeAction.DEPRECATE.value:
                    self._mark_cases_deprecated(record.affected_test_cases)
                    results["details"].append({
                        "module": record.module_name,
                        "action": action,
                        "success": True,
                        "message": f"已废弃{record.affected_test_cases_count}个用例"
                    })
                elif action == ChangeAction.ARCHIVE.value:
                    self._mark_cases_archived(record.affected_test_cases)
                    results["details"].append({
                        "module": record.module_name,
                        "action": action,
                        "success": True,
                        "message": f"已归档{record.affected_test_cases_count}个用例"
                    })
                elif action == ChangeAction.KEEP_OLD.value:
                    results["details"].append({
                        "module": record.module_name,
                        "action": action,
                        "success": True,
                        "message": "保持不变"
                    })
                
                record.status = ChangeRecordStatus.COMPLETED.value
                record.reviewed_by = reviewer_id
                record.reviewed_at = datetime.utcnow()
                record.action_taken = action
                results["processed"] += 1
            
            # 5. 移除受影响的 UI 用例和执行中心条目（仅功能删除 REMOVE/DEPRECATE）
            #    KEEP_OLD 保持不变不级联；UPDATE_EXISTING=派生走 WUI 软删，不在此列
            all_affected = []
            for record_info in generate_records + derive_records + other_records:
                record = record_info["record"]
                action = record_info.get("action", "")
                if action in (ChangeAction.KEEP_OLD.value, ChangeAction.UPDATE_EXISTING.value):
                    continue
                if record.affected_test_cases:
                    all_affected.extend(record.affected_test_cases)
            all_affected = list(set(all_affected))
            ui_result = self._remove_affected_ui_and_scene(all_affected)
            results["affected_ui_removed"] = ui_result["ui_removed"]
            results["affected_scene_removed"] = ui_result["scene_removed"]

            # 6. 提交事务
            self.db.commit()

            # 变更已提交：后台增量探索受影响模块（知识图谱项目级实时更新，
            # 仅 added/modified 且实际生成/派生的记录，去重保序）
            _affected_modules = list(dict.fromkeys(
                ri["record"].module_name
                for ri in generate_records + derive_records
                if ri["record"].change_type in ('added', 'modified')
            ))
            if _affected_modules:
                _spawn_kg_exploration(version_id, _affected_modules)

            parts = [f"处理{results['processed']}条变更", f"生成{results['generated_cases_count']}个用例"]
            if results["derived_cases_count"] > 0:
                parts.append(f"派生{results['derived_cases_count']}个修订")
            if ui_result["ui_removed"] > 0:
                parts.append(f"移除{ui_result['ui_removed']}条旧UI用例")
            if ui_result["scene_removed"] > 0:
                parts.append(f"移除{ui_result['scene_removed']}条执行中心用例")
            msg = f"批量审核完成：{'，'.join(parts)}"

            logger.info(f"批量审核完成: {msg}")

            return {
                "success": True,
                "message": msg,
                **results
            }
            
        except Exception as e:
            # 发生错误时回滚事务
            self.db.rollback()
            logger.error(f"批量批准变更失败，已回滚: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "message": f"批量批准失败: {str(e)}，所有操作已回滚",
                **results
            }
    
    async def _batch_generate_test_cases(
        self,
        records: List[RequirementChangeRecord],
        project: Any,
        version: Any,
        max_tokens: int
    ) -> Dict[str, List[int]]:
        """
        批量生成测试用例（一次性处理多个模块）

        Args:
            records: 变更记录列表
            project: 项目对象
            version: 版本对象
            max_tokens: 最大tokens

        Returns:
            按 module 分区的新测试用例ID字典
        """
        # 构建汇总的生成提示词
        modules_desc = []
        for record in records:
            desc = record.new_description or record.old_description or ""
            modules_desc.append(f"### {record.module_name}\n{desc}")
        
        modules_content = "\n\n".join(modules_desc)
        
        # 构建提示词
        prompt = self._build_batch_generate_prompt(
            modules_content=modules_content,
            module_names=[r.module_name for r in records],
            project_name=project.name,
            version_number=version.version_number
        )
        
        logger.info(f"批量生成提示词长度: {len(prompt)}字符")
        
        try:
            llm_response = await self.llm_service.async_call_llm(
                prompt=prompt,
                system_prompt="你是一位专业的测试用例生成专家。请根据提供的多个模块描述，为每个模块生成完整的测试用例。输出必须是JSON格式。",
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            if not llm_response:
                logger.error("批量生成LLM调用失败 - 没有返回响应，请检查LLM配置")
                raise Exception("LLM调用失败，没有返回响应")
            
            # 解析响应
            test_cases_data = self._parse_batch_test_cases_response(llm_response, records)
            
            if not test_cases_data:
                logger.warning("批量生成响应解析失败")
                return {}

            # 保存测试用例
            new_case_ids = await self._save_batch_test_cases(
                test_cases_data=test_cases_data,
                project_id=project.id,
                version_id=version.id,
                generated_by="ai_change_batch"
            )

            return new_case_ids
            
        except Exception as e:
            logger.error(f"批量生成测试用例失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _build_batch_generate_prompt(
        self,
        modules_content: str,
        module_names: List[str],
        project_name: str,
        version_number: str
    ) -> str:
        """构建批量生成提示词"""
        module_list = "\n".join([f"- {name}" for name in module_names])
        
        json_example = '''
{
  "test_cases": [
    {
      "module": "模块名称",
      "title": "用例标题",
      "description": "用例描述",
      "preconditions": "前置条件",
      "test_steps": [
        {"step_no": 1, "action": "点击「新增」按钮，在「患者姓名」输入框中填写\"张三\"", "expected_result": "页面显示新增成功"}
      ],
      "expected_result": "整体预期结果",
      "priority": "P1",
      "test_type": "positive"
    }
  ]
}'''
        
        prompt = f"""# 项目信息
- 项目名称: {project_name}
- 版本号: {version_number}

# 需要生成测试用例的模块列表
{module_list}

# 模块详细描述
{modules_content}

# 生成要求
请为以上所有模块生成测试用例：
- 每个模块生成5-10个测试用例
- 覆盖正常场景、异常场景、边界场景
- 每个用例包含完整的测试步骤和预期结果
- 标注合理的优先级（P0核心/P1重要/P2一般/P3次要）

# UI 元素命名约定（关键！影响后续自动化转化）

test_steps 中的 action 必须遵循以下约定，以便后续自动化工具能精确识别页面元素：

## 约定 1：用「」标记真正的 UI 元素名

页面上的按钮、输入框、下拉框、卡片等可交互元素的名字，用「」括起来。
描述 UI 组件类型的词（如"卡片""按钮""输入框""下拉框""链接""菜单""页面"）放在「」外面。

✅ 正确写法：
  - 点击「新增」按钮，在「患者姓名」输入框中填写"张三"
  - 在「状态」下拉框中选择"已审核"

❌ 错误写法：
  - 点击「新增按钮」       ← "按钮"是描述词，不是元素名
  - 在「患者姓名输入框」中填写"张三"  ← "输入框"是描述词

## 约定 2：用""标记操作值

填入输入框的值、下拉框选中的选项，用半角双引号""括起来。
值和元素名必须分离，不能混在「」里。

✅ 正确写法：
  - 在「患者姓名」输入框中填写"张三"

❌ 错误写法：
  - 选择「筛选≥30」  ← 值和元素名混在一起

## 约定 3：纯验证步骤用"验证："开头

不需要操作页面元素的断言/检查步骤，以"验证："开头，这类步骤不需要「」标记。

✅ 正确写法：
  - 验证：页面显示所有当天预警

# 输出格式
请输出JSON格式，结构如下：
{json_example}

**请开始生成所有模块的测试用例，确保每个模块都有充分的覆盖。**"""
        
        return prompt
    
    def _parse_batch_test_cases_response(
        self,
        llm_response: str,
        records: List[RequirementChangeRecord]
    ) -> List[Dict[str, Any]]:
        """解析批量生成的测试用例响应"""
        import json
        import re
        
        try:
            # 尝试提取JSON
            json_str = llm_response
            
            # 尝试从代码块提取
            json_match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试提取花括号内容
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
            
            parsed = json.loads(json_str)
            
            test_cases = parsed.get("test_cases", [])
            
            # 验证模块名称是否匹配
            valid_module_names = {r.module_name for r in records}
            valid_cases = []
            
            for tc in test_cases:
                module = tc.get("module", "")
                # 如果模块名称不完全匹配，尝试模糊匹配
                matched_module = None
                for record_module in valid_module_names:
                    if module == record_module or module in record_module or record_module in module:
                        matched_module = record_module
                        break
                
                if matched_module:
                    tc["module"] = matched_module
                    valid_cases.append(tc)
                elif module:
                    # 如果找不到匹配，也保留（可能是新模块名）
                    valid_cases.append(tc)
            
            logger.info(f"解析到{len(test_cases)}个用例，有效{len(valid_cases)}个")
            return valid_cases
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            # 尝试修复截断的JSON
            return self._try_fix_truncated_json(llm_response, records)
    
    def _try_fix_truncated_json(
        self,
        response: str,
        records: List[RequirementChangeRecord]
    ) -> List[Dict[str, Any]]:
        """尝试修复截断的JSON响应"""
        import re
        
        # 提取所有看起来像测试用例的部分
        cases = []
        
        # 尝试提取每个测试用例对象
        pattern = r'"title":\s*"([^"]+)"'
        titles = re.findall(pattern, response)
        
        if titles:
            logger.warning(f"JSON截断，提取到{len(titles)}个用例标题")
            # 如果有标题，至少可以创建基础用例
            for i, title in enumerate(titles[:50]):  # 限制最多50个
                cases.append({
                    "title": title,
                    "module": records[0].module_name if records else "未知模块",
                    "priority": "P1",
                    "test_type": "positive",
                    "description": f"测试用例: {title}",
                    "preconditions": "",
                    "test_steps": [],
                    "expected_result": ""
                })
        
        return cases
    
    async def _save_batch_test_cases(
        self,
        test_cases_data: List[Dict[str, Any]],
        project_id: int,
        version_id: int,
        generated_by: str = "ai_change_batch"
    ) -> Dict[str, List[int]]:
        """批量保存测试用例，按 module 分区返回新用例ID（用于按记录回填 new_test_cases_count）"""
        from app.core.models.requirement import TestCase, TestCaseStatus

        new_case_ids: Dict[str, List[int]] = {}

        for tc_data in test_cases_data:
            try:
                # 处理测试步骤：JSON 列存数组而非字符串
                test_steps = tc_data.get("test_steps", [])
                if not isinstance(test_steps, list):
                    test_steps = [{"step_no": 1, "action": str(test_steps), "expected_result": ""}]

                test_case = TestCase(
                    project_id=project_id,
                    version_id=version_id,
                    module=tc_data.get("module", ""),
                    name=tc_data.get("title", f"测试用例-{sum(len(v) for v in new_case_ids.values())+1}"),
                    description=tc_data.get("description", ""),
                    preconditions=tc_data.get("preconditions", ""),
                    test_steps=test_steps,
                    expected_result=tc_data.get("expected_result", ""),
                    test_data=tc_data.get("test_data") or {},
                    priority=tc_data.get("priority", "P1"),
                    case_type=tc_data.get("test_type", "functional"),
                    execution_type="manual",
                    status=TestCaseStatus.DRAFT.value,
                    tags=tc_data.get("tags") or [],
                    generated_by=generated_by
                )

                self.db.add(test_case)
                self.db.flush()  # 获取ID但不提交

                # 方案B：新建用例逻辑=物理（logical_case_id=自身id）
                test_case.logical_case_id = test_case.id

                # 补建 TestPoint（变更影响范围按 TestPoint 匹配，缺失则新模块用例不可见）
                _module = tc_data.get("module", "")
                _title = tc_data.get("title", "")
                _tp = TestPoint(
                    version_id=version_id,
                    feature_key=tc_data.get("key") or re.sub(r"\s+", "", f"{_module}-{_title}")[:200],
                    name=_title,
                    category=(tc_data.get("category") or "")[:50],
                    detail=tc_data.get("description"),
                    status="active",
                    test_case_id=test_case.id,
                )
                self.db.add(_tp)

                new_case_ids.setdefault(_module, []).append(test_case.id)

            except Exception as e:
                logger.error(f"保存测试用例失败: {str(e)}")
                continue

        logger.info(f"批量保存{sum(len(v) for v in new_case_ids.values())}个测试用例（等待外层事务提交）")

        return new_case_ids
    
