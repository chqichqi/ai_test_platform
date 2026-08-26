"""
LLM服务模块
封装LLM API调用，支持从系统配置中读取当前激活的LLM配置
"""

import json
import re
import requests
import asyncio
import concurrent.futures
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.models.llm_config import LLMConfig


class LLMService:
    """LLM服务类"""
    
    def __init__(self, db: Session):
        self.db = db
        self._config: Optional[LLMConfig] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    
    def get_active_config(self) -> Optional[LLMConfig]:
        """获取当前激活的LLM配置（每次从数据库重新读取，不缓存）"""
        self._config = self.db.query(LLMConfig).filter(
            LLMConfig.is_active == True
        ).first()
        
        return self._config
    
    async def async_call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        cancel_check=None,
    ) -> Optional[str]:
        """
        异步调用LLM API（线程池执行，避免阻塞事件循环）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.call_llm,
            prompt,
            system_prompt,
            temperature,
            max_tokens,
            json_mode,
            cancel_check,
        )

    async def async_call_llm_with_tools(
        self,
        messages: list,
        tools: list,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        cancel_check=None,
    ) -> Optional[str]:
        """异步调用 LLM API（带 function calling / tools）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._call_llm_with_tools_sync,
            messages,
            tools,
            temperature,
            max_tokens,
            cancel_check,
        )

    def _call_llm_with_tools_sync(
        self, messages: list, tools: list,
        temperature=None, max_tokens=None,
        cancel_check=None,
    ) -> Optional[str]:
        """同步执行带 tools 的 LLM 调用"""
        config = self.get_active_config()
        if not config:
            logger.warning("[LLM] 无激活配置")
            return None

        if cancel_check and cancel_check():
            logger.info("[LLM] ⛔ Tool calling 已取消")
            return None

        try:
            base_url = config.base_url.rstrip('/')
            if '/chat/completions' not in base_url:
                if '/v1' in base_url:
                    api_url = f"{base_url}/chat/completions"
                else:
                    api_url = f"{base_url}/v1/chat/completions"
            else:
                api_url = base_url

            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": config.model,
                "messages": messages,
                "tools": tools,
                "temperature": temperature if temperature is not None else config.temperature,
                "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
            }

            logger.info(f"[LLM] Tool calling: {len(tools)} tools, {len(messages)} messages")
            # 流式读取 + 取消检查
            response = requests.post(api_url, headers=headers, json=payload,
                                    timeout=(30, 120), stream=True)

            if response.status_code == 200:
                chunks = []
                for chunk in response.iter_content(chunk_size=8192):
                    if cancel_check and cancel_check():
                        response.close()
                        logger.info("[LLM] ⛔ Tool calling 流式读取中途取消")
                        return None
                    if chunk:
                        chunks.append(chunk)
                content = b''.join(chunks).decode('utf-8')
                result = json.loads(content)
                choice = result.get("choices", [{}])[0]
                msg = choice.get("message", {})
                return json.dumps(msg, ensure_ascii=False)
            else:
                logger.error(f"[LLM] API error: {response.status_code} {response.text[:500]}")
                return None
        except Exception as e:
            logger.error(f"[LLM] Tool calling 异常: {e}")
            return None

    def get_scaled_max_tokens(self, ratio: float = 0.7, cap: int = 100000) -> int:
        """按 LLM 配置 max_tokens 的百分比计算本次调用预算（RULES.md 六章固化规则）。

        推理模型（deepseek-v4-pro）需同时覆盖推理与正文，硬编码小值会导致正文被截断
        （finish_reason=length、content 为空——2026-08-16 批量转化 8000 tokens 耗尽事故）。
        统一公式：min(int(config_max_tokens * ratio), cap)。
        默认 ratio=0.7（70%，留 30% 余量，用户 2026-08-16 确认）、cap=100000——
        cap 为日志实证的 API 安全上限：2026-08-16 17:50 deepseek-v4-flash
        max_tokens=100000 调用成功，全日志无 400 报错；原 cap=32000 过于保守
        （160000 配置下 50% 与 70% 均被 32000 封顶，比例实际失效）。
        小任务用比例+小 cap：0.1/8000（元素提取）、0.05/2000（编号匹配）。
        """
        try:
            _cfg = self.get_active_config()
            _cfg_max = (_cfg.max_tokens if _cfg else 0) or 0
        except Exception:
            _cfg_max = 0
        if _cfg_max <= 0:
            return cap
        return min(int(_cfg_max * ratio), cap)

    def call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        cancel_check=None,   # callable → bool, 返回 True 表示已取消
    ) -> Optional[str]:
        """
        调用LLM API
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数（覆盖默认值）
            max_tokens: 最大token数（覆盖默认值）
        
        Returns:
            LLM响应文本，失败返回None
        """
        config = self.get_active_config()
        if not config:
            logger.warning("No active LLM config found")
            return None

        # ── 取消检查：客户端断开时立即停止 ──
        if cancel_check and cancel_check():
            logger.info("[LLM] ⛔ 调用已取消（客户端断开），跳过 LLM 请求")
            return None

        try:
            base_url = config.base_url.rstrip('/')
            if not base_url.endswith('/chat/completions'):
                if base_url.endswith('/v1'):
                    api_url = f"{base_url}/chat/completions"
                elif '/v1' not in base_url:
                    api_url = f"{base_url}/v1/chat/completions"
                else:
                    api_url = f"{base_url}/chat/completions"
            else:
                api_url = base_url

            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": config.model,
                "messages": messages,
                "temperature": temperature if temperature is not None else config.temperature,
                "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
            logger.info(f"Calling LLM: {config.name}, Model: {config.model}, max_tokens: {actual_max_tokens} (passed: {max_tokens}, config: {config.max_tokens})")

            # 使用流式读取，支持中途取消（每 8KB chunk 检查一次取消令牌）
            LLM_CHUNK_SIZE = 8192
            LLM_CONNECT_TIMEOUT = 30   # 连接超时
            LLM_READ_TIMEOUT = 300     # 读取超时（DeepSeek 生成长文本可能需 2-5 分钟）

            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=(LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT),
                stream=True,  # 流式读取，支持中途取消
            )

            if response.status_code == 200:
                # 流式读取响应体，每读一个 chunk 检查取消令牌
                def _read_stream(resp):
                    _chunks = []
                    for chunk in resp.iter_content(chunk_size=LLM_CHUNK_SIZE):
                        if cancel_check and cancel_check():
                            resp.close()
                            logger.info("[LLM] ⛔ 流式读取中途取消（客户端断开）")
                            return None
                        if chunk:
                            _chunks.append(chunk)
                    return b''.join(_chunks).decode('utf-8')

                content = _read_stream(response)
                if content is None:
                    return None
                result = json.loads(content)

                # 推理模型自愈：content 为空、reasoning_content 有内容且被 max_tokens 截断时，
                # 加大预算重试一次（deepseek-v4-pro 把推理过程写入 reasoning_content，
                # 预算不足时正文还没开始输出就停止，finish_reason=length）
                _retried = False
                if isinstance(result, dict) and result.get("choices"):
                    _c0 = result["choices"][0] or {}
                    _m0 = _c0.get("message", {}) or {}
                    if (not _m0.get("content") and _m0.get("reasoning_content")
                            and _c0.get("finish_reason") == "length"):
                        # 预算来自调用点（已统一 get_scaled_max_tokens 百分比），
                        # 重试按 ×4 封顶配置值（不超过 API 侧上限，自愈语义不变）
                        _used = payload.get("max_tokens") or config.max_tokens
                        _bigger = min(_used * 4, config.max_tokens)
                        logger.warning(f"LLM 正文为空（finish_reason=length，推理耗尽 {_used} tokens），"
                                       f"加大 max_tokens={_bigger} 重试一次")
                        payload["max_tokens"] = _bigger
                        response = requests.post(
                            api_url, headers=headers, json=payload,
                            timeout=(LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT), stream=True,
                        )
                        if response.status_code != 200:
                            logger.error(f"LLM 重试失败: {response.status_code} - {response.text[:200]}")
                            return None
                        content = _read_stream(response)
                        if content is None:
                            return None
                        result = json.loads(content)
                        _retried = True

                if "choices" in result and len(result["choices"]) > 0:
                    _msg = result["choices"][0].get("message", {}) or {}
                    text = _msg.get("content")
                    if not text:
                        # 思维链不是答案：不回退 reasoning_content（会把 CoT 文本喂给 JSON 解析器）
                        _fr = result["choices"][0].get("finish_reason")
                        logger.warning(
                            f"LLM content 仍为空（finish_reason={_fr}，"
                            f"reasoning 长度={len(_msg.get('reasoning_content') or '')}）"
                            + ("，已重试" if _retried else ""))
                    logger.info(f"LLM response received, length: {len(text) if text else 0}")
                    return text
                elif result.get("error"):
                    logger.error(f"LLM 返回错误: {str(result['error'])[:200]}")
                    return None
                else:
                    logger.error(f"LLM response format error: {str(result)[:300]}")
                    return None
            else:
                logger.error(f"LLM API error: {response.status_code} - {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"LLM API timeout")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"LLM API connection error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"LLM API call failed: {str(e)}")
            return None
    
    def call_llm_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ):
        """
        流式调用LLM API，逐块返回内容
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数
        
        Yields:
            每次返回一个文本块
        """
        config = self.get_active_config()
        if not config:
            logger.warning("No active LLM config found for streaming")
            yield None
            return
        
        try:
            base_url = config.base_url.rstrip('/')
            if not base_url.endswith('/chat/completions'):
                if base_url.endswith('/v1'):
                    api_url = f"{base_url}/chat/completions"
                elif '/v1' not in base_url:
                    api_url = f"{base_url}/v1/chat/completions"
                else:
                    api_url = f"{base_url}/chat/completions"
            else:
                api_url = base_url
            
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": config.model,
                "messages": messages,
                "temperature": temperature if temperature is not None else config.temperature,
                "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
                "stream": True,
            }
            
            logger.info(f"Calling LLM stream: {config.name}, Model: {config.model}")
            
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=120,
                stream=True,
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        line_text = line.decode('utf-8')
                        if line_text.startswith('data: '):
                            data_str = line_text[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and len(data['choices']) > 0:
                                    delta = data['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
            else:
                logger.error(f"LLM stream API error: {response.status_code} - {response.text[:200]}")
                yield None
                
        except requests.exceptions.Timeout:
            logger.error("LLM stream API timeout")
            yield None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"LLM stream API connection error: {str(e)}")
            yield None
        except Exception as e:
            logger.error(f"LLM stream API call failed: {str(e)}")
            yield None
    
    def call_llm_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        调用LLM并解析JSON响应
        
        Returns:
            解析后的JSON对象，失败返回None
        """
        response = self.call_llm(prompt, system_prompt, temperature, max_tokens)
        if not response:
            return None
        
        try:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response
            
            start = json_str.find('[')
            end = json_str.rfind(']')
            if start != -1 and end != -1:
                json_str = json_str[start:end+1]
            elif '{' in json_str:
                start = json_str.find('{')
                end = json_str.rfind('}')
                if start != -1 and end != -1:
                    json_str = json_str[start:end+1]
            
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {str(e)}")
            logger.debug(f"Response was: {response[:500]}")
            return None
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        获取文本的向量嵌入
        
        Args:
            text: 要向量化的文本
        
        Returns:
            向量列表，失败返回None
        """
        config = self.get_active_config()
        if not config:
            logger.warning("No active LLM config found for embedding")
            return None
        
        try:
            base_url = config.base_url.rstrip('/')
            if base_url.endswith('/v1'):
                api_url = f"{base_url}/embeddings"
            elif '/v1' not in base_url:
                api_url = f"{base_url}/v1/embeddings"
            else:
                api_url = f"{base_url}/embeddings"
            
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            
            embedding_model = "text-embedding-3-small"
            provider_lower = (config.provider or "").lower()
            base_url_lower = (config.base_url or "").lower()
            
            if "deepseek" in base_url_lower or "deepseek" in provider_lower:
                embedding_model = "text-embedding-3-small"
            elif "openai" in base_url_lower or "openai" in provider_lower:
                embedding_model = "text-embedding-3-small"
            elif "dashscope" in base_url_lower or "aliyun" in provider_lower or "alibaba" in provider_lower:
                embedding_model = "text-embedding-v3"
            elif "zhipu" in base_url_lower or "bigmodel" in base_url_lower:
                embedding_model = "embedding-3"
            elif "moonshot" in base_url_lower or "kimi" in provider_lower:
                embedding_model = "text-embedding-3-small"
            
            payload = {
                "model": embedding_model,
                "input": text[:8000],
            }
            
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=60,
            )
            
            if response.status_code == 200:
                result = response.json()
                if "data" in result and len(result["data"]) > 0:
                    embedding = result["data"][0].get("embedding")
                    logger.info(f"Got embedding, dimension: {len(embedding) if embedding else 0}")
                    return embedding
                else:
                    logger.error(f"Embedding response format error: {result}")
                    return None
            else:
                logger.error(f"Embedding API error: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get embedding: {str(e)}")
            return None
    
    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        批量获取文本的向量嵌入
        
        Args:
            texts: 文本列表
        
        Returns:
            向量列表
        """
        config = self.get_active_config()
        if not config:
            logger.warning("No active LLM config found for embedding batch")
            return [None] * len(texts)
        
        try:
            base_url = config.base_url.rstrip('/')
            if base_url.endswith('/v1'):
                api_url = f"{base_url}/embeddings"
            elif '/v1' not in base_url:
                api_url = f"{base_url}/v1/embeddings"
            else:
                api_url = f"{base_url}/embeddings"
            
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            
            embedding_model = "text-embedding-3-small"
            provider_lower = (config.provider or "").lower()
            base_url_lower = (config.base_url or "").lower()
            
            if "deepseek" in base_url_lower or "deepseek" in provider_lower:
                embedding_model = "text-embedding-3-small"
            elif "openai" in base_url_lower or "openai" in provider_lower:
                embedding_model = "text-embedding-3-small"
            elif "dashscope" in base_url_lower or "aliyun" in provider_lower or "alibaba" in provider_lower:
                embedding_model = "text-embedding-v3"
            elif "zhipu" in base_url_lower or "bigmodel" in base_url_lower:
                embedding_model = "embedding-3"
            elif "moonshot" in base_url_lower or "kimi" in provider_lower:
                embedding_model = "text-embedding-3-small"
            
            all_embeddings = []
            batch_size = 5
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                batch = [t[:8000] if t else "" for t in batch]
                
                payload = {
                    "model": embedding_model,
                    "input": batch,
                }
                
                response = requests.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "data" in result:
                        sorted_data = sorted(result["data"], key=lambda x: x.get("index", 0))
                        all_embeddings.extend([item.get("embedding") for item in sorted_data])
                    else:
                        logger.error(f"No data in response: {result}")
                        all_embeddings.extend([None] * len(batch))
                else:
                    logger.error(f"Batch embedding API error: {response.status_code} - {response.text[:500]}")
                    all_embeddings.extend([None] * len(batch))
            
            logger.info(f"Got {len([e for e in all_embeddings if e])} embeddings from {len(texts)} texts")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Failed to get batch embeddings: {str(e)}")
            return [None] * len(texts)


class RAGRetrievalService:
    """RAG检索服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.llm_service = LLMService(db)
    
    def vectorize_chunks(self, knowledge_base_id: int = None) -> Dict[str, Any]:
        """
        对分块进行向量化
        
        Args:
            knowledge_base_id: 知识库ID，不指定则处理所有
        
        Returns:
            处理结果
        """
        from app.models.knowledge import RagChunkModel, RagDocumentModel
        
        query = self.db.query(RagChunkModel).filter(
            RagChunkModel.embedding.is_(None)
        )
        
        if knowledge_base_id:
            query = query.join(RagDocumentModel).filter(
                RagDocumentModel.knowledge_base_id == knowledge_base_id
            )
        
        chunks = query.limit(100).all()
        
        if not chunks:
            return {"success": True, "message": "No chunks to vectorize", "count": 0}
        
        texts = [chunk.content for chunk in chunks]
        embeddings = self.llm_service.get_embeddings_batch(texts)
        
        updated_count = 0
        for chunk, embedding in zip(chunks, embeddings):
            if embedding:
                chunk.embedding = embedding
                updated_count += 1
        
        self.db.commit()
        
        logger.info(f"Vectorized {updated_count} chunks")
        return {
            "success": True,
            "message": f"Vectorized {updated_count} chunks",
            "count": updated_count,
            "remaining": query.count() - len(chunks)
        }
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0
        
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def search_similar_chunks(
        self,
        query: str,
        knowledge_base_id: int = None,
        top_k: int = 5,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        搜索相似分块
        
        Args:
            query: 查询文本
            knowledge_base_id: 知识库ID
            top_k: 返回数量
            threshold: 相似度阈值
        
        Returns:
            相似分块列表
        """
        from app.models.knowledge import RagChunkModel, RagDocumentModel
        
        query_embedding = self.llm_service.get_embedding(query)
        
        if not query_embedding:
            logger.warning("Failed to get query embedding, returning empty results")
            return []
        
        chunk_query = self.db.query(RagChunkModel).filter(
            RagChunkModel.embedding.isnot(None)
        )
        
        if knowledge_base_id:
            chunk_query = chunk_query.join(RagDocumentModel).filter(
                RagDocumentModel.knowledge_base_id == knowledge_base_id
            )
        
        chunks = chunk_query.all()
        
        if not chunks:
            return []
        
        similarities = []
        for chunk in chunks:
            if chunk.embedding:
                sim = self.cosine_similarity(query_embedding, chunk.embedding)
                if sim >= threshold:
                    similarities.append({
                        "chunk_id": chunk.id,
                        "content": chunk.content,
                        "similarity": sim,
                        "document_id": chunk.document_id,
                    })
        
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        
        return similarities[:top_k]
    
    def rag_query(
        self,
        query: str,
        knowledge_base_id: int = None,
        top_k: int = 5,
        system_prompt: str = None
    ) -> Dict[str, Any]:
        """
        RAG查询：检索相关内容并生成回答
        
        Args:
            query: 用户问题
            knowledge_base_id: 知识库ID
            top_k: 检索数量
            system_prompt: 系统提示词
        
        Returns:
            查询结果
        """
        similar_chunks = self.search_similar_chunks(query, knowledge_base_id, top_k)
        
        if not similar_chunks:
            return {
                "success": False,
                "message": "No relevant content found in knowledge base",
                "answer": None,
                "sources": []
            }
        
        context = "\n\n---\n\n".join([chunk["content"] for chunk in similar_chunks])
        
        if not system_prompt:
            system_prompt = """你是一个专业的AI助手。请基于以下参考内容回答用户的问题。
如果参考内容中没有相关信息，请诚实地说明你不知道，不要编造答案。
回答时要简洁、准确、有帮助。

参考内容：
{context}"""
        
        full_system_prompt = system_prompt.format(context=context)
        
        answer = self.llm_service.call_llm(
            prompt=query,
            system_prompt=full_system_prompt,
            temperature=0.7
        )
        
        return {
            "success": True,
            "message": "Query processed successfully",
            "answer": answer,
            "sources": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "content": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
                    "similarity": round(chunk["similarity"], 3)
                }
                for chunk in similar_chunks
            ]
        }


class KnowledgeGraphExtractor:
    """知识图谱实体关系提取器 - 专注于测试依赖关系"""
    
    ENTITY_EXTRACTION_PROMPT = """你是一个测试自动化专家，正在构建用于WebUI自动化测试的知识图谱。

请从以下需求文档中提取系统模块和功能点，用于确定测试用例的前置条件关系。

文档内容：
{content}

提取规则：
1. 模块：系统的功能模块，如"登录"、"仪表板"、"知识库管理"、"测试用例管理"等
2. 功能：模块内的具体功能，如"创建知识库"、"上传文档"、"生成图谱"等
3. 页面：独立的页面，如"登录页"、"注册页"、"设置页"等

重要：重点关注用户操作流程和功能访问路径！

请以JSON数组格式返回，每个实体包含：
- name: 实体名称（简短，不超过8个字符）
- type: 实体类型（模块/功能/页面）
- description: 简短描述（不超过20个字符）
- requires_login: 是否需要登录才能访问（true/false）

示例：
```json
[
  {{"name": "登录", "type": "模块", "description": "用户登录验证", "requires_login": false}},
  {{"name": "仪表板", "type": "模块", "description": "系统概览页面", "requires_login": true}},
  {{"name": "知识库管理", "type": "模块", "description": "RAG知识库管理", "requires_login": true}},
  {{"name": "创建知识库", "type": "功能", "description": "新建知识库", "requires_login": true}}
]
```

只返回JSON数组，最多提取20个实体。"""

    RELATION_EXTRACTION_PROMPT = """你是一个测试自动化专家，正在分析功能模块之间的测试依赖关系。

已识别的实体：
{entities}

文档内容：
{content}

请分析实体之间的关系，重点关注测试执行的前置条件：

## 关系类型定义：

1. **前置条件**：要执行A必须先完成B（B是A的前置条件）
   
   核心规则：用户操作流程是 注册 → 登录 → 其他功能
   
   正确示例：
   - 登录的前置条件是注册（用户需要先注册账号才能登录）
   - 仪表板的前置条件是登录（未登录无法访问仪表板）
   - 创建知识库的前置条件是登录（未登录无法创建）
   
   错误示例：
   - 注册的前置条件是登录（错误！用户无需登录即可注册）
   
2. **包含**：模块A包含功能B（如：知识库管理包含创建知识库）

3. **依赖**：功能A依赖功能B的结果（如：生成图谱依赖上传文档）

## 重要规则：
- 用户流程：先注册账号 → 然后登录 → 再访问其他功能
- 登录的前置条件必须是注册（没有账号无法登录）
- 注册是公开功能，无前置条件
- 只有登录后的功能才需要"登录"作为前置条件

请以JSON数组格式返回，每个关系包含：
- source: 源实体名称（需要前置条件的实体）
- target: 目标实体名称（作为前置条件的实体）
- relation: 关系类型（前置条件/包含/依赖）

示例：
```json
[
  {{"source": "登录", "target": "注册", "relation": "前置条件"}},
  {{"source": "仪表板", "target": "登录", "relation": "前置条件"}},
  {{"source": "知识库管理", "target": "创建知识库", "relation": "包含"}},
  {{"source": "生成图谱", "target": "上传文档", "relation": "依赖"}}
]
```

只返回JSON数组，最多提取20个关系。"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    def extract_entities(self, content: str) -> List[Dict[str, str]]:
        """
        从文档内容中提取实体
        
        Args:
            content: 文档内容
        
        Returns:
            实体列表，每个实体包含 name, type, description, requires_login
        """
        truncated_content = content[:10000] if len(content) > 10000 else content
        
        # 获取LLM配置的max_tokens
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        # 实体提取需要较小输出空间，取配置值的10%
        extraction_max_tokens = min(int(config_max_tokens * 0.1), 2000)
        logger.info(f"实体提取max_tokens: 配置值{config_max_tokens}, 实际使用{extraction_max_tokens}")
        
        entities = self.llm_service.call_llm_json(
            prompt=self.ENTITY_EXTRACTION_PROMPT.format(content=truncated_content),
            temperature=0.3,
            max_tokens=extraction_max_tokens
        )
        
        if entities and isinstance(entities, list):
            valid_entities = []
            for e in entities:
                if isinstance(e, dict) and 'name' in e and 'type' in e:
                    valid_entities.append({
                        'name': str(e.get('name', ''))[:12],
                        'type': str(e.get('type', '模块'))[:10],
                        'description': str(e.get('description', ''))[:50],
                        'requires_login': e.get('requires_login', True)
                    })
            logger.info(f"Extracted {len(valid_entities)} entities from document")
            return valid_entities
        
        logger.warning("LLM extraction failed, using fallback regex method")
        return self._extract_entities_regex(content)
    
    def extract_relations(
        self, 
        content: str, 
        entities: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        从文档内容中提取实体之间的关系
        
        Args:
            content: 文档内容
            entities: 已识别的实体列表
        
        Returns:
            关系列表，每个关系包含 source, target, relation
        """
        if not entities or len(entities) < 2:
            return []
        
        entity_names = [e['name'] for e in entities]
        entity_str = '\n'.join([f"- {e['name']} ({e['type']})" for e in entities])
        truncated_content = content[:6000] if len(content) > 6000 else content
        
        llm_config = self.llm_service.get_active_config()
        config_max_tokens = llm_config.max_tokens if llm_config else 4000
        extraction_max_tokens = min(int(config_max_tokens * 0.1), 2000)
        
        relations = self.llm_service.call_llm_json(
            prompt=self.RELATION_EXTRACTION_PROMPT.format(
                entities=entity_str,
                content=truncated_content
            ),
            temperature=0.3,
            max_tokens=extraction_max_tokens
        )
        
        if relations and isinstance(relations, list):
            valid_relations = []
            for r in relations:
                if isinstance(r, dict) and 'source' in r and 'target' in r:
                    source = str(r.get('source', ''))
                    target = str(r.get('target', ''))
                    if source in entity_names and target in entity_names:
                        valid_relations.append({
                            'source': source,
                            'target': target,
                            'relation': str(r.get('relation', '关联'))[:10]
                        })
            logger.info(f"Extracted {len(valid_relations)} relations from document")
            return valid_relations
        
        logger.warning("LLM relation extraction failed, using fallback method")
        return self._extract_relations_fallback(entities)
    
    def _extract_entities_regex(self, content: str) -> List[Dict[str, str]]:
        """使用正则表达式作为备选方案提取实体"""
        entities = []
        seen = set()
        
        # 提取模块名称
        module_patterns = [
            r'[一二三四五六七八九十\d]+[、.．]\s*([^\n模块]{2,10})(模块|管理|配置|设置)',
            r'([^\n]{2,8})(模块|管理|配置)',
        ]
        
        for pattern in module_patterns:
            for match in re.finditer(pattern, content):
                name = match.group(1).strip()
                if name and 2 <= len(name) <= 8 and name not in seen:
                    seen.add(name)
                    entities.append({
                        'name': name,
                        'type': '模块',
                        'description': f'{name}模块',
                        'requires_login': True
                    })
        
        # 提取功能
        feature_pattern = r'功能[：:·\s]*([^\n，。]{2,8})'
        for match in re.finditer(feature_pattern, content):
            name = match.group(1).strip()
            if name and 2 <= len(name) <= 8 and name not in seen:
                seen.add(name)
                entities.append({
                    'name': name,
                    'type': '功能',
                    'description': f'{name}功能',
                    'requires_login': True
                })
        
        # 检查是否有登录相关模块
        login_keywords = ['登录', '注册', '忘记密码', '验证码']
        for keyword in login_keywords:
            if keyword in content and keyword not in seen:
                seen.add(keyword)
                entities.append({
                    'name': keyword,
                    'type': '模块',
                    'description': f'{keyword}功能',
                    'requires_login': False
                })
        
        # 如果实体太少，添加默认实体
        if len(entities) < 3:
            default_entities = [
                {'name': '登录', 'type': '模块', 'description': '用户登录验证', 'requires_login': False},
                {'name': '仪表板', 'type': '模块', 'description': '系统概览', 'requires_login': True},
                {'name': '知识库', 'type': '模块', 'description': 'RAG知识库管理', 'requires_login': True},
                {'name': '测试用例', 'type': '模块', 'description': '测试用例管理', 'requires_login': True},
                {'name': 'LLM配置', 'type': '模块', 'description': 'LLM模型配置', 'requires_login': True},
            ]
            for e in default_entities:
                if e['name'] not in seen:
                    entities.append(e)
        
        return entities[:20]
    
    def _extract_relations_fallback(
        self, 
        entities: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """备选方案：根据实体推断测试依赖关系"""
        relations = []
        
        # 找出登录模块
        login_entity = None
        other_entities = []
        for e in entities:
            if e['name'] in ['登录', 'Login', '登录验证']:
                login_entity = e
            else:
                other_entities.append(e)
        
        # 所有需要登录的模块，前置条件都是登录
        if login_entity:
            for e in other_entities:
                if e.get('requires_login', True):
                    relations.append({
                        'source': e['name'],
                        'target': login_entity['name'],
                        'relation': '前置条件'
                    })
        
        # 模块包含功能
        modules = [e for e in entities if e['type'] == '模块' and e != login_entity]
        features = [e for e in entities if e['type'] == '功能']
        
        for i, feature in enumerate(features):
            if i < len(modules):
                relations.append({
                    'source': modules[i]['name'],
                    'target': feature['name'],
                    'relation': '包含'
                })
        
        # 模块之间的顺序关系
        for i in range(len(modules) - 1):
            relations.append({
                'source': modules[i]['name'],
                'target': modules[i + 1]['name'],
                'relation': '关联'
            })
        
        return relations[:20]