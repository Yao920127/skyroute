import type { Leg } from "./types.ts";

type WatchLike = {
  origin: string;
  destination: string;
  departure_date: string;
  return_date: string | null;
  extra_legs?: Leg[];
};

/** 一筆追蹤的所有航段：第 1 段＋（來回的回程）＋第 2 段以後 */
export function watchLegs(w: WatchLike): Leg[] {
  const first = { origin: w.origin, destination: w.destination, departure_date: w.departure_date };
  const back = w.return_date
    ? [{ origin: w.destination, destination: w.origin, departure_date: w.return_date }]
    : [];
  return [first, ...back, ...(w.extra_legs ?? [])];
}

/**
 * 路線文字：首尾相接時串成「TPE → BKK → TPE」；
 * 不相接（例如 台北→倫敦、巴黎→台北）時分段列出「TPE → LON · PAR → TPE」。
 */
export function routeText(legs: Leg[], arrow = "→"): string {
  const isChained = legs.every((leg, i) => i === 0 || leg.origin === legs[i - 1].destination);
  if (isChained) {
    return [legs[0].origin, ...legs.map((l) => l.destination)].join(` ${arrow} `);
  }
  return legs.map((l) => `${l.origin} ${arrow} ${l.destination}`).join(" · ");
}

/** 分段購票各段指定的航司，例如「CZ + BR」；全部不限時回傳 null */
export function legAirlinesText(airlines: (string | null)[]): string | null {
  return airlines.some(Boolean) ? airlines.map((a) => a ?? "—").join(" + ") : null;
}
