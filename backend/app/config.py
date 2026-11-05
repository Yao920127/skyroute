"""集中式設定：全部由環境變數（或 .env）讀入，啟動時即驗證必要值。"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- 基礎設施 ---
    database_url: str = "postgresql+asyncpg://localhost:5432/skyroute"
    redis_url: str | None = None  # 未設定時退回行程內記憶體快取
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- Duffel 外部 API ---
    # 伺服器預設金鑰（選填）：未設定時使用者必須在前端輸入自己的金鑰
    duffel_access_token: SecretStr | None = None
    duffel_base_url: str = "https://api.duffel.com"
    duffel_supplier_timeout_ms: int = Field(default=10_000, ge=2_000, le=60_000)
    duffel_http_timeout_s: float = 60.0

    # --- 快取與節流 ---
    search_cache_ttl_s: int = 30 * 60
    # Duffel 測試帳號 offer_requests 配額約每分鐘 30 次；預設值讓每分鐘 ≤ 28 次
    outbound_rate_per_s: float = Field(default=0.4, gt=0)
    outbound_burst: int = Field(default=4, ge=1)
    matrix_concurrency: int = Field(default=6, ge=1, le=20)

    # --- 資料清理 ---
    # Duffel 測試環境的虛構航司（Duffel Airways = ZZ），不是真實報價，預設一律剔除
    excluded_airlines: list[str] = ["ZZ"]

    # --- 匯率 ---
    fx_source_url: str = "https://open.er-api.com/v6/latest/USD"
    fx_ttl_s: int = 6 * 60 * 60
    default_currency: str = "TWD"

    # --- 背景巡檢 ---
    patrol_daily_at: str = "03:00"
    patrol_timezone: str = "Asia/Taipei"
    patrol_run_on_start: bool = False
    patrol_consumers: int = Field(default=3, ge=1, le=10)
    patrol_lock_ttl_s: int = 30 * 60
    admin_token: SecretStr | None = None
    # 用來加密使用者金鑰（供背景巡檢）；更換後先前保存的金鑰將無法解密
    secret_key: SecretStr | None = None  # 設定後手動觸發巡檢需帶 X-Admin-Token

    # --- 告警 ---
    alert_cooldown_hours: int = 24
    webhook_allowed_hosts: list[str] = [
        "discord.com",
        "discordapp.com",
        "hooks.slack.com",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
