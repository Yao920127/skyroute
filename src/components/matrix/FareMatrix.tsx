import { useEffect, useState } from "react";

import "./matrix.css";
import { useApiKey } from "../../hooks/useApiKey.ts";
import { useI18n, type Lang, type Translate } from "../../i18n/i18n.ts";
import { streamFareMatrix } from "../../lib/api.ts";
import { maskKey } from "../../lib/credentials.ts";
import { formatCompact, formatPrice, useCurrency } from "../../lib/currency.ts";
import { dateWithWeekday, shortDateLabel } from "../../lib/format.ts";
import { buildScale, cellKey, heatColor, heatInk } from "../../lib/heat.ts";
import { filtersOf, tripOf } from "../../lib/searchState.ts";
import type { MatrixCell, SearchState } from "../../lib/types.ts";
import { ApiErrorNotice } from "../settings/ApiErrorNotice.tsx";

type Props = {
  state: SearchState;
  enabled: boolean;
  onPick: (departure: string, returnDate: string | null) => void;
};

type Axes = {
  departures: string[];
  returns: (string | null)[];
  currency: string;
  approximate: boolean;
};
type MatrixParams = ReturnType<typeof tripOf> & ReturnType<typeof filtersOf>;
const RADIUS_OPTIONS = [1, 2, 3];
const DEFAULT_RADIUS_DAYS = 3;
type Status = "idle" | "streaming" | "done" | "error";

export function FareMatrix({ state, enabled, onPick }: Props) {
  const { lang, locale, t } = useI18n();
  const [axes, setAxes] = useState<Axes | null>(null);
  const [cells, setCells] = useState<Record<string, MatrixCell>>({});
  const [status, setStatus] = useState<Status>("idle");
  const [radius, setRadius] = useState(DEFAULT_RADIUS_DAYS);
  const [error, setError] = useState<Error | null>(null);
  const apiKey = useApiKey();
  const currency = useCurrency();
  const keyTag = apiKey ? maskKey(apiKey.token) : "server";
  const isMulti = state.trip_type === "mc";
  const requestKey = JSON.stringify({ ...tripOf(state), ...filtersOf(state) });

  useEffect(() => {
    if (!enabled || isMulti) return;
    const controller = new AbortController();
    setAxes(null);
    setCells({});
    setError(null);
    setStatus("streaming");
    // requestKey 是 trip + filters 的序列化結果，直接還原成請求參數
    const params = JSON.parse(requestKey) as MatrixParams;
    streamFareMatrix(
      { ...params, radius_days: radius, currency },
      (line) => {
        if (line.type === "axes") {
          setAxes({
            departures: line.departure_dates,
            returns: line.return_dates,
            currency: line.currency,
            approximate: line.fx_approximate,
          });
        } else if (line.type === "cell") {
          setCells((prev) => ({ ...prev, [cellKey(line.departure_date, line.return_date)]: line }));
        } else {
          setStatus("done");
        }
      },
      controller.signal,
    ).catch((err: unknown) => {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err : new Error(t("matrix.failed")));
      setStatus("error");
    });
    return () => controller.abort();
    // keyTag 不在 effect 內使用，但換金鑰代表換資料來源，需重新產生矩陣；t 只用於錯誤後援字串
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, enabled, isMulti, radius, keyTag, currency]);

  if (isMulti) return <section className="empty">{t("matrix.multiUnsupported")}</section>;
  if (!enabled) return <section className="empty">{t("matrix.empty")}</section>;

  const list = Object.values(cells);
  const scale = buildScale(list);
  const total = axes ? axes.departures.length * axes.returns.length : (radius * 2 + 1) ** 2;
  const cheapest = scale ? list.find((c) => c.price && Number(c.price) === scale.min) : undefined;
  const isRoundTrip = state.return_date !== null;
  const shownCurrency = axes?.currency ?? currency;

  return (
    <section className="matrix" aria-labelledby="matrix-heading">
      <header className="matrix__head">
        <div>
          <h2 id="matrix-heading">{t("matrix.title")}</h2>
          <p className="matrix__sub">
            {isRoundTrip ? t("matrix.subRt") : t("matrix.subOw")}
            {t("matrix.subTail")}
          </p>
        </div>
        <div className="segmented matrix__radius" role="radiogroup" aria-label={t("matrix.range")}>
          {RADIUS_OPTIONS.map((r) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={radius === r}
              onClick={() => setRadius(r)}
            >
              {t("matrix.days", { n: r })}
            </button>
          ))}
        </div>
        <div className="matrix__progress mono" role="status">
          {status === "streaming" && t("matrix.loading", { done: list.length, total })}
          {status === "done" && t("matrix.done", { n: list.length })}
        </div>
      </header>

      {error && <ApiErrorNotice error={error} />}
      {list.some((c) => c.simulated) && (
        <p className="sim-banner" role="note">
          <span className="sim-tag">{t("offer.simulated")}</span>
          {t("matrix.simulatedBanner")}
        </p>
      )}

      {cheapest && scale && (
        <p className="matrix__best">
          {t("matrix.cheapest")}{" "}
          <strong className="mono">{formatPrice(cheapest.price, shownCurrency, locale)}</strong>
          {" · "}
          {cheapest.return_date
            ? t("matrix.cheapestRt", {
                dep: dateWithWeekday(cheapest.departure_date, lang),
                ret: dateWithWeekday(cheapest.return_date, lang),
              })
            : t("matrix.cheapestOw", { dep: dateWithWeekday(cheapest.departure_date, lang) })}
          {axes?.approximate && <span className="matrix__fx"> · {t("common.fxApprox")}</span>}
          <span className="matrix__legend" aria-hidden="true">
            <span className="mono">{formatPrice(scale.min, shownCurrency, locale)}</span>
            <i />
            <span className="mono">{formatPrice(scale.max, shownCurrency, locale)}</span>
          </span>
        </p>
      )}

      {axes && (
        <div className="matrix__scroll">
          <table className="heat">
            <thead>
              <tr>
                <th scope="col" className="heat__corner">
                  {t("matrix.corner")}
                  {isRoundTrip ? t("matrix.cornerRt") : ""}
                  <span className="heat__currency mono">{shownCurrency}</span>
                </th>
                {axes.returns.map((r) => (
                  <th key={r ?? "oneway"} scope="col">
                    {r ? (
                      <DateLabel iso={r} lang={lang} isAnchor={r === state.return_date} />
                    ) : (
                      t("matrix.oneWay")
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {axes.departures.map((d) => (
                <tr key={d}>
                  <th scope="row">
                    <DateLabel iso={d} lang={lang} isAnchor={d === state.departure_date} />
                  </th>
                  {axes.returns.map((r) => {
                    const cell = cells[cellKey(d, r)];
                    const isSelected = d === state.departure_date && r === state.return_date;
                    return (
                      <td key={r ?? "oneway"}>
                        <HeatCell
                          cell={cell}
                          tone={
                            cell?.status === "ok" && scale
                              ? scale.position(Number(cell.price))
                              : undefined
                          }
                          isSelected={isSelected}
                          isCheapest={cell === cheapest}
                          onPick={() => onPick(d, r)}
                          currency={shownCurrency}
                          locale={locale}
                          lang={lang}
                          t={t}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DateLabel({ iso, lang, isAnchor }: { iso: string; lang: Lang; isAnchor: boolean }) {
  const { md, weekday } = shortDateLabel(iso, lang);
  return (
    <span className={isAnchor ? "heat__date heat__date--anchor" : "heat__date"}>
      <span className="mono">{md}</span>
      <small>{weekday}</small>
    </span>
  );
}

type CellProps = {
  cell: MatrixCell | undefined;
  /** 0 = 最便宜、1 = 最貴 */
  tone: number | undefined;
  isSelected: boolean;
  isCheapest: boolean;
  onPick: () => void;
  currency: string;
  locale: string;
  lang: Lang;
  t: Translate;
};

function HeatCell(props: CellProps) {
  const { cell, tone, isSelected, isCheapest, onPick, currency, locale, lang, t } = props;
  if (!cell)
    return <span className="heat__cell heat__cell--loading" aria-label={t("common.loading")} />;
  if (cell.status === "invalid") return <span className="heat__cell heat__cell--void" />;
  if (cell.status !== "ok") {
    return (
      <span className="heat__cell heat__cell--muted" title={cell.message}>
        {cell.status === "empty" ? t("matrix.noFlights") : t("matrix.error")}
      </span>
    );
  }
  const classes = [
    "heat__cell",
    "heat__cell--ok",
    isSelected && "heat__cell--selected",
    isCheapest && "heat__cell--best",
  ]
    .filter(Boolean)
    .join(" ");
  const label = t("matrix.cellAria", {
    dep: dateWithWeekday(cell.departure_date, lang),
    ret: cell.return_date
      ? t("matrix.cellRet", { ret: dateWithWeekday(cell.return_date, lang) })
      : "",
    price: formatPrice(cell.price, currency, locale),
  });
  return (
    <button
      type="button"
      className={classes}
      style={tone === undefined ? undefined : { background: heatColor(tone), color: heatInk(tone) }}
      onClick={onPick}
      aria-label={label}
    >
      <span className="mono">{formatCompact(cell.price, currency, locale)}</span>
      {cell.cached && <small className="heat__cached">{t("matrix.cached")}</small>}
    </button>
  );
}
