"""
Agent基础类
定义所有Agent的统一接口和核心功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import asyncio
import time

# ── langchain 兼容导入 ──
# 新版 langchain(1.x) 把组件移到了 langchain_openai / langchain_core；旧位置（langchain_community /
# langchain.prompts / langchain.tools）仅作回退。AgentExecutor / create_structured_chat_agent 属旧式
# Agent 运行时，新版已移除；BaseAgent 多数子类直接调 LLMService（如 convert_functional_to_web_ui_ai
# 明确不依赖 Agent 运行时），故 AgentExecutor 不可用时降级为 None，create_agent 跳过创建 agent_executor。
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    from langchain_community.chat_models import ChatOpenAI

try:
    from langchain_core.tools import Tool
except ImportError:
    from langchain.tools import Tool

try:
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:
    from langchain.prompts import ChatPromptTemplate

try:
    from langchain.agents import AgentExecutor, create_structured_chat_agent
    _LANGOCHAIN_HAS_AGENT_EXECUTOR = True
except Exception as _lc_err:  # 新版 langchain 已移除 AgentExecutor / create_structured_chat_agent
    AgentExecutor = None
    create_structured_chat_agent = None
    _LANGOCHAIN_HAS_AGENT_EXECUTOR = False

from app.core.logger import logger
from app.core.models.llm_config import LLMConfig
from sqlalchemy.orm import Session


class BaseAgent(ABC):
    """
    Agent基础类
    
    所有Agent继承此基类，实现：
    1. 统一的execute接口
    2. LangChain Agent自动管理
    3. 截断检测和续写机制
    4. 失败重试机制
    5. 执行日志记录
    """
    
    def __init__(self, llm_config: LLMConfig, db: Session, agent_name: str):
        """
        初始化Agent
        
        Args:
            llm_config: LLM配置对象
            db: 数据库会话
            agent_name: Agent名称（用于日志和追踪）
        """
        self.llm_config = llm_config
        self.db = db
        self.agent_name = agent_name
        
        self.llm = ChatOpenAI(
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
            timeout=900
        )
        
        self.tools: List[Tool] = []
        
        self.agent_executor: Optional[AgentExecutor] = None
        
        self.execution_stats = {
            "start_time": None,
            "end_time": None,
            "duration": 0,
            "iterations": 0,
            "truncations_detected": 0,
            "continuations": 0,
            "retries": 0
        }
    
    @abstractmethod
    def define_tools(self) -> List[Tool]:
        """
        定义Agent工具集
        
        子类必须实现此方法，返回LangChain Tool列表
        
        Returns:
            Tool对象列表
        """
        pass
    
    @abstractmethod
    def build_prompt(self) -> ChatPromptTemplate:
        """
        构建Agent提示词
        
        子类必须实现此方法，返回ChatPromptTemplate
        
        Returns:
            ChatPromptTemplate对象
        """
        pass
    
    def create_agent(self):
        """
        创建LangChain Agent执行器
        
        在子类初始化完成后调用此方法
        """
        # 定义工具集
        self.tools = self.define_tools()
        
        # 构建提示词
        prompt = self.build_prompt()

        if not _LANGOCHAIN_HAS_AGENT_EXECUTOR:
            logger.warning(f"[{self.agent_name}] 当前 langchain 版本无旧 Agent API（AgentExecutor），"
                           "跳过 agent_executor 创建；子类多用 LLMService 直调，如需 Agent 运行时请迁移到 langchain 1.x 的 create_agent")
            return

        # 创建Agent
        agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        # 创建Agent执行器
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=50,
            handle_parsing_errors=True,
            max_execution_time=600  # 10分钟最大执行时间
        )
        
        logger.info(f"Agent {self.agent_name} 创建成功，工具数={len(self.tools)}")
    
    async def execute(self, task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Agent任务
        
        Args:
            task_input: 任务输入参数
        
        Returns:
            执行结果字典
        """
        # 记录开始时间
        self.execution_stats["start_time"] = datetime.now()
        
        logger.info(f"[{self.agent_name}] 开始执行任务")
        logger.debug(f"[{self.agent_name}] 输入参数：{json.dumps(task_input, ensure_ascii=False)[:200]}")
        
        try:
            if self.agent_executor is None:
                logger.error(f"[{self.agent_name}] agent_executor 未创建（langchain 旧 Agent API 在新版本不可用）")
                return {"success": False,
                        "error": "agent_executor 未创建：当前 langchain 版本不支持旧式 Agent 运行时",
                        "stats": self.execution_stats, "agent_name": self.agent_name}
            # Agent执行（自动处理：任务拆分、截断续写、失败重试）
            result = await self.agent_executor.arun(**task_input)
            
            # 记录结束时间
            self.execution_stats["end_time"] = datetime.now()
            self.execution_stats["duration"] = (
                self.execution_stats["end_time"] - self.execution_stats["start_time"]
            ).total_seconds()
            
            logger.info(f"[{self.agent_name}] 任务执行成功，耗时={self.execution_stats['duration']}秒")
            logger.debug(f"[{self.agent_name}] 执行统计：{json.dumps(self.execution_stats)}")
            
            return {
                "success": True,
                "data": result,
                "stats": self.execution_stats,
                "agent_name": self.agent_name
            }
            
        except Exception as e:
            # 记录失败
            self.execution_stats["end_time"] = datetime.now()
            self.execution_stats["duration"] = (
                self.execution_stats["end_time"] - self.execution_stats["start_time"]
            ).total_seconds()
            
            logger.error(f"[{self.agent_name}] 任务执行失败：{str(e)}", exc_info=True)
            
            return {
                "success": False,
                "error": str(e),
                "stats": self.execution_stats,
                "agent_name": self.agent_name
            }
    
    def detect_truncation(self, response: str) -> Dict[str, Any]:
        """
        检测响应是否截断
        
        Args:
            response: LLM响应字符串
        
        Returns:
            {
                "is_truncated": bool,
                "truncated_at": str,
                "generated_count": int,
                "can_continue": bool
            }
        """
        try:
            # 尝试解析JSON
            json.loads(response)
            return {
                "is_truncated": False,
                "generated_count": 0,
                "can_continue": False
            }
        except json.JSONDecodeError:
            # JSON解析失败，可能截断
            truncated_at = response[-100:]
            
            # 检查未闭合的结构
            unclosed_brackets = response.count('{') != response.count('}')
            unclosed_arrays = response.count('[') != response.count(']')
            unclosed_quotes = response.count('"') % 2 != 0
            
            can_continue = unclosed_brackets or unclosed_arrays or unclosed_quotes
            
            # 尝试提取已生成的对象数量
            generated_count = self._count_generated_objects(response)
            
            self.execution_stats["truncations_detected"] += 1
            
            logger.warning(f"[{self.agent_name}] 检测到截断：生成{generated_count}个对象，可续写={can_continue}")
            
            return {
                "is_truncated": True,
                "truncated_at": truncated_at,
                "generated_count": generated_count,
                "can_continue": can_continue,
                "unclosed_structure": {
                    "brackets": unclosed_brackets,
                    "arrays": unclosed_arrays,
                    "quotes": unclosed_quotes
                }
            }
    
    async def continue_generation(
        self,
        truncated_response: str,
        remaining_count: int,
        context: Dict[str, Any]
    ) -> str:
        """
        续写截断的响应
        
        Args:
            truncated_response: 截断的响应字符串
            remaining_count: 需要续写的数量
            context: 上下文信息
        
        Returns:
            续写后的完整响应
        """
        self.execution_stats["continuations"] += 1
        
        logger.info(f"[{self.agent_name}] 开始续写，剩余{remaining_count}个对象")
        
        # 构建续写提示词
        continuation_prompt = f"""
之前的生成在以下位置截断：
{truncated_response[-200:]}

已生成对象数：{self._count_generated_objects(truncated_response)}
需继续生成：{remaining_count}个对象

请继续生成剩余的对象。
从最后一个完整对象之后开始。
保持相同的JSON结构格式。
不要重复已生成的内容。
"""
        
        # 调用LLM续写
        continuation = await asyncio.to_thread(
            self.llm.predict,
            continuation_prompt
        )
        
        # 合并两部分响应
        merged_response = self._merge_responses(truncated_response, continuation)
        
        logger.info(f"[{self.agent_name}] 续写成功，合并后长度={len(merged_response)}")
        
        return merged_response
    
    def _count_generated_objects(self, response: str) -> int:
        """
        计算已生成的对象数量
        
        Args:
            response: 响应字符串
        
        Returns:
            已生成的JSON对象数量
        """
        # 简化实现：通过正则匹配对象数量
        import re
        
        # 匹配对象ID模式（如 "TC001", "API001"）
        pattern = r'"id":\s*"(TC\d+|API\d+|REQ\d+)"'
        matches = re.findall(pattern, response)
        
        return len(matches)
    
    def _merge_responses(self, part1: str, part2: str) -> str:
        """
        合并两部分响应
        
        Args:
            part1: 第一部分响应
            part2: 第二部分响应（续写部分）
        
        Returns:
            合并后的完整响应
        """
        # 提取第一部分的完整对象
        # 尝试截断到最后一个完整的逗号分隔位置
        last_complete_position = part1.rfind(',')
        
        if last_complete_position > 0:
            part1_trimmed = part1[:last_complete_position + 1]
        else:
            part1_trimmed = part1
        
        # 清理第二部分的开头
        part2_cleaned = part2.strip()
        
        # 合并
        merged = part1_trimmed + " " + part2_cleaned
        
        return merged
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """
        获取执行统计信息
        
        Returns:
            执行统计数据字典
        """
        return self.execution_stats