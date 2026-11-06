/**
 * 分段購票的銜接規則（與後端 domain/connections.py 相同）：
 * 下一段要在上一段抵達後留足時間才能起飛——同一機場至少 2 小時、換機場至少 4 小時
 * （分段購票是獨立機票，要重新報到、託運行李）。
 * Duffel 的時間是不含時區的當地時間；銜接點在同一城市時可以直接相減。
 */

export const SAME_AIRPORT_MIN_GAP = 120;
export const OTHER_AIRPORT_MIN_GAP = 240;

export type LegFlight = {
  id: string;
  price: number;
  origin: string;
  destination: string;
  departing_at: string;
  arriving_at: string;
};

/** 不含時區的當地時間 → 分鐘數（當成 UTC 解析，避免受瀏覽器時區影響） */
function minutesOf(iso: string): number {
  return Date.parse(`${iso.slice(0, 19)}Z`) / 60_000;
}

export function minGapMinutes(arrivalAirport: string, departureAirport: string): number {
  return arrivalAirport === departureAirport ? SAME_AIRPORT_MIN_GAP : OTHER_AIRPORT_MIN_GAP;
}

export function connects(previous: LegFlight, following: LegFlight): boolean {
  const gap = minutesOf(following.departing_at) - minutesOf(previous.arriving_at);
  return gap >= minGapMinutes(previous.destination, following.origin);
}

/** 上一段抵達後，這一段最早可以起飛的當地時間（ISO，不含時區） */
export function earliestDeparture(previous: LegFlight, nextOrigin: string): string {
  const at = minutesOf(previous.arriving_at) + minGapMinutes(previous.destination, nextOrigin);
  return new Date(at * 60_000).toISOString().slice(0, 19);
}

/**
 * 每段挑一班、前後都銜接得上，且總價最低（動態規劃，不是各段各自挑最便宜）。
 * fixed[k] 有值時該段只能用那一班（使用者手動選的）。沒有可行組合時回傳 null。
 */
export function cheapestChain(
  options: LegFlight[][],
  fixed: (string | undefined)[] = [],
): LegFlight[] | null {
  const legs = options.map((leg, k) => (fixed[k] ? leg.filter((o) => o.id === fixed[k]) : leg));
  if (legs.length === 0 || legs.some((leg) => leg.length === 0)) return null;
  let costs = legs[0].map((o) => o.price);
  const parents: (number | null)[][] = [legs[0].map(() => null)];
  for (let k = 1; k < legs.length; k++) {
    const nextCosts: number[] = [];
    const nextParents: (number | null)[] = [];
    for (const flight of legs[k]) {
      let best = Infinity;
      let parent: number | null = null;
      legs[k - 1].forEach((previous, j) => {
        if (costs[j] < best && connects(previous, flight)) {
          best = costs[j];
          parent = j;
        }
      });
      nextCosts.push(best + flight.price);
      nextParents.push(parent);
    }
    costs = nextCosts;
    parents.push(nextParents);
  }
  let end = 0;
  costs.forEach((c, j) => {
    if (c < costs[end]) end = j;
  });
  if (!Number.isFinite(costs[end])) return null;
  const chain: LegFlight[] = [];
  let index: number | null = end;
  for (let k = legs.length - 1; k >= 0 && index !== null; k--) {
    chain.unshift(legs[k][index]);
    index = parents[k][index];
  }
  return chain;
}
