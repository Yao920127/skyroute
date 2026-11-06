import { useI18n } from "../../i18n/i18n.ts";
import { formatDuration, localDate, localTime } from "../../lib/format.ts";
import type { FlightOffer } from "../../lib/types.ts";
import "./offer-detail.css";

type Props = {
  offer: FlightOffer;
  id?: string;
  className?: string;
};

/** 航班詳細資料：每一航段的班號、時間、機型、共享班號、中途經停與轉機停留，以及退改票條件 */
export function OfferDetail({ offer, id, className = "" }: Props) {
  const { t } = useI18n();
  const conditionText = (value: boolean | null) =>
    value === null ? t("offer.cond.unknown") : value ? t("offer.cond.yes") : t("offer.cond.no");

  return (
    <div id={id} className={`offer-detail ${className}`}>
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
                    airport: stop.city_name ? `${stop.airport}（${stop.city_name}）` : stop.airport,
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
  );
}
