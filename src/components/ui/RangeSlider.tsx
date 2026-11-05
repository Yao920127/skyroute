import { useEffect, useId, useState } from "react";

type Props = {
  label: string;
  min: number;
  max: number;
  step: number;
  /** 目前套用的範圍 */
  value: [number, number];
  /** 放開把手（或鍵盤調整結束）時才回報，避免拖曳過程不斷重新查詢 */
  onCommit: (next: [number, number]) => void;
  format: (value: number) => string;
  minLabel: string;
  maxLabel: string;
};

/**
 * 雙把手範圍滑桿（shadcn Slider 風格）。
 * 以兩個原生 range input 疊合，鍵盤、螢幕報讀與觸控都有原生支援。
 */
export function RangeSlider({
  label,
  min,
  max,
  step,
  value,
  onCommit,
  format,
  minLabel,
  maxLabel,
}: Props) {
  const id = useId();
  const [draft, setDraft] = useState<[number, number]>(value);
  const [lo, hi] = draft;

  // 外部值改變（例如清除篩選）時同步
  useEffect(() => setDraft(value), [value[0], value[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  const span = Math.max(max - min, 1);
  const left = ((lo - min) / span) * 100;
  const right = ((hi - min) / span) * 100;
  const commit = () => {
    if (draft[0] !== value[0] || draft[1] !== value[1]) onCommit(draft);
  };
  const commitEvents = { onPointerUp: commit, onKeyUp: commit, onBlur: commit, onTouchEnd: commit };

  return (
    <div className="range" role="group" aria-labelledby={`${id}-label`}>
      <div className="range__head">
        <span id={`${id}-label`} className="visually-hidden">
          {label}
        </span>
        <output className="range__value mono" htmlFor={`${id}-lo ${id}-hi`}>
          {format(lo)} – {format(hi)}
        </output>
      </div>
      <div className="range__track">
        <div className="range__fill" style={{ left: `${left}%`, right: `${100 - right}%` }} />
        <input
          id={`${id}-lo`}
          type="range"
          min={min}
          max={max}
          step={step}
          value={lo}
          aria-label={minLabel}
          aria-valuetext={format(lo)}
          onChange={(e) => setDraft([Math.min(Number(e.target.value), hi), hi])}
          {...commitEvents}
        />
        <input
          id={`${id}-hi`}
          type="range"
          min={min}
          max={max}
          step={step}
          value={hi}
          aria-label={maxLabel}
          aria-valuetext={format(hi)}
          onChange={(e) => setDraft([lo, Math.max(Number(e.target.value), lo)])}
          {...commitEvents}
        />
      </div>
      <div className="range__scale mono" aria-hidden="true">
        <span>{format(min)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}
