import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import "./auth.css";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { clearKey } from "../../lib/credentials.ts";
import { renderGoogleButton } from "../../lib/googleIdentity.ts";
import { Sheet } from "../ui/Sheet.tsx";

type Props = {
  clientId: string;
  onClose: () => void;
};

/** 以 Google 帳號登入：按鈕由 Google 官方腳本繪製，取得的 ID Token 交給後端驗證 */
export function LoginDialog({ clientId, onClose }: Props) {
  const { lang, t } = useI18n();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [isButtonReady, setIsButtonReady] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const queryClient = useQueryClient();

  const login = useMutation({
    mutationFn: api.loginWithGoogle,
    onSuccess: async (account) => {
      // 帳號有自己的金鑰設定，不再使用存在這台瀏覽器的金鑰
      clearKey();
      queryClient.setQueryData(["me"], account);
      await queryClient.invalidateQueries();
      onClose();
    },
  });
  const { mutate } = login;

  useEffect(() => {
    const parent = buttonRef.current;
    if (!parent) return;
    renderGoogleButton(parent, clientId, lang === "en" ? "en" : "zh-TW", (credential) =>
      mutate(credential),
    )
      .then(() => setIsButtonReady(true))
      .catch(() => setLoadError(true));
  }, [clientId, lang, mutate]);

  return (
    <Sheet title={t("auth.title")} onClose={onClose}>
      <div className="login">
        <p className="login__lead">{t("auth.lead")}</p>
        <ul className="login__points">
          <li>{t("auth.point1")}</li>
          <li>{t("auth.point2")}</li>
          <li>{t("auth.point3")}</li>
        </ul>
        <div className="login__button" ref={buttonRef} aria-busy={!isButtonReady} />
        {!isButtonReady && !loadError && <p className="login__hint">{t("auth.loading")}</p>}
        {loadError && (
          <p className="notice" role="alert">
            {t("auth.loadFailed")}
          </p>
        )}
        {login.isPending && <p className="login__hint">{t("auth.signingIn")}</p>}
        {login.isError && (
          <p className="notice" role="alert">
            {login.error.message}
          </p>
        )}
      </div>
    </Sheet>
  );
}
