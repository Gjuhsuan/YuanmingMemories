"""
档案影像路由 —— 根据 sourceText 定位 PDF 页码并返回 PNG 访问信息。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..services.archive_locator import locate_page, get_page_count, get_page_url

router = APIRouter(prefix="/api/archive", tags=["archive"])


class LocateRequest(BaseModel):
    sourceText: str


class LocateResponse(BaseModel):
    page: int | None        # 匹配到的页码（1-based），无匹配则为 None
    imageUrl: str | None    # PNG 图片 URL
    totalPages: int         # 总页数
    hasMatch: bool          # 是否有匹配


@router.post("/locate", response_model=LocateResponse)
def locate(req: LocateRequest):
    """根据 sourceText 定位档案页码。"""
    page = locate_page(req.sourceText)
    total = get_page_count()
    if page is not None:
        return LocateResponse(
            page=page,
            imageUrl=get_page_url(page),
            totalPages=total,
            hasMatch=True,
        )
    return LocateResponse(
        page=None,
        imageUrl=None,
        totalPages=total,
        hasMatch=False,
    )


@router.get("/info")
def info():
    """返回档案基本信息。"""
    return {
        "totalPages": get_page_count(),
        "pngBaseUrl": "/static/archive/",
    }
