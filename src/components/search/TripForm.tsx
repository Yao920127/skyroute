import { useState, type FormEvent } from "react";

import "./trip-form.css";
import { useI18n } from "../../i18n/i18n.ts";
import { addDays, cabinLabel, dateWithWeekday } from "../../lib/format.ts";
import { legsOf, MAX_LEGS } from "../../lib/searchState.ts";
import type { Leg, SearchState, TripType } from "../../lib/types.ts";
import { AirportInput } from "../ui/AirportInput.tsx";
import { DatePicker } from "../ui/DatePicker.tsx";
import { PassengerPicker } from "../ui/PassengerPicker.tsx";

type Props = {
  initial: SearchState;
  /** 已有搜尋結果時，平板／手機上收合成一行摘要，點擊才展開 */
  isCollapsible?: boolean;
  submitLabel: string;
  onSubmit: (next: SearchState) => void;
  /** 日期矩陣不支援多航段 */
  allowMultiCity?: boolean;
};

const IATA = /^[A-Z]{3}$/;
const todayIso = () => new Date().toISOString().slice(0, 10);

/** 表單內部狀態：多航段一律以 legs 陣列表示，送出時再轉回 SearchState */
type Draft = {
  tripType: TripType;
  legs: Leg[];
  returnDate: string | null;
  adults: number;
  children: number;
  cabin: SearchState["cabin_class"];
};

function toDraft(s: SearchState): Draft {
  return {
    tripType: s.trip_type,
    legs: s.trip_type === "mc" ? legsOf(s) : [legsOf(s)[0]],
    returnDate: s.return_date ?? addDays(s.departure_date, 7),
    adults: s.adults,
    children: s.children,
    cabin: s.cabin_class,
  };
}

export function TripForm({
  initial,
  isCollapsible = false,
  submitLabel,
  onSubmit,
  allowMultiCity = true,
}: Props) {
  const { lang, t } = useI18n();
  const [draft, setDraft] = useState(() => toDraft(initial));
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(!isCollapsible);
  const today = todayIso();
  const first = draft.legs[0];

  const patch = (next: Partial<Draft>) => setDraft((d) => ({ ...d, ...next }));
  const setLeg = (index: number, next: Partial<Leg>) =>
    setDraft((d) => ({ ...d, legs: d.legs.map((l, i) => (i === index ? { ...l, ...next } : l)) }));

  const setTripType = (tripType: TripType) =>
    setDraft((d) => {
      if (tripType !== "mc") return { ...d, tripType, legs: [d.legs[0]] };
      if (d.legs.length > 1) return { ...d, tripType };
      // 切到多航段：預設第二段從目的地往回飛
      const back: Leg = {
        origin: d.legs[0].destination,
        destination: d.legs[0].origin,
        departure_date: d.returnDate ?? addDays(d.legs[0].departure_date, 7),
      };
      return { ...d, tripType, legs: [d.legs[0], back] };
    });

  const addLeg = () =>
    setDraft((d) => {
      const last = d.legs[d.legs.length - 1];
      const next: Leg = {
        origin: last.destination,
        destination: "",
        departure_date: addDays(last.departure_date, 3),
      };
      return { ...d, legs: [...d.legs, next] };
    });

  const removeLeg = (index: number) =>
    setDraft((d) => ({ ...d, legs: d.legs.filter((_, i) => i !== index) }));

  const validate = (): string | null => {
    for (const leg of draft.legs) {
      if (!IATA.test(leg.origin) || !IATA.test(leg.destination)) return t("trip.err.code");
      if (leg.origin === leg.destination) return t("trip.err.same");
    }
    for (let i = 1; i < draft.legs.length; i++) {
      if (draft.legs[i].departure_date < draft.legs[i - 1].departure_date)
        return t("trip.err.legOrder");
    }
    if (draft.tripType === "rt" && draft.returnDate && draft.returnDate < first.departure_date) {
      return t("trip.err.order");
    }
    return null;
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    onSubmit({
      ...initial,
      trip_type: draft.tripType,
      origin: first.origin,
      destination: first.destination,
      departure_date: first.departure_date,
      return_date: draft.tripType === "rt" ? draft.returnDate : null,
      extra_legs: draft.tripType === "mc" ? draft.legs.slice(1) : [],
      adults: draft.adults,
      children: draft.children,
      cabin_class: draft.cabin,
      mode: draft.tripType === "ow" ? "combined" : initial.mode,
    });
  };

  const swap = () => setLeg(0, { origin: first.destination, destination: first.origin });
  const tripTypes: { id: TripType; label: string }[] = [
    { id: "ow", label: t("trip.oneWay") },
    { id: "rt", label: t("trip.roundTrip") },
    ...(allowMultiCity ? [{ id: "mc" as const, label: t("trip.multiCity") }] : []),
  ];

  const summaryLegs = legsOf(initial);
  const summaryRoute =
    initial.trip_type === "mc"
      ? summaryLegs.map((l) => `${l.origin}→${l.destination}`).join("  ")
      : `${initial.origin} → ${initial.destination}`;
  const summaryDates =
    initial.trip_type === "mc"
      ? t("trip.summary.multi", { n: summaryLegs.length })
      : `${dateWithWeekday(initial.departure_date, lang)}${
          initial.return_date
            ? ` – ${dateWithWeekday(initial.return_date, lang)}`
            : ` · ${t("trip.oneWay")}`
        }`;

  return (
    <div className="trip-wrap" data-collapsed={!isEditing}>
      <button
        type="button"
        className="trip-summary"
        onClick={() => setIsEditing(true)}
        aria-expanded={isEditing}
        aria-label={t("trip.editAria")}
      >
        <span className="trip-summary__route">{summaryRoute}</span>
        <span className="trip-summary__meta">
          {summaryDates} · {t("trip.summary.pax", { n: initial.adults + initial.children })} ·{" "}
          {cabinLabel(initial.cabin_class, t)}
        </span>
        <span className="trip-summary__edit">{t("trip.edit")}</span>
      </button>

      <form className="trip" onSubmit={handleSubmit} aria-label={t("trip.type")}>
        <div className="trip__top">
          <div className="trip__mode" role="radiogroup" aria-label={t("trip.type")}>
            {tripTypes.map((o) => (
              <button
                key={o.id}
                type="button"
                role="radio"
                aria-checked={draft.tripType === o.id}
                onClick={() => setTripType(o.id)}
              >
                {o.label}
              </button>
            ))}
          </div>
          <PassengerPicker
            adults={draft.adults}
            children={draft.children}
            cabin={draft.cabin}
            onChange={(v) =>
              patch({ adults: v.adults, children: v.children, cabin: v.cabin_class })
            }
          />
        </div>

        {draft.tripType !== "mc" ? (
          <div className="trip__main">
            <div className="trip__route">
              <AirportInput
                label={t("trip.from")}
                value={first.origin}
                onChange={(v) => setLeg(0, { origin: v })}
              />
              <button
                type="button"
                className="trip__swap"
                onClick={swap}
                aria-label={t("trip.swap")}
              >
                ⇄
              </button>
              <AirportInput
                label={t("trip.to")}
                value={first.destination}
                onChange={(v) => setLeg(0, { destination: v })}
              />
            </div>
            <div className="trip__dates">
              <DatePicker
                mode={draft.tripType === "rt" ? "range" : "single"}
                minDate={today}
                labels={{ from: t("trip.depart"), to: t("trip.return") }}
                value={{
                  from: first.departure_date,
                  to: draft.tripType === "rt" ? draft.returnDate : null,
                }}
                onChange={(range) => {
                  if (range.from) setLeg(0, { departure_date: range.from });
                  patch({ returnDate: range.to });
                }}
              />
            </div>
          </div>
        ) : (
          <ol className="trip__legs">
            {draft.legs.map((leg, i) => (
              <li key={i} className="trip__leg">
                <span className="trip__leg-no mono">{t("trip.leg", { n: i + 1 })}</span>
                <AirportInput
                  size="compact"
                  className="board-field--from"
                  label={t("trip.from")}
                  value={leg.origin}
                  onChange={(v) => setLeg(i, { origin: v })}
                />
                <AirportInput
                  size="compact"
                  className="board-field--to"
                  label={t("trip.to")}
                  value={leg.destination}
                  onChange={(v) => setLeg(i, { destination: v })}
                />
                <DatePicker
                  mode="single"
                  minDate={i === 0 ? today : draft.legs[i - 1].departure_date}
                  labels={{ from: t("trip.date") }}
                  value={{ from: leg.departure_date, to: null }}
                  onChange={(range) => range.from && setLeg(i, { departure_date: range.from })}
                />
                {draft.legs.length > 2 && (
                  <button
                    type="button"
                    className="trip__leg-remove"
                    onClick={() => removeLeg(i)}
                    aria-label={t("trip.removeLeg", { n: i + 1 })}
                  >
                    ✕
                  </button>
                )}
              </li>
            ))}
            {draft.legs.length < MAX_LEGS && (
              <li>
                <button type="button" className="trip__add" onClick={addLeg}>
                  ＋ {t("trip.addLeg")}
                </button>
              </li>
            )}
          </ol>
        )}

        <div className="trip__actions">
          <button type="submit" className="trip__submit">
            {submitLabel} →
          </button>
          {isCollapsible && (
            <button
              type="button"
              className="trip__cancel btn btn--ghost btn--on-dark"
              onClick={() => setIsEditing(false)}
            >
              {t("trip.collapse")}
            </button>
          )}
        </div>
        {error && (
          <p className="trip__error" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
