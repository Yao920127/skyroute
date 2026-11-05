import { addDays } from "./format.ts";
import type {
  CabinClass,
  FilterParams,
  Leg,
  SearchState,
  SortKey,
  TicketMode,
  TripParams,
  TripType,
} from "./types.ts";

const SORT_KEYS: SortKey[] = ["price", "duration", "departure", "arrival", "airline", "cost"];
const CABINS: CabinClass[] = ["economy", "premium_economy", "business", "first"];
const TRIP_TYPES: TripType[] = ["ow", "rt", "mc"];
export const MAX_LEGS = 5;
const IATA = /^[A-Z]{3}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const DEFAULT_FILTERS: FilterParams = {
  direct_only: false,
  max_stops: 1,
  allowed_hubs: [],
  excluded_hubs: [],
  min_layover_minutes: 90,
  max_layover_minutes: 300,
  airlines: [],
  price_min: null,
  price_max: null,
  duration_min: null,
  duration_max: null,
};

export function defaultSearchState(today: string): SearchState {
  return {
    trip_type: "rt",
    mode: "combined",
    origin: "TPE",
    destination: "TYO",
    departure_date: addDays(today, 30),
    return_date: addDays(today, 37),
    extra_legs: [],
    adults: 1,
    children: 0,
    cabin_class: "economy",
    ...DEFAULT_FILTERS,
    time_value_per_hour: 15,
    sort: "price",
  };
}

const list = (v: string | null) => (v ? v.split(",").filter(Boolean) : []);
const int = (v: string | null, fallback: number, min: number, max: number) => {
  const n = Number.parseInt(v ?? "", 10);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
};
const optionalNumber = (v: string | null) => {
  if (v === null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
};

/** legs=PAR-TPE-2026-12-28,LHR-TPE-2027-01-02 */
function parseLegs(value: string | null): Leg[] {
  return list(value)
    .map((item) => {
      const [origin, destination, ...date] = item.split("-");
      return {
        origin: (origin ?? "").toUpperCase(),
        destination: (destination ?? "").toUpperCase(),
        departure_date: date.join("-"),
      };
    })
    .filter(
      (l) => IATA.test(l.origin) && IATA.test(l.destination) && ISO_DATE.test(l.departure_date),
    )
    .slice(0, MAX_LEGS - 1);
}

function serializeLegs(legs: Leg[]): string {
  return legs.map((l) => `${l.origin}-${l.destination}-${l.departure_date}`).join(",");
}

/** 搜尋條件以 URL 參數保存，方便分享與重新整理後還原。 */
export function parseSearchState(query: string, today: string): SearchState {
  const p = new URLSearchParams(query);
  const base = defaultSearchState(today);
  const sort = p.get("sort") as SortKey | null;
  const cabin = p.get("cabin") as CabinClass | null;
  const code = (key: string, fallback: string) => {
    const v = p.get(key)?.toUpperCase();
    return v && IATA.test(v) ? v : fallback;
  };
  const extraLegs = parseLegs(p.get("legs"));
  const tripParam = p.get("trip") as TripType | null;
  // 舊網址沒有 trip 參數：有回程日就是來回
  const tripType: TripType =
    tripParam && TRIP_TYPES.includes(tripParam)
      ? tripParam
      : p.has("ret") && !p.get("ret")
        ? "ow"
        : "rt";
  const isMulti = tripType === "mc" && extraLegs.length > 0;
  const mode: TicketMode = p.get("mode") === "split" ? "split" : "combined";
  return {
    ...base,
    trip_type: isMulti ? "mc" : tripType === "mc" ? "rt" : tripType,
    mode,
    origin: code("from", base.origin),
    destination: code("to", base.destination),
    departure_date: p.get("dep") ?? base.departure_date,
    return_date: tripType === "rt" ? p.get("ret") || base.return_date : null,
    extra_legs: isMulti ? extraLegs : [],
    adults: int(p.get("ad"), base.adults, 1, 9),
    children: int(p.get("ch"), base.children, 0, 8),
    cabin_class: cabin && CABINS.includes(cabin) ? cabin : base.cabin_class,
    direct_only: p.get("direct") === "1",
    max_stops: int(p.get("stops"), base.max_stops, 0, 2),
    allowed_hubs: list(p.get("via")),
    excluded_hubs: list(p.get("avoid")),
    min_layover_minutes: int(p.get("lmin"), base.min_layover_minutes, 0, 1440),
    max_layover_minutes: int(p.get("lmax"), base.max_layover_minutes, 0, 2880),
    airlines: list(p.get("al")),
    price_min: optionalNumber(p.get("pmin")),
    price_max: optionalNumber(p.get("pmax")),
    duration_min: optionalNumber(p.get("dmin")),
    duration_max: optionalNumber(p.get("dmax")),
    time_value_per_hour: int(p.get("tv"), base.time_value_per_hour, 0, 100000),
    sort: sort && SORT_KEYS.includes(sort) ? sort : base.sort,
  };
}

export function serializeSearchState(s: SearchState): string {
  const p = new URLSearchParams({
    trip: s.trip_type,
    from: s.origin,
    to: s.destination,
    dep: s.departure_date,
    ad: String(s.adults),
    ch: String(s.children),
    cabin: s.cabin_class,
    stops: String(s.max_stops),
    lmin: String(s.min_layover_minutes),
    lmax: String(s.max_layover_minutes),
    tv: String(s.time_value_per_hour),
    sort: s.sort,
  });
  if (s.trip_type === "rt" && s.return_date) p.set("ret", s.return_date);
  if (s.trip_type === "mc" && s.extra_legs.length) p.set("legs", serializeLegs(s.extra_legs));
  if (s.mode === "split" && s.trip_type !== "ow") p.set("mode", "split");
  if (s.direct_only) p.set("direct", "1");
  if (s.allowed_hubs.length) p.set("via", s.allowed_hubs.join(","));
  if (s.excluded_hubs.length) p.set("avoid", s.excluded_hubs.join(","));
  if (s.airlines.length) p.set("al", s.airlines.join(","));
  if (s.price_min !== null) p.set("pmin", String(s.price_min));
  if (s.price_max !== null) p.set("pmax", String(s.price_max));
  if (s.duration_min !== null) p.set("dmin", String(s.duration_min));
  if (s.duration_max !== null) p.set("dmax", String(s.duration_max));
  return p.toString();
}

/** 所有航段（單程 1 段、來回 2 段、多航段 N 段） */
export function legsOf(s: TripParams): Leg[] {
  const first = { origin: s.origin, destination: s.destination, departure_date: s.departure_date };
  if (s.extra_legs.length) return [first, ...s.extra_legs];
  if (s.return_date) {
    return [first, { origin: s.destination, destination: s.origin, departure_date: s.return_date }];
  }
  return [first];
}

export function tripOf(s: SearchState): TripParams {
  const {
    origin,
    destination,
    departure_date,
    return_date,
    extra_legs,
    adults,
    children,
    cabin_class,
  } = s;
  return {
    origin,
    destination,
    departure_date,
    return_date,
    extra_legs,
    adults,
    children,
    cabin_class,
  };
}

export function filtersOf(s: SearchState): FilterParams {
  return {
    direct_only: s.direct_only,
    max_stops: s.max_stops,
    allowed_hubs: s.allowed_hubs,
    excluded_hubs: s.excluded_hubs,
    min_layover_minutes: s.min_layover_minutes,
    max_layover_minutes: s.max_layover_minutes,
    airlines: s.airlines,
    price_min: s.price_min,
    price_max: s.price_max,
    duration_min: s.duration_min,
    duration_max: s.duration_max,
  };
}

/** 單一航段的單程查詢（分段購票時每段各查一次） */
export function oneWayLeg(s: SearchState, leg: Leg): SearchState {
  return {
    ...s,
    trip_type: "ow",
    mode: "combined",
    origin: leg.origin,
    destination: leg.destination,
    departure_date: leg.departure_date,
    return_date: null,
    extra_legs: [],
  };
}
