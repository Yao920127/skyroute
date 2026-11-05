"""剔除明顯虛構的模擬航班（只作用於 Duffel 測試模式的報價）。

Duffel 測試環境會讓任意航司飛任意航線，例如「美國航空 AA118 台北→成田」。真實世界裡，
航司幾乎只飛「起點或終點在自己國家（或區域）」的航段。因此一個航段若行銷航司與實際營運航司的
母國都不在起訖兩地，就視為明顯虛構。

- 只處理 is_simulated 的報價；正式（live）報價一律保留。
- 代碼共享看實際營運航司（AA 掛號、JL 營運的台北→成田是真的）。
- 不認得的航司或機場一律保留，寧可少刪不可錯刪。
- 歐洲（EU／EEA／英國／瑞士）與美國本土＋屬地各視為單一區域（區域內第五航權航線很常見）。
"""

import json
from functools import cache
from pathlib import Path

from app.domain.offers import FlightOffer, Segment

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

EUROPE = frozenset(
    [
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
        "IS",
        "LI",
        "NO",
        "CH",
        "GB",
    ]
)
US_AND_TERRITORIES = frozenset(["US", "GU", "MP", "PR", "VI", "AS"])

# 常見航司的母國（ISO 3166-1）；跨國集團列出所有母國
AIRLINE_COUNTRIES: dict[str, frozenset[str]] = {
    code: frozenset(countries.split())
    for code, countries in {
        # 臺灣
        "BR": "TW",
        "CI": "TW",
        "JX": "TW",
        "AE": "TW",
        "B7": "TW",
        "IT": "TW",
        # 日本
        "JL": "JP",
        "NH": "JP",
        "MM": "JP",
        "GK": "JP",
        "BC": "JP",
        "7G": "JP",
        "NU": "JP",
        "HD": "JP",
        "IJ": "JP",
        "ZG": "JP",
        "6J": "JP",
        # 韓國
        "KE": "KR",
        "OZ": "KR",
        "7C": "KR",
        "TW": "KR",
        "LJ": "KR",
        "BX": "KR",
        "ZE": "KR",
        "RS": "KR",
        "YP": "KR",
        # 港澳、中國
        "CX": "HK",
        "UO": "HK",
        "HX": "HK",
        "HB": "HK",
        "NX": "MO",
        "CA": "CN",
        "MU": "CN",
        "CZ": "CN",
        "HU": "CN",
        "MF": "CN",
        "3U": "CN",
        "ZH": "CN",
        "SC": "CN",
        "FM": "CN",
        "HO": "CN",
        "9C": "CN",
        "KN": "CN",
        "GS": "CN",
        "JD": "CN",
        "TV": "CN",
        "8L": "CN",
        "PN": "CN",
        # 東南亞
        "SQ": "SG",
        "TR": "SG",
        "3K": "SG",
        "MH": "MY",
        "AK": "MY",
        "D7": "MY",
        "OD": "MY",
        "FY": "MY",
        "TG": "TH",
        "FD": "TH",
        "SL": "TH",
        "WE": "TH",
        "DD": "TH",
        "PG": "TH",
        "VZ": "TH",
        "XJ": "TH",
        "VN": "VN",
        "VJ": "VN",
        "QH": "VN",
        "PR": "PH",
        "5J": "PH",
        "Z2": "PH",
        "GA": "ID",
        "QZ": "ID",
        "JT": "ID",
        "ID": "ID",
        "IU": "ID",
        "BI": "BN",
        "8M": "MM",
        "QV": "LA",
        "K6": "KH",
        # 南亞、中東、非洲
        "AI": "IN",
        "6E": "IN",
        "UK": "IN",
        "SG": "IN",
        "IX": "IN",
        "UL": "LK",
        "BG": "BD",
        "PK": "PK",
        "EK": "AE",
        "EY": "AE",
        "FZ": "AE",
        "G9": "AE",
        "QR": "QA",
        "SV": "SA",
        "XY": "SA",
        "GF": "BH",
        "WY": "OM",
        "KU": "KW",
        "RJ": "JO",
        "LY": "IL",
        "MS": "EG",
        "ET": "ET",
        "KQ": "KE",
        "SA": "ZA",
        "AT": "MA",
        "TK": "TR",
        "PC": "TR",
        # 歐洲
        "BA": "GB",
        "VS": "GB",
        "U2": "GB",
        "LS": "GB",
        "AF": "FR",
        "TO": "FR",
        "KL": "NL",
        "HV": "NL",
        "LH": "DE",
        "EW": "DE",
        "DE": "DE",
        "HR": "DE",
        "LX": "CH",
        "OS": "AT",
        "SN": "BE",
        "SK": "DK NO SE",
        "AY": "FI",
        "IB": "ES",
        "VY": "ES",
        "UX": "ES",
        "AZ": "IT",
        "TP": "PT",
        "EI": "IE",
        "FR": "IE",
        "LO": "PL",
        "OK": "CZ",
        "RO": "RO",
        "A3": "GR",
        "W6": "HU",
        "DY": "NO",
        "FI": "IS",
        "SU": "RU",
        "PS": "UA",
        # 美洲
        "AA": "US",
        "UA": "US",
        "DL": "US",
        "AS": "US",
        "B6": "US",
        "WN": "US",
        "HA": "US",
        "NK": "US",
        "F9": "US",
        "AC": "CA",
        "WS": "CA",
        "TS": "CA",
        "AM": "MX",
        "Y4": "MX",
        "LA": "CL PE BR CO EC",
        "AV": "CO",
        "CM": "PA",
        "G3": "BR",
        "AD": "BR",
        "AR": "AR",
        # 大洋洲
        "QF": "AU",
        "VA": "AU",
        "JQ": "AU NZ",
        "NZ": "NZ",
        "FJ": "FJ",
    }.items()  # fmt: skip
}


def region_of(country: str) -> str:
    if country in EUROPE:
        return "EUROPE"
    if country in US_AND_TERRITORIES:
        return "US"
    return country


@cache
def airport_countries() -> dict[str, str]:
    """機場代碼 → 國家，取自內建的全球機場資料（不需查資料庫）。"""
    mapping: dict[str, str] = {}
    for row in json.loads((DATA_DIR / "airports.json").read_text(encoding="utf-8")):
        mapping[row["iata_code"]] = row["country"]
    return mapping


def is_plausible_segment(segment: Segment, countries: dict[str, str]) -> bool:
    endpoints = {
        region_of(c)
        for c in (countries.get(segment.origin), countries.get(segment.destination))
        if c
    }
    if len(endpoints) == 0:
        return True
    carriers = {segment.carrier_code, segment.operating_code} - {None}
    for code in carriers:
        homes = AIRLINE_COUNTRIES.get(str(code))
        if homes is None:
            return True  # 不認得的航司：保留
        if {region_of(h) for h in homes} & endpoints:
            return True
    return False


def is_obviously_fake(offer: FlightOffer, countries: dict[str, str] | None = None) -> bool:
    if not offer.is_simulated:
        return False
    lookup = countries if countries is not None else airport_countries()
    return any(
        not is_plausible_segment(segment, lookup)
        for slice_ in offer.slices
        for segment in slice_.segments
    )


def drop_obviously_fake(offers: tuple[FlightOffer, ...]) -> tuple[FlightOffer, ...]:
    countries = airport_countries()
    return tuple(o for o in offers if not is_obviously_fake(o, countries))
