/**
 * 價格走勢方向：卡片的迷你走勢線與詳情的大走勢圖共用，兩邊顏色一定一致。
 * 降價對旅客是好消息 → 綠；漲價 → 紅；持平 → 灰。
 */

import type { ResolvedTheme } from "./theme.ts";

export type PriceTrend = "down" | "up" | "flat" | "none";

export function priceTrend(values: number[]): PriceTrend {
  if (values.length < 2) return "none";
  const first = values[0];
  const last = values[values.length - 1];
  return last < first ? "down" : last > first ? "up" : "flat";
}

/** CSS 用（對應 tokens.css） */
export const TREND_VAR: Record<PriceTrend, string> = {
  down: "var(--gain)",
  up: "var(--loss)",
  flat: "var(--muted)",
  none: "var(--muted)",
};

/** canvas 讀不到 CSS 變數，用同一組色碼（--gain、--loss／--error、--muted，亮暗各一組） */
const TREND_HEX: Record<ResolvedTheme, Record<PriceTrend, string>> = {
  light: { down: "#0b7a5c", up: "#b30000", flat: "#93939f", none: "#93939f" },
  dark: { down: "#3cc79a", up: "#ff6b66", flat: "#8a8a96", none: "#8a8a96" },
};

export function trendHex(trend: PriceTrend, theme: ResolvedTheme): string {
  return TREND_HEX[theme][trend];
}
