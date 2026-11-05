import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { formatPrice } from "../../lib/currency.ts";
import { cabinLabel, dateWithWeekday } from "../../lib/format.ts";
import { intervalLabel } from "../../lib/schedule.ts";
import type { Watchlist } from "../../lib/types.ts";
import { splitMessage, useConfirm } from "../ui/ConfirmDialog.tsx";
import { EditWatchDialog } from "./EditWatchDialog.tsx";

// Recharts 體積較大，只在打開詳情時才載入
const PriceChart = lazy(() => import("./PriceChart.tsx"));

type Props = {
  watch: Watchlist;
  /** 放在抽屜內時去掉外框與吸頂 */
  isEmbedded?: boolean;
  /** 永久刪除後通知父層（關閉抽屜、清除選取） */
  onDeleted?: () => void;
};

export function WatchDetail({ watch, isEmbedded = false, onDeleted }: Props) {
  const { lang, locale, t } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const currency = watch.currency ?? watch.stats.currency;
  const history = useQuery({
    queryKey: ["history", watch.id, watch.stats.last_checked_at],
    queryFn: () => api.history(watch.id, 60),
  });
  const alerts = useQuery({
    queryKey: ["alerts", watch.id, watch.stats.last_alert_at],
    queryFn: () => api.alerts(watch.id),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelWatchlist(watch.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteWatchlist(watch.id),
    onSuccess: async () => {
      onDeleted?.();
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const route = `${watch.origin} → ${watch.destination}`;
  const handleCancel = async () => {
    const ok = await confirm({
      ...splitMessage(t("detail.stopConfirm", { route })),
      confirmLabel: t("detail.stop"),
    });
    if (ok) cancel.mutate();
  };
  const handleDelete = async () => {
    const ok = await confirm({
      ...splitMessage(t("detail.deleteConfirm", { route })),
      confirmLabel: t("detail.delete"),
      tone: "danger",
    });
    if (ok) remove.mutate();
  };
  const isBusy = cancel.isPending || remove.isPending;
  const endedNote = watch.status === "TRACKING" ? null : t(`detail.ended.${watch.status}`);

  const rules = [
    watch.target_price &&
      t("detail.rule.target", { v: formatPrice(watch.target_price, currency, locale) }),
    watch.drop_percent && t("detail.rule.drop", { v: Number(watch.drop_percent) }),
    watch.max_stops === 0
      ? t("detail.rule.direct")
      : t("detail.rule.stops", { n: watch.max_stops }),
    t("detail.rule.layover", { min: watch.min_layover_minutes, max: watch.max_layover_minutes }),
    watch.allowed_transits.length > 0 &&
      t("detail.rule.via", { v: watch.allowed_transits.join(", ") }),
    watch.excluded_transits.length > 0 &&
      t("detail.rule.avoid", { v: watch.excluded_transits.join(", ") }),
    watch.preferred_airline && t("detail.rule.airline", { v: watch.preferred_airline }),
    watch.has_webhook ? t("detail.rule.webhook") : t("detail.rule.log"),
    watch.status === "TRACKING" &&
      t("detail.rule.interval", { v: intervalLabel(watch.patrol_interval_minutes, t) }),
  ].filter(Boolean) as string[];

  return (
    <article
      className={`detail ${isEmbedded ? "detail--embedded" : ""}`}
      aria-labelledby="detail-title"
    >
      <header className="detail__head">
        <div>
          {isEmbedded ? (
            // 抽屜標題列已顯示航線，這裡只補名稱
            watch.label && (
              <h3 id="detail-title" className="detail__title">
                {watch.label}
              </h3>
            )
          ) : (
            <h3 id="detail-title" className="detail__title">
              <span className="mono">{watch.origin}</span> →{" "}
              <span className="mono">{watch.destination}</span>
              {watch.label && <small> {watch.label}</small>}
            </h3>
          )}
          <p className="detail__trip mono">
            {dateWithWeekday(watch.departure_date, lang)}
            {watch.return_date
              ? ` ⇄ ${dateWithWeekday(watch.return_date, lang)}`
              : ` · ${t("detail.oneWay")}`}{" "}
            · {watch.adults}A{watch.children ? ` ${watch.children}C` : ""} ·{" "}
            {cabinLabel(watch.cabin_class, t)}
            {currency && ` · ${currency}`}
          </p>
        </div>
        <div className="detail__actions">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setIsEditing(true)}
            disabled={isBusy}
          >
            {t("detail.edit")}
          </button>
          {watch.status === "TRACKING" && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={handleCancel}
              disabled={isBusy}
            >
              {t("detail.stop")}
            </button>
          )}
          <button
            type="button"
            className="btn btn--ghost btn--danger"
            onClick={handleDelete}
            disabled={isBusy}
          >
            {remove.isPending ? t("detail.deleting") : t("detail.delete")}
          </button>
        </div>
      </header>

      {endedNote && <p className="detail__ended">{endedNote}</p>}
      {(cancel.isError || remove.isError) && (
        <p className="notice" role="alert">
          {(cancel.error ?? remove.error)?.message}
        </p>
      )}

      <ul className="detail__rules">
        {rules.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>

      <div className="detail__chart">
        {history.isError && <p className="notice">{history.error.message}</p>}
        {history.data && history.data.length < 2 && (
          <p className="empty">{t("detail.chartEmpty")}</p>
        )}
        {history.data && history.data.length >= 2 && (
          <Suspense fallback={<div className="detail__chart-skeleton" />}>
            <PriceChart
              points={history.data}
              targetPrice={watch.target_price ? Number(watch.target_price) : null}
              weekAvg={watch.stats.week_avg ? Number(watch.stats.week_avg) : null}
            />
          </Suspense>
        )}
      </div>

      <section aria-labelledby="alerts-title">
        <h4 id="alerts-title" className="detail__subtitle">
          {t("detail.alerts")}
        </h4>
        {alerts.data?.length === 0 && <p className="detail__muted">{t("detail.noAlerts")}</p>}
        <ol className="alerts">
          {alerts.data?.map((a) => (
            <li key={a.id}>
              <time className="mono" dateTime={a.sent_at}>
                {new Date(a.sent_at).toLocaleString(locale, { hour12: false })}
              </time>
              <span className="mono alerts__price">
                {formatPrice(a.triggered_price, a.currency, locale)}
              </span>
              <span className="chip">{t(`detail.reason.${a.reason}`)}</span>
              <span className="detail__muted">
                {a.channel === "webhook" ? t("detail.sent") : t("detail.logged")}
              </span>
            </li>
          ))}
        </ol>
      </section>
      {isEditing && <EditWatchDialog watch={watch} onClose={() => setIsEditing(false)} />}
    </article>
  );
}
