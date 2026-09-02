"""
测试报告 API — 查看 / 下载 / 删除 Allure 报告
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.core.models.user import User
from app.core.services.allure_reporter import ReportManager
from app.core.logger import logger

# 注意：prefix 统一在 app.api.api_v1.api.include_router 处加（prefix="/test-reports"），
# 此处不能再写 prefix，否则与全站其它模块风格不一致且会双前缀叠加，
# 导致真实路径变成 /api/v1/test-reports/test-reports/...，前端请求 /test-reports/list 404。
router = APIRouter(tags=["test-reports"])


# ═══════════════════════════════════════════════════════════
# 模型
# ═══════════════════════════════════════════════════════════

class ReportSummary(BaseModel):
    project: str
    version: str
    run_id: str
    run_ts: str
    has_html: bool
    has_results: bool
    summary: dict = Field(default_factory=dict)


class ReportListResponse(BaseModel):
    items: List[ReportSummary]
    total: int


class DeleteResponse(BaseModel):
    success: bool
    message: str = ""


# ═══════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════

@router.get("/list", response_model=ReportListResponse)
def list_reports(
    project: Optional[str] = Query(None, description="按项目筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """列出所有测试报告"""
    reports = ReportManager.list_reports(project_key=project)
    return ReportListResponse(items=reports, total=len(reports))


@router.get("/detail/{project}/{version}/{run_id}")
def get_report_detail(
    project: str, version: str, run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单个报告详情（含所有用例结果）"""
    report = ReportManager.get_report(project, version, run_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    return report


@router.get("/view/{project}/{version}/{run_id}")
def view_report_html(
    project: str, version: str, run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查看 Allure HTML 报告（需要有 allure-report/index.html）"""
    report_dir = ReportManager.BASE_DIR / project / version / run_id
    index_path = report_dir / "allure-report" / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "HTML 报告不存在。请在服务器运行 `allure generate` 生成。")
    return FileResponse(str(index_path), media_type="text/html")


@router.get("/download/{project}/{version}/{run_id}")
def download_report(
    project: str, version: str, run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """下载 Allure JSON 结果（打包为 ZIP）"""
    import zipfile, io

    run_dir = ReportManager.BASE_DIR / project / version / run_id
    if not run_dir.exists():
        raise HTTPException(404, "报告不存在")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in run_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(run_dir))
    buf.seek(0)

    return FileResponse(
        buf, media_type="application/zip",
        filename=f"allure-results-{project}-{version}-{run_id}.zip",
    )


@router.delete("/delete/{project}/{version}/{run_id}", response_model=DeleteResponse)
def delete_report(
    project: str, version: str, run_id: str,
    confirm: str = Query("", description="输入 'DELETE' 确认删除"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    删除测试报告 — 三重安全防护：
    1. 必须输入 confirm=DELETE 参数
    2. 路径穿越检测（.. / \\ 等）
    3. 目录必须是合法的报告目录（包含 allure-results 或 allure-report）
    """
    if confirm != "DELETE":
        return DeleteResponse(
            success=False,
            message="请在请求中添加 confirm=DELETE 参数以确认删除。此操作不可撤销！",
        )

    result = ReportManager.delete_report(project, version, run_id)
    return DeleteResponse(**result)


@router.delete("/delete-batch")
def batch_delete_reports(
    report_ids: List[str] = Query(..., description="报告ID列表，格式：project/version/run_id"),
    confirm: str = Query("", description="输入 'DELETE ALL' 确认批量删除"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量删除报告 — 需要 confirm=DELETE ALL"""
    if confirm != "DELETE ALL":
        return JSONResponse(
            content={
                "success": False,
                "message": "批量删除需要 confirm=DELETE ALL 参数。此操作不可撤销！",
            },
        )

    results = []
    for rid in report_ids:
        parts = rid.split("/")
        if len(parts) != 3:
            results.append({"report_id": rid, "success": False, "error": "格式错误"})
            continue
        result = ReportManager.delete_report(parts[0], parts[1], parts[2])
        result["report_id"] = rid
        results.append(result)

    return {"results": results}


@router.get("/serve/{project}/{version}/{run_id}")
def serve_allure_report(
    project: str, version: str, run_id: str,
    path: str = Query("", description="子路径"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提供 Allure HTML 报告的静态资源（CSS/JS/图片等）"""
    report_dir = ReportManager.BASE_DIR / project / version / run_id / "allure-report"

    # 安全检查
    clean_path = path.replace("..", "").replace("\\", "/").lstrip("/")
    file_path = report_dir / (clean_path or "index.html")

    if not file_path.exists() or not str(file_path.resolve()).startswith(str(report_dir.resolve())):
        raise HTTPException(404, "文件不存在")

    # MIME 类型
    ext = file_path.suffix.lower()
    mime_map = {
        ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
        ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml",
        ".woff": "font/woff", ".woff2": "font/woff2",
    }
    return FileResponse(str(file_path), media_type=mime_map.get(ext, "application/octet-stream"))
