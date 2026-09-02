"""测试用例生成 Agent。

在保留原 Agent 工具契约的前提下修复两个会直接影响下游探索的点：
1. 模块生成提示明确只允许输出该模块的数据，避免跨模块污染；
2. 截断续写按 JSON 对象重新解析合并，不再直接拼接两个可能都是数组的字符串；
3. TestCase 保存时 project_id 必须明确传入/封装，符合 requirement.TestCase 的非空约束。
"""
from typing import Dict, Any, List
import json
import re
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from app.core.agents.base_agent import BaseAgent
from app.core.logger import logger
from app.core.models.test_skill import TestSkill, SkillType
from app.core.models.requirement import TestCase as RequirementTestCase


class TestCaseGenerationAgent(BaseAgent):
    def __init__(self, llm_config, db):
        super().__init__(llm_config, db, "TestCaseGenerationAgent")
        self.create_agent()

    def define_tools(self) -> List[Tool]:
        return [
            Tool(name="extract_modules_from_requirement", func=self._extract_modules_from_requirement, description="从需求文档提取功能模块列表"),
            Tool(name="generate_cases_for_single_module", func=self._generate_cases_for_module, description="为单个模块生成测试用例"),
            Tool(name="detect_json_truncation", func=self._detect_json_truncation, description="检测JSON响应是否截断"),
            Tool(name="continue_truncated_generation", func=self._continue_truncated_generation, description="续写截断的JSON响应"),
            Tool(name="merge_batch_results", func=self._merge_batch_results, description="合并多个批次的生成结果"),
            Tool(name="save_test_cases_to_db", func=self._save_test_cases_to_db, description="保存测试用例到数据库；输入可为数组或{project_id,test_cases}对象"),
            Tool(name="get_skill_template", func=self._get_skill_template, description="获取SKILL模板配置"),
        ]

    def build_prompt(self) -> ChatPromptTemplate:
        template = """你是专业的测试用例生成专家。
任务：为需求文档生成完整、结构稳定、可追踪的功能测试用例 JSON。

规则：
1. 先提取主要功能模块；
2. 每个模块独立生成，不把其他模块内容带入；
3. 每批结果必须是完整 JSON 数组；
4. 不要为了达到固定数量而虚构需求中不存在的场景；
5. 每条用例应包含正常、异常、边界等实际有依据的场景；
6. 保存时必须保留 project_id/version_id 等上下文。

输出格式：
[{"id":"TC001","title":"...","module":"...","priority":"P0/P1/P2/P3","test_steps":[],"expected_result":"...","test_data":{"data_plan":{"requirements":[{"key":"patient_name","data_type":"generated","provider":"generator","generator":"name","unique":true,"cleanup_policy":"none","description":"患者姓名"}]}}}]

测试数据规则：
- test_data.data_plan 描述“需要什么数据”，不要把一次运行产生的随机值写死为长期资产；
- static/shared 可以给 value；generated 使用 generator；consumable 使用 data_type=consumable、provider=consumable，默认每次 Case Run 创建独立实例；
- seeded/factory 表示需要业务工厂，必须填写 factory 名称；
- 数据引用可在步骤中使用 ${key}，探索执行时由 TestDataManager 实例化；

输入：
{input}

可用工具：
{tools}

{agent_scratchpad}
"""
        return ChatPromptTemplate.from_template(template)

    def _extract_modules_from_requirement(self, requirement_doc: str) -> str:
        logger.info(f"[Tool] 提取模块，文档长度={len(requirement_doc or '')}")
        prompt = f"""从以下需求文档提取主要功能模块，只返回 JSON 数组。\n规则：过滤概述/背景/目录/附录；最多20个。\n\n{(requirement_doc or '')[:12000]}"""
        raw = self.llm.predict(prompt)
        try:
            modules = json.loads(self._extract_json_array(raw))
            modules = [str(x).strip() for x in modules if str(x).strip()]
            return json.dumps({"modules": modules[:20], "count": min(len(modules),20)}, ensure_ascii=False)
        except Exception:
            matches = re.findall(r'^#{1,4}\s*([^\n]{2,80})$', requirement_doc or '', re.MULTILINE)
            modules = [m.strip() for m in matches if m.strip()][:20]
            return json.dumps({"modules": modules, "count": len(modules)}, ensure_ascii=False)

    def _generate_cases_for_module(self, module_name: str, requirement_doc: str, project_name: str = "测试项目") -> str:
        skill = self._get_skill_template()
        prompt = f"""项目：{project_name}\n模块：{module_name}\n\n仅根据下面需求内容生成该模块的功能测试用例：\n{(requirement_doc or '')[:10000]}\n\nSKILL：{skill}\n\n要求：只输出 JSON 数组。不要输出其他模块用例。不要虚构不存在的业务规则。"""
        response = self.llm.predict(prompt)
        if self._detect_json_truncation(response).get("is_truncated"):
            return self._continue_truncated_generation(response, 0, {"module": module_name})
        return response

    def _detect_json_truncation(self, response: str) -> str:
        return json.dumps(self.detect_truncation(response or {}), ensure_ascii=False)

    def _continue_truncated_generation(self, truncated_response: str, remaining_count: int, context: Dict[str, Any] = None) -> str:
        module = (context or {}).get("module", "未知模块")
        existing = self._parse_cases_safely(truncated_response)
        prompt = f"""之前的 JSON 生成被截断。模块：{module}。已经成功解析 {len(existing)} 条。\n\n不要重复已有用例。只返回新增用例的 JSON 数组；如果无法判断还需要哪些，不要虚构。\n\n已生成内容末尾：\n{(truncated_response or '')[-1200:]}"""
        continuation = self.llm.predict(prompt)
        added = self._parse_cases_safely(continuation)
        merged = self._dedup_cases(existing + added)
        return json.dumps(merged, ensure_ascii=False)

    def _merge_batch_results(self, batch_results: str) -> str:
        try:
            raw = json.loads(batch_results)
            batches = raw if isinstance(raw, list) else [raw]
            cases = []
            for batch in batches:
                if isinstance(batch, str): cases.extend(self._parse_cases_safely(batch))
                elif isinstance(batch, list): cases.extend([x for x in batch if isinstance(x,dict)])
                elif isinstance(batch, dict) and isinstance(batch.get('test_cases'), list): cases.extend(batch['test_cases'])
            return json.dumps(self._dedup_cases(cases), ensure_ascii=False)
        except Exception:
            return batch_results

    @staticmethod
    def _normalize_test_data(data: Any, case: Dict[str, Any]) -> Dict[str, Any]:
        """把 LLM 输出统一成可执行 DataPlan，同时保留旧 test_data 字段兼容 UI 生成器。"""
        raw = dict(data) if isinstance(data, dict) else {}
        if isinstance(raw.get("data_plan"), dict):
            return raw
        requirements = []
        reserved = {"title", "name", "module", "priority", "preconditions", "description", "expected_result"}
        for key, value in raw.items():
            if key in reserved:
                continue
            if isinstance(value, dict) and any(k in value for k in ("type", "data_type", "provider", "generator", "factory")):
                item = dict(value)
                item["key"] = key
                item["data_type"] = item.pop("type", item.get("data_type", "generated"))
                requirements.append(item)
            elif value not in (None, ""):
                requirements.append({"key": key, "data_type": "static", "provider": "static", "value": value, "unique": False})
        raw["data_plan"] = {
            "case_id": str(case.get("id", "")),
            "logical_case_id": str(case.get("logical_case_id", case.get("id", ""))),
            "revision_no": int(case.get("revision_no", 1) or 1),
            "version_id": case.get("version_id"),
            "project_id": case.get("project_id"),
            "requirements": requirements,
        }
        return raw

    def _save_test_cases_to_db(self, payload: str) -> str:
        try:
            data = json.loads(payload)
            project_id = data.get('project_id') if isinstance(data,dict) else None
            version_id = data.get('version_id') if isinstance(data,dict) else None
            cases = data.get('test_cases', []) if isinstance(data,dict) else data
            if not isinstance(cases,list): raise ValueError('test_cases 必须为 JSON 数组')
            # 兼容旧调用：如果 case 本身已经带 project_id，允许逐条读取。
            saved=0
            for c in cases:
                if not isinstance(c,dict): continue
                pid = c.get('project_id', project_id)
                if pid is None:
                    raise ValueError('保存 TestCase 必须提供 project_id（TestCase.project_id 为非空字段）')
                vid = c.get('version_id', version_id)
                normalized_data = self._normalize_test_data(c.get('test_data', {}), {**c, 'project_id': pid, 'version_id': vid})
                tc=RequirementTestCase(project_id=pid,version_id=vid,name=c.get('name') or c.get('title') or '',module=c.get('module',''),description=c.get('description',''),preconditions=c.get('preconditions',''),test_steps=c.get('test_steps',[]),expected_result=c.get('expected_result',''),test_data=normalized_data,priority=c.get('priority','P2'),status=c.get('status','draft'),generated_by=c.get('generated_by','ai'),source_feature=c.get('source_feature',''))
                if not tc.name: raise ValueError('测试用例 name/title 不能为空')
                self.db.add(tc); self.db.flush(); tc.logical_case_id=tc.id; tc.revision_no=1; saved+=1
            self.db.commit()
            return json.dumps({'success':True,'saved_count':saved,'message':f'成功保存{saved}条测试用例'},ensure_ascii=False)
        except Exception as e:
            self.db.rollback(); logger.error(f"[Tool] 保存失败: {e}")
            return json.dumps({'success':False,'error':str(e)},ensure_ascii=False)

    def _get_skill_template(self) -> str:
        try:
            skill=self.db.query(TestSkill).filter(TestSkill.skill_type==SkillType.FUNCTIONAL.value,TestSkill.is_global==True).first()
            return json.dumps(skill.content if skill and skill.content else {'default':True},ensure_ascii=False)
        except Exception as e:
            return json.dumps({'error':str(e)},ensure_ascii=False)

    @staticmethod
    def _extract_json_array(text: str) -> str:
        m=re.search(r'\[.*\]',text or '',re.DOTALL)
        if not m: raise ValueError('JSON array not found')
        return m.group(0)

    def _parse_cases_safely(self,text: str)->List[dict]:
        try:
            obj=json.loads(self._extract_json_array(text))
            return [x for x in obj if isinstance(x,dict)] if isinstance(obj,list) else []
        except Exception:
            return []

    @staticmethod
    def _dedup_cases(cases: List[dict])->List[dict]:
        out=[]; seen=set()
        for c in cases:
            key=str(c.get('id') or c.get('title') or '')
            if not key: key=json.dumps(c,ensure_ascii=False,sort_keys=True)
            if key in seen: continue
            seen.add(key); out.append(c)
        return out
