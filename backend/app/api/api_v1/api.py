"""
API路由主文件
"""

from fastapi import APIRouter

from app.api.api_v1.endpoints import (
    auth,
    users,
    projects,
    versions,
    git,
    tests,
    rag,
    admin,
    web_ui_tests,
    settings,
    llm_configs,
    knowledge,
    requirements,
    test_cases,
    api_tests,
    self_healing,
    issues,
    cicd,
    notifications,
    performance,
    performance_locust,
    db_config,
    project_members,
    project_environments,
    version_doc_history,
    project_settings,
    dashboard,
    skills,
    files,
    generation_tasks,
    requirement_changes,
    knowledge_graph,
    business_flow,
    scene,
    test_reports,
)

api_router = APIRouter()

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["authentication"],
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
)

api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["projects"],
)

api_router.include_router(
    versions.router,
    prefix="/versions",
    tags=["versions"],
)

api_router.include_router(
    files.router,
    prefix="/files",
    tags=["files"],
)

api_router.include_router(
    git.router,
    prefix="/git",
    tags=["git"],
)

api_router.include_router(
    tests.router,
    prefix="/tests",
    tags=["tests"],
)

api_router.include_router(
    rag.router,
    prefix="/rag",
    tags=["rag"],
)

api_router.include_router(
    web_ui_tests.router,
    prefix="/web-ui-tests",
    tags=["web-ui-tests"],
)

api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
)

api_router.include_router(
    settings.router,
    prefix="/settings",
    tags=["settings"],
)

api_router.include_router(
    llm_configs.router,
    prefix="/llm-configs",
    tags=["llm-configs"],
)

api_router.include_router(
    knowledge.router,
    prefix="/knowledge",
    tags=["knowledge"],
)

api_router.include_router(
    requirements.router,
    prefix="/requirements",
    tags=["requirements"],
)

api_router.include_router(
    test_cases.router,
    prefix="/test-cases",
    tags=["test-cases"],
)

api_router.include_router(
    api_tests.router,
    prefix="/api-tests",
    tags=["api-tests"],
)

api_router.include_router(
    self_healing.router,
    prefix="/self-healing",
    tags=["self-healing"],
)

api_router.include_router(
    issues.router,
    prefix="/issues",
    tags=["issues"],
)

api_router.include_router(
    cicd.router,
    prefix="/cicd",
    tags=["cicd"],
)

api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["notifications"],
)

api_router.include_router(
    performance.router,
    prefix="/performance",
    tags=["performance"],
)

api_router.include_router(
    performance_locust.router,
    prefix="/performance",
    tags=["performance-locust"],
)

api_router.include_router(
    db_config.router,
    prefix="/system",
    tags=["system"],
)

api_router.include_router(
    project_members.router,
    prefix="/projects",
    tags=["project-members"],
)

api_router.include_router(
    project_environments.router,
    prefix="/projects",
    tags=["project-environments"],
)

api_router.include_router(
    version_doc_history.router,
    prefix="/projects",
    tags=["version-doc-history"],
)

api_router.include_router(
    project_settings.router,
    prefix="/projects",
    tags=["project-settings"],
)

api_router.include_router(
    dashboard.router,
    prefix="/dashboard",
    tags=["dashboard"],
)

api_router.include_router(
    skills.router,
    prefix="/skills",
    tags=["skills"],
)

api_router.include_router(
    generation_tasks.router,
    prefix="/generation",
    tags=["generation-tasks"],
)

api_router.include_router(
    requirement_changes.router,
    prefix="/requirement-changes",
    tags=["requirement-changes"],
)

api_router.include_router(
    knowledge_graph.router,
    prefix="/knowledge-graph",
    tags=["knowledge-graph"],
)

api_router.include_router(
    business_flow.router,
    prefix="/business-flow",
    tags=["business-flow"],
)

api_router.include_router(
    scene.router,
    prefix="/scenes",
    tags=["scenes"],
)

api_router.include_router(
    test_reports.router,
    prefix="/test-reports",
    tags=["test-reports"],
)