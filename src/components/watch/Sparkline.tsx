import { useI18n } from "../../i18n/i18n.ts";
import { priceTrend, TREND_VAR } from "../../lib/priceTrend.ts";
import { sparklinePath } from "../../lib/sparkline.ts";

type Props = {
  values: number[];
  className?: string;
};

const WIDTH = 120;
const HEIGHT = 32;

/** 卡片上的迷你走勢線：終點比起點低（降價）→ 綠，高 → 紅。 */
export function Sparkline({ values, className }: Props) {
  const { t } = useI18n();
  if (values.length < 2) {
    return <span className={`${className ?? ""} spark--empty`}>{t("card.sparkEmpty")}</span>;
  }
  const path = sparklinePath(values, WIDTH, HEIGHT);
  const tone = TREND_VAR[priceTrend(values)];
  return (
    <svg
      className={className}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      role="img"
      aria-label={t("card.sparkAria", { n: values.length })}
    >
      <path d={path} fill="none" stroke={tone} strokeWidth={1.75} strokeLinejoin="round" />
    </svg>
  );
}
