"""FastAPI 依賴：容器、DB Session、使用者識別。"""

import re
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.integrations.duffel_client import DuffelClient
from app.models import User
from app.services.auth import SESSION_COOKIE, LoginRequired, account_key, user_identifier
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


async def get_current_user(
    request: Request, container: ContainerDep, session: SessionDep
) -> User | None:
    """由簽章 Cookie 取得登入中的使用者；未登入、Cookie 無效或過期時為 None。"""
    signer = container.auth.signer
    raw = request.cookies.get(SESSION_COOKIE)
    if signer is None or not raw:
        return None
    user_id = signer.verify(raw)
    return await session.get(User, user_id) if user_id else None


CurrentUserDep = Annotated[User | None, Depends(get_current_user)]


def get_user_id(
    container: ContainerDep,
    user: CurrentUserDep,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """看盤清單的擁有者：已登入用帳號；啟用 Google 登入後必須登入，否則沿用匿名識別碼。"""
    if user is not None:
        return user_identifier(user)
    if container.auth.enabled:
        raise LoginRequired("請先以 Google 帳號登入")
    if not x_user_id or not _USER_ID_RE.match(x_user_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少或無效的 X-User-Id 標頭")
    return x_user_id


UserDep = Annotated[str, Depends(get_user_id)]


def get_user_token(
    container: ContainerDep,
    user: CurrentUserDep,
    x_duffel_token: Annotated[str | None, Header()] = None,
) -> str | None:
    """選用的 Duffel 金鑰：標頭（未登入時由瀏覽器提供）> 帳號金鑰 > 無（使用伺服器預設金鑰）。"""
    if not x_duffel_token:
        return account_key(container.cipher, user)
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
