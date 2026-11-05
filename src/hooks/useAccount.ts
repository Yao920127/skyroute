import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.ts";
import type { Account, AppConfig } from "../lib/types.ts";

export function useAppConfig(): AppConfig | undefined {
  return useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity }).data;
}

export type AccountState = {
  /** 伺服器是否啟用 Google 登入 */
  isAuthEnabled: boolean;
  account: Account | null;
  isLoading: boolean;
};

/** 目前登入的帳號；伺服器未啟用 Google 登入時一律為 null（匿名模式） */
export function useAccount(): AccountState {
  const config = useAppConfig();
  const isAuthEnabled = Boolean(config?.google_client_id);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    enabled: isAuthEnabled,
    staleTime: 5 * 60_000,
  });
  return {
    isAuthEnabled,
    account: me.data ?? null,
    isLoading: config === undefined || (isAuthEnabled && me.isPending),
  };
}
