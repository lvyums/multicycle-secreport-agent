"""版本 API — 列表 / 详情 / 内容 / 下载"""

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from api.response import ok
from app.services.version_service import VersionService
from common.exception.exception import NotFoundError
from model.enum.enums import ReportCycle

router = APIRouter()


@router.get("/list")
def version_list(cycle: str | None = None, page: int = Query(1, ge=1),
                 limit: int = Query(15, ge=1, le=100), keyword: str | None = None):
    """版本列表（分页，可按周期/关键词过滤）"""
    if cycle:
        cycle = cycle.upper()
        if cycle not in [c.value for c in ReportCycle]:
            return ok({"items": [], "total": 0, "page": page, "limit": limit})
    data = VersionService.list_all(cycle=cycle, page=page, limit=limit, keyword=keyword)
    for item in data["items"]:
        try:
            item["cycleLabel"] = ReportCycle(item["cycle"]).label
        except ValueError:
            item["cycleLabel"] = item["cycle"]
    return ok(data)


@router.get("/detail/{version_id}")
def version_detail(version_id: int):
    """版本详情"""
    return ok(VersionService.get(version_id))


@router.get("/content/{version_id}")
def version_content(version_id: int):
    """版本内容（Markdown 文本，供前端预览）"""
    return ok(VersionService.get_content(version_id))


@router.get("/download/{version_id}")
def version_download(version_id: int):
    """下载报告文件（存在返回文件，否则实时落盘）"""
    info = VersionService.get_download(version_id)
    path = info["path"]
    if not path:
        raise NotFoundError(f"版本 {version_id} 无内容可下载")
    return FileResponse(
        path, filename=path.split("/")[-1],
        media_type="application/octet-stream",
    )
