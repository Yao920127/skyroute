import { useI18n } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { formatPct, relativeTime, trendOf } from "../../lib/format.ts";
import type { Watchlist } from "../../lib/types.ts";
import { Sparkline } from "./Sparkline.tsx";

type Props = {
  watch: Watchlist;
  isSelected: boolean;
  onSelect: () => void;
};

export function WatchCard({ watch, isSelected, onSelect }: Props) {
  const { locale, t } = useI18n();
  const { stats } = watch;
  // 新追蹤以設定的幣別記錄；舊資料沿用航空公司原始幣別
  const currency = watch.currency ?? stats.currency;
  const money = (v: string | number | null) => formatPrice(v, currency, locale);
  const dayTrend = trendOf(stats.day_change);
  const weekTrend = trendOf(stats.week_change_pct);
  const hitTarget =
    watch.target_price !== null &&
    stats.latest_price !== null &&
    Number(stats.latest_price) <= Number(watch.target_price);

  return (
    <li>
      <button
        type="button"
        className={`ticker ticker--${watch.status.toLowerCase()}`}
        aria-pressed={isSelected}
        onClick={onSelect}
      >
        <span className="ticker__route mono">
          {watch.origin}
          <i aria-hidden="true">⇢</i>
          {watch.destination}
        </span>
        <span className="ticker__label">
          {watch.label ??
            `${watch.departure_date}${watch.return_date ? ` ⇄ ${watch.return_date.slice(5)}` : ""}`}
          {watch.preferred_airline && <b className="mono"> · {watch.preferred_airline}</b>}
        </span>

        <span className="ticker__price mono">{money(stats.latest_price)}</span>

        <span className={`ticker__change mono trend--${dayTrend}`}>
          {stats.day_change !== null ? (
            <>
              {dayTrend === "down" ? "▼" : dayTrend === "up" ? "▲" : "■"}{" "}
              {money(Math.abs(Number(stats.day_change)))} ({formatPct(stats.day_change_pct)})
            </>
          ) : (
            `${t("card.yesterday")} —`
          )}
        </span>

        <span className={`ticker__week mono trend--${weekTrend}`}>
          {t("card.week")} {formatPct(stats.week_change_pct)}
        </span>
        <span className="ticker__low mono">
          {t("card.weekLow")} {money(stats.week_low)}
        </span>

        <Sparkline values={stats.sparkline.map(Number)} className="ticker__spark" />

        <span className="ticker__foot">
          <span className={`status status--${watch.status.toLowerCase()}`}>
            {t(`status.${watch.status}`)}
          </span>
          {hitTarget && <span className="status status--hit">{t("status.hit")}</span>}
          {watch.uses_own_key && <span className="status status--own">{t("status.ownKey")}</span>}
          <span className="ticker__time">{relativeTime(stats.last_checked_at, t)}</span>
        </span>
      </button>
    </li>
  );
}
