"""Google 帳號登入：驗證 Google ID Token、簽發工作階段 Cookie、管理帳號專屬的 Duffel 金鑰。

流程：前端以 Google Identity Services 取得 ID Token（JWT）→ 後端用 Google 公開金鑰驗章，
確認 aud／iss／exp／email_verified → 建立或更新使用者 → 回應一個 HttpOnly 的簽章 Cookie。
Cookie 只帶使用者 ID 與到期時間，以 SECRET_KEY 做 HMAC-SHA256，伺服器不需保存工作階段。
"""

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TrackedWatchlist, User, WatchStatus
from app.services.credentials import TokenCipher, token_fingerprint
from app.services.schedule import MIN_SHARED_INTERVAL

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
JWKS_TTL_S = 60 * 60
SESSION_COOKIE = "skyroute_session"
USER_PREFIX = "g:"


class AuthError(Exception):
    """Google 憑證無效、過期或與本站不符。"""


class LoginRequired(Exception):
    """需要登入才能使用的功能。"""


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    name: str | None
    picture: str | None


class GoogleVerifier:
    """驗證 Google ID Token；Google 的公開金鑰會快取一小時。"""

    def __init__(self, http: httpx.AsyncClient, client_id: str) -> None:
        self._http = http
        self._client_id = client_id
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    async def _signing_key(self, kid: str) -> Any:
        is_stale = time.monotonic() - self._fetched_at > JWKS_TTL_S
        if is_stale or kid not in self._keys:
            response = await self._http.get(GOOGLE_CERTS_URL, timeout=10)
            response.raise_for_status()
            jwks = response.json().get("keys", [])
            self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks if "kid" in k}
            self._fetched_at = time.monotonic()
        if kid not in self._keys:
            raise AuthError("無法驗證 Google 登入憑證")
        return self._keys[kid]

    async def verify(self, credential: str) -> GoogleProfile:
        try:
            kid = jwt.get_unverified_header(credential).get("kid")
            if not kid:
                raise AuthError("無法驗證 Google 登入憑證")
            key = await self._signing_key(kid)
            claims = jwt.decode(
                credential,
                key=key,
                algorithms=["RS256"],
                audience=self._client_id,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError) as exc:
            raise AuthError("Google 登入憑證無效或已過期") from exc
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise AuthError("Google 登入憑證無效或已過期")
        if not claims.get("email") or claims.get("email_verified") is not True:
            raise AuthError("Google 帳號的電子郵件尚未驗證")
        return GoogleProfile(
            sub=str(claims["sub"]),
            email=str(claims["email"]),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )


class SessionSigner:
    """無狀態工作階段：`<user_id>.<到期 epoch>.<簽章>`。"""

    def __init__(self, secret: str, ttl_s: int) -> None:
        self._key = hashlib.sha256(b"skyroute-session:" + secret.encode()).digest()
        self.ttl_s = ttl_s

    def _sign(self, payload: str) -> str:
        digest = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def issue(self, user_id: uuid.UUID, now: float | None = None) -> str:
        expires = int((now or time.time()) + self.ttl_s)
        payload = f"{user_id}.{expires}"
        return f"{payload}.{self._sign(payload)}"

    def verify(self, value: str, now: float | None = None) -> uuid.UUID | None:
        parts = value.split(".")
        if len(parts) != 3:
            return None
        raw_id, raw_expires, signature = parts
        payload = f"{raw_id}.{raw_expires}"
        if not hmac.compare_digest(signature, self._sign(payload)):
            return None
        try:
            user_id = uuid.UUID(raw_id)
            expires = int(raw_expires)
        except ValueError:
            return None
        return user_id if expires > (now or time.time()) else None


@dataclass(frozen=True)
class AuthService:
    """登入功能需要 GOOGLE_CLIENT_ID 與 SECRET_KEY；缺一則維持匿名模式。"""

    verifier: GoogleVerifier | None
    signer: SessionSigner | None
    client_id: str | None
    cookie_secure: bool

    @property
    def enabled(self) -> bool:
        return self.verifier is not None and self.signer is not None


def user_identifier(user: User) -> str:
    """看盤清單以 `g:<使用者 ID>` 歸屬，與舊的匿名識別碼不會衝突。"""
    return f"{USER_PREFIX}{user.id}"


async def upsert_user(session: AsyncSession, profile: GoogleProfile) -> User:
    user = await session.scalar(select(User).where(User.google_sub == profile.sub))
    now = datetime.now(UTC)
    if user is None:
        user = User(google_sub=profile.sub, email=profile.email, last_login_at=now)
        session.add(user)
    user.email = profile.email
    user.name = profile.name
    user.picture = profile.picture
    user.last_login_at = now
    await session.commit()
    await session.refresh(user)
    return user


async def claim_anonymous_watchlists(session: AsyncSession, user: User, anonymous_id: str) -> int:
    """登入前在這台瀏覽器建立的追蹤，登入後併入帳號（只轉移匿名識別碼的資料）。"""
    if anonymous_id.startswith(USER_PREFIX):
        return 0
    result = await session.execute(
        update(TrackedWatchlist)
        .where(TrackedWatchlist.user_identifier == anonymous_id)
        .values(user_identifier=user_identifier(user))
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def set_account_key(
    session: AsyncSession, cipher: TokenCipher, user: User, token: str | None
) -> None:
    """設定或清除帳號的 Duffel 金鑰，並同步到仍在追蹤中的標的（背景巡檢用）。"""
    encrypted = cipher.encrypt(token) if token else None
    fingerprint = token_fingerprint(token) if token else None
    user.duffel_token_enc = encrypted
    user.token_fingerprint = fingerprint
    owned = (
        TrackedWatchlist.user_identifier == user_identifier(user),
        TrackedWatchlist.status == WatchStatus.TRACKING,
    )
    await session.execute(
        update(TrackedWatchlist)
        .where(*owned)
        .values(duffel_token_enc=encrypted, token_fingerprint=fingerprint)
    )
    if token is None:
        # 改用網站共用金鑰後，30 分鐘以內的頻率放寬為 30 分鐘
        await session.execute(
            update(TrackedWatchlist)
            .where(*owned, TrackedWatchlist.patrol_interval_minutes < MIN_SHARED_INTERVAL)
            .values(patrol_interval_minutes=MIN_SHARED_INTERVAL)
        )
    await session.commit()


def account_key(cipher: TokenCipher, user: User | None) -> str | None:
    if user is None or not user.duffel_token_enc:
        return None
    return cipher.decrypt(user.duffel_token_enc)
