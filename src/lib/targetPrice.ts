/** 目標價的快速設定：以「目前價格」為基準往下打折 */

export const TARGET_DROP_PRESETS = [10, 20, 30] as const;

/** 目前價格降 pct% 後的目標價（無條件捨去到整數，避免出現 .99 這類難讀的數字） */
export function discountedPrice(base: number, pct: number): number {
  return Math.floor(base * (1 - pct / 100));
}

/** 目標價比目前價格低幾 %（四捨五入到整數）；不是有效數字或高於目前價格時回傳 null */
export function percentBelow(base: number | null, target: string): number | null {
  const value = Number(target);
  if (!base || !target.trim() || !Number.isFinite(value) || value <= 0 || value >= base) {
    return null;
  }
  return Math.round((1 - value / base) * 100);
}
