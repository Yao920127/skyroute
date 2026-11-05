"""把 OurAirports 的 airports.csv（公眾領域）轉成精簡的全球機場對照表 app/data/airports_world.json。

只保留有 IATA 代碼且有定期航班的機場（約 4,000 個）。另外定義幾個多機場城市代碼（如 BJS、ROM）。

用法：
    curl -L -o /tmp/airports.csv https://davidmegginson.github.io/ourairports-data/airports.csv
    uv run python scripts/build_airports.py /tmp/airports.csv
"""

import csv
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "airports_world.json"
SIZE_RANK = {"large_airport": 1, "medium_airport": 2, "small_airport": 3}

# 多機場城市（內建清單已有的 TYO、OSA、SEL、LON、PAR、MIL、NYC、TPE 不重複定義）
METROS: dict[str, tuple[str, str, list[str]]] = {
    "BJS": ("Beijing (all airports)", "CN", ["PEK", "PKX"]),
    "ROM": ("Rome (all airports)", "IT", ["FCO", "CIA"]),
    "WAS": ("Washington (all airports)", "US", ["IAD", "DCA", "BWI"]),
    "CHI": ("Chicago (all airports)", "US", ["ORD", "MDW"]),
    "YTO": ("Toronto (all airports)", "CA", ["YYZ", "YTZ"]),
    "MOW": ("Moscow (all airports)", "RU", ["SVO", "DME", "VKO"]),
    "SAO": ("São Paulo (all airports)", "BR", ["GRU", "CGH", "VCP"]),
    "STO": ("Stockholm (all airports)", "SE", ["ARN", "BMA"]),
}


def build(csv_path: Path) -> list[dict[str, object]]:
    city_of = {code: metro for metro, (_, _, codes) in METROS.items() for code in codes}
    rows: dict[str, dict[str, object]] = {}
    with csv_path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            code = r["iata_code"].strip().upper()
            if len(code) != 3 or r["scheduled_service"] != "yes" or r["type"] not in SIZE_RANK:
                continue
            candidate = {
                "iata_code": code,
                "city_code": city_of.get(code, code),
                "name_en": r["name"].strip()[:100],
                "city_name": (r["municipality"] or "").strip()[:100] or None,
                "country": r["iso_country"].strip()[:2] or "ZZ",
                "kind": "airport",
                "size_rank": SIZE_RANK[r["type"]],
            }
            # 同一 IATA 代碼出現多次時，保留規模較大的那一筆
            if code not in rows or candidate["size_rank"] < rows[code]["size_rank"]:  # type: ignore[operator]
                rows[code] = candidate
    for metro, (name, country, _) in METROS.items():
        rows[metro] = {
            "iata_code": metro,
            "city_code": metro,
            "name_en": name,
            "city_name": name.split(" (")[0],
            "country": country,
            "kind": "city",
            "size_rank": 0,
        }
    return sorted(rows.values(), key=lambda r: str(r["iata_code"]))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    rows = build(Path(sys.argv[1]))
    OUT.write_text(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"寫入 {len(rows)} 筆 → {OUT}")


if __name__ == "__main__":
    main()
