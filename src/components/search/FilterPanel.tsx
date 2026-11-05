import { useI18n } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { formatDuration } from "../../lib/format.ts";
import type { SearchResult, SearchState } from "../../lib/types.ts";
import { RangeSlider } from "../ui/RangeSlider.tsx";
import { Checkbox } from "../ui/Checkbox.tsx";

type Props = {
  state: SearchState;
  result: SearchResult | undefined;
  onChange: (next: SearchState) => void;
};

const LAYOVER_MAX = 12 * 60;
const LAYOVER_STEP = 15;
const DURATION_STEP = 15;

const toggle = (list: string[], value: string) =>
  list.includes(value) ? list.filter((v) => v !== value) : [...list, value].sort();

/** 價格滑桿的級距：依範圍大小取整，避免出現 1,234.57 這種刻度 */
function priceStep(span: number): number {
  if (span <= 200) return 1;
  if (span <= 2_000) return 10;
  if (span <= 20_000) return 100;
  return 1_000;
}

export function FilterPanel({ state, result, onChange }: Props) {
  const { locale, t } = useI18n();
  const set = <K extends keyof SearchState>(key: K, value: SearchState[K]) =>
    onChange({ ...state, [key]: value });

  // 結果中出現的樞紐 ∪ 使用者已選的樞紐（避免已選項目因被濾掉而消失）
  const hubs = [
    ...new Set([...(result?.hubs ?? []), ...state.allowed_hubs, ...state.excluded_hubs]),
  ].sort();

  const currency = result?.currency ?? null;
  const priceBounds = result?.price_bounds;
  const durationBounds = result?.duration_bounds;
  const pMin = priceBounds ? Math.floor(Number(priceBounds.min)) : 0;
  const pMax = priceBounds ? Math.ceil(Number(priceBounds.max)) : 0;
  const dMin = durationBounds ? Number(durationBounds.min) : 0;
  const dMax = durationBounds ? Number(durationBounds.max) : 0;

  // 拖到端點代表「不限」，送 null 讓後端不做限制
  const commitRange = (
    keys: [keyof SearchState, keyof SearchState],
    [lo, hi]: [number, number],
    [min, max]: [number, number],
  ) => onChange({ ...state, [keys[0]]: lo <= min ? null : lo, [keys[1]]: hi >= max ? null : hi });

  return (
    <aside className="filters" aria-label={t("explore.filtersTitle")}>
      <section className="filters__group">
        <h3 className="filters__title">{t("filter.price")}</h3>
        {priceBounds && pMax > pMin && currency ? (
          <RangeSlider
            label={currency}
            min={pMin}
            max={pMax}
            step={priceStep(pMax - pMin)}
            value={[state.price_min ?? pMin, state.price_max ?? pMax]}
            format={(v) => formatPrice(v, currency, locale)}
            minLabel={t("filter.rangeMin")}
            maxLabel={t("filter.rangeMax")}
            onCommit={(v) => commitRange(["price_min", "price_max"], v, [pMin, pMax])}
          />
        ) : (
          <p className="filters__hint">{t("filter.waiting")}</p>
        )}
      </section>

      <section className="filters__group">
        <h3 className="filters__title">{t("filter.duration")}</h3>
        {durationBounds && dMax > dMin ? (
          <RangeSlider
            label={t("filter.duration")}
            min={dMin}
            max={dMax}
            step={DURATION_STEP}
            value={[state.duration_min ?? dMin, state.duration_max ?? dMax]}
            format={formatDuration}
            minLabel={t("filter.rangeMin")}
            maxLabel={t("filter.rangeMax")}
            onCommit={(v) => commitRange(["duration_min", "duration_max"], v, [dMin, dMax])}
          />
        ) : (
          <p className="filters__hint">{t("filter.waiting")}</p>
        )}
      </section>

      <section className="filters__group">
        <h3 className="filters__title">{t("filter.stops")}</h3>
        <Checkbox checked={state.direct_only} onCheckedChange={(v) => set("direct_only", v)}>
          {t("filter.directOnly")}
        </Checkbox>
        <div className="segmented" role="radiogroup" aria-label={t("filter.maxStops")}>
          {[0, 1, 2].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={state.max_stops === n}
              disabled={state.direct_only}
              onClick={() => set("max_stops", n)}
            >
              {t("filter.stopsN", { n })}
            </button>
          ))}
        </div>
      </section>

      <section className="filters__group">
        <h3 className="filters__title">{t("filter.layover")}</h3>
        <RangeSlider
          label={t("filter.layover")}
          min={0}
          max={LAYOVER_MAX}
          step={LAYOVER_STEP}
          value={[
            Math.min(state.min_layover_minutes, LAYOVER_MAX),
            Math.min(state.max_layover_minutes, LAYOVER_MAX),
          ]}
          format={formatDuration}
          minLabel={t("filter.rangeMin")}
          maxLabel={t("filter.rangeMax")}
          onCommit={([lo, hi]) =>
            onChange({
              ...state,
              min_layover_minutes: lo,
              // 拖到最右端代表不限，交給後端上限（48 小時）
              max_layover_minutes: hi >= LAYOVER_MAX ? 2880 : hi,
            })
          }
        />
      </section>

      <section className="filters__group">
        <h3 className="filters__title">{t("filter.hubs")}</h3>
        <p className="filters__hint">{t("filter.hubsHint")}</p>
        {hubs.length === 0 ? (
          <p className="filters__hint">{t("filter.hubsNone")}</p>
        ) : (
          <div className="chips">
            {hubs.map((hub) => {
              const allowed = state.allowed_hubs.includes(hub);
              const avoided = state.excluded_hubs.includes(hub);
              const cycle = () => {
                if (!allowed && !avoided) {
                  onChange({ ...state, allowed_hubs: toggle(state.allowed_hubs, hub) });
                } else if (allowed) {
                  onChange({
                    ...state,
                    allowed_hubs: toggle(state.allowed_hubs, hub),
                    excluded_hubs: toggle(state.excluded_hubs, hub),
                  });
                } else {
                  onChange({ ...state, excluded_hubs: toggle(state.excluded_hubs, hub) });
                }
              };
              const mode = allowed ? "chip--allow" : avoided ? "chip--avoid" : "";
              const status = allowed
                ? t("filter.hubAllow")
                : avoided
                  ? t("filter.hubAvoid")
                  : t("filter.hubAny");
              return (
                <button
                  key={hub}
                  type="button"
                  className={`chip chip--hub ${mode}`}
                  aria-pressed={allowed || avoided}
                  aria-label={`${hub}: ${status}`}
                  onClick={cycle}
                >
                  {allowed ? "✓" : avoided ? "✕" : "·"} {hub}
                </button>
              );
            })}
          </div>
        )}
      </section>

      {result && result.airlines.length > 0 && (
        <section className="filters__group">
          <h3 className="filters__title">{t("filter.airlines")}</h3>
          <div className="chips">
            {result.airlines.map((a) => (
              <button
                key={a.code}
                type="button"
                className="chip chip--pick chip--airline"
                aria-pressed={state.airlines.includes(a.code)}
                onClick={() => set("airlines", toggle(state.airlines, a.code))}
              >
                {/* 同時顯示代碼與名稱，避免 CA（中國國際航空）與 CI（中華航空）這類相近代碼混淆 */}
                <span className="chip__code">{a.code}</span>
                <span className="chip__name">{a.name}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="filters__group">
        <h3 className="filters__title">{t("filter.timeValue")}</h3>
        <label className="field">
          <span>{t("filter.timeValueLabel", { currency: currency ?? "" })}</span>
          <input
            className="input mono"
            type="number"
            min={0}
            step={5}
            value={state.time_value_per_hour}
            onChange={(e) => set("time_value_per_hour", Number(e.target.value))}
          />
        </label>
        <p className="filters__formula mono">{t("filter.formula")}</p>
      </section>
    </aside>
  );
}
