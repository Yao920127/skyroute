"""自選看盤路由：建立、列表（含看盤統計）、軟刪除、歷史價格、告警紀錄、手動巡檢。"""

import secrets
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.deps import ContainerDep, DuffelDep, SessionDep, UserDep, UserTokenDep
from app.schemas import (
    AlertOut,
    ApiResponse,
    DeletedCount,
    PatrolReport,
    PricePoint,
    WatchlistCreate,
    WatchlistOut,
)
from app.services import watchlist_service as svc
from app.services.patrol import run_patrol

router = APIRouter(prefix="/api", tags=["watchlists"])


@router.get("/watchlists", response_model=ApiResponse[list[WatchlistOut]])
async def list_watchlists(
    session: SessionDep, user: UserDep, include_inactive: bool = True
) -> ApiResponse[list[WatchlistOut]]:
    items = await svc.list_watchlists(session, user, include_inactive)
    return ApiResponse(data=items, meta={"total": len(items)})


@router.post(
    "/watchlists", response_model=ApiResponse[WatchlistOut], status_code=status.HTTP_201_CREATED
)
async def create_watchlist(
    body: WatchlistCreate,
    session: SessionDep,
    user: UserDep,
    container: ContainerDep,
    duffel: DuffelDep,
    user_token: UserTokenDep,
) -> ApiResponse[WatchlistOut]:
    created = await svc.create_watchlist(
        session,
        duffel,
        user,
        body,
        container.settings.webhook_allowed_hosts,
        container.cipher,
        user_token,
    )
    return ApiResponse(data=created)


@router.delete("/watchlists", response_model=ApiResponse[DeletedCount])
async def purge_ended_watchlists(
    session: SessionDep,
    user: UserDep,
    scope: Annotated[Literal["ended"], Query(description="目前僅支援 ended：已取消＋已過期")],
) -> ApiResponse[DeletedCount]:
    """批次永久刪除已結束（已取消／已過期）的追蹤。"""
    return ApiResponse(data=DeletedCount(deleted=await svc.purge_ended(session, user)))


@router.delete("/watchlists/{watch_id}", response_model=ApiResponse[WatchlistOut | None])
async def cancel_watchlist(
    watch_id: uuid.UUID,
    session: SessionDep,
    user: UserDep,
    purge: Annotated[bool, Query(description="true＝永久刪除（含歷史），預設為軟刪除")] = False,
) -> ApiResponse[WatchlistOut | None]:
    """預設為軟刪除（狀態改為 CANCELLED、保留歷史）；purge=true 時永久刪除。"""
    if purge:
        await svc.purge_watchlist(session, user, watch_id)
        return ApiResponse(data=None, meta={"purged": True})
    return ApiResponse(data=await svc.cancel_watchlist(session, user, watch_id))


@router.get("/watchlists/{watch_id}/history", response_model=ApiResponse[list[PricePoint]])
async def history(
    watch_id: uuid.UUID,
    session: SessionDep,
    user: UserDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> ApiResponse[list[PricePoint]]:
    return ApiResponse(data=await svc.price_history(session, user, watch_id, days))


@router.get("/watchlists/{watch_id}/alerts", response_model=ApiResponse[list[AlertOut]])
async def alerts(
    watch_id: uuid.UUID, session: SessionDep, user: UserDep
) -> ApiResponse[list[AlertOut]]:
    return ApiResponse(data=await svc.alert_history(session, user, watch_id))


@router.post("/patrol/run", response_model=ApiResponse[PatrolReport])
async def trigger_patrol(
    container: ContainerDep, x_admin_token: Annotated[str | None, Header()] = None
) -> ApiResponse[PatrolReport]:
    """手動觸發一次巡檢（展示與維運用）。設定 ADMIN_TOKEN 後需帶 X-Admin-Token。"""
    expected = container.settings.admin_token
    if expected is not None and not secrets.compare_digest(
        x_admin_token or "", expected.get_secret_value()
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要有效的 X-Admin-Token")
    settings = container.settings
    report = await run_patrol(
        container.patrol_context(),
        container.cache,
        settings.patrol_consumers,
        settings.patrol_lock_ttl_s,
    )
    return ApiResponse(data=report)
