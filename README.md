# SkyRoute · 智慧機票探索與低價看盤監控

把「金融看盤」機制套用到機票：即時多條件搜尋、彈性日期價格矩陣，以及背景 Worker 每日巡檢自選清單、寫入時間序列並在降價時推播。完整規格見 [project.md](project.md)。

- **後端**：FastAPI · SQLAlchemy 2（async/asyncpg）· PostgreSQL · Redis · httpx
- **前端**：React 19 · TanStack Query · Recharts · Vite+
- **外部報價**：[Duffel Flights API](https://duffel.com/docs)（呼叫方式整理於 [apidocs.html](apidocs.html)）

## 快速開始

### 方式 A：Docker Compose（最接近正式部署）

```bash
cp .env.example .env          # 設定 SECRET_KEY；DUFFEL_ACCESS_TOKEN 可留空讓使用者自備
docker compose up -d --build
open http://localhost:8080
```

會啟動 `postgres`、`redis`、`api`（2 個 uvicorn worker）、`worker`（每日巡檢）、`web`（Nginx：靜態資產 + `/api` 反向代理 + 限流 + 安全標頭）。

### 方式 B：本機開發

需求：Python 3.12+、[uv](https://docs.astral.sh/uv/)、PostgreSQL、[Vite+](https://viteplus.dev)（`vp`）。

```bash
cp .env.example .env                     # 填入 DUFFEL_ACCESS_TOKEN；REDIS_URL 留空會用記憶體快取
createdb skyroute && createdb skyroute_test

# 後端（http://localhost:8000，OpenAPI 文件在 /docs）
cd backend && uv sync
uv run uvicorn app.main:app_factory --factory --reload --port 8000

# 背景巡檢（另開終端；--once 立即跑一次就結束）
cd backend && uv run python -m app.worker --once

# 前端（http://localhost:5173，/api 會 proxy 到 8000）
vp install && vp dev
```

## 功能對照

| 規格                                                                                     | 實作位置                                                                                            |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 參數正規化、城市碼聚合（TYO → HND/NRT）                                                  | `schemas.py`、`services/airport_service.py`；不在對照表的機場會向 Duffel `/places/suggestions` 補齊 |
| 轉機拓撲過濾（直飛、轉機上限、樞紐白／黑名單、停留 90–300 分、航司）                     | `domain/topology.py`                                                                                |
| Cache-Aside，鍵 `route:{o}:{d}:{dep}:{ret}:{cabin}:{pax_hash}`，TTL 30 分                | `services/search_service.py`、`services/cache.py`                                                   |
| 綜合代價 = 票價 + (飛行h + 轉機h × 1.5) × 時間單價；最便宜／最快速／性價比標籤；6 種排序 | `domain/metrics.py`                                                                                 |
| 7 × 7 彈性日期矩陣（非同步平行、NDJSON 串流逐格回傳）                                    | `services/explore_service.py`、`components/matrix/`                                                 |
| 看盤：最新價、昨日價差、7 日漲跌幅、7 日低點／均價、走勢圖                               | `services/board_stats.py`、`components/watch/`                                                      |
| 巡檢：過期結清 → 依航線去重聚合 → 佇列 + 令牌桶 → 寫入 `price_history`                   | `services/patrol.py`、`services/rate_limit.py`                                                      |
| 告警：目標價或較 7 日均價下跌 N%；24 小時冷卻（除非再創新低）；Discord/Slack Webhook     | `services/alerts.py`                                                                                |
| 分散式排程鎖（多個 Worker 只會有一個在巡檢）                                             | Redis `SET NX EX` + Lua 釋放（`services/cache.py`）                                                 |
| 主動取消（軟刪除 → `CANCELLED`）                                                         | `DELETE /api/watchlists/{id}`                                                                       |

### 前端頁面

| 頁面     | URL                    | 說明                                                         |
| -------- | ---------------------- | ------------------------------------------------------------ |
| 主頁     | `/`（`?view=home`）    | 產品介紹、熱門航線一鍵查詢；左上角「SkyRoute」可隨時回到這裡 |
| 航班探索 | `?view=explore&from=…` | 多條件搜尋與轉機篩選                                         |
| 日期矩陣 | `?view=matrix&from=…`  | ±1～3 天價格熱力圖                                           |
| 看盤清單 | `?view=board`          | 自選追蹤、走勢圖、告警紀錄、手動巡檢                         |

視覺依 [DESIGN.md](DESIGN.md) 的設計系統實作（專有字型以文件指定的替代字型 Space Grotesk／Inter 呈現）。

### API 一覽

所有 JSON 回應皆為 `{ success, data, error, meta }`。看盤相關端點需帶 `X-User-Id`（前端自動產生的匿名識別碼；本系統不含帳號登入）。

| 方法       | 路徑                              | 說明                                                      |
| ---------- | --------------------------------- | --------------------------------------------------------- |
| GET        | `/api/airports?q=`                | 機場／城市建議                                            |
| POST       | `/api/search`                     | 多條件搜尋（含過濾、排序、代價指標）                      |
| POST       | `/api/fare-matrix`                | 彈性日期矩陣（`application/x-ndjson` 串流）               |
| GET / POST | `/api/watchlists`                 | 看盤清單（含統計）／新增追蹤                              |
| DELETE     | `/api/watchlists/{id}`            | 取消追蹤（軟刪除：狀態改為 CANCELLED，保留歷史）          |
| DELETE     | `/api/watchlists/{id}?purge=true` | 永久刪除，連同歷史價格與告警紀錄                          |
| DELETE     | `/api/watchlists?scope=ended`     | 批次永久刪除所有已取消／已過期的追蹤                      |
| GET        | `/api/watchlists/{id}/history`    | 歷史價格                                                  |
| GET        | `/api/watchlists/{id}/alerts`     | 告警紀錄                                                  |
| POST       | `/api/patrol/run`                 | 手動觸發巡檢（設定 `ADMIN_TOKEN` 後需帶 `X-Admin-Token`） |

## 多航段、分段購票、多幣別與雙語

- **多航段**：行程類型可選單程／來回／多航段（2–5 段，例如 台北→倫敦、巴黎→台北）。`POST /api/search` 以 `extra_legs` 帶入第 2 段以後。
- **兩種購票方式**：「整張票」由 Duffel 一次查詢所有航段（同一張機票）；「分段購票」把每段拆成單程各自查詢，可以混搭航司（例如去程華航、回程長榮），底部合計列即時顯示總價。分段購票是多張獨立機票，畫面上會提示延誤與改退票的風險。
- **滑桿篩選**：票價、每段飛行時長、轉機停留時間都用雙把手滑桿，放開才重新查詢；篩選在後端執行（`price_min/max`、`duration_min/max`），回應附上 `price_bounds`、`duration_bounds` 作為滑桿範圍。
- **多幣別**：支援 TWD、USD、EUR、GBP、JPY、KRW、HKD、SGD、CNY、THB、AUD、CAD。後端以 open.er-api.com 的匯率（快取 6 小時，失敗時退回內建參考匯率並標示「概略」）把報價換算成使用者選的幣別，原始報價保留在 `original_amount`。看盤追蹤會記住建立時的幣別，巡檢時換算後再比對門檻。時間價值固定以 US$ 輸入、後端換算。`GET /api/fx` 回傳目前匯率。
- **中英雙語**：導覽列切換（手機在選單內），選擇會記住；後端依 `Accept-Language` 回傳對應語言的錯誤訊息。
- **剔除測試資料**：Duffel 測試環境的虛構航司 Duffel Airways（`ZZ`）預設一律剔除，可用 `EXCLUDED_AIRLINES` 調整。

## 使用者自備 API 金鑰

網頁右上角的金鑰按鈕可輸入自己的 Duffel 金鑰（`duffel_test_…` 或 `duffel_live_…`），改用自己的帳號與配額查詢。

- **伺服器金鑰變成選填**：`.env` 的 `DUFFEL_ACCESS_TOKEN` 留空時，使用者必須自備金鑰（頁面會提示）。
- **傳遞方式**：前端以 `X-Duffel-Token` 標頭送出；後端先檢查格式，再代為呼叫 Duffel，不寫入日誌。`POST /api/credentials/verify` 可驗證金鑰是否有效。
- **瀏覽器端保存**：預設只存在 sessionStorage（關閉分頁即清除），勾選「記住」才寫入 localStorage。
- **隔離**：快取鍵與令牌桶都依金鑰指紋（SHA-256 前 16 碼）分開，不同帳號的報價不會互相共用。
- **背景巡檢**：建立追蹤時，金鑰以 `SECRET_KEY` 衍生的 Fernet 金鑰加密存入 `tracked_watchlists.duffel_token_enc`，巡檢時解密使用；同航線但金鑰不同的標的不會被合併查詢。取消追蹤或出發日過期即清除。更換 `SECRET_KEY` 後舊金鑰無法解密，對應的巡檢會記為失敗。
- `GET /api/config` 回報伺服器是否有預設金鑰、是否能加密保存使用者金鑰。

## 設計決策與已知限制

- **Duffel 配額**：測試帳號 `offer_requests` 約每分鐘 30 次。令牌桶預設 0.4 次/秒、burst 4（每分鐘 ≤ 28 次），遇到 429 會依 `ratelimit-reset` 等到配額重置再重試。因此冷快取下完整 7×7 矩陣約需 2 分鐘（逐格串流顯示），可在頁面切換 ±1／±2 天。令牌桶是**每個程序各自一份**，API 與 Worker 同時大量呼叫時仍可能撞到上限。
- **Worker 不用 Celery**：以 asyncio 佇列 + 多個 consumer 實作，搭配 Redis 鎖確保同一時間只有一個巡檢。規模變大時可把佇列換成 Redis/RabbitMQ 並拆分 consumer 程序。
- **Schema 管理**：啟動時 `create_all`（以 PostgreSQL advisory lock 序列化）。正式環境建議改用 Alembic。
- **幣別**：直接儲存 Duffel 回傳的幣別（測試環境多為 USD），未做匯率換算。
- **兒童乘客**：Duffel 依年齡計價，目前兒童一律以 10 歲送出。
- 測試環境報價為 Duffel 產生的模擬資料（包含測試航空公司 Duffel Airways `ZZ`）。

## 測試與品質檢查

```bash
# 後端：ruff + mypy（strict）+ pytest（含真實 PostgreSQL 整合測試，Duffel 以 respx mock）
cd backend
uv run ruff check app tests && uv run ruff format --check app tests
uv run mypy app
uv run pytest --cov            # 112 個測試，覆蓋率約 93%

# 前端：格式、lint、型別、單元測試、建置
vp check && vp test && vp run build
```

整合測試預設連 `postgresql+asyncpg://localhost:5432/skyroute_test`，可用 `TEST_DATABASE_URL` 覆寫。

CI（`.github/workflows/ci.yml`）：PR 會跑上述所有檢查（後端覆蓋率低於 80% 即失敗）；合併到 `main` 後建置並推送 API 與 Web 的 OCI 映像到 GHCR。

## AI 輔助開發實務

本專案以 Claude Code 協助開發，實際用法：

1. **先讀 API 再寫防腐層**：讓 AI 先用測試 token 實際呼叫 Duffel，觀察真實回應結構（巢狀 slice → segment、`ratelimit-*` 標頭、城市碼展開行為），再據此產生 `duffel_mapper.py` 與 Pydantic 領域模型，而不是只憑文件猜欄位。
2. **Mock 測試資料**：`tests/factories.py` 依真實回應的最小子集生成原始 offer，供 mapper、過濾引擎與巡檢管線測試共用。
3. **用真實流量找問題**：端到端跑日期矩陣時發現 429，回頭量測配額後調整令牌桶並改依 `ratelimit-reset` 重試，再補上對應測試。
4. **SQL 與索引**：看盤統計一次撈出使用者全部標的的近期價格（避免 N+1），對應建立 `(watchlist_id, recorded_at)` 複合索引；巡檢查詢使用 `(is_active, departure_date)` 索引。

AI 產出的程式碼一律經過 ruff / mypy strict / pytest 與實際瀏覽器截圖驗證後才納入。
