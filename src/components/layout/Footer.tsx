import type { View } from "../../hooks/useUrlState.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { API_GUIDE_URL, ARCHITECTURE_MAP_URL, NAV_ITEMS, PRESENTATION_URL } from "./Navbar.tsx";

type Props = {
  onNavigate: (view: View) => void;
  onOpenKey: () => void;
};

const DUFFEL_DOCS = "https://duffel.com/docs";

/** 底部頁尾列：品牌、產品導覽、設定與資料來源 */
export function Footer({ onNavigate, onOpenKey }: Props) {
  const { t } = useI18n();
  return (
    <footer className="footbar">
      <div className="footbar__inner">
        <div className="footbar__brand">
          <span className="brand__mark" aria-hidden="true">
            ↗
          </span>
          <div>
            <p className="footbar__name">SkyRoute</p>
            <p className="footbar__tagline">{t("footer.tagline")}</p>
          </div>
        </div>

        <nav className="footbar__cols" aria-label={t("footer.product")}>
          <div className="footbar__col">
            <p className="footbar__heading">{t("footer.product")}</p>
            {NAV_ITEMS.map((item) => (
              <button key={item.id} type="button" onClick={() => onNavigate(item.id)}>
                {t(item.labelKey)}
              </button>
            ))}
          </div>
          <div className="footbar__col">
            <p className="footbar__heading">{t("footer.settings")}</p>
            <button type="button" onClick={onOpenKey}>
              {t("footer.apiKey")}
            </button>
            <a href={API_GUIDE_URL} target="_blank" rel="noopener">
              {t("footer.apiGuide")}
              <span className="visually-hidden">{t("common.newTab")}</span>
            </a>
            <a href={PRESENTATION_URL} target="_blank" rel="noopener">
              {t("footer.presentation")}
              <span className="visually-hidden">{t("common.newTab")}</span>
            </a>
            <a href={ARCHITECTURE_MAP_URL} target="_blank" rel="noopener noreferrer">
              {t("footer.archMap")}
              <span className="visually-hidden">{t("common.newTab")}</span>
            </a>
            <a href={DUFFEL_DOCS} target="_blank" rel="noopener noreferrer">
              {t("footer.docs")}
            </a>
          </div>
        </nav>
      </div>

      <div className="footbar__legal">
        <span>{t("footer.legal")}</span>
        <span className="mono">{t("footer.ops")}</span>
      </div>
    </footer>
  );
}
