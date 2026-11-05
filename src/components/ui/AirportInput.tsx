import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { useId, useState, type KeyboardEvent } from "react";

import "./shadcn.css";
import { useDebounce } from "../../hooks/useDebounce.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import type { Airport } from "../../lib/types.ts";
import { usePortalContainer } from "./portal.ts";

type Props = {
  label: string;
  value: string;
  onChange: (code: string) => void;
  /** compact：多航段列表用的小字版 */
  size?: "hero" | "compact";
  /** 多航段格線要指定欄位位置時使用 */
  className?: string;
};

const MIN_TERM = 2;

const PinIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="sc-icon">
    <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Z" />
    <circle cx="12" cy="9.5" r="2.5" />
  </svg>
);

const PlaneIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="sc-icon">
    <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2Z" />
  </svg>
);

/**
 * 機場／城市 Combobox（shadcn/ui 的 Popover + Command 組合）：
 * 輸入城市、中英文名或代碼，下拉清單分「城市」「機場」兩組，方向鍵選取、Enter 帶入。
 */
export function AirportInput({ label, value, onChange, size = "hero", className = "" }: Props) {
  const { lang, t } = useI18n();
  const hintId = useId();
  const container = usePortalContainer();
  const [isOpen, setIsOpen] = useState(false);
  const term = useDebounce(value.trim(), 250);
  const suggestions = useQuery({
    queryKey: ["airports", term],
    queryFn: ({ signal }) => api.airports(term, signal),
    enabled: term.length >= MIN_TERM,
    staleTime: 10 * 60_000,
  });

  const nameOf = (a: Airport) => (lang === "zh" ? (a.name_zh ?? a.name_en) : a.name_en);
  const items = suggestions.data ?? [];
  const cities = items.filter((a) => a.kind === "city");
  const airports = items.filter((a) => a.kind !== "city");
  const match = items.find((a) => a.iata_code === value);
  const showList = isOpen && value.trim().length >= MIN_TERM;

  const choose = (code: string) => {
    onChange(code);
    setIsOpen(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") setIsOpen(false);
    // 清單關閉時讓 Enter 照常送出表單（cmdk 預設會攔下 Enter）
    if (e.key === "Enter" && !showList) {
      e.preventDefault();
      (e.target as HTMLInputElement).form?.requestSubmit();
    }
  };

  const renderItem = (a: Airport) => (
    <Command.Item
      key={`${a.kind}-${a.iata_code}`}
      value={`${a.kind}-${a.iata_code}`}
      className="sc-command-item"
      onSelect={() => choose(a.iata_code)}
    >
      {a.kind === "city" ? <PinIcon /> : <PlaneIcon />}
      <span className="sc-command-item__code">{a.iata_code}</span>
      <span className="sc-command-item__name">{nameOf(a)}</span>
      <span className="sc-command-item__meta">{a.country}</span>
    </Command.Item>
  );

  return (
    <Command
      className="board-field-cmd"
      shouldFilter={false}
      loop
      label={label}
      onKeyDown={handleKeyDown}
    >
      <PopoverPrimitive.Root open={showList} onOpenChange={setIsOpen}>
        <PopoverPrimitive.Anchor asChild>
          <label className={`board-field board-field--${size} ${className}`}>
            <span className="board-field__label">{label}</span>
            <Command.Input
              className="board-field__code mono"
              value={value}
              onValueChange={(raw) => {
                onChange(raw.toUpperCase());
                setIsOpen(true);
              }}
              onFocus={() => setIsOpen(true)}
              onBlur={() => setIsOpen(false)}
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="characters"
              required
              maxLength={40}
              aria-describedby={hintId}
            />
            <span id={hintId} className="board-field__hint">
              {match ? nameOf(match) : t("trip.cityHint")}
            </span>
          </label>
        </PopoverPrimitive.Anchor>
        <PopoverPrimitive.Portal container={container}>
          <PopoverPrimitive.Content
            className="sc-popover sc-command"
            align="start"
            sideOffset={8}
            collisionPadding={12}
            // 焦點留在輸入框，才能邊打字邊用方向鍵選
            onOpenAutoFocus={(e) => e.preventDefault()}
            onCloseAutoFocus={(e) => e.preventDefault()}
            // 點清單時不要先觸發輸入框 blur 而關閉
            onMouseDown={(e) => e.preventDefault()}
          >
            <Command.List className="sc-command-list">
              {suggestions.isFetching && items.length === 0 ? (
                <Command.Loading>
                  <div className="sc-command-empty">{t("common.loading")}</div>
                </Command.Loading>
              ) : (
                <Command.Empty className="sc-command-empty">{t("airport.empty")}</Command.Empty>
              )}
              {cities.length > 0 && (
                <Command.Group heading={t("airport.cities")} className="sc-command-group">
                  {cities.map(renderItem)}
                </Command.Group>
              )}
              {airports.length > 0 && (
                <Command.Group heading={t("airport.airports")} className="sc-command-group">
                  {airports.map(renderItem)}
                </Command.Group>
              )}
            </Command.List>
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </Command>
  );
}
