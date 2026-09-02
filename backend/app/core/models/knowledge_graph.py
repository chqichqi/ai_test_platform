"""知识图谱数据模型：项目级 KG、页面快照、元素定位器、导航流程、API 记录。"""
from datetime import datetime
from sqlalchemy import Column,Integer,BigInteger,String,JSON,Float,DateTime,ForeignKey,Boolean,Text,UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

class KnowledgeGraph(Base):
    __tablename__='system_exploration_graphs'
    __table_args__=(UniqueConstraint('project_id',name='uq_knowledge_graph_project_id'),)
    id=Column(BigInteger,primary_key=True,autoincrement=True); project_id=Column(BigInteger,ForeignKey('projects.id'),nullable=False); version_id=Column(BigInteger,ForeignKey('versions.id'),nullable=True)
    graph_name=Column(String(200)); base_url=Column(String(500)); exploration_strategy=Column(String(20),default='normal'); login_username=Column(String(100)); login_password=Column(String(100)); selected_organization=Column(String(200))
    pages=Column(JSON,default=list); menus=Column(JSON,default=list); elements=Column(JSON,default=list); forms=Column(JSON,default=list); tables=Column(JSON,default=list); flows=Column(JSON,default=list); api_calls=Column(JSON,default=list); dependencies=Column(JSON,default=list); dropdowns=Column(JSON,default=dict); modals=Column(JSON,default=list)
    page_count=Column(Integer,default=0); menu_count=Column(Integer,default=0); element_count=Column(Integer,default=0); flow_count=Column(Integer,default=0); api_count=Column(Integer,default=0)
    exploration_status=Column(String(20),default='pending'); progress_percentage=Column(Integer,default=0); current_page=Column(String(200)); error_message=Column(Text); started_at=Column(DateTime); completed_at=Column(DateTime); duration_seconds=Column(Integer); auth_data=Column(JSON,default=dict); confidence_score=Column(Float,default=0.0); locator_validation_rate=Column(Float,default=0.0); created_at=Column(DateTime,default=datetime.utcnow); updated_at=Column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    project=relationship('Project',back_populates='knowledge_graphs'); version=relationship('Version',back_populates='knowledge_graphs'); page_snapshots=relationship('ExplorationPageSnapshot',back_populates='knowledge_graph',cascade='all, delete-orphan')
    def to_dict(self):
        return {'id':self.id,'project_id':self.project_id,'version_id':self.version_id,'graph_name':self.graph_name,'base_url':self.base_url,'exploration_strategy':self.exploration_strategy,'page_count':self.page_count,'menu_count':self.menu_count,'element_count':self.element_count,'exploration_status':self.exploration_status,'progress_percentage':self.progress_percentage,'current_page':self.current_page,'started_at':self.started_at.isoformat() if self.started_at else None,'completed_at':self.completed_at.isoformat() if self.completed_at else None,'duration_seconds':self.duration_seconds,'confidence_score':self.confidence_score,'created_at':self.created_at.isoformat() if self.created_at else None}
class ExplorationPageSnapshot(Base):
    __tablename__='exploration_page_snapshots'
    id=Column(BigInteger,primary_key=True,autoincrement=True); graph_id=Column(BigInteger,ForeignKey('system_exploration_graphs.id'),nullable=False); page_url=Column(String(500)); page_title=Column(String(200)); page_name=Column(String(200)); menu_level=Column(Integer,default=1); parent_menu=Column(String(200)); elements=Column(JSON,default=list); forms=Column(JSON,default=list); tables=Column(JSON,default=list); buttons=Column(JSON,default=list); links=Column(JSON,default=list); operations=Column(JSON,default=list); api_calls=Column(JSON,default=list); screenshot_path=Column(String(500)); dom_snapshot=Column(Text); visited_at=Column(DateTime,default=datetime.utcnow); visit_order=Column(Integer,default=0)
    knowledge_graph=relationship('KnowledgeGraph',back_populates='page_snapshots')
    def to_dict(self): return {'id':self.id,'graph_id':self.graph_id,'page_url':self.page_url,'page_title':self.page_title,'page_name':self.page_name,'menu_level':self.menu_level,'parent_menu':self.parent_menu,'element_count':len(self.elements) if self.elements else 0,'visited_at':self.visited_at.isoformat() if self.visited_at else None}
class ElementLocator(Base):
    __tablename__='element_locators'
    id=Column(BigInteger,primary_key=True,autoincrement=True); graph_id=Column(BigInteger,ForeignKey('system_exploration_graphs.id'),nullable=False); page_id=Column(BigInteger,ForeignKey('exploration_page_snapshots.id'),nullable=False); element_name=Column(String(200)); element_type=Column(String(50)); element_text=Column(String(200)); element_description=Column(Text); locator_id=Column(String(200)); locator_xpath=Column(Text); locator_css=Column(String(500)); locator_text=Column(String(200)); locator_name=Column(String(200)); locator_class=Column(String(500)); primary_locator=Column(String(20),default='xpath'); primary_locator_value=Column(String(500)); is_validated=Column(Boolean,default=False); validation_attempts=Column(Integer,default=0); validation_success=Column(Boolean,default=False); last_validated_at=Column(DateTime); created_at=Column(DateTime,default=datetime.utcnow)
    def to_dict(self): return {'id':self.id,'element_name':self.element_name,'element_type':self.element_type,'element_text':self.element_text,'locators':{'id':self.locator_id,'xpath':self.locator_xpath,'css':self.locator_css,'text':self.locator_text,'name':self.locator_name,'class':self.locator_class},'primary_locator':{'type':self.primary_locator,'value':self.primary_locator_value},'is_validated':self.is_validated,'validation_success':self.validation_success}
class NavigationFlow(Base):
    __tablename__='navigation_flows'
    id=Column(BigInteger,primary_key=True,autoincrement=True); graph_id=Column(BigInteger,ForeignKey('system_exploration_graphs.id'),nullable=False); flow_name=Column(String(200)); flow_type=Column(String(50)); start_page=Column(String(200)); end_page=Column(String(200)); steps=Column(JSON,default=list); dependencies=Column(JSON,default=list); required_data=Column(JSON,default=dict); created_at=Column(DateTime,default=datetime.utcnow)
    def to_dict(self): return {'id':self.id,'flow_name':self.flow_name,'flow_type':self.flow_type,'start_page':self.start_page,'end_page':self.end_page,'step_count':len(self.steps) if self.steps else 0,'dependencies':self.dependencies}
class APICallRecord(Base):
    __tablename__='api_call_records'
    id=Column(BigInteger,primary_key=True,autoincrement=True); graph_id=Column(BigInteger,ForeignKey('system_exploration_graphs.id'),nullable=False)
    # 模型层 FK 必须指向 metadata 中存在的表（exploration_page_snapshots），
    # 否则 mapper 配置失败（NoReferencedTableError，2026-09-01 曾指向 page_snapshots 中招）。
    # 建表以模型 __tablename__ 为准（database.py create_all）；page_id 允许为空，不伪造快照 ID。
    page_id=Column(BigInteger,ForeignKey('exploration_page_snapshots.id'))
    api_url=Column(String(500)); api_method=Column(String(10)); api_type=Column(String(20)); request_headers=Column(JSON,default=dict); request_params=Column(JSON,default=dict); request_body=Column(JSON,default=dict); response_status=Column(Integer); response_headers=Column(JSON,default=dict); response_body=Column(JSON,default=dict); captured_at=Column(DateTime,default=datetime.utcnow)
    def to_dict(self): return {'id':self.id,'api_url':self.api_url,'api_method':self.api_method,'api_type':self.api_type,'response_status':self.response_status}
