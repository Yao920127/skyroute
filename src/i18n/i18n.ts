import { useSyncExternalStore } from "react";

import { en, zh, type MessageKey } from "./messages.ts";

export type Lang = "zh" | "en";
export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

const STORAGE_KEY = "skyroute.lang";
const DICTS: Record<Lang, Record<MessageKey, string>> = { zh, en };
const listeners = new Set<() => void>();

const hasDom = typeof window !== "undefined" && typeof localStorage !== "undefined";

function detect(): Lang {
  if (!hasDom) return "zh";
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "zh" || saved === "en") return saved;
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function applyDocumentLang(lang: Lang): void {
  if (hasDom) document.documentElement.lang = lang === "zh" ? "zh-Hant-TW" : "en";
}

let current: Lang = detect();
applyDocumentLang(current);

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  if (hasDom) localStorage.setItem(STORAGE_KEY, lang);
  applyDocumentLang(lang);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 取代 {name} 佔位符 */
export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function translate(lang: Lang, key: MessageKey, vars?: Record<string, string | number>) {
  return interpolate(DICTS[lang][key], vars);
}

/** 非 React 程式（例如 API 錯誤訊息）使用目前語系翻譯 */
export const t: Translate = (key, vars) => translate(current, key, vars);

export function useI18n(): { lang: Lang; t: Translate; locale: string } {
  const lang = useSyncExternalStore(subscribe, getLang, getLang);
  return {
    lang,
    locale: lang === "zh" ? "zh-TW" : "en-US",
    t: (key, vars) => translate(lang, key, vars),
  };
}
