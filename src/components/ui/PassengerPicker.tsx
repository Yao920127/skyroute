import { useI18n } from "../../i18n/i18n.ts";
import { CABINS, cabinLabel } from "../../lib/format.ts";
import type { CabinClass } from "../../lib/types.ts";
import { Popover } from "./Popover.tsx";

type Props = {
  adults: number;
  children: number;
  cabin: CabinClass;
  onChange: (next: { adults: number; children: number; cabin_class: CabinClass }) => void;
};

const MAX_PAX = 9;

/** 乘客人數（步進器）與艙等，收在一個 Popover 內 */
export function PassengerPicker({ adults, children, cabin, onChange }: Props) {
  const { t } = useI18n();
  const total = adults + children;
  const set = (patch: Partial<{ adults: number; children: number; cabin_class: CabinClass }>) =>
    onChange({ adults, children, cabin_class: cabin, ...patch });

  return (
    <Popover
      label={t("trip.travellers")}
      align="end"
      className="paxpicker"
      trigger={(props) => (
        <button type="button" className="paxfield" {...props}>
          <span className="datefield__label">{t("trip.travellers")}</span>
          <span className="datefield__value">
            {t("trip.paxSummary", { n: total, cabin: cabinLabel(cabin, t) })}
          </span>
        </button>
      )}
    >
      {(close) => (
        <div className="paxpicker__body">
          <Stepper
            label={t("trip.adults")}
            hint={t("trip.adultsHint")}
            value={adults}
            min={1}
            max={MAX_PAX - children}
            onChange={(v) => set({ adults: v })}
          />
          <Stepper
            label={t("trip.children")}
            hint={t("trip.childrenHint")}
            value={children}
            min={0}
            max={MAX_PAX - adults}
            onChange={(v) => set({ children: v })}
          />
          <div className="paxpicker__cabins" role="radiogroup" aria-label={t("trip.travellers")}>
            {CABINS.map((c) => (
              <button
                key={c}
                type="button"
                role="radio"
                aria-checked={cabin === c}
                className="paxpicker__cabin"
                onClick={() => set({ cabin_class: c })}
              >
                {cabinLabel(c, t)}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn--primary" onClick={close}>
            {t("common.done")}
          </button>
        </div>
      )}
    </Popover>
  );
}

function Stepper(props: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const { label, hint, value, min, max, onChange } = props;
  return (
    <div className="stepper">
      <div>
        <p className="stepper__label">{label}</p>
        <p className="stepper__hint">{hint}</p>
      </div>
      <div className="stepper__controls">
        <button
          type="button"
          className="stepper__btn"
          onClick={() => onChange(value - 1)}
          disabled={value <= min}
          aria-label={`${label} −1`}
        >
          −
        </button>
        <output className="stepper__value mono" aria-live="polite">
          {value}
        </output>
        <button
          type="button"
          className="stepper__btn"
          onClick={() => onChange(value + 1)}
          disabled={value >= max}
          aria-label={`${label} +1`}
        >
          +
        </button>
      </div>
    </div>
  );
}
