import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { PortalContainerContext } from "./portal.ts";

type Props = {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** full：手機上佔滿整個螢幕（用於看盤詳情）；預設為底部抽屜 */
  size?: "auto" | "full";
};

/**
 * 自適應抽屜：手機上從底部滑出，平板／電腦上為置中視窗。
 * 使用原生 <dialog>，自帶焦點鎖定與 Esc 關閉；點背景也可關閉。
 */
export function Sheet({ title, onClose, children, footer, size = "auto" }: Props) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const [dialogEl, setDialogEl] = useState<HTMLDialogElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    ref.current?.showModal();
    setDialogEl(ref.current);
  }, []);

  const close = () => ref.current?.close();

  return (
    <dialog
      ref={ref}
      className={`sheet panel panel--${size}`}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="panel__grip" aria-hidden="true" />
      <header className="panel__bar">
        <h2 id={titleId} className="panel__title">
          {title}
        </h2>
        <button
          type="button"
          className="panel__close"
          onClick={close}
          aria-label={t("common.close")}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </header>
      <PortalContainerContext value={dialogEl}>
        <div className="panel__scroll">{children}</div>
        {footer && <footer className="panel__foot">{footer}</footer>}
      </PortalContainerContext>
    </dialog>
  );
}
