import { useCallback, useSyncExternalStore } from "react";

/** 手機與平板（直向）共用「緊湊版」互動：底部導覽、抽屜式篩選與詳情 */
export const COMPACT_QUERY = "(max-width: 1024px)";

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => matchMedia(query).matches,
    () => false,
  );
}

export function useIsCompact(): boolean {
  return useMediaQuery(COMPACT_QUERY);
}
