import { useState, type KeyboardEvent } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { addDays, weekdayNames } from "../../lib/format.ts";

export type DateRange = { from: string | null; to: string | null };

type Props = {
  mode: "single" | "range";
  value: DateRange;
  onChange: (next: DateRange) => void;
  /** 可選的最早日期（含） */
  minDate: string;
  months?: number;
};

const iso = (y: number, m: number, d: number) =>
  `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

function monthMatrix(year: number, month: number): (string | null)[] {
  const first = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const cells: (string | null)[] = Array.from({ length: first }, () => null);
  for (let d = 1; d <= days; d++) cells.push(iso(year, month, d));
  while (cells.length % 7) cells.push(null);
  return cells;
}

/**
 * shadcn 風格日曆：單日或區間（來回）選擇。
 * 區間：第一下選出發、第二下選回程；滑過時預覽區間；方向鍵移動、Enter 選取。
 */
export function Calendar({ mode, value, onChange, minDate, months = 1 }: Props) {
  const { lang, locale, t } = useI18n();
  const anchor = value.from ?? minDate;
  const [view, setView] = useState(() => {
    const d = new Date(`${anchor}T00:00:00`);
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string>(value.from ?? minDate);
  const today = iso(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());

  const shift = (delta: number) =>
    setView((v) => {
      const d = new Date(v.year, v.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });

  const pick = (day: string) => {
    if (day < minDate) return;
    if (mode === "single") {
      onChange({ from: day, to: null });
      return;
    }
    // 尚未選起點、或兩端都已選 → 重新開始；選到比起點早的日期 → 改成新的起點
    if (!value.from || value.to || day < value.from) {
      onChange({ from: day, to: null });
    } else {
      onChange({ from: value.from, to: day });
    }
  };

  const rangeEnd = mode === "range" && value.from && !value.to ? hovered : value.to;
  const inRange = (day: string) =>
    mode === "range" && value.from && rangeEnd && day > value.from && day < rangeEnd;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const next = addDays(focused, step);
    if (next < minDate) return;
    setFocused(next);
    const d = new Date(`${next}T00:00:00`);
    const first = new Date(view.year, view.month, 1);
    const last = new Date(view.year, view.month + months, 0);
    if (d < first) shift(-1);
    if (d > last) shift(1);
    requestAnimationFrame(() =>
      document.querySelector<HTMLButtonElement>(`[data-day="${next}"]`)?.focus(),
    );
  };

  const canGoBack =
    new Date(view.year, view.month, 1) > new Date(`${minDate.slice(0, 7)}-01T00:00:00`);

  return (
    <div className="calendar" onKeyDown={onKeyDown}>
      <div className="calendar__nav">
        <button
          type="button"
          className="calendar__arrow"
          onClick={() => shift(-1)}
          disabled={!canGoBack}
          aria-label={t("cal.prev")}
        >
          ‹
        </button>
        <button
          type="button"
          className="calendar__arrow"
          onClick={() => shift(1)}
          aria-label={t("cal.next")}
        >
          ›
        </button>
      </div>
      <div className="calendar__months">
        {Array.from({ length: months }, (_, i) => {
          const d = new Date(view.year, view.month + i, 1);
          const title = d.toLocaleDateString(locale, { year: "numeric", month: "long" });
          return (
            <div key={title} className="calendar__month">
              <p className="calendar__title">{title}</p>
              <div className="calendar__grid" role="grid" aria-label={title}>
                {weekdayNames(lang).map((w) => (
                  <span key={w} className="calendar__weekday" role="columnheader">
                    {w}
                  </span>
                ))}
                {monthMatrix(d.getFullYear(), d.getMonth()).map((day, idx) => {
                  if (!day) return <span key={`blank-${idx}`} />;
                  const isStart = day === value.from;
                  const isEnd = day === rangeEnd && mode === "range";
                  const isDisabled = day < minDate;
                  const classes = [
                    "calendar__day",
                    day === today && "is-today",
                    (isStart || (isEnd && value.to)) && "is-selected",
                    isEnd && !value.to && "is-preview",
                    inRange(day) && "is-range",
                    isStart && rangeEnd && mode === "range" && "is-start",
                    isEnd && value.from && "is-end",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <button
                      key={day}
                      type="button"
                      role="gridcell"
                      data-day={day}
                      className={classes}
                      disabled={isDisabled}
                      tabIndex={day === focused ? 0 : -1}
                      aria-selected={isStart || day === value.to}
                      aria-current={day === today ? "date" : undefined}
                      onClick={() => pick(day)}
                      onMouseEnter={() => setHovered(day)}
                      onFocus={() => setFocused(day)}
                      data-autofocus={day === focused ? "" : undefined}
                    >
                      {Number(day.slice(8))}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
