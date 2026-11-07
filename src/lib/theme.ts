import { useSyncExternalStore } from "react";

/**
 * 配色偏好：系統（跟隨作業系統）、亮色、暗色。
 * 偏好存在 localStorage；實際套用的亮／暗寫在 <html data-theme>，CSS token 依此切換。
 * public/theme-init.js 在畫面繪製前先套用一次，避免開頁閃白（兩邊的鍵名與規則必須一致）。
 */

export const THEME_MODES = ["system", "light", "dark"] as const;
export type ThemeMode = (typeof THEME_MODES)[number];
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "skyroute.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

/** 瀏覽器分頁列顏色（與 tokens.css 的 --canvas 一致） */
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: "#ffffff",
  dark: "#111214",
};

const hasDom = typeof window !== "undefined" && typeof document !== "undefined";
const listeners = new Set<() => void>();

export function parseThemeMode(value: unknown): ThemeMode {
  return (THEME_MODES as readonly unknown[]).includes(value) ? (value as ThemeMode) : "system";
}

export function resolveTheme(mode: ThemeMode, prefersDark: boolean): ResolvedTheme {
  if (mode === "system") return prefersDark ? "dark" : "light";
  return mode;
}

function readSavedMode(): ThemeMode {
  try {
    return parseThemeMode(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return hasDom && typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

let mode: ThemeMode = hasDom ? readSavedMode() : "system";
let resolved: ResolvedTheme = resolveTheme(mode, systemPrefersDark());

function applyToDocument(theme: ResolvedTheme): void {
  if (!hasDom) return;
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
}

function update(): void {
  const next = resolveTheme(mode, systemPrefersDark());
  const changed = next !== resolved;
  resolved = next;
  applyToDocument(resolved);
  if (changed) for (const listener of listeners) listener();
}

if (hasDom) {
  applyToDocument(resolved);
  if (typeof window.matchMedia === "function") {
    // 只有「系統」模式需要跟著作業系統切換；其他模式 resolveTheme 不看這個值
    window.matchMedia(DARK_QUERY).addEventListener("change", update);
  }
}

export function getThemeMode(): ThemeMode {
  return mode;
}

export function getResolvedTheme(): ResolvedTheme {
  return resolved;
}

export function setThemeMode(next: ThemeMode): void {
  mode = next;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // 無痕視窗或封鎖儲存時仍可切換，只是不會記住
  }
  update();
  for (const listener of listeners) listener();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useThemeMode(): ThemeMode {
  return useSyncExternalStore(subscribe, getThemeMode, () => "system" as ThemeMode);
}

/** 實際套用的亮／暗（canvas 圖表讀不到 CSS 變數，需要這個值決定配色） */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, getResolvedTheme, () => "light" as ResolvedTheme);
}
