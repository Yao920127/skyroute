import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api.ts";
import { forgetGoogleSelection } from "../../lib/googleIdentity.ts";

/** 登出：清除工作階段 Cookie，並清空所有與帳號相關的快取資料 */
export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      forgetGoogleSelection();
      queryClient.setQueryData(["me"], null);
      queryClient.removeQueries({ queryKey: ["watchlists"] });
      await queryClient.invalidateQueries();
    },
  });
}
