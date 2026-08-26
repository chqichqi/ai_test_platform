"""
数据库配置服务
处理数据库连接配置、测试和初始化
"""

import os
import re
from typing import Dict, Any, Optional
from urllib.parse import quote_plus
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from app.core.logger import logger
from app.core.config import settings


class DatabaseConfigService:
    """数据库配置服务"""
    
    # 配置文件路径
    ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    
    @staticmethod
    def check_db_configured() -> bool:
        """检查数据库是否已配置"""
        try:
            # 尝试导入并使用现有的数据库连接
            from app.core.database import engine
            # 尝试执行一个简单的查询
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.debug(f"数据库未配置或连接失败: {e}")
            return False
    
    @staticmethod
    def get_db_config() -> Dict[str, Any]:
        """获取当前数据库配置"""
        config = {
            'db_type': None,
            'host': None,
            'port': None,
            'database': None,
            'username': None,
        }
        
        # 从环境变量读取
        db_url = str(settings.DATABASE_URL)
        
        if 'sqlite' in db_url.lower():
            config['db_type'] = 'sqlite'
            # 提取SQLite数据库路径
            match = re.search(r'sqlite:///(.+)', db_url)
            if match:
                config['database'] = match.group(1)
        elif 'mysql' in db_url.lower():
            config['db_type'] = 'mysql'
            # 解析MySQL连接字符串
            # 格式: mysql+pymysql://username:password@host:port/database
            match = re.search(r'mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/(\S+)', db_url)
            if match:
                config['username'] = match.group(1)
                # 密码不解密返回
                config['host'] = match.group(3)
                config['port'] = int(match.group(4))
                config['database'] = match.group(5)
        
        return config
    
    @staticmethod
    def test_mysql_connection(
        host: str,
        port: int,
        database: str,
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """测试MySQL连接"""
        try:
            # 先尝试连接MySQL服务器（不指定数据库）
            server_url = f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}"
            server_engine = create_engine(server_url, connect_args={'connect_timeout': 10})
            
            with server_engine.connect() as conn:
                # 获取MySQL版本
                result = conn.execute(text("SELECT VERSION()"))
                version = result.scalar()
                
                # 检查数据库是否存在
                result = conn.execute(
                    text("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = :db"),
                    {'db': database}
                )
                db_exists = result.fetchone() is not None
                
                # 如果数据库存在，检查表
                existing_tables = []
                if db_exists:
                    result = conn.execute(
                        text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = :db"),
                        {'db': database}
                    )
                    existing_tables = [row[0] for row in result.fetchall()]
            
            server_engine.dispose()
            
            return {
                'success': True,
                'message': '连接成功',
                'version': version,
                'db_exists': db_exists,
                'existing_tables': existing_tables,
                'is_initialized': len(existing_tables) > 5 if db_exists else False
            }
            
        except OperationalError as e:
            error_msg = str(e).lower()
            if 'access denied' in error_msg:
                return {'success': False, 'message': '用户名或密码错误'}
            elif 'unknown host' in error_msg or 'could not connect' in error_msg:
                return {'success': False, 'message': f'无法连接到数据库服务器 {host}:{port}，请检查主机地址和端口'}
            elif 'can\'t connect' in error_msg:
                return {'success': False, 'message': '数据库服务器无响应，请检查MySQL服务是否启动'}
            else:
                return {'success': False, 'message': f'连接失败: {str(e)}'}
        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return {'success': False, 'message': f'连接失败: {str(e)}'}
    
    @staticmethod
    def save_db_config(
        db_type: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> bool:
        """保存数据库配置到.env文件"""
        try:
            # 读取现有配置
            env_content = {}
            if os.path.exists(DatabaseConfigService.ENV_FILE_PATH):
                with open(DatabaseConfigService.ENV_FILE_PATH, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_content[key] = value
            
            # 更新配置
            if db_type == 'sqlite':
                db_path = database or './data/app.db'
                env_content['DATABASE_URL'] = f'sqlite:///{db_path}'
            elif db_type == 'mysql':
                db_url = f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}"
                env_content['DATABASE_URL'] = db_url
            
            # 写回文件
            with open(DatabaseConfigService.ENV_FILE_PATH, 'w', encoding='utf-8') as f:
                for key, value in env_content.items():
                    f.write(f'{key}={value}\n')
            
            # 重新加载配置
            settings.DATABASE_URL = env_content['DATABASE_URL']
            
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    @staticmethod
    def init_database(
        db_type: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        init_data: bool = True
    ) -> Dict[str, Any]:
        """初始化数据库"""
        result = {
            'success': False,
            'steps': [],
            'message': ''
        }
        
        try:
            if db_type == 'mysql':
                # 1. 创建数据库
                result['steps'].append({'name': '检查/创建数据库', 'status': 'running'})
                server_url = f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}"
                server_engine = create_engine(server_url)
                
                with server_engine.connect() as conn:
                    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                
                server_engine.dispose()
                result['steps'][-1]['status'] = 'success'
                
                # 2. 创建表
                result['steps'].append({'name': '创建数据表', 'status': 'running'})
                db_url = f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}"
                db_engine = create_engine(db_url)
                
                # 导入模型并创建表
                from app.core.database import Base
                from app.core.models import user, project, requirement, git, issue, notification, performance
                
                Base.metadata.create_all(bind=db_engine)
                result['steps'][-1]['status'] = 'success'
                
                # 3. 初始化基础数据
                if init_data:
                    result['steps'].append({'name': '初始化基础数据', 'status': 'running'})
                    DatabaseConfigService._init_base_data(db_engine)
                    result['steps'][-1]['status'] = 'success'
                
                db_engine.dispose()
                
            elif db_type == 'sqlite':
                # SQLite逻辑
                db_path = database or './data/app.db'
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                
                result['steps'].append({'name': '创建数据库文件', 'status': 'running'})
                db_url = f'sqlite:///{db_path}'
                db_engine = create_engine(db_url, connect_args={'check_same_thread': False})
                result['steps'][-1]['status'] = 'success'
                
                result['steps'].append({'name': '创建数据表', 'status': 'running'})
                from app.core.database import Base
                Base.metadata.create_all(bind=db_engine)
                result['steps'][-1]['status'] = 'success'
                
                if init_data:
                    result['steps'].append({'name': '初始化基础数据', 'status': 'running'})
                    DatabaseConfigService._init_base_data(db_engine)
                    result['steps'][-1]['status'] = 'success'
                
                db_engine.dispose()
            
            # 4. 保存配置
            result['steps'].append({'name': '保存配置', 'status': 'running'})
            DatabaseConfigService.save_db_config(
                db_type=db_type,
                host=host,
                port=port,
                database=database,
                username=username,
                password=password
            )
            result['steps'][-1]['status'] = 'success'
            
            result['success'] = True
            result['message'] = '数据库初始化成功'
            
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
            result['message'] = f'初始化失败: {str(e)}'
            if result['steps']:
                result['steps'][-1]['status'] = 'error'
                result['steps'][-1]['error'] = str(e)
        
        return result
    
    @staticmethod
    def _init_base_data(engine):
        """初始化基础数据"""
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # 导入模型
            from app.core.models.user import User, Role, Permission
            from app.core.models.project import Project
            import uuid
            from datetime import datetime
            
            # 检查是否已有数据
            existing_user = session.query(User).first()
            if existing_user:
                logger.info("基础数据已存在，跳过初始化")
                return
            
            # 1. 创建默认角色
            admin_role = Role(
                id=str(uuid.uuid4()),
                name='admin',
                description='系统管理员',
                is_system=True
            )
            session.add(admin_role)
            
            user_role = Role(
                id=str(uuid.uuid4()),
                name='user',
                description='普通用户',
                is_system=True
            )
            session.add(user_role)
            
            # 2. 创建默认权限
            permissions = [
                Permission(id=str(uuid.uuid4()), name='project:create', description='创建项目'),
                Permission(id=str(uuid.uuid4()), name='project:view', description='查看项目'),
                Permission(id=str(uuid.uuid4()), name='project:edit', description='编辑项目'),
                Permission(id=str(uuid.uuid4()), name='project:delete', description='删除项目'),
            ]
            for perm in permissions:
                session.add(perm)
            
            # 3. 创建默认管理员用户
            admin_user = User(
                id=str(uuid.uuid4()),
                username='admin',
                email='admin@example.com',
                full_name='系统管理员',
                is_active=True,
                is_superuser=True,
                created_at=datetime.utcnow()
            )
            # 设置密码（123456）
            admin_user.set_password('123456')
            session.add(admin_user)
            
            # 4. 关联角色
            admin_user.roles.append(admin_role)
            
            # 5. 创建示例项目
            sample_project = Project(
                name='示例项目',
                code='demo-project',
                description='这是一个示例项目，用于演示系统功能',
                owner_id=admin_user.id,
                status='active',
                created_at=datetime.utcnow()
            )
            session.add(sample_project)
            
            session.commit()
            logger.info("基础数据初始化完成")
            
        except Exception as e:
            session.rollback()
            logger.error(f"初始化基础数据失败: {e}")
            raise
        finally:
            session.close()


# 全局服务实例
db_config_service = DatabaseConfigService()
