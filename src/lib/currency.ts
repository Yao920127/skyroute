import { useSyncExternalStore } from "react";

/** 支援的顯示幣別（與後端 app/services/fx.py 一致） */
export const CURRENCIES = [
  "TWD",
  "USD",
  "EUR",
  "GBP",
  "JPY",
  "KRW",
  "HKD",
  "SGD",
  "CNY",
  "THB",
  "AUD",
  "CAD",
] as const;
export type Currency = (typeof CURRENCIES)[number];

const STORAGE_KEY = "skyroute.currency";
const DEFAULT_CURRENCY: Currency = "TWD";
const listeners = new Set<() => void>();

function isCurrency(value: string | null): value is Currency {
  return value !== null && (CURRENCIES as readonly string[]).includes(value);
}

let current: Currency = (() => {
  if (typeof localStorage === "undefined") return DEFAULT_CURRENCY;
  const saved = localStorage.getItem(STORAGE_KEY);
  return isCurrency(saved) ? saved : DEFAULT_CURRENCY;
})();

export function getCurrency(): Currency {
  return current;
}

export function setCurrency(next: Currency): void {
  current = next;
  if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEY, next);
  for (const listener of listeners) listener();
}

export function useCurrency(): Currency {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getCurrency,
    getCurrency,
  );
}

const ZERO_DECIMAL = new Set(["JPY", "KRW", "TWD"]);

/** 各幣別使用不會混淆的符號（中文語系下 Intl 會把台幣、美金都顯示成 $） */
const SYMBOLS: Record<string, string> = {
  TWD: "NT$",
  USD: "US$",
  HKD: "HK$",
  SGD: "S$",
  AUD: "A$",
  CAD: "C$",
  CNY: "CN¥",
  JPY: "¥",
  KRW: "₩",
  EUR: "€",
  GBP: "£",
  THB: "฿",
};

/** 依語系與幣別格式化金額；台幣、日圓、韓元不顯示小數 */
export function formatPrice(
  amount: string | number | null | undefined,
  currency: string | null | undefined,
  locale: string,
): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const value = typeof amount === "string" ? Number(amount) : amount;
  if (!currency) return value.toLocaleString(locale, { maximumFractionDigits: 2 });
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  const number = Math.abs(value).toLocaleString(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const symbol = SYMBOLS[currency] ?? `${currency} `;
  return `${value < 0 ? "−" : ""}${symbol}${number}`;
}

/** 熱力圖等空間有限處使用的精簡格式（不帶幣別符號） */
export function formatCompact(
  amount: string | number | null | undefined,
  currency: string,
  locale: string,
) {
  if (amount === null || amount === undefined) return "—";
  const value = Number(amount);
  const digits = ZERO_DECIMAL.has(currency) ? 0 : value >= 1000 ? 0 : 2;
  return value.toLocaleString(locale, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}
