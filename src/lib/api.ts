import { getLang, t } from "../i18n/i18n.ts";
import { getKey } from "./credentials.ts";
import { getCurrency } from "./currency.ts";
import { readNdjson } from "./ndjson.ts";
import type {
  AlertRecord,
  Airport,
  ApiEnvelope,
  AppConfig,
  CredentialCheck,
  FilterParams,
  FxTable,
  MatrixLine,
  PatrolReport,
  PricePoint,
  SearchResult,
  SearchState,
  TripParams,
  Watchlist,
  WatchlistCreate,
} from "./types.ts";
import { getUserId } from "./user.ts";

/** 後端以 meta.code 標示需要使用者處理金鑰的錯誤 */
export type ApiErrorCode = "missing_api_key" | "invalid_api_key" | null;

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;

  constructor(status: number, message: string, code: ApiErrorCode = null) {
    super(message);
    this.status = status;
    this.code = code;
  }

  get needsApiKey(): boolean {
    return this.code !== null;
  }
}

/** 共用標頭：使用者識別碼 + （若有設定）使用者自備的 Duffel 金鑰 */
function baseHeaders(init?: HeadersInit, tokenOverride?: string): Headers {
  const headers = new Headers(init);
  headers.set("Content-Type", "application/json");
  headers.set("X-User-Id", getUserId());
  headers.set("Accept-Language", getLang() === "en" ? "en" : "zh-TW");
  const token = tokenOverride ?? getKey()?.token;
  if (token) headers.set("X-Duffel-Token", token);
  return headers;
}

async function toApiError(response: Response, fallback: string): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as ApiEnvelope<unknown> | null;
  const code = (body?.meta?.code as ApiErrorCode | undefined) ?? null;
  return new ApiError(response.status, body?.error ?? fallback, code);
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: baseHeaders(init.headers, token) });
  } catch {
    throw new ApiError(0, t("error.network"));
  }
  if (!response.ok) throw await toApiError(response, t("error.http", { status: response.status }));
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!body?.success) throw new ApiError(response.status, body?.error ?? t("error.format"));
  return body.data as T;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),

  verifyKey: (token: string) =>
    request<CredentialCheck>("/api/credentials/verify", { method: "POST" }, token),

  airports: (q: string, signal?: AbortSignal) =>
    request<Airport[]>(`/api/airports?q=${encodeURIComponent(q)}`, { signal }),

  search: (state: SearchState, currency: string = getCurrency(), limit = 80) =>
    request<SearchResult>("/api/search", {
      method: "POST",
      body: JSON.stringify({ ...state, currency, limit }),
    }),

  fx: () => request<FxTable>("/api/fx"),

  watchlists: () => request<Watchlist[]>("/api/watchlists"),

  createWatchlist: (payload: WatchlistCreate) =>
    request<Watchlist>("/api/watchlists", { method: "POST", body: JSON.stringify(payload) }),

  cancelWatchlist: (id: string) =>
    request<Watchlist>(`/api/watchlists/${id}`, { method: "DELETE" }),

  /** 永久刪除（含歷史價格與告警紀錄） */
  deleteWatchlist: (id: string) =>
    request<null>(`/api/watchlists/${id}?purge=true`, { method: "DELETE" }),

  /** 清除所有已取消／已過期的追蹤 */
  purgeEndedWatchlists: () =>
    request<{ deleted: number }>("/api/watchlists?scope=ended", { method: "DELETE" }),

  history: (id: string, days = 30) =>
    request<PricePoint[]>(`/api/watchlists/${id}/history?days=${days}`),

  alerts: (id: string) => request<AlertRecord[]>(`/api/watchlists/${id}/alerts`),

  runPatrol: () => request<PatrolReport>("/api/patrol/run", { method: "POST" }),
};

/** 以串流方式取得彈性日期矩陣，每收到一行就回呼一次。 */
export async function streamFareMatrix(
  params: TripParams & FilterParams & { radius_days: number; currency: string },
  onLine: (line: MatrixLine) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/fare-matrix", {
    method: "POST",
    headers: baseHeaders(),
    body: JSON.stringify(params),
    signal,
  });
  if (!response.ok || !response.body) throw await toApiError(response, t("matrix.failed"));
  for await (const line of readNdjson<MatrixLine>(response.body)) {
    onLine(line);
  }
}
