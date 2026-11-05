"""FastAPI 應用程式工廠。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api import credentials, explore, watchlists
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.db import init_schema
from app.i18n import language_of, translate
from app.integrations.duffel_client import DuffelError, MissingCredentialsError
from app.services.airport_service import seed_airports
from app.services.watchlist_service import NotFoundError, ValidationFailed

log = logging.getLogger(__name__)


def _error(
    request: Request, status_code: int, message: str, meta: dict[str, object] | None = None
) -> JSONResponse:
    """統一錯誤信封；錯誤訊息依 Accept-Language 回傳繁中或英文。"""
    lang = language_of(request.headers.get("accept-language"))
    body = {"success": False, "data": None, "error": translate(message, lang), "meta": meta}
    return JSONResponse(status_code=status_code, content=body)


def _validation_message(exc: RequestValidationError) -> tuple[str, list[dict[str, str]]]:
    details = [
        {"loc": ".".join(str(p) for p in err.get("loc", ())), "msg": str(err.get("msg", ""))}
        for err in exc.errors()
    ]
    first = details[0]["msg"] if details else "輸入資料格式錯誤"
    return str(first).removeprefix("Value error, "), details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        message, details = _validation_message(exc)
        return _error(request, 422, message, {"details": details})

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        return _error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error(request, 404, str(exc))

    @app.exception_handler(ValidationFailed)
    async def _invalid(request: Request, exc: ValidationFailed) -> JSONResponse:
        return _error(request, 422, str(exc))

    @app.exception_handler(MissingCredentialsError)
    async def _missing_key(request: Request, exc: MissingCredentialsError) -> JSONResponse:
        return _error(request, 401, str(exc), {"code": "missing_api_key"})

    @app.exception_handler(DuffelError)
    async def _duffel(request: Request, exc: DuffelError) -> JSONResponse:
        log.error("Duffel 錯誤：%s", exc)
        if exc.status in (401, 403):
            # 使用者金鑰失效：回 401 讓前端提示重新設定，而不是當成伺服器錯誤
            return _error(
                request,
                401,
                "Duffel 拒絕了目前的 API 金鑰，請檢查設定",
                {"code": "invalid_api_key"},
            )
        status_code = 422 if exc.status in (400, 422) else 502
        return _error(request, status_code, exc.user_message)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = container is None
        active = container or build_container(settings)
        if owned:
            await init_schema(active.engine)
            async with active.sessions() as session:
                count = await seed_airports(session)
            log.info("機場對照表已就緒（%d 筆），快取後端：%s", count, active.cache.backend)
        app.state.container = active
        yield
        if owned:
            await active.close()

    app = FastAPI(
        title="SkyRoute API",
        version="0.1.0",
        description="智慧機票探索與低價看盤監控系統",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Accept-Language",
            "X-User-Id",
            "X-Admin-Token",
            "X-Duffel-Token",
        ],
    )
    register_error_handlers(app)
    app.include_router(explore.router)
    app.include_router(watchlists.router)
    app.include_router(credentials.router)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """直接開後端網址時導向互動式 API 文件（Swagger UI）。"""
        return RedirectResponse(url=app.docs_url or "/redoc")

    @app.get("/api/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


def app_factory() -> FastAPI:  # uvicorn --factory 入口
    _configure_logging()
    return create_app()
