import "./auth.css";
import { useI18n } from "../../i18n/i18n.ts";
import { useOpenLogin } from "./loginContext.ts";

/** 需要登入的頁面區塊（例如看盤清單）未登入時顯示 */
export function LoginPrompt() {
  const { t } = useI18n();
  const openLogin = useOpenLogin();
  return (
    <div className="login-prompt">
      <h2>{t("auth.boardTitle")}</h2>
      <p>{t("auth.boardLead")}</p>
      <button type="button" className="btn btn--primary" onClick={openLogin}>
        {t("auth.signInGoogle")}
      </button>
    </div>
  );
}
