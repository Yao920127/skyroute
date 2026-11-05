import type { MatrixCell } from "./types.ts";

export interface HeatScale {
  min: number;
  max: number;
  /** 0 = 最便宜、1 = 最貴；只有一個價格時回傳 0。 */
  position: (price: number) => number;
}

export function buildScale(cells: MatrixCell[]): HeatScale | null {
  const prices = cells.filter((c) => c.status === "ok" && c.price).map((c) => Number(c.price));
  if (prices.length === 0) return null;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min;
  return {
    min,
    max,
    position: (price) => (span === 0 ? 0 : (price - min) / span),
  };
}

/** 便宜 → 深綠，中段 → 石色，昂貴 → 珊瑚，讓極端值一眼可辨。 */
export function heatColor(t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  if (clamped <= 0.5) {
    const k = clamped / 0.5;
    return `color-mix(in oklch, var(--heat-low) ${Math.round((1 - k) * 100)}%, var(--heat-mid))`;
  }
  const k = (clamped - 0.5) / 0.5;
  return `color-mix(in oklch, var(--heat-high) ${Math.round(k * 100)}%, var(--heat-mid))`;
}

const LIGHT_TEXT_BELOW = 0.3;

/** 深綠端的格子背景較暗，改用白字確保對比。 */
export function heatInk(t: number): string {
  return t < LIGHT_TEXT_BELOW ? "var(--on-dark)" : "var(--ink)";
}

export function cellKey(dep: string, ret: string | null): string {
  return `${dep}|${ret ?? "-"}`;
}
