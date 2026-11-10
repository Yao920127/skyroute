 # SkyRoute 智慧機票探索與低價看盤監控系統

## 軟體架構設計與系統規格書

## 一、系統定位與核心用途

SkyRoute 是一套將「金融看盤機制」引進「國際航班搜尋與票價追蹤」的高可用後端系統。

傳統機票查詢服務普遍受限於外部機票 API 的連線延遲（單次調用約 2 至 5 秒）、呼叫頻率限制（Rate Limits），以及缺乏對中轉歷程的細緻篩選。使用者面對熱門航線時，往往必須重複手動查詢，難以掌握價格波動週期。

SkyRoute 的核心目的是解耦「線上即時查詢」與「離線背景排程」：

1. **即時探索**：提供多維度轉機過濾（樞紐白名單、停留時長）、乘客結構計費與二維價格矩陣。
2. **看盤自選清單（Watchlist）**：使用者可將特定出發區間與航司組合加入監控清單。
3. **主動巡檢與生命週期管理**：背景 Worker 自動聚合監控標的、實施呼叫節流、寫入時間序列歷史價格，並於符合自訂閾值時推播通知；航班啟航後自動退出輪詢。

## 二、軟體模組劃分與詳細功能規格

| 航班探索與過濾 | 票價看盤與分析 | 非同步巡檢與生命週期監控 |
| --- | --- | --- |
| 參數正規化 | 時間序列看盤 | 自選股追蹤清單管理 |
| 轉機拓撲篩選器 | 彈性日期矩陣 | 任務去重與流量削峰 |
| 雙層快取防護 | 綜合代價指標 | 自動失效結清與冷卻通知 |

### 模組 1：航班探索與轉機拓撲過濾引擎

#### 搜尋參數解析與標準化

- 支援單程（One-way）與來回（Round-trip）搜尋。
- 支援 IATA 3 碼機場查詢，並具備城市代碼聚合能力，例如搜尋 TYO 時自動對齊 HND 與 NRT。
- 乘客結構解析：分離成人（Adults）與兒童（Children）人數，動態生成查詢結構。

#### 航線拓撲過濾引擎

- **直飛優先**：過濾所有包含 1 個（含）以上中途停留點的航班。
- **轉機樞紐白名單（Allowed Transit Hubs）**：只保留在指定中轉節點轉機的航段，例如赴歐航線限定經由 HKG、BKK、SIN。
- **轉機樞紐黑名單（Excluded Transit Hubs）**：剔除特定需繁瑣簽證或中轉流程複雜的機場。
- **停留時間窗口限制**：設定最短轉機時間（預設 ≥ 90 分鐘）與最長轉機時間（預設 ≤ 300 分鐘）。

#### 記憶體快取防護（Cache-Aside Strategy）

- 快取鍵：`route:{origin}:{dest}:{depart}:{return}:{cabin}:{pax_hash}`。
- 命中快取時直接於 10ms 內回傳清洗後 DTO；未命中時呼叫外部 REST API，成功後將結構化報價寫入快取，TTL 為 30 分鐘。

### 模組 2：多維度票價看盤與聚合模組

#### 自選看盤板（Market Watchboard）

- 針對追蹤項目輸出最新價格、昨日對比價差、7 天價格變化百分比。
- 支援依航司、總時長、起降時間排序，並為航班標示「最便宜（Cheapest）」、「最快速（Fastest）」與「性價比首選（Best Value）」。

#### 彈性日期價格矩陣（Fare Matrix）

- 支援出發日與回程日 ±3 天區間比價。
- 非同步平行發起查詢，生成 7 × 7 二維價格矩陣供前端渲染熱力圖。

#### 飛行成本代價計算（Time-Cost Tradeoff Metric）

```text
綜合代價 = 票價 + (純飛行時數 + 轉機等待時數 × 1.5) × 時間權重單價
```

### 模組 3：非同步巡檢與生命週期監控管線

#### 自選清單（Watchlist）

- 使用者勾選特定航線組合，並設定目標告警價（Target Price）或相對降幅，例如較 7 日均價下跌 10%。

#### 任務聚合與對外 API 節流防護

- **去重聚合**：若多個使用者監控相同航段與日期，排程 Worker 合併為單一查詢任務，降低對外呼叫次數。
- **令牌桶節流（Token Bucket）**：限制背景 Worker 對外呼叫頻率，避免超出第三方限制。

#### 生命週期自動終止機制

- **過期自動退出**：起飛前 1 小時（以最近一次巡檢選中的航班、出發機場當地時間計算；尚無巡檢紀錄時為出發地當地的出發日結束）起，排程掃描自動將狀態更新為 `EXPIRED`，不再加入輪詢隊列。
- **主動取消**：提供即時軟刪除 API，將狀態更新為 `CANCELLED`。

#### 告警推播與冷卻機制

- 價格符合門檻時，組裝航班細節並觸發 Webhook（Discord / LINE）或發送通知。
- **24 小時冷卻期**：同一追蹤標的在 24 小時內若價格未進一步下探，不重複發送通知，防止訊息轟炸。

## 三、實體資料模型設計（Entity Relationship）

使用關聯式資料庫建立 4 張核心表格，確保資料一致性與時間序列查詢效率：

```text
Airports 1:N Tracked_Watchlists
Tracked_Watchlists 1:N Price_History
Price_History 1:N Alert_History
```

### 1. `airports`（靜態機場對照表）

| 欄位 | 型別／約束 | 說明 |
| --- | --- | --- |
| `iata_code` | VARCHAR(3), PK | 機場代碼，如 TPE、MXP、NRT |
| `city_code` | VARCHAR(3), Index | 城市代碼，如 TYO 包含 HND/NRT |
| `name_zh` / `name_en` | VARCHAR(100) | 機場中英文名稱 |
| `country` | VARCHAR(2) | 國家 ISO 2 碼 |
| `timezone` | VARCHAR(50) | 時區字串 |

### 2. `tracked_watchlists`（用戶自選追蹤表）

| 欄位 | 型別／約束 | 說明 |
| --- | --- | --- |
| `id` | UUID, PK | 追蹤規則識別碼 |
| `user_identifier` | VARCHAR(100), Index | 使用者識別碼或通知端點 |
| `origin` / `destination` | VARCHAR(3), FK | 出發／抵達機場代碼 |
| `departure_date` | DATE, Index | 出發日期 |
| `return_date` | DATE, Nullable | 回程日期；單程為 NULL |
| `adults` | INT, Default 1 | 成人人數 |
| `children` | INT, Default 0 | 兒童人數 |
| `cabin_class` | VARCHAR(20) | 艙等 |
| `target_price` | DECIMAL(10, 2) | 目標告警價格 |
| `preferred_airline` | VARCHAR(2), Nullable | 指定追蹤的航司代碼 |
| `allowed_transits` | JSON / Array | 允許轉機機場白名單 |
| `max_stops` | INT, Default 1 | 最大轉機次數 |
| `is_active` | BOOLEAN, Default True, Index | 是否有效中 |
| `status` | VARCHAR(20), Default `TRACKING` | 狀態：TRACKING、EXPIRED、CANCELLED |
| `created_at` | TIMESTAMP | 建立時間 |

### 3. `price_history`（歷史票價時間序列紀錄表）

| 欄位 | 型別／約束 | 說明 |
| --- | --- | --- |
| `id` | BIGINT, PK | 紀錄識別碼 |
| `watchlist_id` | UUID, FK, Index | 關聯追蹤項目 ID |
| `route_hash` | VARCHAR(64), Index | 航線與日期聚合識別碼 |
| `airline_code` | VARCHAR(2) | 航空公司代碼 |
| `price` | DECIMAL(10, 2) | 當日報價金額 |
| `currency` | VARCHAR(3), Default `TWD` | 幣別 |
| `duration_minutes` | INT | 飛行總耗時（分鐘） |
| `stops` | INT | 轉機次數 |
| `recorded_at` | TIMESTAMP, Index | 紀錄時間點 |

### 4. `alert_history`（告警發送紀錄表）

| 欄位 | 型別／約束 | 說明 |
| --- | --- | --- |
| `id` | UUID, PK | 紀錄識別碼 |
| `watchlist_id` | UUID, FK | 對應追蹤規則 |
| `triggered_price` | DECIMAL(10, 2) | 觸發當下的價格 |
| `channel` | VARCHAR(20) | 通知管道（Webhook / Email） |
| `sent_at` | TIMESTAMP | 推播發送時間 |

## 四、中立系統技術架構設計（Vendor-Agnostic Architecture）

架構基於開源軟體與中立元件標準，可部署於標準 Linux 環境、私有機房或雲端環境。

```text
[客戶端／瀏覽器]
	│ HTTP/HTTPS
	▼
[反向代理／負載平衡器：Nginx / Traefik / HAProxy]
	├── [Web Server：React / Next.js，提供靜態前端資產]
	└── [API Gateway／服務實例：FastAPI / Python]
		 │
	 後端專用區域網路（Private Network / VPC）
		 ├── [API 服務實例（多執行個體）]
		 ├── [快取與分散式鎖：Redis]
		 ├── [關聯式資料庫：PostgreSQL（連線池）]
		 ├── [背景巡檢 Worker 群] ──寫入歷史數據──► PostgreSQL
		 ├── [訊息佇列：RabbitMQ / Redis] ──► [外部通知：Webhook / SMTP]
		 └── [分散式定時排程器：Cron / Celery Beat]
			   │ 發布每日巡檢任務
			   ▼
		    [經由 NAT 存取外部網路]
			   ▼
		    [第三方機票 RESTful API]
```

### 元件職責與選型理由

1. **API 服務實例（FastAPI / Gunicorn）**：Python 原生支援非同步 I/O（async/await），適合處理高延遲外部 HTTP 與資料庫 I/O；Pydantic 提供強型別校驗與 OpenAPI 規格自動生成。
2. **快取與記憶體引擎（Redis）**：以 30 分鐘 TTL 暫存熱門航線結果，將高頻請求延遲由秒級降至毫秒級；提供分散式排程鎖，避免多個 Worker 重複觸發同一排程。
3. **主關聯式資料庫（PostgreSQL）**：以外鍵與交易確保追蹤設定完整性；支援 JSONB 與 GIN 索引，以保留關聯結構並彈性儲存轉機白名單與航段資訊。
4. **非同步訊息佇列（RabbitMQ / Redis Queue）與 Worker（Celery）**：將即時搜尋與每日巡檢切分；排程任務入列後由 Worker 依固定速率消費，保護第三方 API 配額與出口頻寬。
5. **反向代理與安全網關（Nginx / HAProxy）**：負責 SSL/TLS 終結、靜態檔案快取、請求限流（DDoS 防護）及後端多節點負載平衡。

## 五、核心業務流程

### 1. 即時航班比價流程（Online Flow）

```text
[用戶送出多條件搜尋請求]
	▼
[產生 SHA-256 快取鍵]
	├── Cache Hit ──► [讀取 Redis 快取] ──────────────┐
	└── Cache Miss ─► [呼叫外部機票 RESTful API]     │
				  ▼                       │
			 [原始報價資料扁平化]              │
				  ▼                       │
			 [轉機拓撲過濾引擎]                │
		    （直飛／白名單／停留時長篩選）          │
				  ▼                       │
			 [計算綜合飛行代價指數]            │
				  ▼                       │
			 [寫入 Redis，TTL 30 分鐘]         │
				  └───────────────────────┤
							  ▼
					     [回傳結構化比價結果]
```

### 2. 每日看盤巡檢與自動失效流程（Offline Pipeline）

```text
[定時排程器每日固定觸發]
	▼
[讀取有效追蹤清單：is_active = true]
	├── 距起飛不到 1 小時 ──► [更新為 EXPIRED 並結束]
	└── 有效標的 ──► [依 Route + Date 去重]
			      ▼
		    [推入訊息佇列 Broker]
			      ▼
		[Worker 受控拉取任務：Token Bucket]
			      ▼
		[呼叫外部 API 取得最新報價]
			      ▼
		[寫入 price_history 時間序列]
			      ▼
		[比對價格閥值與降幅比例]
		     ├── 未達門檻 ──► [結束當次週期]
		     └── 達到門檻 ──► [檢查 24 小時冷卻期]
					   ├── 冷卻期間內 ──► [略過發送]
					   └── 已脫離冷卻 ──► [Webhook／Email 推播]
								    ▼
							[寫入 alert_history]
```

## 六、加分項目執行方案（中立實施標準）

1. **前端應用程式設計**：採用 Next.js（React）與 Tailwind CSS 建置單頁應用（SPA）。看盤面板以卡片呈現自選清單、昨日漲跌與 7 天最低價；使用 Recharts 繪製歷史票價折線圖與 7 × 7 彈性日期價格熱力矩陣。
2. **第三方 RESTful API 串接**：使用非同步 HTTP 客戶端 httpx 封裝外部航空 API，建立防腐層（Anti-Corruption Layer），將深層巢狀結構轉為標準領域模型。
3. **多人協作 Git 工作流程**：採用 GitHub Flow，透過 `feature/*` 分支開發並發起 Pull Request；自動觸發 CI 測試，設定至少 1 位 Code Review 通過的保護規則；合併至 `main` 後自動打包與發布。
4. **CI/CD 自動化管線**：PR 執行 Flake8／Black 程式碼風格檢查、Mypy 型別校驗與 Pytest 單元測試（涵蓋轉機過濾演算法與快取測試）；合併至 `main` 後建置 OCI 標準 Docker Image，支援容器化滾動發布。
5. **基礎架構即程式碼（Infrastructure as Code）**：使用多階段建置（Multi-stage build）最佳化 Docker 映像檔大小；以 `docker-compose.yml` 統整部署 API、Worker、PostgreSQL 與 Redis。
6. **AI 輔助開發實務**：說明如何使用程式碼輔助工具生成 Pydantic 資料驗證結構、Mock 測試資料集，以及最佳化 SQL 查詢索引。
