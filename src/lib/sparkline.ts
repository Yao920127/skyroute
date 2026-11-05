/** 把數列轉成 SVG path；上下各留 2px 邊距，所有值相同時畫一條中線。 */
export function sparklinePath(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = i * step;
      const y = span === 0 ? height / 2 : pad + (1 - (v - min) / span) * (height - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
