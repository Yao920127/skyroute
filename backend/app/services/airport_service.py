"""機場對照：全球機場資料、城市代碼聚合（TYO → HND/NRT）、搜尋建議、缺漏時向 Duffel 補齊。

資料來源（後者覆寫前者）：
1. airports_world.json：OurAirports 全球有定期航班的機場（scripts/build_airports.py 產生）
2. airports_zh.json：常用機場的繁體中文名稱
3. airports.json：內建常用城市與機場（含城市代碼、時區），優先權最高
"""

import json
import logging
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.duffel_client import DuffelClient, DuffelError
from app.models import Airport

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORLD_FILE = DATA_DIR / "airports_world.json"
ZH_FILE = DATA_DIR / "airports_zh.json"
CURATED_FILE = DATA_DIR / "airports.json"
SEED_FILE = CURATED_FILE  # 相容舊名稱
SEED_BATCH = 1000  # asyncpg 單一語句的參數上限約 32k，分批寫入
SEARCH_LIMIT = 12
COLUMNS = (
    "city_code",
    "name_zh",
    "name_en",
    "country",
    "timezone",
    "kind",
    "city_name",
    "size_rank",
    "search_text",
)


def fold(text: str) -> str:
    """去除重音、轉小寫，讓 reykjavik 與 Reykjavík、sao paulo 與 São Paulo 都能比對。"""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def search_text_of(row: dict[str, Any]) -> str:
    parts: Iterable[Any] = (
        row.get("iata_code"),
        row.get("city_code"),
        row.get("name_en"),
        row.get("name_zh"),
        row.get("city_name"),
    )
    return fold(" ".join(str(p) for p in parts if p))


def load_seed_rows(include_world: bool = True) -> list[dict[str, Any]]:
    """合併三份資料；內建清單優先，中文名稱補在全球資料上。"""
    rows: dict[str, dict[str, Any]] = {}
    world = json.loads(WORLD_FILE.read_text(encoding="utf-8")) if include_world else []
    for r in world:
        rows[r["iata_code"]] = {"name_zh": None, "timezone": None, **r}
    for code, name_zh in json.loads(ZH_FILE.read_text(encoding="utf-8")).items():
        if code in rows:
            rows[code]["name_zh"] = name_zh
    for r in json.loads(CURATED_FILE.read_text(encoding="utf-8")):
        base = rows.get(r["iata_code"], {"city_name": None})
        rows[r["iata_code"]] = {**base, **r, "size_rank": 0}
    for row in rows.values():
        row["search_text"] = search_text_of(row)
    return list(rows.values())


async def _upsert(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), SEED_BATCH):
        stmt = insert(Airport).values(rows[start : start + SEED_BATCH])
        stmt = stmt.on_conflict_do_update(
            index_elements=[Airport.iata_code],
            set_={c: stmt.excluded[c] for c in COLUMNS},
        )
        await session.execute(stmt)


async def seed_airports(session: AsyncSession, include_world: bool = True) -> int:
    """include_world=False 只寫入內建常用清單（測試用，避免每個測試都寫入 4,000 筆）。"""
    rows = load_seed_rows(include_world)
    await _upsert(session, rows)
    await session.commit()
    return len(rows)


async def search_airports(
    session: AsyncSession, query: str, limit: int = SEARCH_LIMIT
) -> list[Airport]:
    q = query.strip()
    if not q:
        return []
    code = q.upper()
    needle = f"%{fold(q)}%"
    stmt = (
        select(Airport)
        .where(
            or_(
                Airport.iata_code.ilike(f"{q}%"),
                Airport.city_code.ilike(f"{q}%"),
                Airport.search_text.ilike(needle),
                Airport.name_zh.ilike(f"%{q}%"),
            )
        )
        .order_by(
            # 代碼完全相符 → 城市代碼相符 → 城市優先 → 大型機場優先
            case((Airport.iata_code == code, 0), (Airport.city_code == code, 1), else_=2),
            case((Airport.kind == "city", 0), else_=1),
            Airport.size_rank,
            Airport.iata_code,
        )
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def expand_code(session: AsyncSession, code: str) -> list[str]:
    """城市代碼展開為所屬機場；單一機場則回傳自己。"""
    stmt = select(Airport.iata_code).where(Airport.city_code == code, Airport.kind == "airport")
    members = sorted((await session.scalars(stmt)).all())
    airport = await session.get(Airport, code)
    if airport is not None and airport.kind == "city":
        return members or [code]
    return [code]


def _place_to_row(place: dict[str, Any]) -> dict[str, Any]:
    city = place.get("city") or {}
    row = {
        "iata_code": place["iata_code"],
        "city_code": place.get("iata_city_code") or place["iata_code"],
        "name_zh": None,
        "name_en": (place.get("name") or place["iata_code"])[:100],
        "country": place.get("iata_country_code") or "ZZ",
        "timezone": place.get("time_zone"),
        "kind": "city" if place.get("type") == "city" else "airport",
        "city_name": (place.get("city_name") or city.get("name") or None),
        "size_rank": 2,
    }
    row["search_text"] = search_text_of(row)
    return row


async def _store_places(session: AsyncSession, places: list[dict[str, Any]]) -> None:
    rows = [
        _place_to_row(p)
        for p in places
        if isinstance(p.get("iata_code"), str) and len(p["iata_code"]) == 3
    ]
    if rows:
        # 只補缺漏，不覆寫既有（可能含中文名稱）的資料
        await session.execute(insert(Airport).values(rows).on_conflict_do_nothing())
        await session.commit()


async def search_with_fallback(
    session: AsyncSession, client: DuffelClient | None, query: str
) -> list[Airport]:
    """本機清單找不到時，改問 Duffel 的地點搜尋，並把結果存入對照表供之後使用。"""
    found = await search_airports(session, query)
    if found or client is None or len(query.strip()) < 2:
        return found
    try:
        places = await client.place_suggestions(query.strip())
    except DuffelError as exc:
        log.warning("Duffel 地點搜尋失敗 %s：%s", query, exc)
        return []
    await _store_places(session, places)
    return await search_airports(session, query)


async def ensure_airport(session: AsyncSession, client: DuffelClient, code: str) -> bool:
    """確保機場存在於對照表（追蹤清單有外鍵約束）。找不到時回傳 False。"""
    if await session.get(Airport, code) is not None:
        return True
    try:
        places = await client.place_suggestions(code)
    except DuffelError as exc:
        log.warning("查詢機場 %s 失敗：%s", code, exc)
        return False
    match = next((p for p in places if p.get("iata_code") == code), None)
    if match is None:
        return False
    await session.execute(insert(Airport).values(_place_to_row(match)).on_conflict_do_nothing())
    await session.flush()
    return True
