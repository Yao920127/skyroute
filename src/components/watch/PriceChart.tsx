import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useI18n } from "../../i18n/i18n.ts";
import { formatPrice } from "../../lib/currency.ts";
import { formatNumber } from "../../lib/format.ts";
import type { PricePoint } from "../../lib/types.ts";

type Props = {
  points: PricePoint[];
  targetPrice: number | null;
  weekAvg: number | null;
};

const AXIS_STYLE = {
  fontFamily: "IBM Plex Mono, monospace",
  fontSize: 11,
  fill: "#75758a",
};

function tick(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}h`;
}

// Recharts 的 SVG 屬性無法讀 CSS 變數，這裡的色碼對應 tokens.css
/** 歷史票價折線圖：目標價（深綠虛線）與 7 日均價（灰虛線）作為參考。 */
export default function PriceChart({ points, targetPrice, weekAvg }: Props) {
  const { locale, t } = useI18n();
  const data = points.map((p) => ({
    t: p.recorded_at,
    price: Number(p.price),
    airline: p.airline_code,
  }));
  const currency = points[0]?.currency ?? "";
  const prices = data.map((d) => d.price);
  const bounds = [...prices, targetPrice ?? prices[0]];
  const min = Math.min(...bounds);
  const max = Math.max(...bounds);
  const pad = Math.max(1, (max - min) * 0.15);

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 12, right: 32, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#e5e7eb" strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey="t"
          tickFormatter={tick}
          tick={AXIS_STYLE}
          tickLine={false}
          axisLine={false}
          minTickGap={32}
        />
        <YAxis
          domain={[Math.floor(min - pad), Math.ceil(max + pad)]}
          tick={AXIS_STYLE}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(v: number) => formatNumber(v, locale)}
        />
        <Tooltip
          formatter={(value) => [formatPrice(Number(value), currency, locale), t("chart.lowest")]}
          labelFormatter={(label) =>
            typeof label === "string"
              ? new Date(label).toLocaleString(locale, { hour12: false })
              : ""
          }
          contentStyle={{ borderRadius: 6, border: "1px solid #d9d9dd", fontSize: 12 }}
        />
        {targetPrice !== null && (
          <ReferenceLine
            y={targetPrice}
            stroke="#003c33"
            strokeDasharray="6 4"
            label={{
              value: t("chart.target"),
              position: "insideTopLeft",
              fontSize: 11,
              fill: "#003c33",
            }}
          />
        )}
        {weekAvg !== null && <ReferenceLine y={weekAvg} stroke="#93939f" strokeDasharray="2 3" />}
        <Line
          type="monotone"
          dataKey="price"
          stroke="#17171c"
          strokeWidth={1.5}
          dot={{ r: 2.5, fill: "#ff7759", strokeWidth: 0 }}
          activeDot={{ r: 5, fill: "#ff7759", stroke: "#17171c" }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
