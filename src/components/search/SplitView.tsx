import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { dateWithWeekday, dayOffset, formatDuration, localTime } from "../../lib/format.ts";
import { stopsText } from "../../lib/stops.ts";
import type { Leg, RankedOffer, SearchResult } from "../../lib/types.ts";
import { ApiErrorNotice } from "../settings/ApiErrorNotice.tsx";
import { OfferDetail } from "./OfferDetail.tsx";

type Props = {
  legs: Leg[];
  queries: UseQueryResult<SearchResult>[];
  /** 把目前選好的組合（每段一班）整個加入看盤，追蹤合計價格 */
  onWatchCombo: (selections: RankedOffer[]) => void;
};

const PREVIEW = 6;

/** 每段預設選最便宜的那班 */
function cheapestId(result: SearchResult | undefined): string | null {
  if (!result?.offers.length) return null;
  return result.offers.reduce((best, o) =>
    Number(o.offer.total_amount) < Number(best.offer.total_amount) ? o : best,
  ).offer.id;
}

/**
 * 分段購票：每段各自是單程票，可以自由搭配航司（例如去程華航、回程長榮）。
 * 底部固定一條合計列，顯示目前組合的總價與混搭航司數。
 */
export function SplitView({ legs, queries, onWatchCombo }: Props) {
  const { lang, locale, t } = useI18n();
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  // 展開詳細航班資料的選項（以報價 ID 記錄）
  const [openDetail, setOpenDetail] = useState<string | null>(null);

  const selectedFor = (i: number): RankedOffer | undefined => {
    const result = queries[i]?.data;
    const id = picked[i] ?? cheapestId(result);
    return result?.offers.find((o) => o.offer.id === id);
  };
  const selections = legs.map((_, i) => selectedFor(i));
  const isComplete = selections.every(Boolean);
  const currency = queries.find((q) => q.data)?.data?.currency ?? null;
  const total = selections.reduce((sum, s) => sum + (s ? Number(s.offer.total_amount) : 0), 0);
  const airlines = new Set(selections.filter(Boolean).map((s) => s!.offer.airline_code));

  return (
    <section className="split" aria-label={t("split.title")}>
      <div className="split__intro">
        <p>{t("split.intro")}</p>
        <p className="split__warn">{t("split.warn")}</p>
      </div>

      {legs.map((leg, i) => {
        const query = queries[i];
        const offers = query?.data?.offers ?? [];
        const isExpanded = expanded[i] ?? false;
        const visible = isExpanded ? offers : offers.slice(0, PREVIEW);
        const selected = selections[i];
        return (
          <section key={i} className="split__leg" aria-labelledby={`leg-${i}`}>
            <header className="split__leg-head">
              <h3 id={`leg-${i}`}>
                {t("split.legTitle", { n: i + 1, from: leg.origin, to: leg.destination })}
              </h3>
              <span className="split__leg-meta mono">
                {dateWithWeekday(leg.departure_date, lang)}
                {query?.data && ` · ${t("split.results", { n: query.data.total_filtered })}`}
              </span>
            </header>

            {query?.isError && (
              <ApiErrorNotice
                error={query.error}
                prefix={t("split.legFailed", { n: i + 1 })}
                onRetry={() => void query.refetch()}
              />
            )}
            {query?.isPending && <div className="split__skeleton" aria-hidden="true" />}
            {query?.data && offers.length === 0 && (
              <p className="split__empty">{t("split.noneForLeg")}</p>
            )}

            <ul className="split__options" role="radiogroup" aria-labelledby={`leg-${i}`}>
              {visible.map((item) => {
                const isSelected = selected?.offer.id === item.offer.id;
                const s = item.offer.slices[0];
                const offset = dayOffset(s.departing_at, s.arriving_at);
                return (
                  <li
                    key={item.offer.id}
                    className={`split__option ${isSelected ? "is-selected" : ""}`}
                  >
                    <button
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      className="split__pick"
                      onClick={() => setPicked((p) => ({ ...p, [i]: item.offer.id }))}
                    >
                      <span className="split__radio" aria-hidden="true" />
                      <span className="split__airline">
                        {item.offer.airline_logo ? (
                          <img
                            src={item.offer.airline_logo}
                            alt=""
                            width={22}
                            height={22}
                            loading="lazy"
                          />
                        ) : (
                          <span className="offer__logo-fallback mono">
                            {item.offer.airline_code}
                          </span>
                        )}
                        <span className="split__airline-name">{item.offer.airline_name}</span>
                        {item.offer.is_simulated && (
                          <span className="sim-tag" title={t("offer.simulatedHint")}>
                            {t("offer.simulated")}
                          </span>
                        )}
                      </span>
                      <span className="split__times mono">
                        {localTime(s.departing_at)} → {localTime(s.arriving_at)}
                        {offset > 0 && <sup>+{offset}</sup>}
                      </span>
                      <span className="split__info">
                        {formatDuration(s.duration_minutes)} · {stopsText(s, t).text}
                      </span>
                      <span className="split__price mono">
                        {formatPrice(item.offer.total_amount, item.offer.currency, locale)}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost split__watch"
                      aria-expanded={openDetail === item.offer.id}
                      aria-controls={`split-detail-${item.offer.id}`}
                      onClick={() =>
                        setOpenDetail((id) => (id === item.offer.id ? null : item.offer.id))
                      }
                    >
                      {openDetail === item.offer.id ? t("offer.collapse") : t("split.details")}
                    </button>
                    {openDetail === item.offer.id && (
                      <OfferDetail
                        id={`split-detail-${item.offer.id}`}
                        offer={item.offer}
                        className="split__detail"
                      />
                    )}
                  </li>
                );
              })}
            </ul>
            {offers.length > PREVIEW && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setExpanded((e) => ({ ...e, [i]: !isExpanded }))}
              >
                {isExpanded
                  ? t("split.less", { n: PREVIEW })
                  : t("split.more", { n: offers.length })}
              </button>
            )}
          </section>
        );
      })}

      <div className="split__summary" role="status">
        <ol className="split__chosen">
          {legs.map((leg, i) => (
            <li key={i}>
              <span className="mono">
                {leg.origin}→{leg.destination}
              </span>
              <strong>{selections[i]?.offer.airline_code ?? "—"}</strong>
              <span className="mono">
                {selections[i]
                  ? formatPrice(
                      selections[i]!.offer.total_amount,
                      selections[i]!.offer.currency,
                      locale,
                    )
                  : "—"}
              </span>
            </li>
          ))}
        </ol>
        <div className="split__total">
          <span className="label">{t("split.total")}</span>
          <strong className="mono">
            {isComplete && currency ? formatPrice(total, currency, locale) : t("split.pick")}
          </strong>
          {isComplete && airlines.size > 1 && (
            <span className="split__mixed">{t("split.mixed", { n: airlines.size })}</span>
          )}
        </div>
        <div className="split__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setPicked({})}
            disabled={Object.keys(picked).length === 0}
          >
            {t("split.cheapest")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!isComplete}
            onClick={() => onWatchCombo(selections as RankedOffer[])}
          >
            {t("split.watchCombo")}
          </button>
        </div>
      </div>
    </section>
  );
}
