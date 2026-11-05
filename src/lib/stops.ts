import type { Translate } from "../i18n/i18n.ts";
import type { Slice } from "./types.ts";

/** 同一段行程中所有中途經停（不換機）的機場 */
export function stopAirports(slice: Slice): string[] {
  return slice.segments.flatMap((seg) => (seg.stops ?? []).map((stop) => stop.airport));
}

/**
 * 行程類型文字：
 * - 直飛：不轉機、不經停
 * - 直達・經停 BKK：同班機中途落地（例如 BR67），不算直飛
 * - 1 次轉機 · HKG（· 經停 BKK）
 */
export function stopsText(slice: Slice, t: Translate): { text: string; isNonstop: boolean } {
  const stops = stopAirports(slice);
  if (slice.stops === 0) {
    return stops.length === 0
      ? { text: t("offer.direct"), isNonstop: true }
      : { text: t("offer.directVia", { airports: stops.join(", ") }), isNonstop: false };
  }
  const via = slice.layovers.map((l) => l.airport).join(", ");
  const also = stops.length ? t("offer.alsoStops", { airports: stops.join(", ") }) : "";
  return { text: `${t("offer.stops", { n: slice.stops })} · ${via}${also}`, isNonstop: false };
}
