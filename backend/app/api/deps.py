"""FastAPI 依賴：容器、DB Session、使用者識別。"""

import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.integrations.duffel_client import DuffelClient
from app.services.credentials import InvalidTokenFormat, validate_token

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,100}$")


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_id(x_user_id: Annotated[str | None, Header()] = None) -> str:
    """本系統不含帳號登入；以前端產生的匿名識別碼（或通知端點）區分使用者。"""
    if not x_user_id or not _USER_ID_RE.match(x_user_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少或無效的 X-User-Id 標頭")
    return x_user_id


UserDep = Annotated[str, Depends(get_user_id)]


def get_user_token(x_duffel_token: Annotated[str | None, Header()] = None) -> str | None:
    """使用者自備的 Duffel 金鑰（選填）；格式不符直接拒絕，不轉送到外部。"""
    if not x_duffel_token:
        return None
    token = x_duffel_token.strip()
    try:
        validate_token(token)
    except InvalidTokenFormat as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return token


UserTokenDep = Annotated[str | None, Depends(get_user_token)]


def get_duffel(container: ContainerDep, user_token: UserTokenDep) -> DuffelClient:
    return container.gateway.client(user_token)


DuffelDep = Annotated[DuffelClient, Depends(get_duffel)]
