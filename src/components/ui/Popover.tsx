import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import "./ui.css";

type TriggerProps = {
  id: string;
  "aria-haspopup": "dialog";
  "aria-expanded": boolean;
  "aria-controls": string;
  onClick: () => void;
};

type Props = {
  /** 觸發按鈕；需把 props 展開到 <button> 上 */
  trigger: (props: TriggerProps) => ReactNode;
  /** 面板內容；close() 可在選完後關閉 */
  children: (close: () => void) => ReactNode;
  label: string;
  align?: "start" | "end";
  className?: string;
};

/**
 * shadcn 風格的 Popover：電腦／平板上是貼著觸發按鈕的浮動面板，
 * 手機上（≤ 640px）以 CSS 改成底部抽屜。點外面或按 Esc 關閉，關閉後焦點回到觸發按鈕。
 */
export function Popover({ trigger, children, label, align = "start", className }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const triggerId = `${id}-trigger`;
  const panelId = `${id}-panel`;

  const close = () => {
    setIsOpen(false);
    document.getElementById(triggerId)?.focus();
  };

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    addEventListener("keydown", onKey);
    addEventListener("pointerdown", onPointer);
    // 開啟後把焦點移進面板，方便鍵盤操作
    panelRef.current?.querySelector<HTMLElement>("[data-autofocus], button, input")?.focus();
    return () => {
      removeEventListener("keydown", onKey);
      removeEventListener("pointerdown", onPointer);
    };
    // close 只依賴穩定的 triggerId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  return (
    <div className={`popover ${className ?? ""}`} ref={rootRef}>
      {trigger({
        id: triggerId,
        "aria-haspopup": "dialog",
        "aria-expanded": isOpen,
        "aria-controls": panelId,
        onClick: () => setIsOpen((v) => !v),
      })}
      {isOpen && (
        <>
          <div className="popover__scrim" aria-hidden="true" onClick={() => setIsOpen(false)} />
          <div
            ref={panelRef}
            id={panelId}
            role="dialog"
            aria-label={label}
            className={`popover__panel popover__panel--${align}`}
          >
            {children(close)}
          </div>
        </>
      )}
    </div>
  );
}
