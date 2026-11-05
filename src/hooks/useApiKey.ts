import { useSyncExternalStore } from "react";

import { getKey, subscribeKey, type StoredKey } from "../lib/credentials.ts";

export function useApiKey(): StoredKey | null {
  return useSyncExternalStore(subscribeKey, getKey, getKey);
}
