import { useState } from "react";

import { useI18n, type Translate } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { dayOffset, formatDuration, localTime } from "../../lib/format.ts";
import { stopsText } from "../../lib/stops.ts";
import { OfferDetail } from "./OfferDetail.tsx";
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

      {isOpen && <OfferDetail id={detailId} offer={offer} className="offer__detail" />}
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
