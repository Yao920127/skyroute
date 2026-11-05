"""設定：託管平台提供的資料庫網址要自動改用 asyncpg 驅動。"""

import pytest

from app.config import Settings


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
    ],
)
def test_database_url_uses_asyncpg_driver(raw: str, expected: str) -> None:
    assert Settings(database_url=raw).database_url == expected
