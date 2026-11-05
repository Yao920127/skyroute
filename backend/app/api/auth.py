"""帳號路由：Google 登入／登出、目前使用者、帳號專屬的 Duffel 金鑰。"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, SessionDep
from app.container import Container
from app.integrations.duffel_client import DuffelError
from app.models import User
from app.schemas import AccountKeyIn, AccountOut, ApiResponse, GoogleLogin
from app.services.auth import (
    SESSION_COOKIE,
    LoginRequired,
    account_key,
    claim_anonymous_watchlists,
    set_account_key,
    upsert_user,
)
from app.services.credentials import (
    CipherUnavailable,
    InvalidTokenFormat,
    TokenMode,
    validate_token,
)

router = APIRouter(prefix="/api", tags=["auth"])

KEY_MASK_TAIL = 4


def _account(container: Container, user: User) -> AccountOut:
    token = account_key(container.cipher, user)
    mode: TokenMode | None = validate_token(token) if token else None
    mask = f"duffel_{mode}_••••{token[-KEY_MASK_TAIL:]}" if token and mode else None
    return AccountOut(
        email=user.email, name=user.name, picture=user.picture, key_mask=mask, key_mode=mode
    )


def _require_user(user: User | None) -> User:
    if user is None:
        raise LoginRequired("請先以 Google 帳號登入")
    return user


@router.post("/auth/google", response_model=ApiResponse[AccountOut])
async def login_with_google(
    body: GoogleLogin,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
    x_user_id: Annotated[str | None, Header()] = None,
) -> ApiResponse[AccountOut]:
    """以 Google ID Token 登入；登入前在這台瀏覽器建立的追蹤會一併轉入帳號。"""
    auth = container.auth
    if auth.verifier is None or auth.signer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "此伺服器未啟用 Google 登入")
    profile = await auth.verifier.verify(body.credential)
    user = await upsert_user(session, profile)
    claimed = await claim_anonymous_watchlists(session, user, x_user_id) if x_user_id else 0
    response.set_cookie(
        SESSION_COOKIE,
        auth.signer.issue(user.id),
        max_age=auth.signer.ttl_s,
        httponly=True,
        secure=auth.cookie_secure,
        samesite="lax",
        path="/",
    )
    return ApiResponse(data=_account(container, user), meta={"claimed_watchlists": claimed})


@router.post("/auth/logout", response_model=ApiResponse[None])
async def logout(response: Response, container: ContainerDep) -> ApiResponse[None]:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=container.auth.cookie_secure,
        samesite="lax",
    )
    return ApiResponse(data=None)


@router.get("/auth/me", response_model=ApiResponse[AccountOut | None])
async def me(container: ContainerDep, user: CurrentUserDep) -> ApiResponse[AccountOut | None]:
    """未登入時 data 為 null（不是錯誤），前端據此顯示「登入」按鈕。"""
    return ApiResponse(data=_account(container, user) if user else None)


@router.put("/me/duffel-key", response_model=ApiResponse[AccountOut])
async def save_account_key(
    body: AccountKeyIn, container: ContainerDep, session: SessionDep, user: CurrentUserDep
) -> ApiResponse[AccountOut]:
    """先實際呼叫 Duffel 驗證金鑰，再加密存入帳號；之後搜尋與背景巡檢都改用這把金鑰。"""
    owner = _require_user(user)
    token = body.token.strip()
    try:
        validate_token(token)
    except InvalidTokenFormat as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    try:
        await container.gateway.client(token).verify()
    except DuffelError as exc:
        if exc.status in (401, 403):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Duffel 拒絕了這把金鑰") from exc
        raise
    try:
        await set_account_key(session, container.cipher, owner, token)
    except CipherUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return ApiResponse(data=_account(container, owner))


@router.delete("/me/duffel-key", response_model=ApiResponse[AccountOut])
async def clear_account_key(
    container: ContainerDep, session: SessionDep, user: CurrentUserDep
) -> ApiResponse[AccountOut]:
    """清除帳號金鑰，之後改用伺服器預設金鑰。"""
    owner = _require_user(user)
    await set_account_key(session, container.cipher, owner, None)
    return ApiResponse(data=_account(container, owner))
