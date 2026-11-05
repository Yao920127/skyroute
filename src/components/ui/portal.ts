import { createContext, useContext } from "react";

/**
 * Radix 的浮動層預設掛在 <body>。但原生 <dialog showModal> 位於瀏覽器 top layer，
 * 且會讓 dialog 以外的內容無法互動；因此在 dialog 內使用時，要把浮動層掛進 dialog 本身。
 */
export const PortalContainerContext = createContext<HTMLElement | null>(null);

export function usePortalContainer(): HTMLElement | undefined {
  return useContext(PortalContainerContext) ?? undefined;
}
