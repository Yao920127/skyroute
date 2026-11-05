"""用 OurAirports 的 airports.csv（公眾領域）更新 app/data/airports.json。

只收有 IATA 代碼且有定期航班的機場。合併規則：
- size_rank＝0（人工維護的常用城市與機場）整筆保留，不會被覆寫
- 其他機場以 CSV 更新英文名稱、城市、國家與規模，但保留檔案裡已填的 name_zh、timezone、city_code
- 檔案裡有、CSV 已沒有的機場（例如 Duffel 補進來或手動新增的）一律保留

用法：
    curl -L -o /tmp/airports.csv https://davidmegginson.github.io/ourairports-data/airports.csv
    uv run python scripts/build_airports.py /tmp/airports.csv
"""

import csv
import json
import sys
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "app" / "data" / "airports.json"
SIZE_RANK = {"large_airport": 1, "medium_airport": 2, "small_airport": 3}
CURATED_RANK = 0
KEYS = (
    "iata_code",
    "city_code",
    "kind",
    "name_zh",
    "name_en",
    "city_name",
    "country",
    "timezone",
    "size_rank",
)


def read_csv(csv_path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with csv_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            code = r["iata_code"].strip().upper()
            if len(code) != 3 or r["scheduled_service"] != "yes" or r["type"] not in SIZE_RANK:
                continue
            candidate = {
                "iata_code": code,
                "name_en": r["name"].strip()[:100],
                "city_name": (r["municipality"] or "").strip()[:100] or None,
                "country": r["iso_country"].strip()[:2] or "ZZ",
                "size_rank": SIZE_RANK[r["type"]],
            }
            # 同一 IATA 代碼出現多次時，保留規模較大的那一筆
            if code not in rows or candidate["size_rank"] < rows[code]["size_rank"]:
                rows[code] = candidate
    return rows


def merge(existing: list[dict[str, Any]], fresh: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {r["iata_code"]: r for r in existing}
    for code, row in fresh.items():
        current = merged.get(code)
        if current is None:
            merged[code] = {
                "city_code": code,
                "kind": "airport",
                "name_zh": None,
                "timezone": None,
                **row,
            }
        elif current["size_rank"] != CURATED_RANK:
            merged[code] = {**current, **row}
    return sorted(merged.values(), key=lambda r: str(r["iata_code"]))


def write(rows: list[dict[str, Any]]) -> None:
    """每行一個機場，方便搜尋與檢視差異。"""
    lines = [
        json.dumps({k: r.get(k) for k in KEYS}, ensure_ascii=False, separators=(",", ":"))
        for r in rows
    ]
    DATA_FILE.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rows = merge(existing, read_csv(Path(sys.argv[1])))
    write(rows)
    print(f"寫入 {len(rows)} 筆（原有 {len(existing)} 筆）→ {DATA_FILE}")


if __name__ == "__main__":
    main()
