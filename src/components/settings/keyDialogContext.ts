import { createContext, useContext } from "react";

/** 讓任何元件（例如搜尋錯誤提示）都能打開 API 金鑰設定對話框 */
export const KeyDialogContext = createContext<() => void>(() => undefined);

export function useOpenKeyDialog(): () => void {
  return useContext(KeyDialogContext);
}
