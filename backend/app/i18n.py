"""回應給使用者的錯誤訊息雙語化：程式內以繁中撰寫，依 Accept-Language 轉為英文。"""

from typing import Literal

Lang = Literal["zh", "en"]

_EXACT: dict[str, str] = {
    "出發地與目的地不可相同": "Origin and destination must be different",
    "出發日期不可早於今天": "Departure date cannot be in the past",
    "回程日期不可早於出發日期": "Return date cannot be earlier than the departure date",
    "乘客總數不可超過 9 人": "No more than 9 passengers in total",
    "多航段行程請用 extra_legs 描述回程，不可同時設定回程日期": (
        "Multi-city trips describe later legs in extra_legs; do not also set a return date"
    ),
    "多航段的日期必須依序排列": "Multi-city leg dates must be in chronological order",
    "最短轉機時間不可大於最長轉機時間": "Minimum layover cannot exceed the maximum layover",
    "最低票價不可大於最高票價": "Minimum price cannot exceed the maximum price",
    "最短飛行時長不可大於最長飛行時長": "Minimum duration cannot exceed the maximum duration",
    "日期矩陣只支援單程或來回行程": "The fare matrix supports one-way and round trips only",
    "看盤追蹤只支援單程或來回行程": "Price watches support one-way and round trips only",
    "請至少設定目標價或相對降幅其中一項": "Set a target price or a percentage drop",
    "請先設定 Duffel API 金鑰": "Please set a Duffel API key first",
    "找不到此追蹤項目": "Watch not found",
    "Duffel 金鑰格式應為 duffel_test_… 或 duffel_live_…": (
        "Duffel keys look like duffel_test_… or duffel_live_…"
    ),
    "伺服器未設定 SECRET_KEY，無法保存你的金鑰供背景巡檢使用": (
        "The server has no SECRET_KEY, so your key cannot be stored for background checks"
    ),
    "Webhook 網址必須是 https://": "Webhook URL must start with https://",
    "Duffel 拒絕了這把金鑰": "Duffel rejected this key",
    "Duffel 拒絕了目前的 API 金鑰，請檢查設定": (
        "Duffel rejected the current API key; please check it"
    ),
    "缺少或無效的 X-User-Id 標頭": "Missing or invalid X-User-Id header",
    "請先以 Google 帳號登入": "Please sign in with Google first",
    "此伺服器未啟用 Google 登入": "Google sign-in is not enabled on this server",
    "無法驗證 Google 登入憑證": "Could not verify the Google sign-in credential",
    "Google 登入憑證無效或已過期": "The Google sign-in credential is invalid or expired",
    "Google 帳號的電子郵件尚未驗證": "This Google account's email address is not verified",
    "請在 X-Duffel-Token 標頭提供金鑰": "Provide a key in the X-Duffel-Token header",
    "需要有效的 X-Admin-Token": "A valid X-Admin-Token is required",
    "無法連線到外部航班服務": "Cannot reach the flight data provider",
    "外部航班服務重試次數用盡": "The flight data provider did not respond after several retries",
    "外部航班服務暫時無法使用": "The flight data provider is temporarily unavailable",
    "外部航班服務錯誤": "Flight data provider error",
    "輸入資料格式錯誤": "Invalid input",
}

# 帶動態內容的訊息：以前綴對應
_PREFIX: tuple[tuple[str, str], ...] = (
    ("找不到機場或城市代碼：", "Unknown airport or city code: "),
    ("Webhook 主機不在允許清單內：", "Webhook host is not allowed. Allowed: "),
    ("不支援的幣別：", "Unsupported currency: "),
)


def language_of(accept_language: str | None) -> Lang:
    """取第一個語系標籤；英文開頭就回英文，其餘一律繁中。"""
    if not accept_language:
        return "zh"
    first = accept_language.split(",")[0].strip().lower()
    return "en" if first.startswith("en") else "zh"


def translate(message: str, lang: Lang) -> str:
    if lang == "zh":
        return message
    if message in _EXACT:
        return _EXACT[message]
    for zh, en in _PREFIX:
        if message.startswith(zh):
            return en + message[len(zh) :]
    return message
