"""
RAG知识库服务模块
处理文档上传、向量化、检索和生成
"""

import os
import hashlib
import json
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from sqlalchemy.orm import Session
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader, 
    TextLoader,
    UnstructuredFileLoader
)
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document as LangchainDocument
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.llms import OpenAI


from app.core.config import settings
from app.core.logger import logger
from app.models.rag import (
    RAGKnowledgeBase, 
    RAGDocument, 
    RAGQueryHistory,
    TestCaseFromRAG,
    MindMapFromRAG
)
from app.core.models.user import User


class RAGService:
    """RAG知识库服务"""
    
    def __init__(self, db: Session):
        self.db = db
        self.embeddings = None
        self.vector_store = None
        self.llm = None
        
    def _get_embeddings(self):
        """获取嵌入模型"""
        if self.embeddings is None:
            model_name = settings.EMBEDDING_MODEL or "sentence-transformers/all-MiniLM-L6-v2"
            self.embeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
        return self.embeddings
    
    def _get_llm(self):
        """获取LLM模型 - 支持多提供商"""
        if self.llm is None:
            provider = settings.LLM_PROVIDER.lower()
            
            if provider == "openai" and settings.OPENAI_API_KEY:
                self.llm = OpenAI(
                    openai_api_key=settings.OPENAI_API_KEY,
                    openai_api_base=settings.OPENAI_BASE_URL,
                    model_name=settings.OPENAI_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            elif provider == "deepseek" and settings.DEEPSEEK_API_KEY:
                # DeepSeek使用OpenAI兼容接口
                self.llm = OpenAI(
                    openai_api_key=settings.DEEPSEEK_API_KEY,
                    openai_api_base=settings.DEEPSEEK_BASE_URL,
                    model_name=settings.DEEPSEEK_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            elif provider == "minimax" and settings.MINIMAX_API_KEY:
                # MiniMax使用OpenAI兼容接口
                self.llm = OpenAI(
                    openai_api_key=settings.MINIMAX_API_KEY,
                    openai_api_base=settings.MINIMAX_BASE_URL,
                    model_name=settings.MINIMAX_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            elif provider == "zhipuai" and settings.ZHIPUAI_API_KEY:
                # 智谱AI使用OpenAI兼容接口
                self.llm = OpenAI(
                    openai_api_key=settings.ZHIPUAI_API_KEY,
                    openai_api_base=settings.ZHIPUAI_BASE_URL,
                    model_name=settings.ZHIPUAI_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            elif provider == "moonshot" and settings.MOONSHOT_API_KEY:
                # Moonshot使用OpenAI兼容接口
                self.llm = OpenAI(
                    openai_api_key=settings.MOONSHOT_API_KEY,
                    openai_api_base=settings.MOONSHOT_BASE_URL,
                    model_name=settings.MOONSHOT_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            elif provider == "custom" and settings.CUSTOM_API_KEY:
                # 自定义LLM提供商
                self.llm = OpenAI(
                    openai_api_key=settings.CUSTOM_API_KEY,
                    openai_api_base=settings.CUSTOM_BASE_URL or "https://api.openai.com/v1",
                    model_name=settings.CUSTOM_MODEL or "gpt-3.5-turbo",
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS
                )
            else:
                # 如果没有配置任何API Key，尝试使用本地模型或返回None
                logger.warning(f"未配置LLM提供商 '{provider}' 的API密钥，将使用本地模型或禁用LLM功能")
                try:
                    from langchain_community.llms import HuggingFacePipeline
                    # 这里可以配置本地模型
                    self.llm = None
                except Exception as e:
                    logger.error(f"初始化本地模型失败: {str(e)}")
                    self.llm = None
                    
        return self.llm
    
    def upload_document(
        self,
        file_path: str,
        project_name: str,
        version: str,
        name: str = None,
        description: str = None,
        user: User = None
    ) -> RAGKnowledgeBase:
        """
        上传文档到知识库
        
        Args:
            file_path: 文件路径
            project_name: 项目名称
            version: 项目版本
            name: 知识库名称（可选）
            description: 描述（可选）
            user: 上传用户（可选）
            
        Returns:
            RAGKnowledgeBase: 创建的知识库记录
        """
        try:
            # 获取文件信息
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            file_name = file_path_obj.name
            file_size = file_path_obj.stat().st_size
            file_type = file_path_obj.suffix.lower().lstrip('.')
            
            # 创建知识库记录
            kb = RAGKnowledgeBase(
                name=name or f"{project_name}_{version}",
                description=description or f"{project_name} {version} 需求文档",
                project_name=project_name,
                version=version,
                file_name=file_name,
                file_path=str(file_path),
                file_size=file_size,
                file_type=file_type,
                status="pending",
                processing_progress=0.0,
                created_by_id=user.id if user else None
            )
            
            self.db.add(kb)
            self.db.commit()
            self.db.refresh(kb)
            
            logger.info(f"创建知识库记录: {kb.id} - {kb.name}")
            
            # 异步处理文档（这里简化处理，实际应该使用后台任务）
            self._process_document_async(kb)
            
            return kb
            
        except Exception as e:
            logger.error(f"上传文档失败: {str(e)}")
            raise
    
    def _process_document_async(self, kb: RAGKnowledgeBase):
        """异步处理文档（这里简化实现）"""
        try:
            # 更新状态为处理中
            kb.status = "processing"
            kb.processing_progress = 10.0
            self.db.commit()
            
            # 加载文档
            documents = self._load_document(kb.file_path, kb.file_type)
            
            # 更新进度
            kb.processing_progress = 30.0
            self.db.commit()
            
            # 分块
            chunks = self._split_documents(documents)
            
            # 更新进度
            kb.processing_progress = 60.0
            self.db.commit()
            
            # 向量化并存储
            vector_store_path = self._create_vector_store(kb, chunks)
            
            # 更新进度和状态
            kb.status = "completed"
            kb.processing_progress = 100.0
            kb.vector_store_path = vector_store_path
            kb.embedding_model = settings.EMBEDDING_MODEL or "sentence-transformers/all-MiniLM-L6-v2"
            kb.chunk_size = settings.CHUNK_SIZE or 1000
            kb.chunk_overlap = settings.CHUNK_OVERLAP or 200
            kb.total_chunks = len(chunks)
            
            self.db.commit()
            
            logger.info(f"文档处理完成: {kb.id} - 总块数: {len(chunks)}")
            
        except Exception as e:
            logger.error(f"文档处理失败: {str(e)}")
            kb.status = "failed"
            kb.error_message = str(e)
            self.db.commit()
    
    def _load_document(self, file_path: str, file_type: str) -> List[LangchainDocument]:
        """加载文档"""
        try:
            if file_type == "pdf":
                loader = PyPDFLoader(file_path)
            elif file_type in ["doc", "docx"]:
                loader = UnstructuredFileLoader(file_path)
            elif file_type == "txt":
                loader = TextLoader(file_path, encoding="utf-8")
            else:
                # 使用通用加载器
                loader = UnstructuredFileLoader(file_path)
            
            documents = loader.load()
            logger.info(f"加载文档成功: {len(documents)} 页/部分")
            return documents
            
        except Exception as e:
            logger.error(f"加载文档失败: {str(e)}")
            raise
    
    def _split_documents(self, documents: List[LangchainDocument]) -> List[LangchainDocument]:
        """文档分块"""
        try:
            chunk_size = settings.CHUNK_SIZE or 1000
            chunk_overlap = settings.CHUNK_OVERLAP or 200
            
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
            )
            
            chunks = text_splitter.split_documents(documents)
            logger.info(f"文档分块完成: {len(chunks)} 块")
            return chunks
            
        except Exception as e:
            logger.error(f"文档分块失败: {str(e)}")
            raise
    
    def _create_vector_store(self, kb: RAGKnowledgeBase, chunks: List[LangchainDocument]) -> str:
        """创建向量存储"""
        try:
            # 创建存储目录
            vector_store_dir = Path(settings.VECTOR_DB_PATH) / f"kb_{kb.id}"
            vector_store_dir.mkdir(parents=True, exist_ok=True)
            
            # 添加元数据
            for i, chunk in enumerate(chunks):
                chunk.metadata["knowledge_base_id"] = kb.id
                chunk.metadata["chunk_index"] = i
                chunk.metadata["project_name"] = kb.project_name
                chunk.metadata["version"] = kb.version
            
            # 创建向量存储
            embeddings = self._get_embeddings()
            vector_store = Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=str(vector_store_dir),
                collection_name=f"kb_{kb.id}"
            )
            
            # 持久化
            vector_store.persist()
            
            # 保存分块到数据库
            for i, chunk in enumerate(chunks):
                chunk_hash = hashlib.sha256(chunk.page_content.encode()).hexdigest()
                
                rag_doc = RAGDocument(
                    knowledge_base_id=kb.id,
                    chunk_index=i,
                    chunk_text=chunk.page_content,
                    chunk_hash=chunk_hash,
                    extra_metadata=chunk.metadata,
                    embedding_model=kb.embedding_model
                )
                self.db.add(rag_doc)
            
            self.db.commit()
            
            logger.info(f"向量存储创建完成: {vector_store_dir}")
            return str(vector_store_dir)
            
        except Exception as e:
            logger.error(f"创建向量存储失败: {str(e)}")
            raise
    
    def query_knowledge_base(
        self,
        kb_id: int,
        query: str,
        query_type: str = "general",
        top_k: int = 5,
        user: User = None
    ) -> Dict[str, Any]:
        """
        查询知识库
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            query_type: 查询类型
            top_k: 返回结果数量
            user: 查询用户
            
        Returns:
            查询结果
        """
        try:
            start_time = datetime.now()
            
            # 获取知识库
            kb = self.db.query(RAGKnowledgeBase).filter(
                RAGKnowledgeBase.id == kb_id,
                RAGKnowledgeBase.deleted_at.is_(None)
            ).first()
            
            if not kb:
                raise ValueError(f"知识库不存在: {kb_id}")
            
            if kb.status != "completed":
                raise ValueError(f"知识库状态不可用: {kb.status}")
            
            # 加载向量存储
            vector_store_path = Path(kb.vector_store_path)
            if not vector_store_path.exists():
                raise FileNotFoundError(f"向量存储不存在: {vector_store_path}")
            
            embeddings = self._get_embeddings()
            vector_store = Chroma(
                persist_directory=str(vector_store_path),
                embedding_function=embeddings,
                collection_name=f"kb_{kb_id}"
            )
            
            # 检索相似文档
            retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
            retrieved_docs = retriever.get_relevant_documents(query)
            
            retrieval_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # 记录查询历史
            query_history = RAGQueryHistory(
                knowledge_base_id=kb_id,
                query_text=query,
                query_type=query_type,
                retrieved_chunks=[doc.metadata.get("chunk_index") for doc in retrieved_docs],
                similarity_scores=[],  # 这里可以计算相似度分数
                retrieval_time_ms=retrieval_time,
                user_id=user.id if user else None
            )
            
            self.db.add(query_history)
            self.db.commit()
            self.db.refresh(query_history)
            
            # 根据查询类型生成响应
            response_text = ""
            generated_content = ""
            generation_time_ms = 0
            
            if query_type == "test_case":
                generated_content = self._generate_test_cases(kb, query, retrieved_docs)
                generation_time_ms = (datetime.now() - start_time).total_seconds() * 1000 - retrieval_time
                response_text = "已生成测试用例"
            elif query_type == "mind_map":
                generated_content = self._generate_mind_map(kb, query, retrieved_docs)
                generation_time_ms = (datetime.now() - start_time).total_seconds() * 1000 - retrieval_time
                response_text = "已生成思维导图"
            else:
                # 通用查询
                llm = self._get_llm()
                if llm:
                    qa_chain = RetrievalQA.from_chain_type(
                        llm=llm,
                        chain_type="stuff",
                        retriever=retriever,
                        return_source_documents=True
                    )
                    
                    generation_start = datetime.now()
                    result = qa_chain({"query": query})
                    generation_time_ms = (datetime.now() - generation_start).total_seconds() * 1000
                    
                    response_text = result["result"]
                    generated_content = response_text
                else:
                    # 如果没有LLM，返回检索结果
                    response_text = "\n\n".join([doc.page_content for doc in retrieved_docs])
                    generated_content = response_text
            
            # 更新查询历史
            total_time_ms = retrieval_time + generation_time_ms
            query_history.response_text = response_text
            query_history.generated_content = generated_content
            query_history.generation_time_ms = generation_time_ms
            query_history.total_time_ms = total_time_ms
            
            self.db.commit()
            
            return {
                "query_id": query_history.id,
                "knowledge_base": {
                    "id": kb.id,
                    "name": kb.name,
                    "project_name": kb.project_name,
                    "version": kb.version
                },
                "query": query,
                "response": response_text,
                "generated_content": generated_content,
                "retrieved_documents": [
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": 0.0  # 这里可以添加相似度分数
                    }
                    for doc in retrieved_docs
                ],
                "performance": {
                    "retrieval_time_ms": retrieval_time,
                    "generation_time_ms": generation_time_ms,
                    "total_time_ms": total_time_ms
                }
            }
            
        except Exception as e:
            logger.error(f"查询知识库失败: {str(e)}")
            raise
    
    def _generate_test_cases(
        self, 
        kb: RAGKnowledgeBase, 
        query: str, 
        retrieved_docs: List[LangchainDocument]
    ) -> str:
        """生成测试用例"""
        try:
            # 构建提示词
            context = "\n\n".join([doc.page_content for doc in retrieved_docs])
            
            prompt_template = PromptTemplate(
                input_variables=["project_name", "version", "query", "context"],
                template="""
                基于以下需求文档内容，为项目 {project_name} 版本 {version} 生成测试用例。
                
                用户查询: {query}
                
                相关文档内容:
                {context}
                
                请生成详细的测试用例，包括：
                1. 测试用例ID（格式：TC-项目缩写-序号）
                2. 测试用例标题
                3. 测试用例描述
                4. 优先级（low/medium/high/critical）
                5. 测试类别（功能测试/性能测试/安全测试等）
                6. 前置条件
                7. 测试步骤（详细步骤）
                8. 预期结果
                9. 相关标签
                
                请以JSON数组格式返回，每个测试用例是一个JSON对象。
                """
            )
            
            prompt = prompt_template.format(
                project_name=kb.project_name,
                version=kb.version,
                query=query,
                context=context[:5000]  # 限制上下文长度
            )
            
            llm = self._get_llm()
            if llm:
                response = llm(prompt)
                
                # 解析响应并保存测试用例
                try:
                    test_cases = json.loads(response)
                    if isinstance(test_cases, list):
                        for i, tc_data in enumerate(test_cases):
                            test_case = TestCaseFromRAG(
                                knowledge_base_id=kb.id,
                                test_case_id=tc_data.get("test_case_id", f"TC-{kb.project_name[:3].upper()}-{i+1:03d}"),
                                title=tc_data.get("title", f"测试用例 {i+1}"),
                                description=tc_data.get("description", ""),
                                priority=tc_data.get("priority", "medium"),
                                category=tc_data.get("category", "功能测试"),
                                preconditions=tc_data.get("preconditions", ""),
                                test_steps=tc_data.get("test_steps", []),
                                expected_results=tc_data.get("expected_results", ""),
                                tags=tc_data.get("tags", []),
                                requirements=tc_data.get("requirements", [])
                            )
                            self.db.add(test_case)
                        
                        self.db.commit()
                
                except json.JSONDecodeError:
                    logger.warning("无法解析测试用例JSON响应")
                
                return response
            else:
                return "LLM不可用，无法生成测试用例"
                
        except Exception as e:
            logger.error(f"生成测试用例失败: {str(e)}")
            return f"生成测试用例失败: {str(e)}"
    
    def _generate_mind_map(
        self, 
        kb: RAGKnowledgeBase, 
        query: str, 
        retrieved_docs: List[LangchainDocument]
    ) -> str:
        """生成思维导图"""
        try:
            # 构建提示词
            context = "\n\n".join([doc.page_content for doc in retrieved_docs])
            
            prompt_template = PromptTemplate(
                input_variables=["project_name", "version", "query", "context"],
                template="""
                基于以下需求文档内容，为项目 {project_name} 版本 {version} 生成思维导图结构。
                
                用户查询: {query}
                
                相关文档内容:
                {context}
                
                请生成思维导图的结构，以XMIND格式的JSON表示。
                思维导图应该包括：
                1. 中心主题（项目名称和版本）
                2. 主要功能模块作为一级分支
                3. 每个功能模块下的子功能作为二级分支
                4. 关键需求点作为三级分支
                5. 测试关注点作为叶子节点
                
                返回格式示例:
                {{
                  "title": "项目思维导图",
                  "centralTopic": "{project_name} {version}",
                  "branches": [
                    {{
                      "topic": "功能模块1",
                      "children": [
                        {{
                          "topic": "子功能1.1",
                          "children": [
                            {{"topic": "需求点1.1.1"}},
                            {{"topic": "测试点1.1.1"}}
                          ]
                        }}
                      ]
                    }}
                  ]
                }}
                """
            )
            
            prompt = prompt_template.format(
                project_name=kb.project_name,
                version=kb.version,
                query=query,
                context=context[:5000]  # 限制上下文长度
            )
            
            llm = self._get_llm()
            if llm:
                response = llm(prompt)
                
                # 解析响应并保存思维导图
                try:
                    mind_map_data = json.loads(response)
                    mind_map = MindMapFromRAG(
                        knowledge_base_id=kb.id,
                        title=mind_map_data.get("title", f"{kb.project_name} {kb.version} 思维导图"),
                        description=f"基于需求文档生成的思维导图",
                        mind_map_data=mind_map_data,
                        format="xmind"
                    )
                    self.db.add(mind_map)
                    self.db.commit()
                
                except json.JSONDecodeError:
                    logger.warning("无法解析思维导图JSON响应")
                
                return response
            else:
                return "LLM不可用，无法生成思维导图"
                
        except Exception as e:
            logger.error(f"生成思维导图失败: {str(e)}")
            return f"生成思维导图失败: {str(e)}"
    
    def get_knowledge_bases(
        self,
        project_name: str = None,
        status: str = None,
        user_id: int = None
    ) -> List[RAGKnowledgeBase]:
        """获取知识库列表"""
        query = self.db.query(RAGKnowledgeBase).filter(
            RAGKnowledgeBase.deleted_at.is_(None)
        )
        
        if project_name:
            query = query.filter(RAGKnowledgeBase.project_name.ilike(f"%{project_name}%"))
        
        if status:
            query = query.filter(RAGKnowledgeBase.status == status)
        
        if user_id:
            query = query.filter(RAGKnowledgeBase.created_by_id == user_id)
        
        return query.order_by(RAGKnowledgeBase.created_at.desc()).all()
    
    def get_knowledge_base(self, kb_id: int) -> Optional[RAGKnowledgeBase]:
        """获取知识库详情"""
        return self.db.query(RAGKnowledgeBase).filter(
            RAGKnowledgeBase.id == kb_id,
            RAGKnowledgeBase.deleted_at.is_(None)
        ).first()
    
    def delete_knowledge_base(self, kb_id: int) -> bool:
        """软删除知识库"""
        kb = self.get_knowledge_base(kb_id)
        if not kb:
            return False
        
        kb.deleted_at = datetime.now()
        self.db.commit()
        
        # 可选：删除向量存储文件
        try:
            if kb.vector_store_path and Path(kb.vector_store_path).exists():
                import shutil
                shutil.rmtree(kb.vector_store_path)
        except Exception as e:
            logger.warning(f"删除向量存储文件失败: {str(e)}")
        
        return True
    
    def get_query_history(
        self,
        kb_id: int = None,
        user_id: int = None,
        limit: int = 100
    ) -> List[RAGQueryHistory]:
        """获取查询历史"""
        query = self.db.query(RAGQueryHistory)
        
        if kb_id:
            query = query.filter(RAGQueryHistory.knowledge_base_id == kb_id)
        
        if user_id:
            query = query.filter(RAGQueryHistory.user_id == user_id)
        
        return query.order_by(RAGQueryHistory.created_at.desc()).limit(limit).all()
    
    def get_test_cases_from_rag(
        self,
        kb_id: int = None,
        status: str = None
    ) -> List[TestCaseFromRAG]:
        """获取从RAG生成的测试用例"""
        query = self.db.query(TestCaseFromRAG)
        
        if kb_id:
            query = query.filter(TestCaseFromRAG.knowledge_base_id == kb_id)
        
        if status:
            query = query.filter(TestCaseFromRAG.status == status)
        
        return query.order_by(TestCaseFromRAG.created_at.desc()).all()
    
    def get_mind_maps_from_rag(self, kb_id: int = None) -> List[MindMapFromRAG]:
        """获取从RAG生成的思维导图"""
        query = self.db.query(MindMapFromRAG)
        
        if kb_id:
            query = query.filter(MindMapFromRAG.knowledge_base_id == kb_id)
        
        return query.order_by(MindMapFromRAG.created_at.desc()).all()