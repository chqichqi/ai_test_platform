"""
向量数据库服务 - ChromaDB集成
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.documents import Document as LangchainDocument

from app.core.config import settings
from app.core.logger import logger


class VectorService:
    """向量数据库服务类"""
    
    def __init__(self):
        self._ready = False
        self.vector_db_path = Path(settings.VECTOR_DB_PATH)
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        self.chroma_client = None
        self.collection = None
        self.embedding_function = None
        # 延迟初始化——只有RAG功能调用时才触发模型下载
        # 生成功功能流不依赖ChromaDB

    def _ensure_ready(self):
        if self._ready:
            return
        try:
            self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.vector_db_path),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True)
            )
            self.collection = self.chroma_client.get_or_create_collection(
                name="documents",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            self._ready = True
            logger.info(f"Vector service initialized. Collection: {self.collection.name}")
        except Exception as e:
            logger.warning(f"Vector service not available: {e}")
    
    def get_embedding(self, text: str) -> List[float]:
        self._ensure_ready()
        """
        获取文本的嵌入向量
        
        Args:
            text: 文本内容
            
        Returns:
            嵌入向量列表
        """
        try:
            # 使用ChromaDB的嵌入函数
            embeddings = self.embedding_function([text])
            return embeddings[0] if embeddings else []
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            # 返回空向量作为降级方案
            return [0.0] * 384  # 默认嵌入维度
    
    def load_document(self, file_path: str) -> List[LangchainDocument]:
        """
        加载文档内容
        
        Args:
            file_path: 文档文件路径
            
        Returns:
            文档内容列表
        """
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()
        
        try:
            if file_ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif file_ext == ".txt":
                loader = TextLoader(file_path, encoding="utf-8")
            elif file_ext in [".doc", ".docx"]:
                loader = Docx2txtLoader(file_path)
            elif file_ext == ".md":
                loader = UnstructuredMarkdownLoader(file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")
            
            documents = loader.load()
            logger.info(f"Loaded {len(documents)} document(s) from {file_path}")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to load document {file_path}: {str(e)}")
            raise
    
    def split_documents(self, documents: List[LangchainDocument]) -> List[LangchainDocument]:
        """
        分割文档为小块
        
        Args:
            documents: 文档列表
            
        Returns:
            分割后的文档块列表
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
        )
        
        chunks = text_splitter.split_documents(documents)
        logger.info(f"Split {len(documents)} document(s) into {len(chunks)} chunk(s)")
        return chunks
    
    def process_and_store_document(self, file_path: str, document_id: str, metadata: Dict[str, Any] = None) -> int:
        """
        处理文档并存储到向量数据库
        
        Args:
            file_path: 文档文件路径
            document_id: 文档ID
            metadata: 文档元数据
            
        Returns:
            存储的块数量
        """
        try:
            # 加载文档
            documents = self.load_document(file_path)
            
            # 分割文档
            chunks = self.split_documents(documents)
            
            if not chunks:
                logger.warning(f"No chunks generated from document: {file_path}")
                return 0
            
            # 准备数据用于存储
            ids = []
            metadatas = []
            documents_text = []
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"{document_id}_{i}"
                chunk_text = chunk.page_content
                
                # 准备元数据
                chunk_metadata = {
                    "document_id": document_id,
                    "chunk_index": i,
                    "source": str(file_path),
                    "total_chunks": len(chunks),
                }
                
                if metadata:
                    chunk_metadata.update(metadata)
                
                ids.append(chunk_id)
                metadatas.append(chunk_metadata)
                documents_text.append(chunk_text)
            
            # 存储到向量数据库 - ChromaDB会自动生成嵌入向量
            self.collection.add(
                ids=ids,
                metadatas=metadatas,
                documents=documents_text
            )
            
            logger.info(f"Stored {len(chunks)} chunks for document {document_id}")
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Failed to process and store document {file_path}: {str(e)}")
            raise
    
    def search_similar(self, query: str, document_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        self._ensure_ready()
        """
        搜索相似的文档块
        
        Args:
            query: 查询文本
            document_id: 文档ID（可选，用于限制搜索范围）
            top_k: 返回的最相似结果数量
            
        Returns:
            相似文档块列表
        """
        try:
            # 构建查询过滤器
            where_filter = None
            if document_id:
                where_filter = {"document_id": document_id}
            
            # 执行搜索 - ChromaDB会自动为查询生成嵌入向量
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
                include=["metadatas", "documents", "distances"]
            )
            
            # 格式化结果
            formatted_results = []
            if results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    formatted_results.append({
                        "id": results["ids"][0][i],
                        "document_id": results["metadatas"][0][i].get("document_id"),
                        "chunk_index": results["metadatas"][0][i].get("chunk_index"),
                        "content": results["documents"][0][i],
                        "score": 1 - results["distances"][0][i],  # 转换为相似度分数
                        "metadata": results["metadatas"][0][i]
                    })
            
            logger.info(f"Search completed for query: '{query[:50]}...'. Found {len(formatted_results)} results.")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search similar documents: {str(e)}")
            raise
    
    def delete_document_chunks(self, document_id: str) -> bool:
        """
        删除指定文档的所有块
        
        Args:
            document_id: 文档ID
            
        Returns:
            是否成功删除
        """
        try:
            # 查询该文档的所有块
            results = self.collection.get(
                where={"document_id": document_id},
                include=["metadatas"]
            )
            
            if results["ids"]:
                # 删除这些块
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} chunks for document {document_id}")
                return True
            else:
                logger.info(f"No chunks found for document {document_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete document chunks {document_id}: {str(e)}")
            raise
    
    def get_document_chunks_count(self, document_id: str) -> int:
        """
        获取指定文档的块数量
        
        Args:
            document_id: 文档ID
            
        Returns:
            块数量
        """
        try:
            results = self.collection.get(
                where={"document_id": document_id},
                include=["metadatas"]
            )
            return len(results["ids"])
        except Exception as e:
            logger.error(f"Failed to get document chunks count {document_id}: {str(e)}")
            return 0
    
    def clear_collection(self) -> bool:
        self._ensure_ready()
        """
        清空整个集合
        
        Returns:
            是否成功清空
        """
        try:
            self.chroma_client.delete_collection(name="documents")
            self.collection = self.chroma_client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("Collection cleared and recreated")
            return True
        except Exception as e:
            logger.error(f"Failed to clear collection: {str(e)}")
            raise


    # ====== Feature→TestCase 映射（用于变更管理去重） ======
    def get_feature_collection(self):
        self._ensure_ready()
        """获取或创建 feature→test_case 映射集合"""
        try:
            return self.chroma_client.get_collection("test_case_features")
        except Exception:
            return self.chroma_client.create_collection(
                name="test_case_features",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )

    def upsert_feature(self, version_id: int, feature_key: str, feature_name: str,
                       module: str, test_case_ids: list):
        self._ensure_ready()
        """记录一个 feature 及其生成的用例 ID（用于后续去重匹配）"""
        try:
            coll = self.get_feature_collection()
            doc_id = f"v{version_id}_{feature_key}"
            metadata = {
                "version_id": version_id,
                "feature_key": feature_key,
                "feature_name": feature_name,
                "module": module,
                "test_case_ids": ",".join(str(x) for x in test_case_ids),
                "test_case_count": len(test_case_ids),
            }
            coll.upsert(
                ids=[doc_id],
                documents=[feature_name],
                metadatas=[metadata],
            )
            logger.info(f"[FeatureDB] upsert: {feature_key} → {len(test_case_ids)} cases")
        except Exception as e:
            logger.warning(f"[FeatureDB] upsert failed: {e}")

    def search_feature(self, version_id: int, feature_name: str):
        self._ensure_ready()
        """语义搜索：查找 version 下是否已有相似的 feature"""
        try:
            coll = self.get_feature_collection()
            results = coll.query(
                query_texts=[feature_name],
                n_results=3,
                where={"version_id": version_id},
            )
            if results and results["ids"] and results["ids"][0]:
                distances = results.get("distances", [[1.0]])[0]
                for i, dist in enumerate(distances):
                    if dist < 0.85:  # 余弦距离 < 0.85 = 相似度 > 0.15
                        meta = results["metadatas"][0][i]
                        return {
                            "feature_key": meta.get("feature_key", ""),
                            "test_case_ids": [int(x) for x in meta.get("test_case_ids", "").split(",") if x],
                            "similarity": round(1 - dist, 2),
                        }
            return None
        except Exception as e:
            logger.warning(f"[FeatureDB] search failed: {e}")
            return None

    def get_version_features(self, version_id: int) -> list:
        self._ensure_ready()
        """获取版本下所有已记录的 feature keys"""
        try:
            coll = self.get_feature_collection()
            results = coll.get(where={"version_id": version_id})
            if results and results["ids"]:
                return [
                    {"feature_key": results["metadatas"][i].get("feature_key", ""),
                     "test_case_ids": results["metadatas"][i].get("test_case_ids", "")}
                    for i in range(len(results["ids"]))
                ]
            return []
        except Exception:
            return []

    def mark_deprecated_features(self, version_id: int, active_keys: set):
        """标记不再活跃的 feature（本次未生成→可能已过时）"""
        all_features = self.get_version_features(version_id)
        deprecated = [f for f in all_features if f["feature_key"] not in active_keys]
        if deprecated:
            logger.info(f"[FeatureDB] {len(deprecated)} deprecated features detected")
        return deprecated


# 创建全局实例
vector_service = None

def get_vector_service() -> VectorService:
    """获取向量服务实例"""
    global vector_service
    if vector_service is None:
        vector_service = VectorService()
    return vector_service