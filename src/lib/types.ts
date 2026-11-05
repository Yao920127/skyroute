// 與後端 app/schemas.py、app/domain/offers.py 對應的型別

export type CabinClass = "economy" | "premium_economy" | "business" | "first";
export type SortKey = "price" | "duration" | "departure" | "arrival" | "airline" | "cost";
export type OfferTag = "cheapest" | "fastest" | "best_value";

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta: Record<string, unknown> | null;
}

export interface Airport {
  iata_code: string;
  city_code: string;
  name_zh: string | null;
  name_en: string;
  country: string;
  timezone: string | null;
  kind: "airport" | "city";
}

/** 同一班機中途落地（不換機），例如 BR67 台北→倫敦 經停曼谷 */
export interface TechnicalStop {
  airport: string;
  city_name: string | null;
  minutes: number;
}

export interface Segment {
  carrier_code: string;
  carrier_name: string;
  flight_number: string;
  origin: string;
  destination: string;
  departing_at: string;
  arriving_at: string;
  duration_minutes: number;
  aircraft: string | null;
  stops: TechnicalStop[];
  /** 代碼共享時的實際營運航司 */
  operating_code: string | null;
  operating_name: string | null;
}

export interface Layover {
  airport: string;
  city_name: string | null;
  minutes: number;
}

export interface Slice {
  origin: string;
  destination: string;
  departing_at: string;
  arriving_at: string;
  duration_minutes: number;
  segments: Segment[];
  layovers: Layover[];
  /** 轉機（換機）次數 */
  stops: number;
  /** 中途經停（不換機）次數 */
  technical_stops: number;
  flight_minutes: number;
  layover_minutes: number;
}

export interface FlightOffer {
  id: string;
  airline_code: string;
  airline_name: string;
  airline_logo: string | null;
  total_amount: string;
  currency: string;
  slices: Slice[];
  refundable: boolean | null;
  changeable: boolean | null;
  emissions_kg: number | null;
  /** Duffel 測試模式的模擬報價（班號、航線、時間、票價都不是真實資料） */
  is_simulated: boolean;
  /** 換算成顯示幣別後保留的航空公司原始報價 */
  original_amount: string | null;
  original_currency: string | null;
}

export interface RankedOffer {
  offer: FlightOffer;
  total_duration_minutes: number;
  flight_minutes: number;
  layover_minutes: number;
  max_stops: number;
  cost_index: string;
  tags: OfferTag[];
}

export interface NumericRange {
  min: string;
  max: string;
}

export interface FxInfo {
  currency: string;
  as_of: string;
  source: string;
  approximate: boolean;
}

export interface FxTable {
  base: string;
  rates: Record<string, string>;
  as_of: string;
  source: string;
  approximate: boolean;
}

export interface SearchResult {
  currency: string;
  fx: FxInfo;
  price_bounds: NumericRange | null;
  duration_bounds: NumericRange | null;
  origin_airports: string[];
  destination_airports: string[];
  cache: { hit: boolean; key: string; fetched_at: string };
  total_raw: number;
  total_filtered: number;
  hubs: string[];
  airlines: { code: string; name: string }[];
  offers: RankedOffer[];
}

export interface Leg {
  origin: string;
  destination: string;
  departure_date: string;
}

export type TripType = "ow" | "rt" | "mc";
export type TicketMode = "combined" | "split";

export interface TripParams {
  origin: string;
  destination: string;
  departure_date: string;
  return_date: string | null;
  /** 多航段的第 2 段以後 */
  extra_legs: Leg[];
  adults: number;
  children: number;
  cabin_class: CabinClass;
}

export interface FilterParams {
  direct_only: boolean;
  max_stops: number;
  allowed_hubs: string[];
  excluded_hubs: string[];
  min_layover_minutes: number;
  max_layover_minutes: number;
  airlines: string[];
  price_min: number | null;
  price_max: number | null;
  duration_min: number | null;
  duration_max: number | null;
}

export interface SearchState extends TripParams, FilterParams {
  trip_type: TripType;
  mode: TicketMode;
  time_value_per_hour: number;
  sort: SortKey;
}

export type MatrixLine =
  | {
      type: "axes";
      currency: string;
      fx_approximate: boolean;
      departure_dates: string[];
      return_dates: (string | null)[];
    }
  | {
      type: "cell";
      departure_date: string;
      return_date: string | null;
      status: "ok" | "empty" | "error" | "invalid";
      price?: string | null;
      currency?: string | null;
      cached?: boolean;
      simulated?: boolean;
      message?: string;
    }
  | { type: "done" };

export type MatrixCell = Extract<MatrixLine, { type: "cell" }>;

export interface WatchStats {
  latest_price: string | null;
  currency: string | null;
  last_checked_at: string | null;
  previous_day_price: string | null;
  day_change: string | null;
  day_change_pct: string | null;
  week_change_pct: string | null;
  week_low: string | null;
  week_avg: string | null;
  last_alert_at: string | null;
  sparkline: string[];
}

export interface Watchlist extends TripParams {
  id: string;
  label: string | null;
  target_price: string | null;
  drop_percent: string | null;
  preferred_airline: string | null;
  allowed_transits: string[];
  excluded_transits: string[];
  max_stops: number;
  min_layover_minutes: number;
  max_layover_minutes: number;
  currency: string | null;
  has_webhook: boolean;
  uses_own_key: boolean;
  is_active: boolean;
  status: "TRACKING" | "EXPIRED" | "CANCELLED";
  created_at: string;
  stats: WatchStats;
}

export interface WatchlistCreate extends TripParams {
  label: string | null;
  target_price: number | null;
  drop_percent: number | null;
  preferred_airline: string | null;
  allowed_transits: string[];
  excluded_transits: string[];
  max_stops: number;
  min_layover_minutes: number;
  max_layover_minutes: number;
  webhook_url: string | null;
  currency: string;
}

export interface PricePoint {
  recorded_at: string;
  price: string;
  currency: string;
  airline_code: string;
  stops: number;
  duration_minutes: number;
}

export interface AlertRecord {
  id: string;
  triggered_price: string;
  currency: string;
  reason: "target" | "drop";
  channel: string;
  sent_at: string;
}

export interface PatrolReport {
  expired: number;
  active: number;
  route_groups: number;
  api_calls: number;
  prices_recorded: number;
  alerts_sent: number;
  alerts_suppressed: number;
  failures: number;
  skipped_locked: boolean;
}

export interface AppConfig {
  has_server_key: boolean;
  can_store_user_key: boolean;
  /** 有值代表伺服器已啟用 Google 登入 */
  google_client_id?: string | null;
}

/** 以 Google 登入的帳號；金鑰只回遮罩與模式 */
export interface Account {
  email: string;
  name: string | null;
  picture: string | null;
  key_mask: string | null;
  key_mode: "test" | "live" | null;
}

export interface CredentialCheck {
  valid: boolean;
  mode: "test" | "live";
}
