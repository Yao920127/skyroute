import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { useAccount } from "../../hooks/useAccount.ts";
import { useApiKey } from "../../hooks/useApiKey.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { formatPrice, useCurrency } from "../../lib/currency.ts";
import { cabinLabel, dateWithWeekday } from "../../lib/format.ts";
import { legsOf } from "../../lib/searchState.ts";
import { routeText } from "../../lib/watchRoute.ts";
import type { SearchState, WatchlistCreate } from "../../lib/types.ts";
import { ApiErrorNotice } from "../settings/ApiErrorNotice.tsx";
import { Select } from "../ui/Select.tsx";
import { PortalContainerContext } from "../ui/portal.ts";
import { IntervalSelect } from "./IntervalSelect.tsx";

export type WatchDraft = {
  trip: SearchState;
  airline?: string;
  /** 目前價格（顯示幣別）；分段購票為各段合計 */
  price?: number;
  currency?: string;
  /** 分段購票：每段各自查單程，airlines 依航段順序帶入目前選的航司 */
  split?: { airlines: string[] };
};

type Props = {
  draft: WatchDraft;
  onClose: () => void;
  onCreated: () => void;
};

const SUGGESTED_DISCOUNT = 0.92;

function initialForm(draft: WatchDraft) {
  const { trip } = draft;
  return {
    label: "",
    targetPrice: draft.price ? String(Math.floor(draft.price * SUGGESTED_DISCOUNT)) : "",
    dropPercent: "10",
    airline: draft.airline ?? "",
    webhook: "",
    maxStops: trip.direct_only ? 0 : trip.max_stops,
    interval: null as number | null,
    legAirlines: draft.split?.airlines ?? [],
  };
}

export function WatchForm({ draft, onClose, onCreated }: Props) {
  const { lang, locale, t } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState(() => initialForm(draft));
  const queryClient = useQueryClient();
  const apiKey = useApiKey();
  const { account } = useAccount();
  // 已登入看帳號金鑰；未登入看這台瀏覽器的金鑰
  const hasOwnKey = account ? Boolean(account.key_mask) : Boolean(apiKey);
  const [dialogEl, setDialogEl] = useState<HTMLDialogElement | null>(null);
  const displayCurrency = useCurrency();
  // 目標價以建立當下的價格幣別為準（搜尋結果已換算成顯示幣別）
  const currency = draft.currency ?? displayCurrency;
  const { trip } = draft;
  const isSplit = Boolean(draft.split);
  const legs = legsOf(trip);
  const isMultiCity = trip.trip_type === "mc" && trip.extra_legs.length > 0;

  useEffect(() => {
    dialogRef.current?.showModal();
    setDialogEl(dialogRef.current);
  }, []);

  const create = useMutation({
    mutationFn: (payload: WatchlistCreate) => api.createWatchlist(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      onCreated();
    },
  });

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    // 分段購票：所有航段（含來回的回程）都列為一段；整張票：沿用單程／來回／多航段
    const [first, ...rest] = legs;
    create.mutate({
      origin: first.origin,
      destination: first.destination,
      departure_date: first.departure_date,
      return_date: !isSplit && trip.trip_type === "rt" ? trip.return_date : null,
      extra_legs: isSplit ? rest : isMultiCity ? trip.extra_legs : [],
      ticket_mode: isSplit ? "split" : "ticket",
      leg_airlines: isSplit
        ? legs.map((_, i) => form.legAirlines[i]?.trim().toUpperCase() || null)
        : [],
      adults: trip.adults,
      children: trip.children,
      cabin_class: trip.cabin_class,
      label: form.label.trim() || null,
      target_price: form.targetPrice ? Number(form.targetPrice) : null,
      drop_percent: form.dropPercent ? Number(form.dropPercent) : null,
      preferred_airline: isSplit ? null : form.airline.trim().toUpperCase() || null,
      allowed_transits: trip.allowed_hubs,
      excluded_transits: trip.excluded_hubs,
      max_stops: form.maxStops,
      min_layover_minutes: trip.min_layover_minutes,
      max_layover_minutes: trip.max_layover_minutes,
      webhook_url: form.webhook.trim() || null,
      currency,
      patrol_interval_minutes: form.interval,
    });
  };

  const hasThreshold = Boolean(form.targetPrice || form.dropPercent);
  const isRoundTrip = trip.trip_type === "rt" && trip.return_date;
  const dates =
    legs.length > 2 || isMultiCity
      ? legs.map((l) => dateWithWeekday(l.departure_date, lang)).join(" · ")
      : isRoundTrip
        ? `${dateWithWeekday(trip.departure_date, lang)} ⇄ ${dateWithWeekday(trip.return_date!, lang)}`
        : `${dateWithWeekday(trip.departure_date, lang)}${t("watch.oneWay")}`;
  const pax =
    t("watch.paxAdults", { n: trip.adults }) +
    (trip.children ? t("watch.paxChildren", { n: trip.children }) : "");

  return (
    <dialog ref={dialogRef} className="sheet" onClose={onClose} aria-labelledby="watch-form-title">
      <PortalContainerContext value={dialogEl}>
        <form className="sheet__body" onSubmit={handleSubmit}>
          <header className="sheet__head">
            <p className="sheet__kicker mono">{t("watch.kicker")}</p>
            <h2 id="watch-form-title" className="mono">
              {routeText(legs)}
            </h2>
            {isSplit && <p className="sheet__mode">{t("watch.splitMode")}</p>}
            <p className="sheet__trip">
              {t("watch.trip", { dates, pax, cabin: cabinLabel(trip.cabin_class, t) })}
              {draft.price
                ? t("watch.current", { price: formatPrice(draft.price, currency, locale) })
                : ""}
            </p>
            {(trip.allowed_hubs.length > 0 || trip.excluded_hubs.length > 0) && (
              <p className="sheet__hubs">
                {trip.allowed_hubs.length > 0 &&
                  t("watch.via", { v: trip.allowed_hubs.join(", ") })}
                {trip.excluded_hubs.length > 0 &&
                  t("watch.avoid", { v: trip.excluded_hubs.join(", ") })}
              </p>
            )}
          </header>

          <div className="sheet__grid">
            <label className="field">
              <span>{t("watch.label")}</span>
              <input
                className="input"
                maxLength={100}
                value={form.label}
                placeholder={t("watch.labelPh")}
                onChange={(e) => set("label", e.target.value)}
              />
            </label>
            {isSplit ? (
              <div className="field sheet__wide">
                <span>{t("watch.legAirlines")}</span>
                <div className="leg-airlines">
                  {legs.map((leg, i) => (
                    <label key={i} className="leg-airlines__item">
                      <span className="mono">
                        {leg.origin}→{leg.destination}
                      </span>
                      <input
                        className="input mono"
                        maxLength={2}
                        value={form.legAirlines[i] ?? ""}
                        placeholder={t("watch.anyAirline")}
                        aria-label={t("watch.legAirline", { n: i + 1 })}
                        onChange={(e) =>
                          set(
                            "legAirlines",
                            legs.map((_, j) =>
                              j === i ? e.target.value.toUpperCase() : (form.legAirlines[j] ?? ""),
                            ),
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <label className="field">
                <span>{t("watch.airline")}</span>
                <input
                  className="input mono"
                  maxLength={2}
                  value={form.airline}
                  placeholder="BR"
                  onChange={(e) => set("airline", e.target.value.toUpperCase())}
                />
              </label>
            )}
            <label className="field">
              <span>{t("watch.target", { currency })}</span>
              <input
                className="input mono"
                type="number"
                inputMode="decimal"
                min={1}
                step="0.01"
                value={form.targetPrice}
                onChange={(e) => set("targetPrice", e.target.value)}
              />
            </label>
            <label className="field">
              <span>{t("watch.drop")}</span>
              <input
                className="input mono"
                type="number"
                inputMode="decimal"
                min={0.5}
                max={90}
                step="0.5"
                value={form.dropPercent}
                onChange={(e) => set("dropPercent", e.target.value)}
              />
            </label>
            <div className="field">
              <span>{t("watch.maxStops")}</span>
              <Select
                value={String(form.maxStops)}
                onValueChange={(v) => set("maxStops", Number(v))}
                ariaLabel={t("watch.maxStops")}
                options={[
                  { value: "0", label: t("watch.direct") },
                  { value: "1", label: t("watch.stopsN", { n: 1 }) },
                  { value: "2", label: t("watch.stopsN", { n: 2 }) },
                ]}
              />
            </div>
            <div className="field">
              <span>{t("watch.interval")}</span>
              <IntervalSelect
                value={form.interval}
                hasOwnKey={hasOwnKey}
                onChange={(v) => set("interval", v)}
              />
            </div>
            <label className="field sheet__wide">
              <span>{t("watch.webhook")}</span>
              <input
                className="input mono"
                type="url"
                inputMode="url"
                placeholder="https://discord.com/api/webhooks/…"
                value={form.webhook}
                onChange={(e) => set("webhook", e.target.value)}
              />
            </label>
          </div>

          <p className="sheet__note">{t("watch.intervalHint")}</p>
          <p className="sheet__note">{t("watch.note")}</p>
          {apiKey && <p className="sheet__note">{t("watch.ownKeyNote")}</p>}
          {create.isError && <ApiErrorNotice error={create.error} />}

          <footer className="sheet__foot">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => dialogRef.current?.close()}
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={!hasThreshold || create.isPending}
            >
              {create.isPending ? t("watch.submitting") : t("watch.submit")}
            </button>
          </footer>
        </form>
      </PortalContainerContext>
    </dialog>
  );
}
