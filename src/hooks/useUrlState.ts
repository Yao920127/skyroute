import { useCallback, useEffect, useState } from "react";

export type View = "home" | "explore" | "matrix" | "board";
const VIEWS: View[] = ["home", "explore", "matrix", "board"];

function readView(): View {
  const v = new URLSearchParams(location.search).get("view") as View | null;
  return v && VIEWS.includes(v) ? v : "home";
}

/** 目前頁籤與搜尋條件都放在 URL，方便分享、書籤與上一頁。 */
export function useUrlState(): {
  view: View;
  query: string;
  navigate: (view: View, query?: string) => void;
} {
  const [snapshot, setSnapshot] = useState(() => ({ view: readView(), query: location.search }));

  useEffect(() => {
    const onPop = () => setSnapshot({ view: readView(), query: location.search });
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((view: View, query?: string) => {
    const params = new URLSearchParams(query ?? location.search);
    params.set("view", view);
    const next = `?${params.toString()}`;
    const isNewPage = view !== readView();
    if (next !== location.search) history.pushState(null, "", next);
    // 切換頁面時回到頂端（例如從頁尾連結點過來）；同頁內改篩選則維持捲動位置
    if (isNewPage) scrollTo({ top: 0 });
    setSnapshot({ view, query: next });
  }, []);

  return { view: snapshot.view, query: snapshot.query, navigate };
}
