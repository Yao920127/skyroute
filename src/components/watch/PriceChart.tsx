import { Liveline, type LivelinePoint } from "liveline";
import { useMemo } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import type { PricePoint } from "../../lib/types.ts";

type Props = {
  points: PricePoint[];
  targetPrice: number | null;
};

// liveline 以 canvas 繪製，讀不到 CSS 變數；色碼對應 tokens.css 的 --gain
const LINE_COLOR = "#0b7a5c";
const MIN_WINDOW_S = 60 * 60;
const WINDOW_PADDING = 1.04;

/** 「11/6 14:30」：巡檢可以短到每 5 分鐘一次，時間軸要到分鐘 */
function timeLabel(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
}

/**
 * 歷史票價走勢（liveline）：平滑曲線、不在每筆資料上畫點；目標價為參考線，滑過可看各時間點的價格。
 * liveline 是即時圖表，橫軸終點是「現在」，最新價格會延伸到現在，代表目前的價格。
 */
export default function PriceChart({ points, targetPrice }: Props) {
  const { locale, t } = useI18n();
  const currency = points[0]?.currency ?? "";

  const data = useMemo<LivelinePoint[]>(
    () =>
      points
        .map((p) => ({ time: Date.parse(p.recorded_at) / 1000, value: Number(p.price) }))
        .sort((a, b) => a.time - b.time),
    [points],
  );
  const latest = data[data.length - 1]?.value ?? 0;
  // 視窗涵蓋第一筆資料到現在，左右各留一點空間
  const windowSecs = Math.max(
    MIN_WINDOW_S,
    (Date.now() / 1000 - (data[0]?.time ?? Date.now() / 1000)) * WINDOW_PADDING,
  );

  return (
    <div className="price-chart">
      <Liveline
        data={data}
        value={latest}
        theme="light"
        color={LINE_COLOR}
        window={windowSecs}
        lineWidth={2}
        grid
        fill
        badge
        badgeVariant="minimal"
        pulse={false}
        momentum={false}
        referenceLine={
          targetPrice !== null ? { value: targetPrice, label: t("chart.target") } : undefined
        }
        formatValue={(v) => formatPrice(v, currency, locale)}
        formatTime={timeLabel}
      />
    </div>
  );
}
