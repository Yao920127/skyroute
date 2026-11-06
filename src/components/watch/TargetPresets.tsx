import { useI18n } from "../../i18n/i18n.ts";
import { TARGET_DROP_PRESETS, discountedPrice, percentBelow } from "../../lib/targetPrice.ts";
import { Select } from "../ui/Select.tsx";

type Props = {
  /** 目前價格（與目標價同幣別）；沒有價格時不顯示 */
  base: number | null;
  value: string;
  onPick: (target: string) => void;
};

const CUSTOM = "custom";

/**
 * 依跌幅設定目標價：選「−20%」就填入目前價格 × 0.8。
 * 直接在輸入框打任意金額也可以，這時選單顯示「自訂金額」並標出比目前價格低多少。
 */
export function TargetPresets({ base, value, onPick }: Props) {
  const { t } = useI18n();
  if (!base) return null;
  const presetOf = (pct: number) => String(discountedPrice(base, pct));
  const matched = TARGET_DROP_PRESETS.find((pct) => presetOf(pct) === value.trim());
  const below = percentBelow(base, value);
  return (
    <div className="target-presets">
      <Select
        size="sm"
        className="target-presets__select"
        value={matched ? String(matched) : CUSTOM}
        onValueChange={(v) => v !== CUSTOM && onPick(presetOf(Number(v)))}
        ariaLabel={t("watch.byDrop")}
        options={[
          { value: CUSTOM, label: t("watch.customTarget"), disabled: true },
          ...TARGET_DROP_PRESETS.map((pct) => ({
            value: String(pct),
            label: t("watch.dropPreset", { n: pct }),
          })),
        ]}
      />
      {below !== null && (
        <span className="target-presets__hint">{t("watch.belowNow", { n: below })}</span>
      )}
    </div>
  );
}
