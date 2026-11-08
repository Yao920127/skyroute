import { useEffect, useRef, useState } from "react";

import "./layout.css";
import type { View } from "../../hooks/useUrlState.ts";
import { setLang, useI18n, type Lang } from "../../i18n/i18n.ts";
import type { MessageKey } from "../../i18n/messages.ts";
import { CURRENCIES, setCurrency, useCurrency, type Currency } from "../../lib/currency.ts";
import { setThemeMode, useThemeMode, type ThemeMode } from "../../lib/theme.ts";
import { AccountMenu } from "../auth/AccountMenu.tsx";
import { Select } from "../ui/Select.tsx";

const CURRENCY_OPTIONS = CURRENCIES.map((c) => ({ value: c, label: c }));

type Props = {
  view: View;
  trackingCount: number;
  keyLabel: string;
  keyTone: "own" | "missing" | "server";
  onNavigate: (view: View) => void;
  onOpenKey: () => void;
};

export const NAV_ITEMS: { id: Exclude<View, "home">; labelKey: MessageKey }[] = [
  { id: "explore", labelKey: "nav.explore" },
  { id: "matrix", labelKey: "nav.matrix" },
  { id: "board", labelKey: "nav.board" },
];

/** Duffel 串接指南（public/apidocs.html），一律在新分頁開啟 */
export const API_GUIDE_URL = "/apidocs";

/** 產品簡報（public/presentation.html，由 nginx 以 /presentation 提供），一律在新分頁開啟 */
export const PRESENTATION_URL = "/presentation";

/** 系統架構圖（floorplan 匯出版，Railway 的 floorplan 服務），一律在新分頁開啟 */
export const ARCHITECTURE_MAP_URL = "https://floorplan-skyroute.up.railway.app";

const LANGS: { id: Lang; label: string }[] = [
  { id: "zh", label: "中" },
  { id: "en", label: "EN" },
];

const THEMES: { id: ThemeMode; labelKey: MessageKey }[] = [
  { id: "system", labelKey: "theme.system" },
  { id: "light", labelKey: "theme.light" },
  { id: "dark", labelKey: "theme.dark" },
];

/** 細線圖示：系統（螢幕）、亮色（太陽）、暗色（月亮） */
function ThemeIcon({ mode }: { mode: ThemeMode }) {
  return (
    <svg className="prefs__icon" viewBox="0 0 24 24" aria-hidden="true">
      {mode === "system" && (
        <>
          <rect x="3" y="4" width="18" height="12" rx="2" />
          <path d="M8 20h8M12 16v4" />
        </>
      )}
      {mode === "light" && (
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </>
      )}
      {mode === "dark" && <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />}
    </svg>
  );
}

/** 配色切換：系統／亮色／暗色 */
function ThemeSwitch() {
  const { t } = useI18n();
  const mode = useThemeMode();
  return (
    <div className="prefs__seg prefs__theme" role="radiogroup" aria-label={t("common.theme")}>
      {THEMES.map((item) => (
        <button
          key={item.id}
          type="button"
          role="radio"
          aria-checked={mode === item.id}
          title={t(item.labelKey)}
          onClick={() => setThemeMode(item.id)}
        >
          <ThemeIcon mode={item.id} />
          <span className="visually-hidden">{t(item.labelKey)}</span>
        </button>
      ))}
    </div>
  );
}

/** 語言、配色與幣別（導覽列與手機選單共用） */
function Preferences({ variant }: { variant: "bar" | "menu" }) {
  const { lang, t } = useI18n();
  const currency = useCurrency();
  return (
    <div className={`prefs prefs--${variant}`}>
      <div className="prefs__seg prefs__lang" role="radiogroup" aria-label={t("common.lang")}>
        {LANGS.map((l) => (
          <button
            key={l.id}
            type="button"
            role="radio"
            aria-checked={lang === l.id}
            onClick={() => setLang(l.id)}
          >
            {l.label}
          </button>
        ))}
      </div>
      <ThemeSwitch />
      <Select
        size="sm"
        className="prefs__currency"
        value={currency}
        onValueChange={(c) => setCurrency(c as Currency)}
        ariaLabel={t("common.currency")}
        options={CURRENCY_OPTIONS}
      />
    </div>
  );
}

/**
 * 頂部導覽列（所有裝置都在頂端）：
 * - 電腦／平板：品牌｜分頁｜語言・幣別・金鑰
 * - 手機：品牌｜金鑰｜選單按鈕，分頁與偏好設定收進下拉選單
 */
export function Navbar({ view, trackingCount, keyLabel, keyTone, onNavigate, onOpenKey }: Props) {
  const { t } = useI18n();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setIsMenuOpen(false);
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Element;
      // 幣別 Select 的選單掛在 <body>，點它不算點到選單外面
      if (target.closest?.("[data-radix-popper-content-wrapper]")) return;
      if (!menuRef.current?.contains(target)) setIsMenuOpen(false);
    };
    addEventListener("keydown", onKey);
    addEventListener("pointerdown", onPointer);
    return () => {
      removeEventListener("keydown", onKey);
      removeEventListener("pointerdown", onPointer);
    };
  }, [isMenuOpen]);

  const go = (target: View) => {
    setIsMenuOpen(false);
    onNavigate(target);
  };

  const count = (id: View) =>
    id === "board" && trackingCount > 0 ? (
      <span className="navbar__count mono">{trackingCount}</span>
    ) : null;

  return (
    <header className="navbar">
      <div className="navbar__inner" ref={menuRef}>
        <a
          href="/"
          className="brand"
          aria-current={view === "home" ? "page" : undefined}
          onClick={(e) => {
            e.preventDefault();
            go("home");
          }}
        >
          <span className="brand__mark" aria-hidden="true">
            ↗
          </span>
          <span className="brand__name">SkyRoute</span>
        </a>

        <nav className="navbar__tabs" aria-label={t("nav.home")}>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="navbar__tab"
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => go(item.id)}
            >
              {t(item.labelKey)}
              {count(item.id)}
            </button>
          ))}
          <a
            className="navbar__tab navbar__tab--external"
            href={API_GUIDE_URL}
            target="_blank"
            rel="noopener"
          >
            <span className="navbar__ext-full">{t("nav.apiGuide")}</span>
            <span className="navbar__ext-short" aria-hidden="true">
              API
            </span>
            <span className="navbar__ext-arrow" aria-hidden="true">
              ↗
            </span>
            <span className="visually-hidden">{t("common.newTab")}</span>
          </a>
        </nav>

        <div className="navbar__end">
          <Preferences variant="bar" />
          <button
            type="button"
            className={`keychip is-${keyTone}`}
            onClick={onOpenKey}
            aria-label={t("nav.keyAria", { label: keyLabel })}
          >
            <i aria-hidden="true" />
            <span className="mono">{keyLabel}</span>
          </button>
          <AccountMenu onOpenKey={onOpenKey} />
          <button
            type="button"
            className="navbar__menu-btn"
            aria-expanded={isMenuOpen}
            aria-controls="navbar-menu"
            aria-label={isMenuOpen ? t("nav.menuClose") : t("nav.menuOpen")}
            onClick={() => setIsMenuOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {isMenuOpen ? (
                <path d="M6 6l12 12M18 6L6 18" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h16" />
              )}
            </svg>
            {!isMenuOpen && trackingCount > 0 && (
              <span className="navbar__dot" aria-hidden="true" />
            )}
          </button>
        </div>

        {isMenuOpen && (
          <div id="navbar-menu" className="navbar__menu">
            <nav aria-label={t("nav.home")}>
              {[{ id: "home" as const, labelKey: "nav.home" as const }, ...NAV_ITEMS].map(
                (item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="navbar__menu-item"
                    aria-current={view === item.id ? "page" : undefined}
                    onClick={() => go(item.id)}
                  >
                    <span>{t(item.labelKey)}</span>
                    {count(item.id)}
                  </button>
                ),
              )}
              <a
                className="navbar__menu-item navbar__menu-item--external"
                href={API_GUIDE_URL}
                target="_blank"
                rel="noopener"
                onClick={() => setIsMenuOpen(false)}
              >
                <span>{t("nav.apiGuide")}</span>
                <span aria-hidden="true">↗</span>
                <span className="visually-hidden">{t("common.newTab")}</span>
              </a>
            </nav>
            <div className="navbar__menu-prefs">
              <span className="label">{t("nav.settings")}</span>
              <Preferences variant="menu" />
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
