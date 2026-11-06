import { useQuery } from "@tanstack/react-query";

import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { formatPrice } from "../../lib/currency.ts";
import type { Watchlist } from "../../lib/types.ts";
import { OfferDetail } from "../search/OfferDetail.tsx";

type Props = {
  watch: Watchlist;
};

/** 看盤詳情的航班明細：最近一次巡檢選中的最低價航班（分段購票逐段列出） */
export function WatchItinerary({ watch }: Props) {
  const { locale, t } = useI18n();
  const itinerary = useQuery({
    queryKey: ["itinerary", watch.id, watch.stats.last_checked_at],
    queryFn: () => api.itinerary(watch.id),
  });
  const data = itinerary.data;
  const isSplit = (data?.offers.length ?? 0) > 1;

  return (
    <section className="itinerary" aria-labelledby={`itinerary-${watch.id}`}>
      <h4 id={`itinerary-${watch.id}`} className="detail__subtitle">
        {t("detail.flights")}
      </h4>
      {itinerary.isError && <p className="notice">{itinerary.error.message}</p>}
      {data === null && <p className="detail__muted">{t("detail.flightsEmpty")}</p>}
      {data && (
        <>
          <p className="detail__muted">
            {t("detail.flightsAt", {
              time: new Date(data.recorded_at).toLocaleString(locale, {
                hour12: false,
                month: "numeric",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              }),
            })}
          </p>
          {data.offers.map((offer, i) => (
            <div key={`${offer.id}-${i}`} className="itinerary__offer">
              <header className="itinerary__head">
                {offer.airline_logo && (
                  <img
                    src={offer.airline_logo}
                    alt=""
                    width={20}
                    height={20}
                    onError={(e) => {
                      e.currentTarget.hidden = true;
                    }}
                  />
                )}
                <span className="itinerary__airline">
                  {isSplit && <span className="mono">{t("detail.legN", { n: i + 1 })} · </span>}
                  {offer.airline_name}
                </span>
                {offer.is_simulated && (
                  <span className="sim-tag" title={t("offer.simulatedHint")}>
                    {t("offer.simulated")}
                  </span>
                )}
                {isSplit && (
                  <span className="mono itinerary__price">
                    {formatPrice(offer.total_amount, offer.currency, locale)}
                  </span>
                )}
              </header>
              <OfferDetail offer={offer} className="itinerary__legs" />
            </div>
          ))}
        </>
      )}
    </section>
  );
}
