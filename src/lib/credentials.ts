/**
 * 使用者自備的 Duffel API 金鑰。
 * 預設只存在 sessionStorage（關閉分頁即清除）；勾選「記住」才寫入 localStorage。
 */

const STORAGE_KEY = "skyroute.duffel-key";
const KEY_PATTERN = /^duffel_(test|live)_[A-Za-z0-9_-]{10,200}$/;

export type KeyMode = "test" | "live";

export interface StoredKey {
  token: string;
  mode: KeyMode;
  remembered: boolean;
}

type Listener = () => void;
const listeners = new Set<Listener>();
let snapshot: StoredKey | null = read();

function read(): StoredKey | null {
  const remembered = localStorage.getItem(STORAGE_KEY);
  const token = remembered ?? sessionStorage.getItem(STORAGE_KEY);
  const mode = token ? keyMode(token) : null;
  return token && mode ? { token, mode, remembered: remembered !== null } : null;
}

function emit(): void {
  snapshot = read();
  for (const listener of listeners) listener();
}

export function keyMode(token: string): KeyMode | null {
  const match = KEY_PATTERN.exec(token.trim());
  return match ? (match[1] as KeyMode) : null;
}

export function maskKey(token: string): string {
  const tail = token.slice(-4);
  const prefix = token.startsWith("duffel_live_") ? "duffel_live_" : "duffel_test_";
  return `${prefix}••••${tail}`;
}

export function saveKey(token: string, remember: boolean): void {
  const value = token.trim();
  clearStorage();
  (remember ? localStorage : sessionStorage).setItem(STORAGE_KEY, value);
  emit();
}

export function clearKey(): void {
  clearStorage();
  emit();
}

function clearStorage(): void {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}

export function getKey(): StoredKey | null {
  return snapshot;
}

export function subscribeKey(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 其他分頁修改 localStorage 時同步 */
addEventListener("storage", (e) => {
  if (e.key === STORAGE_KEY || e.key === null) emit();
});
