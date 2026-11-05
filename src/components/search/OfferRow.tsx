import { useState } from "react";

import { useI18n, type Translate } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { dayOffset, formatDuration, localDate, localTime } from "../../lib/format.ts";
import { stopsText } from "../../lib/stops.ts";
import type { RankedOffer, Slice } from "../../lib/types.ts";

type Props = {
  item: RankedOffer;
  /** 多航段整張票無法加入看盤時為 undefined */
  onWatch?: () => void;
  /** 多航段：段標籤用 1、2、3，而不是去／回 */
  isMultiCity?: boolean;
};

/** 每段行程的標籤：來回用「去／回」，多航段用 1、2、3… */
function sliceLabel(index: number, total: number, isMultiCity: boolean, t: Translate): string {
  if (isMultiCity) return t("offer.leg", { n: index + 1 });
  if (total === 2) return index === 0 ? t("offer.out") : t("offer.back");
  if (total === 1) return t("offer.out");
  return t("offer.leg", { n: index + 1 });
}

export function OfferRow({ item, onWatch, isMultiCity = false }: Props) {
  const { locale, t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const { offer } = item;
  const detailId = `detail-${offer.id}`;
  const conditionText = (value: boolean | null) =>
    value === null ? t("offer.cond.unknown") : value ? t("offer.cond.yes") : t("offer.cond.no");

  return (
    <li className={`offer ${item.tags.length ? "offer--tagged" : ""}`}>
      <div className="offer__airline">
        {offer.airline_logo ? (
          <img src={offer.airline_logo} alt="" width={28} height={28} loading="lazy" />
        ) : (
          <span className="offer__logo-fallback mono">{offer.airline_code}</span>
        )}
        <div>
          <strong>{offer.airline_name}</strong>
          {offer.is_simulated && (
            <span className="sim-tag" title={t("offer.simulatedHint")}>
              {t("offer.simulated")}
            </span>
          )}
          {item.tags.length > 0 && (
            <ul className="offer__tags" aria-label={t("offer.tags")}>
              {item.tags.map((tag) => (
                <li key={tag} className={`tag tag--${tag}`}>
                  {t(`offer.tag.${tag}`)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="offer__slices">
        {offer.slices.map((s, i) => (
          <SliceLine
            key={i}
            slice={s}
            label={sliceLabel(i, offer.slices.length, isMultiCity, t)}
            t={t}
          />
        ))}
      </div>

      <div className="offer__price">
        <span className="offer__amount mono">
          {formatPrice(offer.total_amount, offer.currency, locale)}
        </span>
        {offer.original_currency && offer.original_amount && (
          <span className="offer__original mono">
            {t("offer.original", {
              value: formatPrice(offer.original_amount, offer.original_currency, locale),
            })}
          </span>
        )}
        <span className="offer__cost mono" title={t("sort.cost")}>
          {t("offer.cost", { value: formatPrice(item.cost_index, offer.currency, locale) })}
        </span>
      </div>

      <div className="offer__actions">
        {onWatch ? (
          <button type="button" className="btn btn--primary" onClick={onWatch}>
            {t("offer.watch")}
          </button>
        ) : (
          <span className="offer__no-watch" title={t("offer.watchMulti")}>
            {t("offer.watchMulti")}
          </span>
        )}
        <button
          type="button"
          className="btn btn--ghost"
          aria-expanded={isOpen}
          aria-controls={detailId}
          onClick={() => setIsOpen((v) => !v)}
        >
          {isOpen ? t("offer.collapse") : t("offer.legs")}
        </button>
      </div>

      {isOpen && (
        <div id={detailId} className="offer__detail">
          {offer.slices.map((s, i) => (
            <ol key={i} className="legs">
              {s.segments.map((seg, j) => (
                <li key={seg.flight_number + j}>
                  <span className="mono legs__flight">{seg.flight_number}</span>
                  <span className="mono">
                    {seg.origin} {localDate(seg.departing_at)} {localTime(seg.departing_at)} →{" "}
                    {seg.destination} {localTime(seg.arriving_at)}
                  </span>
                  <span className="legs__meta">
                    {formatDuration(seg.duration_minutes)}
                    {seg.aircraft ? ` · ${seg.aircraft}` : ""}
                  </span>
                  {seg.operating_code && (
                    <span className="legs__operated">
                      {t("offer.operatedBy", { name: seg.operating_name ?? seg.operating_code })}
                    </span>
                  )}
                  {(seg.stops ?? []).map((stop) => (
                    <span key={stop.airport} className="legs__stop">
                      {t("offer.techStop", {
                        airport: stop.city_name
                          ? `${stop.airport}（${stop.city_name}）`
                          : stop.airport,
                        time: formatDuration(stop.minutes),
                      })}
                    </span>
                  ))}
                  {s.layovers[j] && (
                    <span className="legs__layover">
                      {t("offer.layoverAt", {
                        airport: s.layovers[j].airport,
                        time: formatDuration(s.layovers[j].minutes),
                      })}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          ))}
          <p className="offer__conditions">
            {t("offer.refund", { v: conditionText(offer.refundable) })} ·{" "}
            {t("offer.change", { v: conditionText(offer.changeable) })}
            {offer.emissions_kg ? ` · ${t("offer.emissions", { n: offer.emissions_kg })}` : ""}
          </p>
        </div>
      )}
    </li>
  );
}

function SliceLine({ slice, label, t }: { slice: Slice; label: string; t: Translate }) {
  const offset = dayOffset(slice.departing_at, slice.arriving_at);
  const { text: stopsLabel, isNonstop } = stopsText(slice, t);
  return (
    <div className="slice">
      <span className="slice__label">{label}</span>
      <span className="slice__time slice__time--dep mono">
        {localTime(slice.departing_at)}
        <small>{slice.origin}</small>
      </span>
      <span className="slice__track" aria-hidden="true">
        {slice.layovers.map((l) => (
          <i key={l.airport} className="slice__dot" />
        ))}
        {slice.segments.flatMap((seg) =>
          (seg.stops ?? []).map((stop) => (
            <i key={`stop-${stop.airport}`} className="slice__dot slice__dot--stop" />
          )),
        )}
      </span>
      <span className="slice__time slice__time--arr mono">
        {localTime(slice.arriving_at)}
        {offset > 0 && <sup>+{offset}</sup>}
        <small>{slice.destination}</small>
      </span>
      <span className="slice__info">
        <span className="mono">{formatDuration(slice.duration_minutes)}</span>
        <small className={isNonstop ? "slice__direct" : slice.stops === 0 ? "slice__via" : ""}>
          {stopsLabel}
        </small>
      </span>
    </div>
  );
}
