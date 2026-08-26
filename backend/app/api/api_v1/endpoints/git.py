"""
Git版本管理API端点 - 完整实现
对应需求文档 3.2 Git版本管理
"""

import subprocess
import re
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.models.git import (
    GitRepository, GitBranch, GitCommit, GitWebhook, GitWebhookLog,
    GitCommitTestCase, AuthType, RepositoryStatus
)
from app.core.schemas.git import (
    RepositoryCreate, RepositoryUpdate, RepositoryResponse, RepositoryListResponse,
    RepositoryTestResult, BranchResponse, BranchListResponse,
    CommitResponse, CommitDetailResponse, CommitListResponse,
    WebhookCreate, WebhookUpdate, WebhookResponse, WebhookListResponse,
    WebhookLogResponse, WebhookLogListResponse,
    BranchCompareRequest, BranchCompareResponse,
    CommitLinkRequest, SyncRepositoryRequest
)
from app.core.logger import logger
from app.core.config import settings
from app.core.middleware.permission_middleware import Permissions

router = APIRouter()


@router.post("/", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def create_repository(
    repo_in: RepositoryCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_CREATE)
):
    """添加仓库"""
    from app.core.models.project import Project
    
    project = db.query(Project).filter(Project.id == repo_in.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=f"项目ID {repo_in.project_id} 不存在")
    
    existing = db.query(GitRepository).filter(
        GitRepository.project_id == repo_in.project_id,
        GitRepository.url == repo_in.url
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该仓库URL已存在于项目中")
    
    repo = GitRepository(
        project_id=repo_in.project_id,
        name=repo_in.name,
        url=repo_in.url,
        auth_type=repo_in.auth_type.value,
        auth_token=repo_in.auth_token,
        ssh_key=repo_in.ssh_key,
        username=repo_in.username,
        password=repo_in.password,
        default_branch=repo_in.default_branch,
        status=RepositoryStatus.ACTIVE.value
    )
    
    db.add(repo)
    db.commit()
    db.refresh(repo)
    
    logger.info(f"创建Git仓库成功: {repo.name}")
    
    return RepositoryResponse.model_validate(repo)


@router.get("/", response_model=RepositoryListResponse)
def list_repositories(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    project_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_READ)
):
    """仓库列表"""
    query = db.query(GitRepository)
    
    if project_id:
        query = query.filter(GitRepository.project_id == project_id)
    
    if status_filter:
        query = query.filter(GitRepository.status == status_filter)
    
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                GitRepository.name.ilike(pattern),
                GitRepository.url.ilike(pattern)
            )
        )
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    repos = query.order_by(GitRepository.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return RepositoryListResponse(
        items=[RepositoryResponse.model_validate(r) for r in repos],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{repo_id}", response_model=RepositoryResponse)
def get_repository(repo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_READ)):
    """获取仓库详情"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    return RepositoryResponse.model_validate(repo)


@router.put("/{repo_id}", response_model=RepositoryResponse)
def update_repository(
    repo_id: int,
    repo_in: RepositoryUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_UPDATE)
):
    """编辑仓库"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    update_data = repo_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == 'auth_type' and value:
            value = value.value
        setattr(repo, field, value)
    
    db.commit()
    db.refresh(repo)
    
    logger.info(f"更新Git仓库: {repo.name}")
    
    return RepositoryResponse.model_validate(repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(repo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_DELETE)):
    """删除仓库"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    db.delete(repo)
    db.commit()
    
    logger.info(f"删除Git仓库: {repo.name}")
    
    return None


@router.post("/{repo_id}/test", response_model=RepositoryTestResult)
def test_repository_connection(repo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_SYNC)):
    """测试仓库连接"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    try:
        result = _test_git_connection(repo)
        
        repo.last_sync_at = datetime.utcnow()
        repo.last_sync_status = "success" if result["success"] else "error"
        repo.last_sync_error = None if result["success"] else result["message"]
        db.commit()
        
        return RepositoryTestResult(**result)
    except Exception as e:
        repo.last_sync_at = datetime.utcnow()
        repo.last_sync_status = "error"
        repo.last_sync_error = str(e)
        db.commit()
        
        return RepositoryTestResult(success=False, message=str(e))


def _test_git_connection(repo: GitRepository) -> dict:
    """执行Git连接测试"""
    try:
        cmd = ["git", "ls-remote", "--heads", repo.url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return {"success": False, "message": result.stderr or "连接失败"}
        
        branches = []
        for line in result.stdout.strip().split('\n'):
            if line:
                match = re.search(r'refs/heads/(.+)$', line)
                if match:
                    branches.append(match.group(1))
        
        last_commit = None
        if branches:
            cmd = ["git", "ls-remote", repo.url, f"refs/heads/{repo.default_branch}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                parts = result.stdout.strip().split()
                if parts:
                    last_commit = {"hash": parts[0][:7], "full_hash": parts[0]}
        
        return {
            "success": True,
            "message": "连接成功",
            "branch_count": len(branches),
            "last_commit": last_commit
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "连接超时"}
    except Exception as e:
        return {"success": False, "message": f"连接错误: {str(e)}"}


@router.post("/{repo_id}/sync", response_model=dict)
def sync_repository(
    repo_id: int,
    sync_in: SyncRepositoryRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_SYNC)
):
    """同步仓库数据（分支和提交）"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    try:
        branches_synced = _sync_branches(repo, db)
        commits_synced = _sync_commits(repo, db)
        
        repo.last_sync_at = datetime.utcnow()
        repo.last_sync_status = "success"
        repo.last_sync_error = None
        db.commit()
        
        return {
            "success": True,
            "message": "同步成功",
            "branches_synced": branches_synced,
            "commits_synced": commits_synced
        }
    except Exception as e:
        repo.last_sync_at = datetime.utcnow()
        repo.last_sync_status = "error"
        repo.last_sync_error = str(e)
        db.commit()
        
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


def _sync_branches(repo: GitRepository, db: Session) -> int:
    """同步分支数据"""
    cmd = ["git", "ls-remote", "--heads", repo.url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        raise Exception(result.stderr or "获取分支失败")
    
    count = 0
    for line in result.stdout.strip().split('\n'):
        if line:
            match = re.search(r'([a-f0-9]+)\s+refs/heads/(.+)$', line)
            if match:
                commit_hash = match.group(1)
                branch_name = match.group(2)
                
                existing = db.query(GitBranch).filter(
                    GitBranch.repository_id == repo.id,
                    GitBranch.name == branch_name
                ).first()
                
                if existing:
                    existing.last_commit_hash = commit_hash
                    existing.status = "active"
                else:
                    branch = GitBranch(
                        repository_id=repo.id,
                        name=branch_name,
                        last_commit_hash=commit_hash,
                        is_default=1 if branch_name == repo.default_branch else 0,
                        status="active"
                    )
                    db.add(branch)
                count += 1
    
    db.commit()
    return count


def _sync_commits(repo: GitRepository, db: Session) -> int:
    """同步提交数据"""
    count = 0
    branches = db.query(GitBranch).filter(
        GitBranch.repository_id == repo.id,
        GitBranch.status == "active"
    ).limit(10).all()
    
    for branch in branches:
        cmd = ["git", "ls-remote", repo.url, f"refs/heads/{branch.name}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout:
            parts = result.stdout.strip().split()
            if parts:
                commit_hash = parts[0]
                
                existing = db.query(GitCommit).filter(
                    GitCommit.repository_id == repo.id,
                    GitCommit.commit_hash == commit_hash
                ).first()
                
                if not existing:
                    commit = GitCommit(
                        repository_id=repo.id,
                        commit_hash=commit_hash,
                        short_hash=commit_hash[:7],
                        branch=branch.name
                    )
                    db.add(commit)
                    count += 1
    
    db.commit()
    return count


@router.get("/{repo_id}/branches", response_model=BranchListResponse)
def list_branches(repo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_READ)):
    """分支列表"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    branches = db.query(GitBranch).filter(
        GitBranch.repository_id == repo_id,
        GitBranch.status == "active"
    ).order_by(GitBranch.is_default.desc(), GitBranch.name).all()
    
    return BranchListResponse(
        items=[BranchResponse.model_validate(b) for b in branches],
        total=len(branches)
    )


@router.get("/{repo_id}/commits", response_model=CommitListResponse)
def list_commits(
    repo_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    branch: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_READ)
):
    """提交记录列表"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    query = db.query(GitCommit).filter(GitCommit.repository_id == repo_id)
    
    if branch:
        query = query.filter(GitCommit.branch == branch)
    
    if author:
        query = query.filter(GitCommit.author.ilike(f"%{author}%"))
    
    if search:
        query = query.filter(GitCommit.message.ilike(f"%{search}%"))
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    commits = query.order_by(GitCommit.committed_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return CommitListResponse(
        items=[CommitResponse.model_validate(c) for c in commits],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{repo_id}/commits/{commit_id}", response_model=CommitDetailResponse)
def get_commit(repo_id: int, commit_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_READ)):
    """提交详情"""
    commit = db.query(GitCommit).filter(
        GitCommit.id == commit_id,
        GitCommit.repository_id == repo_id
    ).first()
    
    if not commit:
        raise HTTPException(status_code=404, detail=f"提交ID {commit_id} 不存在")
    
    return CommitDetailResponse.model_validate(commit)


@router.post("/{repo_id}/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    repo_id: int,
    webhook_in: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_WEBHOOK)
):
    """创建Webhook"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    import secrets
    secret = secrets.token_hex(16)
    
    webhook_url = f"{settings.API_V1_STR}/git/webhooks/{repo_id}/receive"
    
    webhook = GitWebhook(
        repository_id=repo_id,
        name=webhook_in.name,
        webhook_url=webhook_url,
        secret=secret,
        trigger_events=webhook_in.trigger_events,
        trigger_branches=webhook_in.trigger_branches,
        trigger_paths=webhook_in.trigger_paths,
        test_plan_id=webhook_in.test_plan_id,
        execution_config=webhook_in.execution_config,
        enabled=1
    )
    
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    
    logger.info(f"创建Webhook: repo_id={repo_id}")
    
    return WebhookResponse.model_validate(webhook)


@router.get("/{repo_id}/webhooks", response_model=WebhookListResponse)
def list_webhooks(repo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_WEBHOOK)):
    """Webhook列表"""
    webhooks = db.query(GitWebhook).filter(GitWebhook.repository_id == repo_id).all()
    
    return WebhookListResponse(
        items=[WebhookResponse.model_validate(w) for w in webhooks],
        total=len(webhooks)
    )


@router.put("/{repo_id}/webhooks/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    repo_id: int,
    webhook_id: int,
    webhook_in: WebhookUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_WEBHOOK)
):
    """更新Webhook"""
    webhook = db.query(GitWebhook).filter(
        GitWebhook.id == webhook_id,
        GitWebhook.repository_id == repo_id
    ).first()
    
    if not webhook:
        raise HTTPException(status_code=404, detail=f"Webhook ID {webhook_id} 不存在")
    
    update_data = webhook_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == 'enabled':
            value = 1 if value else 0
        setattr(webhook, field, value)
    
    db.commit()
    db.refresh(webhook)
    
    return WebhookResponse.model_validate(webhook)


@router.delete("/{repo_id}/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(repo_id: int, webhook_id: int, db: Session = Depends(get_db), current_user: dict = Depends(Permissions.GIT_WEBHOOK)):
    """删除Webhook"""
    webhook = db.query(GitWebhook).filter(
        GitWebhook.id == webhook_id,
        GitWebhook.repository_id == repo_id
    ).first()
    
    if not webhook:
        raise HTTPException(status_code=404, detail=f"Webhook ID {webhook_id} 不存在")
    
    db.delete(webhook)
    db.commit()
    
    return None


@router.post("/webhooks/{repo_id}/receive")
def receive_webhook(
    repo_id: int,
    event_type: str = Query(...),
    db: Session = Depends(get_db)
):
    """接收Webhook回调"""
    repo = db.query(GitRepository).filter(GitRepository.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"仓库ID {repo_id} 不存在")
    
    webhooks = db.query(GitWebhook).filter(
        GitWebhook.repository_id == repo_id,
        GitWebhook.enabled == 1
    ).all()
    
    triggered_count = 0
    for webhook in webhooks:
        if event_type in (webhook.trigger_events or []):
            log = GitWebhookLog(
                webhook_id=webhook.id,
                event_type=event_type,
                triggered=1,
                trigger_reason=f"事件 {event_type} 匹配触发规则"
            )
            db.add(log)
            
            webhook.last_triggered_at = datetime.utcnow()
            webhook.trigger_count = (webhook.trigger_count or 0) + 1
            triggered_count += 1
    
    db.commit()
    
    return {"success": True, "triggered_count": triggered_count}


@router.get("/{repo_id}/webhooks/{webhook_id}/logs", response_model=WebhookLogListResponse)
def list_webhook_logs(
    repo_id: int,
    webhook_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(Permissions.GIT_WEBHOOK)
):
    """Webhook日志列表"""
    webhook = db.query(GitWebhook).filter(
        GitWebhook.id == webhook_id,
        GitWebhook.repository_id == repo_id
    ).first()
    
    if not webhook:
        raise HTTPException(status_code=404, detail=f"Webhook ID {webhook_id} 不存在")
    
    query = db.query(GitWebhookLog).filter(GitWebhookLog.webhook_id == webhook_id)
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    logs = query.order_by(GitWebhookLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return WebhookLogListResponse(
        items=[WebhookLogResponse.model_validate(l) for l in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )