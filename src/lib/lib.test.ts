import { describe, expect, it } from "vite-plus/test";

import {
  addDays,
  dayOffset,
  dateWithWeekday,
  formatDuration,
  formatNumber,
  formatPct,
  localTime,
  relativeTime,
  shortDateLabel,
  trendOf,
} from "./format.ts";
import { interpolate, translate } from "../i18n/i18n.ts";
import { en, zh } from "../i18n/messages.ts";
import { formatCompact, formatPrice } from "./currency.ts";
import { buildScale, cellKey, heatColor, heatInk } from "./heat.ts";
import { splitLines } from "./ndjson.ts";
import {
  defaultSearchState,
  legsOf,
  oneWayLeg,
  parseSearchState,
  serializeSearchState,
} from "./searchState.ts";
import { intervalKey, isIntervalAllowed, nextCheckLabel, parseIntervalKey } from "./schedule.ts";
import { sparklinePath } from "./sparkline.ts";
import { discountedPrice, percentBelow } from "./targetPrice.ts";
import { cheapestChain, connects, earliestDeparture } from "./splitPlan.ts";
import { legAirlinesText, routeText, watchLegs } from "./watchRoute.ts";
import { stopAirports, stopsText } from "./stops.ts";
import type { MatrixCell } from "./types.ts";

describe("format", () => {
  it("formats durations", () => {
    expect(formatDuration(45)).toBe("45m");
    expect(formatDuration(120)).toBe("2h");
    expect(formatDuration(404)).toBe("6h 44m");
  });

  it("reads local time without timezone conversion", () => {
    expect(localTime("2026-12-20T23:05:00")).toBe("23:05");
    expect(dayOffset("2026-12-20T23:05:00", "2026-12-21T04:00:00")).toBe(1);
  });

  it("formats money and percentages", () => {
    expect(formatNumber("1234.5")).toBe("1,234.50");
    expect(formatNumber(200)).toBe("200");
    expect(formatNumber(null)).toBe("—");
    expect(formatPct("-10.53")).toBe("−10.53%");
    expect(formatPct(3)).toBe("+3.00%");
    expect(formatPct(0)).toBe("±0.00%");
    expect(formatPct(null)).toBe("—");
  });

  it("treats price drops as the favourable trend", () => {
    expect(trendOf("-5")).toBe("down");
    expect(trendOf(2)).toBe("up");
    expect(trendOf(0)).toBe("flat");
    expect(trendOf(null)).toBe("none");
  });

  it("handles dates and relative time", () => {
    expect(addDays("2026-12-30", 3)).toBe("2027-01-02");
    expect(shortDateLabel("2026-12-20")).toEqual({ md: "12/20", weekday: "日" });
    expect(dateWithWeekday("2026-12-20", "zh")).toBe("12/20（日）");
    expect(dateWithWeekday("2026-12-20", "en")).toBe("Sun 12/20");
    const now = Date.parse("2026-11-05T10:00:00Z");
    const zhT = (key: keyof typeof zh, vars?: Record<string, string | number>) =>
      translate("zh", key, vars);
    const enT = (key: keyof typeof zh, vars?: Record<string, string | number>) =>
      translate("en", key, vars);
    expect(relativeTime(null, zhT, now)).toBe("尚未巡檢");
    expect(relativeTime("2026-11-05T09:59:40Z", zhT, now)).toBe("剛剛");
    expect(relativeTime("2026-11-05T09:30:00Z", zhT, now)).toBe("30 分鐘前");
    expect(relativeTime("2026-11-05T07:00:00Z", enT, now)).toBe("3 h ago");
    expect(relativeTime("2026-11-03T10:00:00Z", enT, now)).toBe("2 d ago");
  });
});

describe("ndjson", () => {
  it("keeps the trailing partial line for the next chunk", () => {
    expect(splitLines('{"a":1}\n{"b":2}\n{"c"')).toEqual({
      lines: ['{"a":1}', '{"b":2}'],
      rest: '{"c"',
    });
    expect(splitLines("\n\n")).toEqual({ lines: [], rest: "" });
  });
});

describe("heat scale", () => {
  const cell = (price: string | null, status: MatrixCell["status"] = "ok"): MatrixCell => ({
    type: "cell",
    departure_date: "2026-12-20",
    return_date: null,
    status,
    price,
  });

  it("normalises prices between min and max", () => {
    const scale = buildScale([cell("100"), cell("300"), cell(null, "empty")]);
    expect(scale?.min).toBe(100);
    expect(scale?.max).toBe(300);
    expect(scale?.position(200)).toBe(0.5);
  });

  it("returns null without priced cells and 0 for a flat scale", () => {
    expect(buildScale([cell(null, "error")])).toBeNull();
    expect(buildScale([cell("50")])?.position(50)).toBe(0);
  });

  it("mixes toward the low/high colours", () => {
    expect(heatColor(0)).toContain("var(--heat-low) 100%");
    expect(heatColor(1)).toContain("var(--heat-high) 100%");
    expect(heatColor(2)).toBe(heatColor(1));
    expect(cellKey("2026-12-20", null)).toBe("2026-12-20|-");
    expect(heatInk(0)).toBe("var(--on-dark)");
    expect(heatInk(0.8)).toBe("var(--ink)");
  });
});

describe("search state in URL", () => {
  const today = "2026-11-05";

  it("round-trips through the query string", () => {
    const state = {
      ...defaultSearchState(today),
      origin: "TPE",
      destination: "MXP",
      allowed_hubs: ["BKK", "HKG"],
      excluded_hubs: ["PEK"],
      airlines: ["BR"],
      direct_only: true,
      trip_type: "ow" as const,
      return_date: null,
      sort: "cost" as const,
    };
    expect(parseSearchState(serializeSearchState(state), today)).toEqual(state);
  });

  it("falls back to defaults for invalid values", () => {
    const parsed = parseSearchState("from=xx&ad=99&sort=bogus&cabin=jet", today);
    expect(parsed.origin).toBe("TPE");
    expect(parsed.adults).toBe(9);
    expect(parsed.sort).toBe("price");
    expect(parsed.cabin_class).toBe("economy");
    expect(parsed.departure_date).toBe("2026-12-05");
  });
});

describe("sparkline", () => {
  it("draws a path scaled to the box", () => {
    expect(sparklinePath([], 100, 20)).toBe("");
    expect(sparklinePath([10, 10], 100, 20)).toBe("M0.0,10.0 L100.0,10.0");
    expect(sparklinePath([0, 10], 100, 20)).toBe("M0.0,18.0 L100.0,2.0");
  });
});

describe("currency", () => {
  it("formats with the currency's own precision", () => {
    expect(formatPrice("1234.5", "USD", "en-US")).toBe("US$1,234.50");
    expect(formatPrice(5400.4, "TWD", "zh-TW")).toBe("NT$5,400");
    expect(formatPrice(15000, "JPY", "en-US")).toBe("¥15,000");
    expect(formatPrice(-20, "EUR", "en-US")).toBe("−€20.00");
    expect(formatPrice(null, "USD", "en-US")).toBe("—");
    expect(formatCompact("1234.56", "USD", "en-US")).toBe("1,235");
    expect(formatCompact("123.456", "EUR", "en-US")).toBe("123.46");
  });
});

describe("i18n", () => {
  it("has an English string for every key", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zh).sort());
    for (const value of Object.values(en)) expect(value.length).toBeGreaterThan(0);
  });

  it("keeps the same placeholders in both languages", () => {
    const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const key of Object.keys(zh) as (keyof typeof zh)[]) {
      expect(vars(en[key]), key).toEqual(vars(zh[key]));
    }
  });

  it("interpolates variables", () => {
    expect(interpolate("{n} 段", { n: 3 })).toBe("3 段");
    expect(interpolate("keep {missing}", {})).toBe("keep {missing}");
    expect(translate("en", "trip.leg", { n: 2 })).toBe("Leg 2");
  });
});

describe("multi-city search state", () => {
  const today = "2026-11-05";

  it("round-trips legs, ticket mode and slider ranges through the URL", () => {
    const state = {
      ...defaultSearchState(today),
      trip_type: "mc" as const,
      mode: "split" as const,
      origin: "TPE",
      destination: "LON",
      return_date: null,
      extra_legs: [{ origin: "PAR", destination: "TPE", departure_date: "2026-12-28" }],
      price_min: 5000,
      price_max: 30000,
      duration_min: null,
      duration_max: 900,
    };
    const parsed = parseSearchState(serializeSearchState(state), today);
    expect(parsed).toEqual(state);
    expect(legsOf(parsed).map((l) => `${l.origin}-${l.destination}`)).toEqual([
      "TPE-LON",
      "PAR-TPE",
    ]);
  });

  it("derives legs for one-way and round trips", () => {
    const rt = defaultSearchState(today);
    expect(legsOf(rt)).toHaveLength(2);
    expect(legsOf(rt)[1]).toMatchObject({ origin: rt.destination, destination: rt.origin });
    expect(legsOf({ ...rt, return_date: null })).toHaveLength(1);
  });

  it("ignores malformed legs and falls back to a round trip", () => {
    const parsed = parseSearchState("trip=mc&from=TPE&to=LON&legs=bad,XX-YY-2026", today);
    expect(parsed.trip_type).toBe("rt");
    expect(parsed.extra_legs).toEqual([]);
  });

  it("keeps old share links working (no trip param)", () => {
    expect(parseSearchState("from=TPE&to=TYO&ret=", today).trip_type).toBe("ow");
    expect(parseSearchState("from=TPE&to=TYO&ret=2026-12-27", today).return_date).toBe(
      "2026-12-27",
    );
  });

  it("builds a one-way query for a single leg", () => {
    const leg = { origin: "PAR", destination: "TPE", departure_date: "2026-12-28" };
    const single = oneWayLeg({ ...defaultSearchState(today), mode: "split" }, leg);
    expect(single).toMatchObject({ trip_type: "ow", mode: "combined", return_date: null, ...leg });
  });
});

describe("stops text", () => {
  const zhT = (key: keyof typeof zh, vars?: Record<string, string | number>) =>
    translate("zh", key, vars);
  const segment = (
    stops: { airport: string; city_name: string | null; minutes: number }[] = [],
  ) => ({
    carrier_code: "BR",
    carrier_name: "EVA Air",
    flight_number: "BR0067",
    origin: "TPE",
    destination: "LHR",
    departing_at: "2026-12-20T08:05:00",
    arriving_at: "2026-12-20T19:05:00",
    duration_minutes: 1140,
    aircraft: null,
    stops,
    operating_code: null,
    operating_name: null,
  });
  const slice = (stops: number, segs: ReturnType<typeof segment>[], layovers: string[] = []) => ({
    origin: "TPE",
    destination: "LHR",
    departing_at: "2026-12-20T08:05:00",
    arriving_at: "2026-12-20T19:05:00",
    duration_minutes: 1140,
    segments: segs,
    layovers: layovers.map((airport) => ({ airport, city_name: null, minutes: 120 })),
    stops,
    technical_stops: segs.reduce((n, s) => n + s.stops.length, 0),
    flight_minutes: 1140,
    layover_minutes: 0,
  });

  it("labels a same-aircraft stop as direct-with-stop, not non-stop", () => {
    const br67 = slice(0, [segment([{ airport: "BKK", city_name: "Bangkok", minutes: 90 }])]);
    expect(stopAirports(br67)).toEqual(["BKK"]);
    expect(stopsText(br67, zhT)).toEqual({ text: "直達・經停 BKK", isNonstop: false });
  });

  it("keeps true non-stops and connections distinct", () => {
    expect(stopsText(slice(0, [segment()]), zhT)).toEqual({ text: "直飛", isNonstop: true });
    const withBoth = slice(
      1,
      [segment([{ airport: "BKK", city_name: null, minutes: 60 }]), segment()],
      ["HKG"],
    );
    expect(stopsText(withBoth, zhT).text).toBe("1 次轉機 · HKG · 經停 BKK");
  });
});

describe("patrol schedule", () => {
  it("round-trips select values", () => {
    expect(intervalKey(null)).toBe("daily");
    expect(parseIntervalKey("daily")).toBeNull();
    expect(parseIntervalKey(intervalKey(30))).toBe(30);
    expect(parseIntervalKey("7")).toBeNull();
  });

  it("allows short intervals only with an own key", () => {
    expect(isIntervalAllowed(5, false)).toBe(false);
    expect(isIntervalAllowed(15, true)).toBe(true);
    expect(isIntervalAllowed(30, false)).toBe(true);
    expect(isIntervalAllowed(null, false)).toBe(true);
  });

  it("shows only the time for checks later today", () => {
    const now = new Date(2026, 10, 6, 9, 0);
    expect(nextCheckLabel(new Date(2026, 10, 6, 14, 30).toISOString(), now)).toBe("14:30");
    expect(nextCheckLabel(new Date(2026, 10, 7, 3, 0).toISOString(), now)).toBe("11/7 03:00");
  });
});

describe("watch route", () => {
  const leg = (origin: string, destination: string) => ({
    origin,
    destination,
    departure_date: "2026-12-05",
  });

  it("expands round trips and extra legs", () => {
    const rt = watchLegs({ ...leg("TPE", "BKK"), return_date: "2026-12-12", extra_legs: [] });
    expect(rt.map((l) => `${l.origin}-${l.destination}`)).toEqual(["TPE-BKK", "BKK-TPE"]);
  });

  it("chains connected legs and separates open jaws", () => {
    expect(routeText([leg("TPE", "BKK"), leg("BKK", "TPE")])).toBe("TPE → BKK → TPE");
    expect(routeText([leg("TPE", "LON"), leg("PAR", "TPE")])).toBe("TPE → LON · PAR → TPE");
  });

  it("formats per-leg airlines", () => {
    expect(legAirlinesText(["CZ", "BR"])).toBe("CZ + BR");
    expect(legAirlinesText(["CZ", null])).toBe("CZ + —");
    expect(legAirlinesText([null, null])).toBeNull();
  });
});

describe("split ticket connections", () => {
  const f = (id: string, price: number, o: string, d: string, dep: string, arr: string) => ({
    id,
    price,
    origin: o,
    destination: d,
    departing_at: dep,
    arriving_at: arr,
  });
  const toCts = f("a", 100, "NRT", "CTS", "2026-12-12T17:50:00", "2026-12-12T19:40:00");
  const backEarly = f("b", 50, "CTS", "NRT", "2026-12-12T13:40:00", "2026-12-12T15:30:00");
  const backOk = f("c", 90, "CTS", "NRT", "2026-12-12T21:45:00", "2026-12-12T23:35:00");

  it("rejects a leg that leaves before the previous one lands", () => {
    expect(connects(toCts, backEarly)).toBe(false);
    expect(connects(toCts, backOk)).toBe(true);
    expect(earliestDeparture(toCts, "CTS")).toBe("2026-12-12T21:40:00");
  });

  it("finds the cheapest feasible chain and honours fixed picks", () => {
    expect(cheapestChain([[toCts], [backEarly, backOk]])?.map((x) => x.id)).toEqual(["a", "c"]);
    expect(cheapestChain([[toCts], [backEarly, backOk]], [undefined, "b"])).toBeNull();
    expect(cheapestChain([[toCts], [backEarly]])).toBeNull();
  });
});

describe("target price presets", () => {
  it("discounts from the current price", () => {
    expect(discountedPrice(36320, 20)).toBe(29056);
    expect(discountedPrice(199.99, 10)).toBe(179);
    expect(discountedPrice(36320, 50)).toBe(18160);
  });

  it("reports how far below the current price a target is", () => {
    expect(percentBelow(36320, "29056")).toBe(20);
    expect(percentBelow(36320, "40000")).toBeNull();
    expect(percentBelow(null, "100")).toBeNull();
    expect(percentBelow(36320, "")).toBeNull();
  });
});
