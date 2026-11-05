import { useI18n } from "../../i18n/i18n.ts";
import type { MessageKey } from "../../i18n/messages.ts";
import { heatColor, heatInk } from "../../lib/heat.ts";

/** 航線弧線：以 TPE 為中心，往東、南、西三個方向展開（純裝飾，比例非實際地理） */
const ARCS: { d: string; label: string; x: number; y: number }[] = [
  { d: "M260 250 Q360 120 520 130", label: "TYO", x: 528, y: 126 },
  { d: "M260 250 Q330 190 430 210", label: "SEL", x: 438, y: 206 },
  { d: "M260 250 Q250 330 190 380", label: "SIN", x: 150, y: 400 },
  { d: "M260 250 Q140 140 60 170", label: "LON", x: 22, y: 166 },
];

const CONSOLE_LINES: { time: string; text: MessageKey; tone?: "gain" | "muted" }[] = [
  { time: "03:00:00", text: "home.log1", tone: "muted" },
  { time: "03:00:01", text: "home.log2" },
  { time: "03:00:14", text: "home.log3" },
  { time: "03:00:14", text: "home.log4", tone: "gain" },
  { time: "03:00:15", text: "home.log5", tone: "muted" },
];

/** 7×7 示意矩陣：確定性的價格起伏，讓色階有高有低 */
const MATRIX = Array.from({ length: 7 }, (_, r) =>
  Array.from(
    { length: 7 },
    (_, c) => (Math.sin(r * 1.7 + c * 0.9) + Math.cos(c * 1.3 - r)) / 4 + 0.5,
  ),
);

export function HeroMedia() {
  const { t } = useI18n();
  return (
    <div className="hero-media">
      <figure className="media-card media-card--route">
        <svg className="route-map" viewBox="0 0 600 420" aria-hidden="true">
          <defs>
            <pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="1" fill="rgb(255 255 255 / 0.12)" />
            </pattern>
          </defs>
          <rect width="600" height="420" fill="url(#dots)" />
          {ARCS.map((a, i) => (
            <g key={a.label}>
              <path d={a.d} className="route-map__arc" style={{ animationDelay: `${i * 220}ms` }} />
              <text x={a.x} y={a.y} className="route-map__label">
                {a.label}
              </text>
            </g>
          ))}
          <circle cx="260" cy="250" r="6" className="route-map__origin" />
          <circle cx="260" cy="250" r="16" className="route-map__ring" />
          <text x="276" y="270" className="route-map__label route-map__label--origin">
            TPE
          </text>
        </svg>

        <div className="console-card" aria-label={t("home.consoleAria")}>
          <div className="console-card__head">
            <span className="console-card__status">
              <i aria-hidden="true" /> Patrol worker
            </span>
            <span className="console-card__badge">{t("home.demo")}</span>
          </div>
          <ol className="console-card__log">
            {CONSOLE_LINES.map((l) => (
              <li key={l.text} className={l.tone ? `is-${l.tone}` : undefined}>
                <time className="mono">{l.time}</time>
                <span>{t(l.text)}</span>
              </li>
            ))}
          </ol>
        </div>
      </figure>

      <figure className="media-card media-card--matrix" aria-label={t("home.matrixAria")}>
        <div className="mini-matrix" aria-hidden="true">
          {MATRIX.flatMap((row, r) =>
            row.map((t, c) => (
              <span
                key={`${r}-${c}`}
                style={{
                  background: heatColor(t),
                  color: heatInk(t),
                  animationDelay: `${(r + c) * 40}ms`,
                }}
              />
            )),
          )}
        </div>
        <figcaption>
          <span className="label">Fare matrix · {t("home.demo")}</span>
          <strong>{t("home.matrixCaption")}</strong>
          <span>{t("home.matrixSub")}</span>
        </figcaption>
      </figure>
    </div>
  );
}
