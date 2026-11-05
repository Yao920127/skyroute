import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useState } from "react";

import "./auth.css";
import "../ui/shadcn.css";
import { useAccount } from "../../hooks/useAccount.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { useOpenLogin } from "./loginContext.ts";
import { useSignOut } from "./useSignOut.ts";

type Props = {
  onOpenKey: () => void;
};

function initialOf(name: string | null, email: string): string {
  return (name?.trim() || email).charAt(0).toUpperCase();
}

/** 導覽列右側的帳號入口：未登入顯示「登入」，已登入顯示頭像與選單 */
export function AccountMenu({ onOpenKey }: Props) {
  const { t } = useI18n();
  const { isAuthEnabled, account, isLoading } = useAccount();
  const openLogin = useOpenLogin();
  const signOut = useSignOut();
  const [isOpen, setIsOpen] = useState(false);

  if (!isAuthEnabled || isLoading) return null;

  if (!account) {
    return (
      <button type="button" className="btn btn--primary account__signin" onClick={openLogin}>
        {t("auth.signIn")}
      </button>
    );
  }

  return (
    <PopoverPrimitive.Root open={isOpen} onOpenChange={setIsOpen}>
      <PopoverPrimitive.Trigger
        className="account__avatar"
        aria-label={t("auth.menu", { email: account.email })}
      >
        {account.picture ? (
          <img src={account.picture} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span aria-hidden="true">{initialOf(account.name, account.email)}</span>
        )}
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className="sc-popover account__menu"
          align="end"
          sideOffset={8}
          collisionPadding={12}
        >
          <div className="account__who">
            <strong>{account.name ?? account.email}</strong>
            <span>{account.email}</span>
          </div>
          <div className="account__key">
            <span className="label">{t("auth.keyLabel")}</span>
            <span className="mono">{account.key_mask ?? t("auth.keyDefault")}</span>
          </div>
          <button
            type="button"
            className="account__item"
            onClick={() => {
              setIsOpen(false);
              onOpenKey();
            }}
          >
            {t("auth.keySettings")}
          </button>
          <button
            type="button"
            className="account__item account__item--danger"
            disabled={signOut.isPending}
            onClick={() => signOut.mutate(undefined, { onSuccess: () => setIsOpen(false) })}
          >
            {t("auth.signOut")}
          </button>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
