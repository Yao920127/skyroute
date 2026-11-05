import type { Translate } from "../i18n/i18n.ts";

/** 巡檢頻率（分鐘）；null＝每日固定時間（台北 03:00） */
export type PatrolInterval = 5 | 15 | 30 | 60 | 360 | 720;

/** 由慢到快排列，下拉選單照這個順序顯示 */
export const INTERVAL_OPTIONS: readonly (PatrolInterval | null)[] = [null, 720, 360, 60, 30, 15, 5];

/** 使用網站共用金鑰時的最短頻率；更短需要使用者自己的 Duffel 金鑰 */
export const MIN_SHARED_INTERVAL = 30;

const DAILY = "daily";

export function intervalKey(minutes: number | null): string {
  return minutes === null ? DAILY : String(minutes);
}

export function parseIntervalKey(value: string): PatrolInterval | null {
  if (value === DAILY) return null;
  const minutes = Number(value);
  return (INTERVAL_OPTIONS as readonly (number | null)[]).includes(minutes)
    ? (minutes as PatrolInterval)
    : null;
}

export function isIntervalAllowed(minutes: number | null, hasOwnKey: boolean): boolean {
  return minutes === null || hasOwnKey || minutes >= MIN_SHARED_INTERVAL;
}

export function intervalLabel(minutes: number | null, t: Translate): string {
  if (minutes === null) return t("schedule.daily");
  return minutes >= 60
    ? t("schedule.hours", { n: minutes / 60 })
    : t("schedule.minutes", { n: minutes });
}

/** 今天內顯示「14:30」；其他日子加上日期「11/7 03:00」 */
export function nextCheckLabel(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  const time = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
  const isSameDay =
    at.getFullYear() === now.getFullYear() &&
    at.getMonth() === now.getMonth() &&
    at.getDate() === now.getDate();
  return isSameDay ? time : `${at.getMonth() + 1}/${at.getDate()} ${time}`;
}
