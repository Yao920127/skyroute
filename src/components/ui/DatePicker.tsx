import { useMediaQuery } from "../../hooks/useMediaQuery.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { dateWithWeekday, daysBetween } from "../../lib/format.ts";
import { Calendar, type DateRange } from "./Calendar.tsx";
import { Popover } from "./Popover.tsx";

type Props = {
  mode: "single" | "range";
  value: DateRange;
  onChange: (next: DateRange) => void;
  minDate: string;
  labels: { from: string; to?: string };
  tone?: "dark" | "light";
};

/** 日期欄位：按鈕顯示已選日期，點開為日曆（電腦兩個月、手機一個月） */
export function DatePicker({ mode, value, onChange, minDate, labels, tone = "dark" }: Props) {
  const { lang, t } = useI18n();
  const isWide = useMediaQuery("(min-width: 900px)");
  const months = mode === "range" && isWide ? 2 : 1;
  const text = (d: string | null, placeholder: string) =>
    d ? dateWithWeekday(d, lang) : placeholder;

  return (
    <Popover
      label={mode === "range" ? t("trip.pickDates") : t("trip.date")}
      className={`datepicker datepicker--${tone}`}
      trigger={(props) => (
        <button type="button" className={`datefield datefield--${mode}`} {...props}>
          <span className="datefield__part">
            <span className="datefield__label">{labels.from}</span>
            <span className="datefield__value">{text(value.from, t("cal.selectStart"))}</span>
          </span>
          {mode === "range" && (
            <span className="datefield__part">
              <span className="datefield__label">{labels.to}</span>
              <span className="datefield__value">{text(value.to, t("cal.selectEnd"))}</span>
            </span>
          )}
        </button>
      )}
    >
      {(close) => (
        <div className="datepicker__body">
          <p className="datepicker__hint">
            {mode === "range"
              ? value.from && !value.to
                ? t("cal.selectEnd")
                : value.from && value.to
                  ? `${text(value.from, "")} → ${text(value.to, "")} · ${t("cal.nights", { n: daysBetween(value.from, value.to) })}`
                  : t("cal.selectStart")
              : t("cal.selectStart")}
          </p>
          <Calendar
            mode={mode}
            value={value}
            minDate={minDate}
            months={months}
            onChange={(next) => {
              onChange(next);
              // 單日選完、或區間兩端都選好就自動關閉
              if (mode === "single" || (next.from && next.to)) close();
            }}
          />
          <div className="datepicker__foot">
            <button type="button" className="btn btn--ghost" onClick={close}>
              {t("common.done")}
            </button>
          </div>
        </div>
      )}
    </Popover>
  );
}
