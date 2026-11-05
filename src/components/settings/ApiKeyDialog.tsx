import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import "./settings.css";
import { useApiKey } from "../../hooks/useApiKey.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import { clearKey, keyMode, maskKey, saveKey } from "../../lib/credentials.ts";
import type { Account, AppConfig } from "../../lib/types.ts";
import { Checkbox } from "../ui/Checkbox.tsx";

type Props = {
  config: AppConfig | undefined;
  /** 已登入時金鑰存在帳號（伺服器端加密）；未登入時存在這台瀏覽器 */
  account: Account | null;
  onClose: () => void;
};

const DUFFEL_DASHBOARD = "https://app.duffel.com/";

export function ApiKeyDialog({ config, account, onClose }: Props) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputId = useId();
  const browserKey = useApiKey();
  const current = account
    ? account.key_mask && account.key_mode
      ? { mask: account.key_mask, mode: account.key_mode }
      : null
    : browserKey
      ? { mask: maskKey(browserKey.token), mode: browserKey.mode }
      : null;
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(browserKey?.remembered ?? false);
  const [isRevealed, setIsRevealed] = useState(false);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  const resetDependentQueries = () =>
    queryClient.invalidateQueries({
      predicate: (q) => q.queryKey[0] === "search" || q.queryKey[0] === "watchlists",
    });

  const verify = useMutation({
    mutationFn: async (value: string) => {
      if (account) {
        queryClient.setQueryData(["me"], await api.saveAccountKey(value));
      } else {
        await api.verifyKey(value);
        saveKey(value, remember);
      }
    },
    onSuccess: async () => {
      setToken("");
      await resetDependentQueries();
      dialogRef.current?.close();
    },
  });

  const clear = useMutation({
    mutationFn: async () => {
      if (account) queryClient.setQueryData(["me"], await api.clearAccountKey());
      else clearKey();
    },
    onSuccess: resetDependentQueries,
  });

  const trimmed = token.trim();
  const mode = trimmed ? keyMode(trimmed) : null;
  const formatError = trimmed && !mode ? t("key.format") : null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (mode) verify.mutate(trimmed);
  };

  const status = current
    ? t("key.own", { mask: current.mask, mode: t(`key.mode.${current.mode}`) })
    : config?.has_server_key
      ? t("key.server")
      : t("key.none");
  // 介紹文字中的連結：以佔位符切開字串，連結本身維持可點擊
  const [introBefore, introAfter] = t("key.intro").split("{link}");

  return (
    <dialog
      ref={dialogRef}
      className="sheet keysheet"
      onClose={onClose}
      aria-labelledby="key-title"
    >
      <form className="sheet__body" onSubmit={handleSubmit}>
        <header className="sheet__head">
          <p className="sheet__kicker mono">{t("key.kicker")}</p>
          <h2 id="key-title">{t("key.title")}</h2>
          <p className="sheet__trip">
            {introBefore}
            <a href={DUFFEL_DASHBOARD} target="_blank" rel="noopener noreferrer">
              Duffel Dashboard
            </a>
            {introAfter}
          </p>
        </header>

        <div className={`keysheet__status ${current ? "is-own" : ""}`} role="status">
          <span className="keysheet__dot" aria-hidden="true" />
          <span>
            {t("key.using")}
            <strong>{status}</strong>
          </span>
          {current && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => clear.mutate()}
              disabled={clear.isPending}
            >
              {t("common.clear")}
            </button>
          )}
        </div>

        <label className="field" htmlFor={inputId}>
          <span>{current ? t("key.replace") : t("key.enter")}</span>
          <div className="keysheet__input">
            <input
              id={inputId}
              className="input mono"
              type={isRevealed ? "text" : "password"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="duffel_test_…"
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="off"
              maxLength={220}
              aria-invalid={Boolean(formatError)}
            />
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setIsRevealed((v) => !v)}
              aria-pressed={isRevealed}
            >
              {isRevealed ? t("key.hide") : t("key.show")}
            </button>
          </div>
        </label>
        {formatError && <p className="keysheet__error">{formatError}</p>}
        {mode === "live" && <p className="keysheet__warn">{t("key.liveWarn")}</p>}

        {!account && (
          <Checkbox checked={remember} onCheckedChange={setRemember}>
            {t("key.remember")}
          </Checkbox>
        )}

        <ul className="keysheet__notes">
          {account ? (
            <>
              <li>{t("key.accountNote1", { email: account.email })}</li>
              <li>{t("key.accountNote2")}</li>
            </>
          ) : (
            <>
              <li>{t("key.note1")}</li>
              <li>{t("key.note2")}</li>
              <li>{config?.can_store_user_key === false ? t("key.note3off") : t("key.note3")}</li>
            </>
          )}
        </ul>

        {(verify.error ?? clear.error) && (
          <p className="notice" role="alert">
            {(verify.error ?? clear.error)?.message}
          </p>
        )}

        <footer className="sheet__foot">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => dialogRef.current?.close()}
          >
            {t("common.close")}
          </button>
          <button type="submit" className="btn btn--primary" disabled={!mode || verify.isPending}>
            {verify.isPending ? t("key.verifying") : t("key.verify")}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
