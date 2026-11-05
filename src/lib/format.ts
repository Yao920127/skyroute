import type { Lang, Translate } from "../i18n/i18n.ts";

const MINUTES_PER_HOUR = 60;
const DAY_MS = 86_400_000;

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / MINUTES_PER_HOUR);
  const m = minutes % MINUTES_PER_HOUR;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${String(m).padStart(2, "0")}m`;
}

/** Duffel 回傳的是當地時間字串（無時區），直接擷取時分避免被瀏覽器時區換算。 */
export function localTime(iso: string): string {
  return iso.slice(11, 16);
}

export function localDate(iso: string): string {
  return iso.slice(5, 10).replace("-", "/");
}

/** 抵達日比出發日多幾天（+1、+2）。 */
export function dayOffset(departIso: string, arriveIso: string): number {
  const a = Date.parse(departIso.slice(0, 10));
  const b = Date.parse(arriveIso.slice(0, 10));
  return Math.round((b - a) / DAY_MS);
}

/** 不帶幣別的數字（圖表座標軸等） */
export function formatNumber(amount: string | number | null | undefined, locale = "en-US") {
  if (amount === null || amount === undefined) return "—";
  const value = typeof amount === "string" ? Number(amount) : amount;
  return value.toLocaleString(locale, {
    minimumFractionDigits: value % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

export function formatPct(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
  return `${sign}${Math.abs(n).toFixed(2)}%`;
}

export type Trend = "down" | "up" | "flat" | "none";

/** 機票價格下跌對使用者是好消息，因此 down 會以「利多」色呈現。 */
export function trendOf(value: string | number | null | undefined): Trend {
  if (value === null || value === undefined) return "none";
  const n = Number(value);
  if (n < 0) return "down";
  if (n > 0) return "up";
  return "flat";
}

const WEEKDAYS: Record<Lang, string[]> = {
  zh: ["日", "一", "二", "三", "四", "五", "六"],
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
};

export function weekdayNames(lang: Lang): string[] {
  return WEEKDAYS[lang];
}

export function shortDateLabel(
  isoDate: string,
  lang: Lang = "zh",
): { md: string; weekday: string } {
  const d = new Date(`${isoDate}T00:00:00`);
  return { md: `${d.getMonth() + 1}/${d.getDate()}`, weekday: WEEKDAYS[lang][d.getDay()] };
}

/** 「12/20（日）」或「Sun 12/20」 */
export function dateWithWeekday(isoDate: string, lang: Lang): string {
  const { md, weekday } = shortDateLabel(isoDate, lang);
  return lang === "zh" ? `${md}（${weekday}）` : `${weekday} ${md}`;
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / DAY_MS);
}

export function relativeTime(iso: string | null, t: Translate, now = Date.now()): string {
  if (!iso) return t("time.never");
  const diff = Math.max(0, now - Date.parse(iso));
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return t("time.justNow");
  if (minutes < 60) return t("time.minutes", { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("time.hours", { n: hours });
  return t("time.days", { n: Math.floor(hours / 24) });
}

export const CABINS = ["economy", "premium_economy", "business", "first"] as const;

export function cabinLabel(cabin: string, t: Translate): string {
  const key = `cabin.${cabin}` as const;
  return (CABINS as readonly string[]).includes(cabin) ? t(key as "cabin.economy") : cabin;
}
