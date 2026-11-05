import { createContext, useContext } from "react";

/** 開啟「以 Google 帳號登入」視窗；任何需要登入的功能都可以呼叫 */
export const LoginDialogContext = createContext<() => void>(() => undefined);

export function useOpenLogin(): () => void {
  return useContext(LoginDialogContext);
}
