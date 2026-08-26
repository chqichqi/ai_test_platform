"""
数据库连接和会话管理
使用SQLAlchemy进行数据库操作
"""

from typing import Generator, Optional
from contextlib import contextmanager
import json
import os
import logging as _logging

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.core.logger import logger, log_database_operation


# 创建数据库引擎
# SQLite需要特殊处理（不支持连接池）
if str(settings.DATABASE_URL).startswith("sqlite"):
    engine = create_engine(
        str(settings.DATABASE_URL),
        connect_args={"check_same_thread": False},  # SQLite需要这个参数
        echo=False,
    )
else:
    engine = create_engine(
        str(settings.DATABASE_URL),
        poolclass=QueuePool,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_pre_ping=True,
        echo=False,
    )

# ═══════════════════════════════════════════════════════════════
# 关闭 SQLAlchemy 引擎 INFO 日志（SQL 查询输出）
# 必须在引擎创建之后设置，因为 create_engine 会重置 logger 配置
# ═══════════════════════════════════════════════════════════════
for _name in ('sqlalchemy.engine', 'sqlalchemy.engine.Engine',
              'sqlalchemy.pool', 'sqlalchemy.pool.impl',
              'sqlalchemy.orm', 'sqlalchemy.dialects'):
    _logging.getLogger(_name).setLevel(_logging.WARNING)

# 创建会话工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# 声明基类
Base = declarative_base()


def add_query_logging_listener():
    """添加查询日志监听器"""
    
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """在执行查询前记录日志"""
        import time
        conn.info.setdefault("query_start_time", []).append(time.time())
    
    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """在执行查询后记录日志"""
        import time
        total_time = time.time() - conn.info["query_start_time"].pop(-1)
        log_database_operation(
            statement=statement,
            parameters=str(parameters),
            total_time=total_time
        )


# 添加查询日志监听
add_query_logging_listener()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话 - 用于FastAPI依赖注入
    使用方式：
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    """
    数据库会话上下文管理器
    使用方式：
        with db_session() as session:
            # 使用session进行数据库操作
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {str(e)}")
        raise
    finally:
        session.close()


def init_db():
    """初始化数据库"""
    logger.info("Initializing database...")
    
    try:
        # from app.core.models import document
        # from app.models import rag
        from app.core.models import web_ui_test
        from app.core.models import knowledge_graph  # Import KnowledgeGraph first
        from app.core.models import project, git
        from app.core.models import issue
        from app.core.models import requirement, api_test
        from app.core.models import cicd
        from app.core.models import notification
        from app.core.models import performance
        from app.core.models import scene
        from app.core.models import performance_locust  # Import Locust models
        from app.core.models import project_ext  # Import project_ext models
        from app.core.models import test_skill  # Import SKILL models
        
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")

        _apply_schema_migrations(engine)

        _init_base_data()
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


def _apply_schema_migrations(db_engine):
    """应用数据库schema迁移（为已有表添加新列）"""
    from sqlalchemy import text
    import re

    logger.info("Checking for schema migrations...")

    with db_engine.connect() as conn:
        # 检测数据库类型
        db_url = str(settings.DATABASE_URL) if hasattr(settings, 'DATABASE_URL') else ""
        is_mysql = "mysql" in db_url.lower()

        # 1. api_test_cases 表添加审批字段
        if is_mysql:
            # MySQL: 使用 INFORMATION_SCHEMA
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'api_test_cases' AND COLUMN_NAME = 'reviewer_id'"
            ))
        else:
            # SQLite: 使用 PRAGMA
            result = conn.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('api_test_cases') WHERE name = 'reviewer_id'"
            ))

        if result.scalar() == 0:
            logger.info("添加 api_test_cases 审批相关列...")
            try:
                conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN reviewer_id VARCHAR(36) NULL"))
                conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN review_comment TEXT NULL"))
                conn.execute(text("ALTER TABLE api_test_cases ADD COLUMN reviewed_at DATETIME NULL"))
                conn.commit()
                logger.info("api_test_cases 审批列添加成功")
            except Exception as e:
                logger.warning(f"添加审批列失败（可能已存在）: {e}")
        else:
            logger.info("api_test_cases 审批列已存在，跳过迁移")

        # 2. performance_scenarios 表添加梯度线程字段
        if is_mysql:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'performance_scenarios' AND COLUMN_NAME = 'step_enabled'"
            ))
        else:
            try:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM pragma_table_info('performance_scenarios') WHERE name = 'step_enabled'"
                ))
            except Exception:
                result = type('obj', (object,), {'scalar': lambda: 0})()  # table may not exist yet

        if result.scalar() == 0:
            logger.info("添加 performance_scenarios 梯度线程相关列...")
            try:
                conn.execute(text("ALTER TABLE performance_scenarios ADD COLUMN step_enabled BOOLEAN DEFAULT FALSE"))
                conn.execute(text("ALTER TABLE performance_scenarios ADD COLUMN step_count INT DEFAULT 5"))
                conn.execute(text("ALTER TABLE performance_scenarios ADD COLUMN step_duration INT DEFAULT 60"))
                conn.execute(text("ALTER TABLE performance_scenarios ADD COLUMN step_thread_increment INT DEFAULT 10"))
                conn.commit()
                logger.info("performance_scenarios 梯度线程列添加成功")
            except Exception as e:
                logger.warning(f"添加梯度线程列失败（可能已存在）: {e}")
        else:
            logger.info("performance_scenarios 梯度线程列已存在，跳过迁移")

        # 3. projects 表添加 project_type 和 APP相关字段
        if is_mysql:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'projects' AND COLUMN_NAME = 'project_type'"
            ))
        else:
            try:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM pragma_table_info('projects') WHERE name = 'project_type'"
                ))
            except Exception:
                result = type('obj', (object,), {'scalar': lambda: 0})()

        if result.scalar() == 0:
            logger.info("添加 projects 表 project_type 和 APP相关列...")
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE projects ADD COLUMN project_type VARCHAR(20) DEFAULT 'web' COMMENT '项目类型: web/app'"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_platform VARCHAR(20) NULL COMMENT 'APP平台: android/ios/harmonyos'"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_package_name VARCHAR(200) NULL COMMENT 'APP包名'"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_launch_activity VARCHAR(500) NULL COMMENT '启动Activity'"))
                else:
                    conn.execute(text("ALTER TABLE projects ADD COLUMN project_type VARCHAR(20) DEFAULT 'web'"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_platform VARCHAR(20)"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_package_name VARCHAR(200)"))
                    conn.execute(text("ALTER TABLE projects ADD COLUMN app_launch_activity VARCHAR(500)"))
                conn.commit()
                logger.info("projects APP相关列添加成功")
            except Exception as e:
                logger.warning(f"添加APP列失败（可能已存在）: {e}")
        else:
            logger.info("projects APP列已存在，跳过迁移")

        # 4. test_cases 表审核字段：修复 reviewer_id 类型（BIGINT → VARCHAR(36)）
        if is_mysql:
            result = conn.execute(text(
                "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'test_cases' AND COLUMN_NAME = 'reviewer_id'"
            ))
            col_type = result.scalar()
        else:
            try:
                result = conn.execute(text(
                    "SELECT type FROM pragma_table_info('test_cases') WHERE name = 'reviewer_id'"
                ))
                col_type = result.scalar()
            except Exception:
                col_type = None

        # 列不存在 → 添加；类型是 bigint → 修改为 varchar
        if col_type is None:
            logger.info("添加 test_cases 审核相关列...")
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN reviewer_id VARCHAR(36) NULL COMMENT '审核人ID'"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN review_comment TEXT NULL COMMENT '审核意见'"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN reviewed_at DATETIME NULL COMMENT '审核时间'"))
                else:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN reviewer_id VARCHAR(36)"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN review_comment TEXT"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN reviewed_at DATETIME"))
                conn.commit()
                logger.info("test_cases 审核列添加成功")
            except Exception as e:
                logger.warning(f"添加审核列失败: {e}")
        elif 'bigint' in str(col_type).lower():
            logger.info(f"修改 test_cases.reviewer_id 类型: {col_type} → VARCHAR(36)...")
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE test_cases MODIFY COLUMN reviewer_id VARCHAR(36) NULL COMMENT '审核人ID'"))
                else:
                    # SQLite 不支持 MODIFY COLUMN，需重建
                    conn.execute(text("ALTER TABLE test_cases RENAME COLUMN reviewer_id TO reviewer_id_old"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN reviewer_id VARCHAR(36)"))
                    conn.execute(text("UPDATE test_cases SET reviewer_id = CAST(reviewer_id_old AS TEXT) WHERE reviewer_id_old IS NOT NULL"))
                conn.commit()
                logger.info("test_cases.reviewer_id 类型修改成功")
            except Exception as e:
                logger.warning(f"修改 reviewer_id 类型失败: {e}")
        else:
            logger.info(f"test_cases.reviewer_id 类型正确 ({col_type})，跳过迁移")

        # 5. test_cases 表添加 sort_order 字段
        if is_mysql:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'test_cases' AND COLUMN_NAME = 'sort_order'"
            ))
        else:
            try:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM pragma_table_info('test_cases') WHERE name = 'sort_order'"
                ))
            except Exception:
                result = type('obj', (object,), {'scalar': lambda: 0})()

        if result.scalar() == 0:
            logger.info("添加 test_cases.sort_order 字段...")
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN sort_order INT DEFAULT 0 COMMENT '执行顺序(10间隔递增)'"))
                else:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN sort_order INT DEFAULT 0"))
                conn.commit()
                logger.info("test_cases.sort_order 添加成功")
            except Exception as e:
                logger.warning(f"添加 sort_order 失败（可能已存在）: {e}")
        else:
            logger.info("test_cases.sort_order 已存在，跳过迁移")

        # 6. web_ui_test_case 表添加 project_id 字段
        if is_mysql:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'web_ui_test_case' AND COLUMN_NAME = 'project_id'"
            ))
        else:
            try:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM pragma_table_info('web_ui_test_case') WHERE name = 'project_id'"
                ))
            except Exception:
                result = type('obj', (object,), {'scalar': lambda: 0})()

        if result.scalar() == 0:
            logger.info("添加 web_ui_test_case.project_id 字段...")
            try:
                if is_mysql:
                    conn.execute(text(
                        "ALTER TABLE web_ui_test_case ADD COLUMN project_id VARCHAR(36) NULL COMMENT '所属项目ID'"
                    ))
                else:
                    conn.execute(text(
                        "ALTER TABLE web_ui_test_case ADD COLUMN project_id VARCHAR(36)"
                    ))
                conn.commit()
                logger.info("web_ui_test_case.project_id 添加成功")
            except Exception as e:
                logger.warning(f"添加 project_id 失败（可能已存在）: {e}")
        else:
            logger.info("web_ui_test_case.project_id 已存在，跳过迁移")

        # 7. system_exploration_graphs: 知识图谱项目级改造——version_id 可空（版本删除时置空）+ project_id 唯一
        if is_mysql:
            try:
                # MySQL: version_id 改可空（表 0 行时无数据风险；MySQL 5.7 不支持 CREATE INDEX IF NOT EXISTS，先查后建）
                conn.execute(text(
                    "ALTER TABLE system_exploration_graphs MODIFY COLUMN version_id BIGINT NULL"
                ))
                _idx = conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'system_exploration_graphs' "
                    "AND INDEX_NAME = 'uq_knowledge_graph_project_id'"
                )).scalar()
                if not _idx:
                    conn.execute(text(
                        "CREATE UNIQUE INDEX uq_knowledge_graph_project_id "
                        "ON system_exploration_graphs(project_id)"
                    ))
                conn.commit()
                logger.info("system_exploration_graphs 项目级改造完成（version_id 可空 + project_id 唯一）")
            except Exception as e:
                logger.warning(f"system_exploration_graphs 项目级改造失败: {e}")
        else:
            try:
                # SQLite: 检测 version_id 是否仍为 NOT NULL
                result = conn.execute(text(
                    "SELECT notnull FROM pragma_table_info('system_exploration_graphs') WHERE name = 'version_id'"
                ))
                if result.scalar() == 1:
                    conn.execute(text("ALTER TABLE system_exploration_graphs RENAME COLUMN version_id TO version_id_old"))
                    conn.execute(text("ALTER TABLE system_exploration_graphs ADD COLUMN version_id BIGINT"))
                    conn.execute(text("UPDATE system_exploration_graphs SET version_id = version_id_old WHERE version_id_old IS NOT NULL"))
                    conn.commit()
                    logger.info("system_exploration_graphs.version_id 可空化成功")
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_graph_project_id "
                    "ON system_exploration_graphs(project_id)"
                ))
                conn.commit()
                logger.info("system_exploration_graphs 项目级改造完成（SQLite）")
            except Exception as e:
                logger.warning(f"system_exploration_graphs 项目级改造失败（SQLite）: {e}")

        # 8. 方案B 用例版本化：
        #    test_cases 加 logical_case_id/revision_no/derived_from_id（派生行共享逻辑id，revision 递增）
        #    scene_items 加 wui_id（执行中心条目绑定具体 WUI 实例）
        #    web_ui_test_case 加 is_deleted（旧 WUI 软删载体，执行时重解析）
        def _col_exists(_table, _col):
            if is_mysql:
                return conn.execute(text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '%s' AND COLUMN_NAME = '%s'" % (_table, _col)
                )).scalar() > 0
            try:
                return conn.execute(text(
                    "SELECT COUNT(*) FROM pragma_table_info('%s') WHERE name = '%s'" % (_table, _col)
                )).scalar() > 0
            except Exception:
                return True  # 表不存在视为无需迁移

        # 8.1 test_cases 三列
        if not _col_exists('test_cases', 'logical_case_id'):
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN logical_case_id BIGINT NULL COMMENT '逻辑用例ID'"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN revision_no INT NOT NULL DEFAULT 1 COMMENT '修订号'"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN derived_from_id BIGINT NULL COMMENT '派生来源行ID'"))
                else:
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN logical_case_id BIGINT"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN revision_no INTEGER NOT NULL DEFAULT 1"))
                    conn.execute(text("ALTER TABLE test_cases ADD COLUMN derived_from_id BIGINT"))
                conn.commit()
                logger.info("test_cases 版本化三列添加成功")
            except Exception as e:
                logger.warning(f"test_cases 版本化列添加失败: {e}")
        else:
            logger.info("test_cases 版本化列已存在，跳过迁移")

        # 8.2 幂等回填：logical_case_id = id（现有数据逻辑=物理；每次启动兜底遗漏创建点）
        try:
            conn.execute(text(
                "UPDATE test_cases SET logical_case_id = id WHERE logical_case_id IS NULL"
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"test_cases logical_case_id 回填失败: {e}")

        # 8.3 scene_items.wui_id
        if not _col_exists('scene_items', 'wui_id'):
            try:
                conn.execute(text("ALTER TABLE scene_items ADD COLUMN wui_id VARCHAR(36) NULL"))
                conn.commit()
                logger.info("scene_items.wui_id 添加成功")
            except Exception as e:
                logger.warning(f"scene_items.wui_id 添加失败: {e}")
        else:
            logger.info("scene_items.wui_id 已存在，跳过迁移")

        # 8.4 web_ui_test_case.is_deleted（旧 WUI 软删载体）
        if not _col_exists('web_ui_test_case', 'is_deleted'):
            try:
                if is_mysql:
                    conn.execute(text("ALTER TABLE web_ui_test_case ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '软删标记'"))
                else:
                    conn.execute(text("ALTER TABLE web_ui_test_case ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
                conn.commit()
                logger.info("web_ui_test_case.is_deleted 添加成功")
            except Exception as e:
                logger.warning(f"web_ui_test_case.is_deleted 添加失败: {e}")
        else:
            logger.info("web_ui_test_case.is_deleted 已存在，跳过迁移")

        # 8.5 wui_id 回填（Python 侧，数据量小）：按 test_case_id==str(case_id) 取最新非软删 WUI
        try:
            rows = conn.execute(text(
                "SELECT si.id AS item_id, si.case_id FROM scene_items si "
                "WHERE si.wui_id IS NULL AND si.case_type = 'ui'"
            )).fetchall()
            for r in rows:
                w = conn.execute(text(
                    "SELECT id FROM web_ui_test_case "
                    "WHERE test_case_id = :cid AND (is_deleted IS NULL OR is_deleted = 0) "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ), {"cid": str(r[1])}).fetchone()
                if w:
                    conn.execute(text(
                        "UPDATE scene_items SET wui_id = :wid WHERE id = :iid"
                    ), {"wid": w[0], "iid": r[0]})
            conn.commit()
            logger.info(f"scene_items.wui_id 回填完成（{len(rows)} 条待回填）")
        except Exception as e:
            logger.warning(f"scene_items.wui_id 回填失败: {e}")

        # 8.6 索引（先判存在再建；SQLite 用 IF NOT EXISTS）
        try:
            if is_mysql:
                for _col, _idx in (('logical_case_id', 'ix_test_cases_logical_case_id'),
                                   ('derived_from_id', 'ix_test_cases_derived_from_id')):
                    _cnt = conn.execute(text(
                        "SELECT COUNT(*) FROM information_schema.STATISTICS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_cases' "
                        "AND INDEX_NAME = '%s'" % _idx
                    )).scalar()
                    if not _cnt:
                        conn.execute(text(
                            "CREATE INDEX %s ON test_cases(%s)" % (_idx, _col)
                        ))
            else:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_test_cases_logical_case_id ON test_cases(logical_case_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_test_cases_derived_from_id ON test_cases(derived_from_id)"
                ))
            conn.commit()
            logger.info("test_cases 版本化索引创建完成")
        except Exception as e:
            logger.warning(f"test_cases 版本化索引创建失败: {e}")


def _init_base_data():
    """初始化基础数据（角色、权限等）"""
    from app.core.models import Role, Permission
    from app.core.services.auth_service import AuthService
    
    with db_session() as session:
        # 检查是否已初始化
        if session.query(Role).count() > 0:
            logger.info("Base data already initialized")
            # 即使基础数据已初始化，也检查是否需要插入预设SKILL
            _init_preset_skills(session)
            return
        
        logger.info("Creating base data...")
        
        permissions = [
            Permission(code="project:read", name="查看项目", description="查看项目列表和详情"),
            Permission(code="project:create", name="创建项目", description="创建新项目"),
            Permission(code="project:update", name="编辑项目", description="编辑项目信息"),
            Permission(code="project:delete", name="删除项目", description="删除项目"),
            Permission(code="project:archive", name="归档项目", description="归档项目"),
            
            Permission(code="version:read", name="查看版本", description="查看版本列表和详情"),
            Permission(code="version:create", name="创建版本", description="创建新版本"),
            Permission(code="version:update", name="编辑版本", description="编辑版本信息"),
            Permission(code="version:delete", name="删除版本", description="删除版本"),
            
            Permission(code="git:read", name="查看Git仓库", description="查看Git仓库信息"),
            Permission(code="git:create", name="添加Git仓库", description="添加Git仓库"),
            Permission(code="git:sync", name="同步Git仓库", description="同步Git仓库数据"),
            Permission(code="git:webhook", name="配置Webhook", description="配置Git Webhook"),
            
            Permission(code="test:read", name="查看测试", description="查看测试用例和结果"),
            Permission(code="test:create", name="创建测试", description="创建测试用例"),
            Permission(code="test:update", name="编辑测试", description="编辑测试用例"),
            Permission(code="test:delete", name="删除测试", description="删除测试用例"),
            Permission(code="test:execute", name="执行测试", description="执行测试用例"),
            Permission(code="test:approve", name="审批测试", description="审批测试用例"),
            
            Permission(code="api_test:read", name="查看API测试", description="查看API测试用例"),
            Permission(code="api_test:create", name="创建API测试", description="创建API测试用例"),
            Permission(code="api_test:execute", name="执行API测试", description="执行API测试"),
            
            Permission(code="web_test:read", name="查看WEB测试", description="查看WEB UI测试用例"),
            Permission(code="web_test:create", name="创建WEB测试", description="创建WEB UI测试用例"),
            Permission(code="web_test:execute", name="执行WEB测试", description="执行WEB UI测试"),
            
            Permission(code="functional_test:read", name="查看功能测试", description="查看功能测试用例"),
            Permission(code="functional_test:create", name="创建功能测试", description="创建功能测试用例"),
            Permission(code="functional_test:generate", name="生成功能测试", description="AI生成功能测试"),
            
            Permission(code="rag:read", name="查看知识库", description="查看RAG知识库"),
            Permission(code="rag:upload", name="上传文档", description="上传文档到知识库"),
            Permission(code="rag:query", name="查询知识库", description="查询RAG知识库"),
            Permission(code="rag:delete", name="删除文档", description="删除知识库文档"),
            
            Permission(code="skill:read", name="查看SKILL", description="查看SKILL列表"),
            Permission(code="skill:create", name="创建SKILL", description="创建新SKILL"),
            Permission(code="skill:update", name="编辑SKILL", description="编辑SKILL"),
            Permission(code="skill:delete", name="删除SKILL", description="删除SKILL"),
            Permission(code="skill:use", name="使用SKILL", description="使用SKILL生成测试"),
            
            Permission(code="report:view", name="查看报告", description="查看测试报告"),
            Permission(code="report:export", name="导出报告", description="导出测试报告"),
            Permission(code="report:delete", name="删除报告", description="删除测试报告"),
            
            Permission(code="dashboard:view", name="查看统计大屏", description="查看统计数据和图表"),
            
            Permission(code="user:manage", name="用户管理", description="管理系统用户"),
            Permission(code="role:manage", name="角色管理", description="管理系统角色"),
            Permission(code="system:config", name="系统配置", description="管理系统配置"),
        ]
        
        session.add_all(permissions)
        session.flush()
        
        external_permissions = [p for p in permissions if p.code in [
            "dashboard:view"
        ]]
        
        tester_permissions = external_permissions + [p for p in permissions if p.code in [
            "project:read", "version:read", "git:read",
            "test:read", "test:execute",
            "api_test:read", "api_test:execute",
            "web_test:read", "web_test:execute",
            "functional_test:read", "functional_test:generate",
            "rag:read", "rag:query",
            "skill:read", "skill:use",
            "report:view"
        ]]
        
        test_engineer_permissions = tester_permissions + [p for p in permissions if p.code in [
            "test:create", "test:update",
            "api_test:create",
            "web_test:create",
            "functional_test:create",
            "rag:upload",
            "report:export"
        ]]
        
        test_manager_permissions = test_engineer_permissions + [p for p in permissions if p.code in [
            "project:read", "project:create", "project:update",
            "version:read", "version:create", "version:update",
            "git:read", "git:create", "git:sync", "git:webhook",
            "test:delete", "test:approve",
            "skill:create"
        ]]
        
        admin_permissions = permissions
        
        roles = [
            Role(
                name="external",
                description="外部人员",
                is_default=True,
                permissions=external_permissions
            ),
            Role(
                name="tester",
                description="测试员",
                permissions=tester_permissions
            ),
            Role(
                name="test_engineer",
                description="测试工程师",
                permissions=test_engineer_permissions
            ),
            Role(
                name="test_manager",
                description="测试经理/总监",
                permissions=test_manager_permissions
            ),
            Role(
                name="admin",
                description="系统管理员/超管",
                permissions=admin_permissions
            ),
        ]
        
        session.add_all(roles)
        
        # 创建默认管理员用户
        auth_service = AuthService(session)
        admin_user = auth_service.create_user(
            username="admin",
            email="admin@ai-test-platform.com",
            password="admin123",
            full_name="系统管理员",
            department="系统部",
            is_active=True,
            is_superuser=True,
        )
        
        # 分配管理员角色
        admin_role = next(r for r in roles if r.name == "admin")
        admin_user.roles.append(admin_role)
        
        session.commit()
        logger.info("Base data created successfully")
        
        # 初始化预设SKILL
        _init_preset_skills(session)


def _init_preset_skills(session):
    """初始化预设SKILL模板"""
    from app.core.models.test_skill import TestSkill, SkillType, SkillStatus
    
    logger.info("Initializing preset skills...")
    
    # 预设SKILL文件路径
    preset_skills_dir = os.path.join(os.path.dirname(__file__), "data", "preset_skills")
    
    if not os.path.exists(preset_skills_dir):
        logger.warning(f"Preset skills directory not found: {preset_skills_dir}")
        return
    
    preset_files = [
        "functional_test_template.json",
        "webui_automation_template.json", 
        "api_test_template.json",
        "performance_test_template.json"
    ]
    
    admin_user_id = "system"  # 使用system作为预设SKILL的创建者
    
    for filename in preset_files:
        filepath = os.path.join(preset_skills_dir, filename)
        if not os.path.exists(filepath):
            logger.warning(f"Preset skill file not found: {filepath}")
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                skill_data = json.load(f)
            
            # 检查是否已存在
            existing = session.query(TestSkill).filter(
                TestSkill.code == skill_data["code"]
            ).first()
            
            if existing:
                logger.info(f"Preset skill already exists: {skill_data['code']}")
                continue
            
            # 创建SKILL
            skill = TestSkill(
                name=skill_data["name"],
                code=skill_data["code"],
                description=skill_data["description"],
                skill_type=skill_data["skill_type"],
                tags=skill_data.get("tags", []),
                is_global=skill_data.get("is_global", True),
                is_default=skill_data.get("is_default", True),
                content=skill_data["content"],
                status=SkillStatus.ACTIVE.value,
                created_by=admin_user_id,
                version="1.0.0",
                is_latest=True,
                usage_count=0,
                generation_count=0
            )
            
            session.add(skill)
            session.flush()
            
            logger.info(f"Created preset skill: {skill_data['code']} - {skill_data['name']}")
            
        except Exception as e:
            logger.error(f"Failed to create preset skill from {filename}: {str(e)}")
            continue
    
    session.commit()
    logger.info("Preset skills initialization completed")


def drop_db():
    """删除所有表（谨慎使用）"""
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("All database tables dropped")


# 数据库健康检查
def check_db_health() -> bool:
    """检查数据库连接是否正常"""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return False


# 导出常用函数和类
__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
    "db_session",
    "init_db",
    "drop_db",
    "check_db_health",
]
