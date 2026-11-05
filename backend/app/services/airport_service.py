"""機場對照：城市代碼聚合（TYO → HND/NRT）、搜尋建議、缺漏時向 Duffel 補齊。"""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.duffel_client import DuffelClient, DuffelError
from app.models import Airport

log = logging.getLogger(__name__)

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "airports.json"


async def seed_airports(session: AsyncSession) -> int:
    rows: list[dict[str, Any]] = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    stmt = insert(Airport).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Airport.iata_code],
        set_={
            c: stmt.excluded[c]
            for c in ("city_code", "name_zh", "name_en", "country", "timezone", "kind")
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(rows)


async def search_airports(session: AsyncSession, query: str, limit: int = 12) -> list[Airport]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(Airport)
        .where(
            or_(
                Airport.iata_code.ilike(f"{q}%"),
                Airport.city_code.ilike(f"{q}%"),
                Airport.name_en.ilike(pattern),
                Airport.name_zh.ilike(pattern),
            )
        )
        .order_by((Airport.iata_code == q.upper()).desc(), Airport.kind, Airport.iata_code)
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
    return {
        "iata_code": place["iata_code"],
        "city_code": place.get("iata_city_code") or place["iata_code"],
        "name_zh": None,
        "name_en": (place.get("name") or place["iata_code"])[:100],
        "country": place.get("iata_country_code") or "ZZ",
        "timezone": place.get("time_zone"),
        "kind": "city" if place.get("type") == "city" else "airport",
    }


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
