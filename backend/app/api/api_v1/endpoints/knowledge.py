"""
知识管理API端点
包含RAG知识库和知识图谱管理
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import base64
import re
import io

from app.core.database import get_db
from app.core.logger import logger
from app.core.responses import success_response, error_response
from app.core.services.llm_service import LLMService, KnowledgeGraphExtractor
from app.models.knowledge import (
    RagKnowledgeBaseModel, RagDocumentModel, RagChunkModel,
    KnowledgeGraphModel, GraphEntityModel, GraphRelationModel
)
from app.core.schemas.knowledge import (
    RagKnowledgeBaseCreate, RagKnowledgeBaseUpdate, RagKnowledgeBaseResponse,
    RagDocumentCreate, RagDocumentResponse,
    KnowledgeGraphCreate, KnowledgeGraphResponse, KnowledgeGraphDetailResponse,
    KnowledgeStatisticsResponse
)
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


def _is_base64_file(content: str) -> bool:
    """检测内容是否为base64编码的文件"""
    if not content or len(content) < 100:
        return False
    
    if not re.match(r'^[A-Za-z0-9+/=]+$', content[:500]):
        return False
    
    try:
        decoded = base64.b64decode(content[:100])
        if decoded.startswith(b'PK\x03\x04'):
            return True
        if decoded.startswith(b'%PDF'):
            return True
        if b'word/' in decoded[:500]:
            return True
    except:
        pass
    
    return False


def _parse_file_content(content: str) -> str:
    """解析文件内容，处理 [FILE:type:base64] 格式或纯base64格式"""
    if not content:
        return content
    
    if content.startswith("[FILE:"):
        match = re.match(r"\[FILE:(\w+):([A-Za-z0-9+/=]+)\]", content)
        if match:
            file_type = match.group(1)
            base64_data = match.group(2)
            return _decode_file_content(file_type, base64_data)
        return content
    
    if re.match(r'^[A-Za-z0-9+/=]{100,}$', content):
        file_type = "unknown"
        try:
            decoded = base64.b64decode(content[:100])
            if decoded.startswith(b'PK\x03\x04'):
                file_type = "docx"
            elif decoded.startswith(b'%PDF'):
                file_type = "pdf"
            elif b'word/' in decoded[:500]:
                file_type = "docx"
            
            if file_type != "unknown":
                return _decode_file_content(file_type, content)
        except:
            pass
    
    return content


def _decode_file_content(file_type: str, base64_data: str) -> str:
    """解码并提取文件文本内容"""
    try:
        binary_data = base64.b64decode(base64_data)
        
        if file_type == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(binary_data))
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            logger.info(f"Parsed PDF, extracted {len(text)} characters")
            return text
        
        elif file_type in ["docx", "doc"]:
            from docx import Document
            doc = Document(io.BytesIO(binary_data))
            text = "\n".join([para.text for para in doc.paragraphs if para.text])
            logger.info(f"Parsed DOCX, extracted {len(text)} characters")
            return text
        
    except Exception as e:
        logger.error(f"Failed to parse {file_type} file: {str(e)}")
        return f"[解析失败: {file_type} 文件]"
    
    return ""


def _get_or_create_user(db: Session):
    """获取或创建默认用户（临时方案）"""
    from app.core.models.user import User
    user = db.query(User).first()
    if not user:
        user = User(
            username="default_user",
            email="default@example.com",
            hashed_password="dummy",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/rag", response_model=dict)
async def list_rag_knowledge_bases(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """获取RAG知识库列表"""
    try:
        query = db.query(RagKnowledgeBaseModel).filter(RagKnowledgeBaseModel.deleted_at == None)
        
        if search:
            query = query.filter(
                RagKnowledgeBaseModel.name.ilike(f"%{search}%") |
                RagKnowledgeBaseModel.project.ilike(f"%{search}%")
            )
        
        total = query.count()
        items = query.order_by(RagKnowledgeBaseModel.updated_at.desc()).offset(skip).limit(limit).all()
        
        return success_response(
            data={
                "items": [
                    {
                        "id": str(item.id),
                        "name": item.name,
                        "description": item.description or "",
                        "project": item.project,
                        "version": item.version,
                        "documentCount": item.document_count,
                        "chunkCount": item.chunk_count,
                        "status": item.status,
                        "hasGraph": item.has_graph,
                        "chunkSize": item.chunk_size,
                        "chunkMethod": item.chunk_method,
                        "embeddingModel": item.embedding_model,
                        "createdAt": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
                        "updatedAt": item.updated_at.strftime("%Y-%m-%d %H:%M:%S") if item.updated_at else "",
                    }
                    for item in items
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        )
    except Exception as e:
        logger.error(f"Failed to list RAG knowledge bases: {str(e)}")
        return error_response(code=500, message="Failed to list knowledge bases", error=str(e))


@router.post("/rag", response_model=dict)
async def create_rag_knowledge_base(
    data: RagKnowledgeBaseCreate,
    db: Session = Depends(get_db),
):
    """创建RAG知识库"""
    try:
        user = _get_or_create_user(db)
        
        kb = RagKnowledgeBaseModel(
            name=data.name,
            description=data.description or "",
            project=data.name.lower().replace(" ", "-"),
            version="v1.0.0",
            document_count=0,
            chunk_count=0,
            status="inactive",
            has_graph=False,
            chunk_size=data.chunk_size,
            chunk_method=data.chunk_method,
            embedding_model=data.embedding_model,
            created_by_id=user.id,
        )
        
        db.add(kb)
        db.commit()
        db.refresh(kb)
        
        logger.info(f"Created RAG knowledge base: {kb.id} - {kb.name}")
        
        return success_response(
            data={
                "id": str(kb.id),
                "name": kb.name,
                "description": kb.description,
                "project": kb.project,
                "version": kb.version,
                "documentCount": kb.document_count,
                "chunkCount": kb.chunk_count,
                "status": kb.status,
                "hasGraph": kb.has_graph,
                "createdAt": kb.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
            message="Knowledge base created successfully",
            status_code=status.HTTP_201_CREATED,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create RAG knowledge base: {str(e)}")
        return error_response(code=500, message="Failed to create knowledge base", error=str(e))


@router.get("/rag/{kb_id}", response_model=dict)
async def get_rag_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
):
    """获取RAG知识库详情"""
    try:
        kb = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.id == kb_id,
            RagKnowledgeBaseModel.deleted_at == None
        ).first()
        
        if not kb:
            return error_response(code=404, message="Knowledge base not found")
        
        documents = db.query(RagDocumentModel).filter(
            RagDocumentModel.knowledge_base_id == kb_id
        ).all()
        
        return success_response(
            data={
                "id": str(kb.id),
                "name": kb.name,
                "description": kb.description or "",
                "project": kb.project,
                "version": kb.version,
                "documentCount": kb.document_count,
                "chunkCount": kb.chunk_count,
                "status": kb.status,
                "hasGraph": kb.has_graph,
                "chunkSize": kb.chunk_size,
                "chunkMethod": kb.chunk_method,
                "embeddingModel": kb.embedding_model,
                "createdAt": kb.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "documents": [
                    {
                        "id": str(doc.id),
                        "name": doc.name,
                        "type": doc.type,
                        "size": doc.size,
                        "content": doc.content,
                        "status": doc.status,
                        "uploadTime": doc.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    for doc in documents
                ]
            }
        )
    except Exception as e:
        logger.error(f"Failed to get RAG knowledge base: {str(e)}")
        return error_response(code=500, message="Failed to get knowledge base", error=str(e))


@router.put("/rag/{kb_id}", response_model=dict)
async def update_rag_knowledge_base(
    kb_id: int,
    data: RagKnowledgeBaseUpdate,
    db: Session = Depends(get_db),
):
    """更新RAG知识库"""
    try:
        kb = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.id == kb_id,
            RagKnowledgeBaseModel.deleted_at == None
        ).first()
        
        if not kb:
            return error_response(code=404, message="Knowledge base not found")
        
        if data.name is not None:
            kb.name = data.name
        if data.description is not None:
            kb.description = data.description
        if data.status is not None:
            kb.status = data.status
        
        db.commit()
        db.refresh(kb)
        
        return success_response(
            data={
                "id": str(kb.id),
                "name": kb.name,
                "description": kb.description,
                "status": kb.status,
                "updatedAt": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
            message="Knowledge base updated successfully",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update RAG knowledge base: {str(e)}")
        return error_response(code=500, message="Failed to update knowledge base", error=str(e))


@router.delete("/rag/{kb_id}")
async def delete_rag_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
):
    """删除RAG知识库（同步删除关联图谱）"""
    try:
        kb = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.id == kb_id,
            RagKnowledgeBaseModel.deleted_at == None
        ).first()
        
        if not kb:
            return error_response(code=404, message="Knowledge base not found")
        
        graphs = db.query(KnowledgeGraphModel).filter(
            KnowledgeGraphModel.knowledge_base_id == kb_id
        ).all()
        
        for graph in graphs:
            db.query(GraphRelationModel).filter(
                GraphRelationModel.graph_id == graph.id
            ).delete()
            db.query(GraphEntityModel).filter(
                GraphEntityModel.graph_id == graph.id
            ).delete()
            db.delete(graph)
        
        if graphs:
            logger.info(f"Deleted {len(graphs)} associated knowledge graphs for KB {kb_id}")
        
        kb.deleted_at = func.now()
        db.commit()
        
        logger.info(f"Deleted RAG knowledge base: {kb_id}")
        
        return success_response(message=f"Knowledge base deleted successfully (including {len(graphs)} associated graphs)")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete RAG knowledge base: {str(e)}")
        return error_response(code=500, message="Failed to delete knowledge base", error=str(e))


@router.post("/rag/{kb_id}/documents", response_model=dict)
async def add_document_to_knowledge_base(
    kb_id: int,
    data: RagDocumentCreate,
    db: Session = Depends(get_db),
):
    """向知识库添加文档并自动分块"""
    try:
        kb = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.id == kb_id,
            RagKnowledgeBaseModel.deleted_at == None
        ).first()
        
        if not kb:
            return error_response(code=404, message="Knowledge base not found")
        
        content = data.content or ""
        if content.startswith("[FILE:"):
            parsed_content = _parse_file_content(content)
        elif len(content) > 100 and _is_base64_file(content):
            parsed_content = _parse_file_content(content)
        else:
            parsed_content = content
        
        doc = RagDocumentModel(
            knowledge_base_id=kb_id,
            name=data.name,
            type=data.type,
            size=data.size,
            content=parsed_content,
            file_path=data.file_path,
            status="processed",
            chunk_count=0,
        )
        
        db.add(doc)
        db.flush()
        
        chunk_size = kb.chunk_size or 500
        chunk_method = kb.chunk_method or "auto"
        
        chunks = _chunk_content(parsed_content, chunk_size, chunk_method)
        
        for idx, chunk_content in enumerate(chunks):
            chunk = RagChunkModel(
                document_id=doc.id,
                chunk_index=idx,
                content=chunk_content,
                embedding_model=kb.embedding_model,
            )
            db.add(chunk)
        
        doc.chunk_count = len(chunks)
        kb.document_count += 1
        kb.chunk_count += len(chunks)
        kb.status = "active"
        kb.updated_at = func.now()
        
        db.commit()
        db.refresh(doc)
        
        logger.info(f"Added document {doc.id} with {len(chunks)} chunks to knowledge base {kb_id}")
        
        return success_response(
            data={
                "id": str(doc.id),
                "name": doc.name,
                "type": doc.type,
                "size": doc.size,
                "status": doc.status,
                "chunkCount": doc.chunk_count,
            },
            message="Document added successfully",
            status_code=status.HTTP_201_CREATED,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add document: {str(e)}")
        return error_response(code=500, message="Failed to add document", error=str(e))


def _chunk_content(content: str, chunk_size: int = 500, method: str = "auto") -> list:
    """将文档内容分块"""
    if not content or len(content.strip()) == 0:
        return []
    
    content = content.strip()
    
    if method == "fixed" or len(content) <= chunk_size:
        return [content] if content else []
    
    chunks = []
    
    if method in ["auto", "paragraph"]:
        paragraphs = re.split(r'\n\s*\n', content)
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                if len(para) > chunk_size:
                    for i in range(0, len(para), chunk_size):
                        chunks.append(para[i:i+chunk_size].strip())
                    current_chunk = ""
                else:
                    current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk.strip())
    
    elif method == "sentence":
        sentences = re.split(r'[。！？.!?]\s*', content)
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                current_chunk += ("。" if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
    
    else:
        for i in range(0, len(content), chunk_size):
            chunks.append(content[i:i+chunk_size].strip())
    
    return [c for c in chunks if c and len(c) >= 50] or [content[:chunk_size]] if content else []


@router.delete("/rag/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
):
    """删除文档"""
    try:
        doc = db.query(RagDocumentModel).filter(
            RagDocumentModel.id == doc_id,
            RagDocumentModel.knowledge_base_id == kb_id
        ).first()
        
        if not doc:
            return error_response(code=404, message="Document not found")
        
        chunk_count = doc.chunk_count
        
        kb = db.query(RagKnowledgeBaseModel).filter(RagKnowledgeBaseModel.id == kb_id).first()
        if kb:
            kb.document_count = max(0, kb.document_count - 1)
            kb.chunk_count = max(0, kb.chunk_count - chunk_count)
            if kb.document_count <= 0:
                kb.document_count = 0
                kb.status = "inactive"
        
        db.delete(doc)
        db.commit()
        
        return success_response(message="Document deleted successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete document: {str(e)}")
        return error_response(code=500, message="Failed to delete document", error=str(e))


@router.post("/rag/{kb_id}/generate-graph", response_model=dict)
async def generate_knowledge_graph(
    kb_id: str,
    payload: dict = None,
    db: Session = Depends(get_db),
):
    """
    从RAG知识库生成知识图谱
    支持两种模式：
    1. 如果数据库中有知识库记录，使用数据库中的文档
    2. 如果没有，使用前端传递的文档内容
    """
    try:
        kb = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.id == kb_id,
            RagKnowledgeBaseModel.deleted_at == None
        ).first()
        
        if kb and kb.has_graph:
            existing_graph = db.query(KnowledgeGraphModel).filter(
                KnowledgeGraphModel.knowledge_base_id == kb_id
            ).first()
            if existing_graph:
                return success_response(
                    data={"graphId": existing_graph.id, "entityCount": existing_graph.entity_count, "relationCount": existing_graph.relation_count, "status": "exists"},
                    message="Knowledge graph already exists"
                )
        
        doc_content = ""
        
        logger.info(f"开始生成图谱，kb_id={kb_id}, payload={payload is not None}")
        
        if kb:
            documents = db.query(RagDocumentModel).filter(
                RagDocumentModel.knowledge_base_id == kb_id
            ).all()
            raw_contents = [doc.content or "" for doc in documents if doc.content]
            logger.info(f"数据库文档数: {len(raw_contents)}, 原始内容长度: {[len(c) for c in raw_contents]}")
            parsed_contents = [_parse_file_content(c) for c in raw_contents]
            logger.info(f"解析后内容长度: {[len(c) for c in parsed_contents]}")
            doc_content = "\n\n".join([c for c in parsed_contents if c and len(c.strip()) > 10])
        elif payload and "documents" in payload:
            raw_contents = [doc.get("content", "") for doc in payload["documents"] if doc.get("content")]
            logger.info(f"前端文档数: {len(raw_contents)}, 原始内容长度: {[len(c) for c in raw_contents]}")
            parsed_contents = [_parse_file_content(c) for c in raw_contents]
            logger.info(f"解析后内容长度: {[len(c) for c in parsed_contents]}")
            doc_content = "\n\n".join([c for c in parsed_contents if c and len(c.strip()) > 10])
        
        logger.info(f"最终文档内容长度: {len(doc_content.strip())} 字符")
        
        if not doc_content or len(doc_content.strip()) < 50:
            logger.warning(f"文档内容不足: {len(doc_content.strip())} 字符")
            return error_response(code=400, message=f"文档内容不足（{len(doc_content.strip())}字符），无法生成图谱。请确保文档有足够的内容。")
        
        kb_name = kb.name if kb else (payload.get("name", "知识库") if payload else "知识库")
        
        graph = KnowledgeGraphModel(
            knowledge_base_id=int(kb_id) if kb else None,
            name=f"{kb_name} - 知识图谱",
            source_rag=kb_name,
            entity_count=0,
            relation_count=0,
            triple_count=0,
            status="processing",
            progress=0,
        )
        
        db.add(graph)
        db.flush()
        
        llm_service = LLMService(db)
        active_llm = llm_service.get_active_config()
        
        if active_llm:
            logger.info(f"Using LLM ({active_llm.name}) for entity extraction")
            extractor = KnowledgeGraphExtractor(llm_service)
            entities = extractor.extract_entities(doc_content)
            relations = extractor.extract_relations(doc_content, entities)
        else:
            logger.info("No active LLM config, using regex extraction")
            entities = _extract_entities_regex(doc_content)
            relations = _extract_relations_regex(doc_content, entities)
        
        entity_map = {}
        colors = {
            "模块": "#6366f1",
            "功能": "#10b981",
            "页面": "#0891b2",
        }
        
        for entity in entities:
            db_entity = GraphEntityModel(
                graph_id=graph.id,
                name=entity.get("name", "未命名"),
                type=entity.get("type", "模块"),
                color=colors.get(entity.get("type", "模块"), "#6366f1"),
                description=entity.get("description", ""),
                properties={"requires_login": entity.get("requires_login", True)},
            )
            db.add(db_entity)
            db.flush()
            entity_map[entity.get("name", "")] = db_entity.id
        
        for relation in relations:
            source_name = relation.get("source", "")
            target_name = relation.get("target", "")
            if source_name in entity_map and target_name in entity_map:
                db_relation = GraphRelationModel(
                    graph_id=graph.id,
                    source_id=entity_map[source_name],
                    target_id=entity_map[target_name],
                    relation=relation.get("relation", "关联"),
                )
                db.add(db_relation)
        
        entity_count = len(entities)
        relation_count = len([r for r in relations if r.get("source") in entity_map and r.get("target") in entity_map])
        
        graph.entity_count = entity_count
        graph.relation_count = relation_count
        graph.triple_count = relation_count
        graph.status = "completed"
        graph.progress = 100
        
        if kb:
            kb.has_graph = True
            kb.updated_at = func.now()
        
        db.commit()
        
        logger.info(f"Generated knowledge graph: {entity_count} entities, {relation_count} relations, LLM: {bool(active_llm)}")
        
        return success_response(
            data={
                "graphId": graph.id,
                "entityCount": entity_count,
                "relationCount": relation_count,
                "status": "completed",
                "usedLLM": bool(active_llm),
            },
            message=f"Knowledge graph generated successfully using {'LLM' if active_llm else 'regex'}",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate knowledge graph: {str(e)}")
        return error_response(code=500, message="Failed to generate knowledge graph", error=str(e))


def _extract_entities_regex(content: str) -> list:
    """使用正则表达式提取实体（无LLM时的备选方案）"""
    import re
    
    entities = []
    seen = set()
    
    patterns = {
        "module": r"[一二三四五六七八九十\d]+[、.．]\s*([^\n模块]{2,10})(模块|管理|配置|设置)",
        "feature": r"功能[：:·\s]*([^\n，。]{2,10})",
        "tech": r"(React|Vue|Python|FastAPI|TypeScript|Node\.?js|LLM|RAG|AI\s*Agent|Embedding|知识图谱|向量数据库|Ant Design|Redux|SQLAlchemy)",
        "role": r"(管理员|用户|测试人员|开发者|项目经理|查看者)",
    }
    
    for match in re.finditer(patterns["module"], content):
        name = match.group(1).strip()
        if name and len(name) >= 2 and name not in seen:
            seen.add(name)
            entities.append({"name": name, "type": "模块", "description": f"{name}模块"})
    
    for match in re.finditer(patterns["feature"], content):
        name = match.group(1).strip()
        if name and len(name) >= 2 and name not in seen:
            seen.add(name)
            entities.append({"name": name, "type": "功能", "description": f"{name}功能"})
    
    for match in re.finditer(patterns["tech"], content):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            entities.append({"name": name, "type": "技术", "description": f"{name}技术"})
    
    for match in re.finditer(patterns["role"], content):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            entities.append({"name": name, "type": "角色", "description": f"{name}角色"})
    
    if len(entities) < 3:
        default_entities = [
            {"name": "知识库", "type": "模块", "description": "知识存储管理"},
            {"name": "文档管理", "type": "功能", "description": "文档上传与管理"},
            {"name": "向量检索", "type": "功能", "description": "语义向量检索"},
            {"name": "图谱分析", "type": "功能", "description": "知识图谱分析"},
        ]
        for e in default_entities:
            if e["name"] not in seen:
                entities.append(e)
    
    return entities[:15]


def _extract_relations_regex(content: str, entities: list) -> list:
    """使用正则表达式提取关系（无LLM时的备选方案）"""
    relations = []
    
    if len(entities) < 2:
        return relations
    
    login_entity = None
    register_entity = None
    modules = []
    functions = []
    
    for e in entities:
        name = e.get("name", "")
        if "登录" in name or "login" in name.lower():
            login_entity = e
        if "注册" in name or "register" in name.lower():
            register_entity = e
        if e.get("type") == "模块":
            modules.append(e)
        elif e.get("type") == "功能":
            functions.append(e)
    
    if register_entity and login_entity:
        relations.append({
            "source": login_entity["name"],
            "target": register_entity["name"],
            "relation": "前置条件"
        })
    
    for module in modules:
        for func in functions:
            if module.get("name") in func.get("name", "") or func.get("name", "") in module.get("name", ""):
                relations.append({
                    "source": module["name"],
                    "target": func["name"],
                    "relation": "包含"
                })
    
    if login_entity:
        for e in entities:
            if e.get("requires_login") and e.get("name") != login_entity.get("name"):
                is_register = "注册" in e.get("name", "") or "register" in e.get("name", "").lower()
                if not is_register:
                    relations.append({
                        "source": e["name"],
                        "target": login_entity["name"],
                        "relation": "前置条件"
                    })
    
    for i, func in enumerate(functions):
        if i > 0:
            prev_func = functions[i - 1]
            if prev_func.get("requires_login") and func.get("requires_login"):
                relations.append({
                    "source": func["name"],
                    "target": prev_func["name"],
                    "relation": "依赖"
                })
    
    seen = set()
    unique_relations = []
    for r in relations:
        key = f"{r['source']}-{r['target']}-{r['relation']}"
        if key not in seen:
            seen.add(key)
            unique_relations.append(r)
    
    return unique_relations[:20]


@router.get("/graphs", response_model=dict)
async def list_knowledge_graphs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """获取知识图谱列表（按知识库去重，每个知识库只显示最新图谱）"""
    try:
        query = db.query(KnowledgeGraphModel)
        
        if search:
            query = query.filter(
                KnowledgeGraphModel.name.ilike(f"%{search}%") |
                KnowledgeGraphModel.source_rag.ilike(f"%{search}%")
            )
        
        all_items = query.order_by(KnowledgeGraphModel.created_at.desc()).all()
        
        seen_kb_ids = set()
        unique_items = []
        for item in all_items:
            kb_id = item.knowledge_base_id
            if kb_id is None:
                unique_items.append(item)
            elif kb_id not in seen_kb_ids:
                seen_kb_ids.add(kb_id)
                unique_items.append(item)
        
        total = len(unique_items)
        items = unique_items[skip:skip+limit]
        
        return success_response(
            data={
                "items": [
                    {
                        "id": str(item.id),
                        "name": item.name,
                        "sourceRag": item.source_rag,
                        "entityCount": item.entity_count,
                        "relationCount": item.relation_count,
                        "tripleCount": item.triple_count,
                        "status": item.status,
                        "progress": item.progress,
                        "createdAt": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
                    }
                    for item in items
                ],
                "total": total,
            }
        )
    except Exception as e:
        logger.error(f"Failed to list knowledge graphs: {str(e)}")
        return error_response(code=500, message="Failed to list knowledge graphs", error=str(e))


@router.get("/graphs/{graph_id}", response_model=dict)
async def get_knowledge_graph(
    graph_id: int,
    db: Session = Depends(get_db),
):
    """获取知识图谱详情（包含实体和关系）"""
    try:
        graph = db.query(KnowledgeGraphModel).filter(KnowledgeGraphModel.id == graph_id).first()
        
        if not graph:
            return error_response(code=404, message="Knowledge graph not found")
        
        entities = db.query(GraphEntityModel).filter(GraphEntityModel.graph_id == graph_id).all()
        relations = db.query(GraphRelationModel).filter(GraphRelationModel.graph_id == graph_id).all()
        
        entity_map = {e.id: e for e in entities}
        
        edges = []
        for rel in relations:
            source = entity_map.get(rel.source_id)
            target = entity_map.get(rel.target_id)
            if source and target:
                edges.append({
                    "id": rel.id,
                    "source": rel.source_id,
                    "target": rel.target_id,
                    "relation": rel.relation,
                    "sourceName": source.name,
                    "targetName": target.name,
                })
        
        return success_response(
            data={
                "id": str(graph.id),
                "name": graph.name,
                "sourceRag": graph.source_rag,
                "entityCount": graph.entity_count,
                "relationCount": graph.relation_count,
                "tripleCount": graph.triple_count,
                "status": graph.status,
                "progress": graph.progress,
                "createdAt": graph.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "nodes": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "type": e.type,
                        "color": e.color,
                        "properties": e.properties or {},
                    }
                    for e in entities
                ],
                "edges": edges,
            }
        )
    except Exception as e:
        logger.error(f"Failed to get knowledge graph: {str(e)}")
        return error_response(code=500, message="Failed to get knowledge graph", error=str(e))


@router.delete("/graphs/{graph_id}")
async def delete_knowledge_graph(
    graph_id: int,
    db: Session = Depends(get_db),
):
    """删除知识图谱"""
    try:
        graph = db.query(KnowledgeGraphModel).filter(KnowledgeGraphModel.id == graph_id).first()
        
        if not graph:
            return error_response(code=404, message="Knowledge graph not found")
        
        if graph.knowledge_base_id:
            kb = db.query(RagKnowledgeBaseModel).filter(
                RagKnowledgeBaseModel.id == graph.knowledge_base_id
            ).first()
            if kb:
                kb.has_graph = False
                kb.updated_at = func.now()
        
        db.delete(graph)
        db.commit()
        
        logger.info(f"Deleted knowledge graph: {graph_id}")
        
        return success_response(message="Knowledge graph deleted successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete knowledge graph: {str(e)}")
        return error_response(code=500, message="Failed to delete knowledge graph", error=str(e))


@router.get("/statistics", response_model=dict)
async def get_knowledge_statistics(
    db: Session = Depends(get_db),
):
    """获取知识库统计数据"""
    try:
        total_kbs = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.deleted_at == None
        ).count()
        
        total_docs = db.query(RagDocumentModel).count()
        
        total_chunks = db.query(RagChunkModel).count()
        
        kbs_with_graph = db.query(RagKnowledgeBaseModel).filter(
            RagKnowledgeBaseModel.deleted_at == None,
            RagKnowledgeBaseModel.has_graph == True
        ).count()
        
        graph_rate = (kbs_with_graph / total_kbs * 100) if total_kbs > 0 else 0
        
        total_graphs = db.query(KnowledgeGraphModel).count()
        total_entities = db.query(GraphEntityModel).count()
        total_relations = db.query(GraphRelationModel).count()
        
        return success_response(
            data={
                "rag": {
                    "totalKnowledgeBases": total_kbs,
                    "totalDocuments": total_docs,
                    "totalChunks": total_chunks,
                    "graphCoverageRate": round(graph_rate, 1),
                },
                "graph": {
                    "totalGraphs": total_graphs,
                    "totalEntities": total_entities,
                    "totalRelations": total_relations,
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to get knowledge statistics: {str(e)}")
        return error_response(code=500, message="Failed to get statistics", error=str(e))


@router.post("/rag/{kb_id}/vectorize", response_model=dict)
async def vectorize_knowledge_base_chunks(
    kb_id: int,
    db: Session = Depends(get_db),
):
    """对知识库的分块进行向量化"""
    try:
        from app.core.services.llm_service import RAGRetrievalService
        
        rag_service = RAGRetrievalService(db)
        result = rag_service.vectorize_chunks(knowledge_base_id=kb_id)
        
        return success_response(
            data=result,
            message=result.get("message", "Vectorization completed")
        )
    except Exception as e:
        logger.error(f"Failed to vectorize chunks: {str(e)}")
        return error_response(code=500, message="Failed to vectorize chunks", error=str(e))


@router.post("/rag/query", response_model=dict)
async def rag_query(
    data: dict,
    db: Session = Depends(get_db),
):
    """
    RAG查询接口
    
    请求体:
    - query: 查询文本（必须）
    - knowledge_base_id: 知识库ID（可选）
    - top_k: 返回数量（默认5）
    """
    try:
        from app.core.services.llm_service import RAGRetrievalService
        
        query = data.get("query")
        if not query:
            return error_response(code=400, message="Query is required")
        
        kb_id = data.get("knowledge_base_id")
        top_k = data.get("top_k", 5)
        
        rag_service = RAGRetrievalService(db)
        
        unvectorized = db.query(RagChunkModel).filter(
            RagChunkModel.embedding == None
        ).count()
        
        if unvectorized > 0:
            logger.info(f"Found {unvectorized} unvectorized chunks, vectorizing...")
            rag_service.vectorize_chunks(kb_id)
        
        result = rag_service.rag_query(
            query=query,
            knowledge_base_id=kb_id,
            top_k=top_k
        )
        
        return success_response(
            data=result,
            message=result.get("message", "Query processed")
        )
    except Exception as e:
        logger.error(f"Failed to process RAG query: {str(e)}")
        return error_response(code=500, message="Failed to process query", error=str(e))