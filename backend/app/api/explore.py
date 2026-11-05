"""航班探索路由：機場建議、多條件搜尋、彈性日期價格矩陣。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.deps import ContainerDep, DuffelDep, SessionDep, UserTokenDep
from app.integrations.duffel_client import DuffelClient, MissingCredentialsError
from app.schemas import (
    AirportOut,
    ApiResponse,
    FxTable,
    MatrixRequest,
    SearchRequest,
    SearchResult,
)
from app.services.airport_service import expand_code, fold, search_with_fallback
from app.services.explore_service import run_search, stream_matrix
from app.services.fx import SUPPORTED_CURRENCIES

router = APIRouter(prefix="/api", tags=["explore"])


PLACE_MISS_TTL_S = 24 * 60 * 60


@router.get("/airports", response_model=ApiResponse[list[AirportOut]])
async def airports(
    session: SessionDep,
    container: ContainerDep,
    user_token: UserTokenDep,
    q: Annotated[str, Query(min_length=1, max_length=40)],
) -> ApiResponse[list[AirportOut]]:
    """先查本機的全球機場對照表；找不到時才問 Duffel（同一個查不到的字一天只問一次）。"""
    miss_key = f"places-miss:{fold(q.strip())}"
    client: DuffelClient | None = None
    if await container.cache.get(miss_key) is None:
        try:
            client = container.gateway.client(user_token)
        except MissingCredentialsError:
            client = None
    rows = await search_with_fallback(session, client, q)
    if not rows and client is not None:
        await container.cache.set(miss_key, "1", PLACE_MISS_TTL_S)
    return ApiResponse(data=[AirportOut.model_validate(r) for r in rows])


@router.post("/search", response_model=ApiResponse[SearchResult])
async def search(
    body: SearchRequest, container: ContainerDep, session: SessionDep, duffel: DuffelDep
) -> ApiResponse[SearchResult]:
    origins = await expand_code(session, body.origin)
    destinations = await expand_code(session, body.destination)
    fx = await container.fx.rates()
    result = await run_search(container.search, duffel, fx, body, origins, destinations)
    return ApiResponse(data=result)


@router.post("/fare-matrix", response_class=StreamingResponse)
async def fare_matrix(
    body: MatrixRequest, container: ContainerDep, duffel: DuffelDep
) -> StreamingResponse:
    """NDJSON 串流：axes → cell × N → done。前端可邊收邊畫熱力圖。"""
    fx = await container.fx.rates()
    stream = stream_matrix(
        container.search, duffel, fx, body, container.settings.matrix_concurrency, date.today()
    )
    return StreamingResponse(
        stream,
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/fx", response_model=ApiResponse[FxTable])
async def fx_rates(container: ContainerDep) -> ApiResponse[FxTable]:
    """支援的幣別與匯率（1 USD = x），供前端換算看盤資料與顯示匯率時間。"""
    fx = await container.fx.rates()
    return ApiResponse(
        data=FxTable(
            base="USD",
            rates={code: fx.rates[code] for code in SUPPORTED_CURRENCIES},
            as_of=fx.as_of,
            source=fx.source,
            approximate=fx.approximate,
        )
    )
