"""金鑰相關路由：查詢伺服器能力、驗證使用者自備的 Duffel 金鑰。"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ContainerDep, UserTokenDep
from app.integrations.duffel_client import DuffelError
from app.schemas import ApiResponse, AppConfig, CredentialCheck
from app.services.credentials import validate_token

router = APIRouter(prefix="/api", tags=["credentials"])


@router.get("/config", response_model=ApiResponse[AppConfig])
async def app_config(container: ContainerDep) -> ApiResponse[AppConfig]:
    return ApiResponse(
        data=AppConfig(
            has_server_key=container.gateway.has_server_token,
            can_store_user_key=container.cipher.available,
        )
    )


@router.post("/credentials/verify", response_model=ApiResponse[CredentialCheck])
async def verify_credentials(
    container: ContainerDep, user_token: UserTokenDep
) -> ApiResponse[CredentialCheck]:
    """以 X-Duffel-Token 實際呼叫一次 Duffel，確認金鑰有效；金鑰不會被儲存或記錄。"""
    if not user_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "請在 X-Duffel-Token 標頭提供金鑰")
    try:
        await container.gateway.client(user_token).verify()
    except DuffelError as exc:
        if exc.status in (401, 403):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Duffel 拒絕了這把金鑰") from exc
        raise
    return ApiResponse(data=CredentialCheck(valid=True, mode=validate_token(user_token)))
