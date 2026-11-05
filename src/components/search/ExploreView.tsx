import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import "./explore.css";
import { useApiKey } from "../../hooks/useApiKey.ts";
import { useIsCompact } from "../../hooks/useMediaQuery.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { maskKey } from "../../lib/credentials.ts";
import { useCurrency } from "../../lib/currency.ts";
import { relativeTime } from "../../lib/format.ts";
import { DEFAULT_FILTERS, legsOf, oneWayLeg } from "../../lib/searchState.ts";
import type {
  Leg,
  RankedOffer,
  SearchResult,
  SearchState,
  SortKey,
  TicketMode,
} from "../../lib/types.ts";
import { ApiErrorNotice } from "../settings/ApiErrorNotice.tsx";
import { Sheet } from "../ui/Sheet.tsx";
import type { WatchDraft } from "../watch/WatchForm.tsx";
import { FilterPanel } from "./FilterPanel.tsx";
import { OfferRow } from "./OfferRow.tsx";
import { SplitView } from "./SplitView.tsx";

type Props = {
  state: SearchState;
  enabled: boolean;
  onChange: (next: SearchState) => void;
  onWatch: (draft: WatchDraft) => void;
};

const SORTS: SortKey[] = ["price", "cost", "duration", "departure", "arrival", "airline"];
const SPLIT_LIMIT = 40;

/** 分段購票時把各段結果合併，給篩選面板計算滑桿範圍、樞紐與航司選項 */
function mergeResults(results: SearchResult[]): SearchResult | undefined {
  if (!results.length) return undefined;
  const nums = (pick: (r: SearchResult) => string[]) => results.flatMap(pick).map(Number);
  const range = (values: number[]) =>
    values.length ? { min: String(Math.min(...values)), max: String(Math.max(...values)) } : null;
  const airlines = new Map(results.flatMap((r) => r.airlines).map((a) => [a.code, a]));
  return {
    ...results[0],
    total_raw: results.reduce((n, r) => n + r.total_raw, 0),
    total_filtered: results.reduce((n, r) => n + r.total_filtered, 0),
    hubs: [...new Set(results.flatMap((r) => r.hubs))].sort(),
    airlines: [...airlines.values()],
    price_bounds: range(
      nums((r) => (r.price_bounds ? [r.price_bounds.min, r.price_bounds.max] : [])),
    ),
    duration_bounds: range(
      nums((r) => (r.duration_bounds ? [r.duration_bounds.min, r.duration_bounds.max] : [])),
    ),
    offers: [],
  };
}

export function ExploreView({ state, enabled, onChange, onWatch }: Props) {
  const { t } = useI18n();
  const apiKey = useApiKey();
  const currency = useCurrency();
  const isCompact = useIsCompact();
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const keyTag = apiKey ? maskKey(apiKey.token) : "server";

  // 票價範圍是以舊幣別設定的數字，換幣別後清除，避免誤把台幣上限當成美金使用
  const previousCurrency = useRef(currency);
  useEffect(() => {
    if (previousCurrency.current === currency) return;
    previousCurrency.current = currency;
    if (state.price_min !== null || state.price_max !== null) {
      onChange({ ...state, price_min: null, price_max: null });
    }
  }, [currency, state, onChange]);

  const legs = legsOf(state);
  const canSplit = legs.length > 1;
  const mode: TicketMode = canSplit ? state.mode : "combined";

  // 換金鑰或幣別就是不同的資料來源，需重新查詢
  const combined = useQuery({
    queryKey: ["search", state, keyTag, currency],
    queryFn: () => api.search(state, currency),
    enabled: enabled && mode === "combined",
    placeholderData: keepPreviousData,
  });
  const legQueries = useQueries({
    queries: legs.map((leg) => {
      const legState = oneWayLeg(state, leg);
      return {
        queryKey: ["search", legState, keyTag, currency, SPLIT_LIMIT],
        queryFn: () => api.search(legState, currency, SPLIT_LIMIT),
        enabled: enabled && mode === "split",
        placeholderData: keepPreviousData,
      };
    }),
  });

  if (!enabled) {
    return (
      <section className="empty">
        <p>{t("explore.empty")}</p>
        <p className="mono">{t("explore.emptyHint")}</p>
      </section>
    );
  }

  const result =
    mode === "combined"
      ? combined.data
      : mergeResults(legQueries.flatMap((q) => (q.data ? [q.data] : [])));
  const hasSimulated =
    mode === "combined"
      ? Boolean(combined.data?.offers.some((o) => o.offer.is_simulated))
      : legQueries.some((q) => q.data?.offers.some((o) => o.offer.is_simulated));
  const isFetching =
    mode === "combined" ? combined.isFetching : legQueries.some((q) => q.isFetching);
  const filterCount = activeFilterCount(state);
  const filters = <FilterPanel state={state} result={result} onChange={onChange} />;

  const watchFrom = (item: RankedOffer) =>
    onWatch({
      trip: state,
      airline: item.offer.airline_code,
      price: Number(item.offer.total_amount),
      currency: item.offer.currency,
    });
  const watchLeg = (leg: Leg, item: RankedOffer) =>
    onWatch({
      trip: oneWayLeg(state, leg),
      airline: item.offer.airline_code,
      price: Number(item.offer.total_amount),
      currency: item.offer.currency,
    });

  return (
    <div className="explore">
      {!isCompact && filters}
      {isCompact && isFilterOpen && (
        <Sheet
          title={t("explore.filtersTitle")}
          onClose={() => setIsFilterOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="btn"
                onClick={() => onChange({ ...state, ...DEFAULT_FILTERS })}
                disabled={filterCount === 0}
              >
                {t("common.clear")}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={(e) => e.currentTarget.closest("dialog")?.close()}
              >
                {t("explore.showResults", { n: result?.total_filtered ?? "…" })}
              </button>
            </>
          }
        >
          {filters}
        </Sheet>
      )}

      <section className="results" aria-labelledby="results-heading" aria-busy={isFetching}>
        <header className="results__head">
          <div>
            <h2 id="results-heading" className="results__title">
              {result ? t("explore.count", { n: result.total_filtered }) : t("explore.searching")}
            </h2>
            {result && (
              <p className="results__meta mono">
                {result.origin_airports.join("/")} → {result.destination_airports.join("/")} ·{" "}
                {t("explore.meta", { n: result.total_raw })} ·{" "}
                <span className={result.cache.hit ? "badge badge--hit" : "badge"}>
                  {result.cache.hit ? t("explore.cacheHit") : t("explore.live")}
                </span>{" "}
                {t("explore.fetchedAt", { time: relativeTime(result.cache.fetched_at, t) })}
                {result.fx.approximate && ` · ${t("common.fxApprox")}`}
              </p>
            )}
          </div>

          {canSplit && (
            <div className="ticket-mode" role="radiogroup" aria-label={t("explore.modeAria")}>
              {(["combined", "split"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => onChange({ ...state, mode: m })}
                >
                  <strong>{t(`explore.mode.${m}`)}</strong>
                  <small>{t(`explore.mode.${m}Hint`)}</small>
                </button>
              ))}
            </div>
          )}

          <div className="toolbar">
            <button
              type="button"
              className="filter-btn only-compact"
              onClick={() => setIsFilterOpen(true)}
              aria-haspopup="dialog"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 6h16M7 12h10M10 18h4" />
              </svg>
              {t("explore.filters")}
              {filterCount > 0 && <span className="filter-btn__count mono">{filterCount}</span>}
            </button>
            <div className="sortbar" role="group" aria-label={t("explore.sortAria")}>
              {SORTS.map((key) => (
                <button
                  key={key}
                  type="button"
                  className="sortbar__item"
                  aria-pressed={state.sort === key}
                  onClick={() => onChange({ ...state, sort: key })}
                >
                  {t(`sort.${key}`)}
                </button>
              ))}
            </div>
          </div>
        </header>

        {hasSimulated && (
          <p className="sim-banner" role="note">
            <span className="sim-tag">{t("offer.simulated")}</span>
            {t("explore.simulatedBanner")}
          </p>
        )}

        {mode === "split" ? (
          <SplitView legs={legs} queries={legQueries} onWatchLeg={watchLeg} />
        ) : (
          <>
            {combined.isError && (
              <ApiErrorNotice
                error={combined.error}
                prefix={t("explore.failed")}
                onRetry={() => void combined.refetch()}
              />
            )}
            {combined.isPending && <ResultsSkeleton />}
            {combined.data && combined.data.offers.length === 0 && (
              <div className="empty">{t("explore.none")}</div>
            )}
            <ol className="results__list">
              {combined.data?.offers.map((item) => (
                <OfferRow
                  key={item.offer.id}
                  item={item}
                  onWatch={state.trip_type === "mc" ? undefined : () => watchFrom(item)}
                  isMultiCity={state.trip_type === "mc"}
                />
              ))}
            </ol>
          </>
        )}
      </section>
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <ol className="results__list" aria-hidden="true">
      {Array.from({ length: 4 }, (_, i) => (
        <li key={i} className="offer offer--skeleton" style={{ animationDelay: `${i * 90}ms` }} />
      ))}
    </ol>
  );
}

/** 與預設值不同的篩選條件數，顯示在「篩選」按鈕上 */
function activeFilterCount(s: SearchState): number {
  return [
    s.direct_only,
    s.max_stops !== DEFAULT_FILTERS.max_stops,
    s.allowed_hubs.length > 0,
    s.excluded_hubs.length > 0,
    s.min_layover_minutes !== DEFAULT_FILTERS.min_layover_minutes ||
      s.max_layover_minutes !== DEFAULT_FILTERS.max_layover_minutes,
    s.airlines.length > 0,
    s.price_min !== null || s.price_max !== null,
    s.duration_min !== null || s.duration_max !== null,
  ].filter(Boolean).length;
}
