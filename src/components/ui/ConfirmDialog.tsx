import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

import "./shadcn.css";
import { useI18n } from "../../i18n/i18n.ts";
import { usePortalContainer } from "./portal.ts";

export type ConfirmOptions = {
  title: string;
  description?: string;
  confirmLabel?: string;
  tone?: "default" | "danger";
};

type Confirm = (options: ConfirmOptions) => Promise<boolean>;

/** 訊息第一行當標題、其餘當說明（i18n 字串以 \n 分隔） */
export function splitMessage(message: string): Pick<ConfirmOptions, "title" | "description"> {
  const [title = "", ...rest] = message.split("\n");
  return { title, description: rest.join("\n") || undefined };
}

const ConfirmContext = createContext<Confirm>(() => Promise.resolve(false));

/** shadcn/ui Alert Dialog：以 await confirm({...}) 取代瀏覽器原生 confirm() */
export function useConfirm(): Confirm {
  return useContext(ConfirmContext);
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const confirm = useCallback<Confirm>(
    (next) =>
      new Promise<boolean>((resolve) => {
        resolver.current = resolve;
        setOptions(next);
      }),
    [],
  );

  const settle = (ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setOptions(null);
  };

  return (
    <ConfirmContext value={confirm}>
      {children}
      {options && <ConfirmDialogView options={options} onSettle={settle} />}
    </ConfirmContext>
  );
}

function ConfirmDialogView({
  options,
  onSettle,
}: {
  options: ConfirmOptions;
  onSettle: (ok: boolean) => void;
}) {
  const { t } = useI18n();
  // 從原生 <dialog>（例如手機的看盤詳情抽屜）裡觸發時，掛進最上層的 dialog 才點得到
  const fallback = usePortalContainer();
  const container =
    fallback ?? (document.querySelector("dialog[open]") as HTMLElement | null) ?? undefined;
  return (
    <AlertDialog.Root open onOpenChange={(open) => !open && onSettle(false)}>
      <AlertDialog.Portal container={container}>
        <AlertDialog.Overlay className="sc-overlay" />
        <AlertDialog.Content className="sc-alert">
          <AlertDialog.Title className="sc-alert__title">{options.title}</AlertDialog.Title>
          {options.description ? (
            <AlertDialog.Description className="sc-alert__desc">
              {options.description}
            </AlertDialog.Description>
          ) : (
            <AlertDialog.Description className="visually-hidden">
              {options.title}
            </AlertDialog.Description>
          )}
          <div className="sc-alert__footer">
            <AlertDialog.Cancel className="sc-btn sc-btn--outline" onClick={() => onSettle(false)}>
              {t("common.cancel")}
            </AlertDialog.Cancel>
            <AlertDialog.Action
              className={`sc-btn ${options.tone === "danger" ? "sc-btn--destructive" : "sc-btn--default"}`}
              onClick={() => onSettle(true)}
            >
              {options.confirmLabel ?? t("common.done")}
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
