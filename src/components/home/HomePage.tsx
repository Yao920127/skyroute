import "./home.css";
import type { View } from "../../hooks/useUrlState.ts";
import { useI18n } from "../../i18n/i18n.ts";
import type { MessageKey } from "../../i18n/messages.ts";
import { addDays } from "../../lib/format.ts";
import { defaultSearchState, serializeSearchState } from "../../lib/searchState.ts";
import type { SearchState } from "../../lib/types.ts";
import { HeroMedia } from "./HeroMedia.tsx";

type Props = {
  trackingCount: number;
  onNavigate: (view: View, query?: string) => void;
};

const POPULAR_ROUTES = ["TYO", "OSA", "SEL", "BKK", "SIN", "LON"] as const;
const STACK = ["Duffel Flights API", "FastAPI", "PostgreSQL", "Redis", "React"];

const CAPABILITIES: { n: 1 | 2 | 3; view: View; icon: "route" | "grid" | "pulse" }[] = [
  { n: 1, view: "explore", icon: "route" },
  { n: 2, view: "matrix", icon: "grid" },
  { n: 3, view: "board", icon: "pulse" },
];

const PIPELINE = [1, 2, 3, 4, 5] as const;
const SPECS = [1, 2, 3, 4, 5, 6] as const;
const SPEC_TAGS = ["Cache-Aside", "Token bucket", "Topology", "Fare matrix", "Alerting", "FX"];

const todayIso = () => new Date().toISOString().slice(0, 10);

export function HomePage({ trackingCount, onNavigate }: Props) {
  const { t } = useI18n();
  const today = todayIso();
  const base = defaultSearchState(today);

  const search = (next: Partial<SearchState>) =>
    onNavigate("explore", serializeSearchState({ ...base, ...next }));

  const searchTo = (destination: string) =>
    search({
      destination,
      departure_date: addDays(today, 30),
      return_date: addDays(today, 37),
    });

  // 示範：台北→倫敦、巴黎→台北，分段購票可各挑航司
  const tryMultiCity = () =>
    search({
      trip_type: "mc",
      mode: "split",
      origin: "TPE",
      destination: "LON",
      departure_date: addDays(today, 40),
      return_date: null,
      extra_legs: [{ origin: "PAR", destination: "TPE", departure_date: addDays(today, 50) }],
    });

  return (
    <div className="home">
      <section className="hero" aria-labelledby="hero-title">
        <p className="label">{t("home.kicker")}</p>
        <h1 id="hero-title" className="hero__title">
          {t("home.title1")}
          <br />
          {t("home.title2")}
        </h1>
        <p className="hero__lead">{t("home.lead")}</p>
        <div className="hero__actions">
          <button
            type="button"
            className="btn btn--primary btn--lg"
            onClick={() => onNavigate("explore")}
          >
            {t("home.cta")}
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => onNavigate("board")}>
            {trackingCount > 0 ? t("home.ctaBoardN", { n: trackingCount }) : t("home.ctaBoard")}
          </button>
        </div>

        <HeroMedia />

        <div className="routes" aria-label={t("home.routesAria")}>
          <p className="label">{t("home.routes")}</p>
          <div className="routes__list">
            {POPULAR_ROUTES.map((code) => (
              <button
                key={code}
                type="button"
                className="route-pill"
                onClick={() => searchTo(code)}
              >
                <span className="mono">TPE → {code}</span>
                <span>{t(`city.${code}`)}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="stack" aria-label={t("home.stackAria")}>
        <p className="stack__lead">{t("home.stackLead")}</p>
        <ul className="stack__list">
          {STACK.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      </section>

      <section className="capabilities" aria-labelledby="cap-title">
        <header className="section-head">
          <p className="label">{t("home.capKicker")}</p>
          <h2 id="cap-title" className="section-head__title">
            {t("home.capTitle")}
          </h2>
        </header>
        <div className="capabilities__grid">
          {CAPABILITIES.map((c) => {
            const key = (suffix: string) => `home.cap${c.n}.${suffix}` as MessageKey;
            return (
              <article key={c.n} className="capability">
                <CapabilityIcon kind={c.icon} />
                <p className="label">{t(key("kicker"))}</p>
                <h3 className="capability__title">{t(key("title"))}</h3>
                <p className="capability__body">{t(key("body"))}</p>
                <button type="button" className="btn btn--ghost" onClick={() => onNavigate(c.view)}>
                  {t(key("link"))} →
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="mix" aria-labelledby="mix-title">
        <div className="mix__copy">
          <p className="label">{t("home.newKicker")}</p>
          <h2 id="mix-title" className="section-head__title">
            {t("home.newTitle")}
          </h2>
          <p className="formula__lead">{t("home.newBody")}</p>
          <button type="button" className="btn btn--primary btn--lg" onClick={tryMultiCity}>
            {t("home.newLink")} →
          </button>
        </div>
        <ol className="mix__legs" aria-hidden="true">
          <li>
            <span className="mono">TPE → LHR</span>
            <strong>CI</strong>
            <small>{t("trip.leg", { n: 1 })}</small>
          </li>
          <li>
            <span className="mono">CDG → TPE</span>
            <strong>BR</strong>
            <small>{t("trip.leg", { n: 2 })}</small>
          </li>
          <li className="mix__currencies mono">TWD · USD · EUR · GBP · JPY · KRW …</li>
        </ol>
      </section>

      <section className="band" aria-labelledby="band-title">
        <div className="band__head">
          <p className="label label--on-dark">{t("home.bandKicker")}</p>
          <h2 id="band-title" className="band__title">
            {t("home.bandTitle1")}
            <br />
            {t("home.bandTitle2")}
          </h2>
          <p className="band__lead">{t("home.bandLead")}</p>
        </div>
        <ol className="pipeline">
          {PIPELINE.map((n) => (
            <li key={n} className="pipeline__step">
              <span className="pipeline__num mono">0{n}</span>
              <h3>{t(`home.p${n}.title`)}</h3>
              <p>{t(`home.p${n}.body`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="formula" aria-labelledby="formula-title">
        <div className="formula__copy">
          <p className="label">{t("home.fKicker")}</p>
          <h2 id="formula-title" className="section-head__title">
            {t("home.fTitle1")}
            <br />
            {t("home.fTitle2")}
          </h2>
          <p className="formula__lead">{t("home.fLead")}</p>
        </div>
        <div className="formula__card">
          <p className="label">{t("home.fCard")}</p>
          <p className="formula__expr mono">
            {t("home.fFare")}
            <br />+ ( {t("home.fFlight")}
            <br />+ {t("home.fLayover")} <em>× 1.5</em> )
            <br />× {t("home.fValue")}
          </p>
          <ul className="formula__tags">
            <li className="tag-chip tag-chip--green">{t("offer.tag.cheapest")}</li>
            <li className="tag-chip tag-chip--blue">{t("offer.tag.fastest")}</li>
            <li className="tag-chip tag-chip--dark">{t("offer.tag.best_value")}</li>
          </ul>
        </div>
      </section>

      <section className="specs" aria-labelledby="specs-title">
        <header className="section-head">
          <p className="label">{t("home.specsKicker")}</p>
          <h2 id="specs-title" className="section-head__title">
            {t("home.specsTitle")}
          </h2>
        </header>
        <table className="specs__table">
          <tbody>
            {SPECS.map((n, i) => (
              <tr key={n}>
                <th scope="row">{t(`home.s${n}`)}</th>
                <td>
                  <span className="pill-outline mono">{SPEC_TAGS[i]}</span>
                </td>
                <td className="specs__value mono">{t(`home.s${n}v`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="cta" aria-labelledby="cta-title">
        <h2 id="cta-title" className="cta__title">
          {t("home.ctaTitle1")}
          <br />
          {t("home.ctaTitle2")}
        </h2>
        <div className="cta__actions">
          <button
            type="button"
            className="btn btn--light btn--lg"
            onClick={() => onNavigate("explore")}
          >
            {t("home.cta")}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--on-dark"
            onClick={() => onNavigate("matrix")}
          >
            {t("home.ctaMatrix")}
          </button>
        </div>
      </section>
    </div>
  );
}

/** 細線幾何圖示（依 DESIGN.md：thin-line geometric illustrations）。 */
function CapabilityIcon({ kind }: { kind: "route" | "grid" | "pulse" }) {
  return (
    <svg className="capability__icon" viewBox="0 0 64 64" aria-hidden="true">
      {kind === "route" && (
        <>
          <circle cx="10" cy="48" r="4" />
          <circle cx="32" cy="18" r="4" />
          <circle cx="54" cy="44" r="4" />
          <path d="M13 45 Q20 24 29 20" />
          <path d="M35 20 Q48 26 52 40" />
          <path d="M14 48 H50" strokeDasharray="2 4" />
        </>
      )}
      {kind === "grid" &&
        [0, 1, 2, 3].flatMap((row) =>
          [0, 1, 2, 3].map((col) => (
            <rect
              key={`${row}-${col}`}
              x={8 + col * 13}
              y={8 + row * 13}
              width="10"
              height="10"
              rx="2"
              className={row === 2 && col === 1 ? "is-hot" : undefined}
            />
          )),
        )}
      {kind === "pulse" && (
        <>
          <path d="M6 40 L18 40 L24 28 L32 46 L40 18 L46 34 L58 34" />
          <path d="M6 24 H58" strokeDasharray="2 4" />
          <circle cx="40" cy="18" r="3" className="is-hot" />
        </>
      )}
    </svg>
  );
}
