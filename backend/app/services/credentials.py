"""使用者自備的 Duffel 金鑰：格式驗證、不可逆指紋、靜態加密（供背景巡檢使用）。"""

import base64
import hashlib
import re
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

_TOKEN_RE = re.compile(r"^duffel_(test|live)_[A-Za-z0-9_\-]{10,200}$")
FINGERPRINT_LENGTH = 16

TokenMode = Literal["test", "live"]


class InvalidTokenFormat(ValueError):
    pass


class CipherUnavailable(RuntimeError):
    """伺服器未設定 SECRET_KEY，無法加密保存金鑰。"""


def validate_token(token: str) -> TokenMode:
    """只接受 Duffel 金鑰格式，避免把任意字串轉送到外部服務。"""
    match = _TOKEN_RE.match(token.strip())
    if not match:
        raise InvalidTokenFormat("Duffel 金鑰格式應為 duffel_test_… 或 duffel_live_…")
    mode: TokenMode = "test" if match.group(1) == "test" else "live"
    return mode


def token_fingerprint(token: str) -> str:
    """金鑰的不可逆指紋，用於快取命名空間與巡檢分組，不會洩漏金鑰本身。"""
    return hashlib.sha256(token.encode()).hexdigest()[:FINGERPRINT_LENGTH]


class TokenCipher:
    """以伺服器 SECRET_KEY 衍生的 Fernet 金鑰加解密（AES-128-CBC + HMAC-SHA256）。"""

    def __init__(self, secret: str | None) -> None:
        if secret:
            derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
            self._fernet: Fernet | None = Fernet(derived)
        else:
            self._fernet = None

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, token: str) -> str:
        if self._fernet is None:
            raise CipherUnavailable("伺服器未設定 SECRET_KEY，無法保存你的金鑰供背景巡檢使用")
        return self._fernet.encrypt(token.encode()).decode()

    def decrypt(self, ciphertext: str) -> str | None:
        """解密失敗（SECRET_KEY 已更換或資料損毀）時回傳 None。"""
        if self._fernet is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None
