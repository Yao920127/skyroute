import { useI18n } from "../../i18n/i18n.ts";
import { TARGET_DROP_PRESETS, discountedPrice, percentBelow } from "../../lib/targetPrice.ts";

type Props = {
  /** 目前價格（與目標價同幣別）；沒有價格時不顯示 */
  base: number | null;
  value: string;
  onPick: (target: string) => void;
};

/** 目標價下方的快捷鍵：比目前價格低 10／20／30%，並顯示目前輸入的目標比現價低多少 */
export function TargetPresets({ base, value, onPick }: Props) {
  const { t } = useI18n();
  if (!base) return null;
  const below = percentBelow(base, value);
  return (
    <div className="target-presets">
      {TARGET_DROP_PRESETS.map((pct) => {
        const price = String(discountedPrice(base, pct));
        return (
          <button
            key={pct}
            type="button"
            className={`chip ${value === price ? "is-on" : ""}`}
            aria-pressed={value === price}
            onClick={() => onPick(price)}
          >
            −{pct}%
          </button>
        );
      })}
      {below !== null && (
        <span className="target-presets__hint">{t("watch.belowNow", { n: below })}</span>
      )}
    </div>
  );
}
