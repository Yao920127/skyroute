import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import "./app.css";
import { HomePage } from "./components/home/HomePage.tsx";
import { ApiKeyDialog } from "./components/settings/ApiKeyDialog.tsx";
import { Footer } from "./components/layout/Footer.tsx";
import { Navbar } from "./components/layout/Navbar.tsx";
import { KeyDialogContext } from "./components/settings/keyDialogContext.ts";
import { FareMatrix } from "./components/matrix/FareMatrix.tsx";
import { ExploreView } from "./components/search/ExploreView.tsx";
import { TripForm } from "./components/search/TripForm.tsx";
import { WatchForm, type WatchDraft } from "./components/watch/WatchForm.tsx";
import { Watchboard } from "./components/watch/Watchboard.tsx";
import { useApiKey } from "./hooks/useApiKey.ts";
import { useI18n } from "./i18n/i18n.ts";
import type { MessageKey } from "./i18n/messages.ts";
import { useUrlState, type View } from "./hooks/useUrlState.ts";
import { api } from "./lib/api.ts";
import { maskKey } from "./lib/credentials.ts";
import { parseSearchState, serializeSearchState } from "./lib/searchState.ts";
import type { SearchState } from "./lib/types.ts";

const HEADLINES: Record<
  "explore" | "matrix",
  { kicker: MessageKey; title: MessageKey; lead: MessageKey }
> = {
  explore: {
    kicker: "head.explore.kicker",
    title: "head.explore.title",
    lead: "head.explore.lead",
  },
  matrix: {
    kicker: "head.matrix.kicker",
    title: "head.matrix.title",
    lead: "head.matrix.lead",
  },
};

const todayIso = () => new Date().toISOString().slice(0, 10);

export function App() {
  const { view, query, navigate } = useUrlState();
  const { t } = useI18n();
  const state = useMemo(() => parseSearchState(query, todayIso()), [query]);
  const hasSearch = new URLSearchParams(query).has("from");
  const [watchDraft, setWatchDraft] = useState<WatchDraft | null>(null);
  const [isKeyDialogOpen, setIsKeyDialogOpen] = useState(false);
  const apiKey = useApiKey();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
  const isKeyMissing = config.data?.has_server_key === false && !apiKey;
  const openKeyDialog = useCallback(() => setIsKeyDialogOpen(true), []);

  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: api.watchlists });
  const trackingCount = watchlists.data?.filter((w) => w.status === "TRACKING").length ?? 0;

  const update = (next: SearchState, target: View = view) =>
    navigate(target, serializeSearchState(next));
  const headline = view === "explore" || view === "matrix" ? HEADLINES[view] : null;

  const keyLabel = apiKey
    ? maskKey(apiKey.token)
    : isKeyMissing
      ? t("nav.keyMissing")
      : t("nav.keyServer");
  const keyTone = apiKey ? "own" : isKeyMissing ? "missing" : "server";

  return (
    <KeyDialogContext value={openKeyDialog}>
      <div className="announce" role="note">
        {isKeyMissing ? (
          <>
            {t("announce.missing")}{" "}
            <button type="button" className="announce__link" onClick={openKeyDialog}>
              {t("announce.missingLink")}
            </button>
          </>
        ) : apiKey?.mode === "live" ? (
          t("announce.live")
        ) : (
          t("announce.test")
        )}
      </div>

      <Navbar
        view={view}
        trackingCount={trackingCount}
        keyLabel={keyLabel}
        keyTone={keyTone}
        onNavigate={navigate}
        onOpenKey={openKeyDialog}
      />

      <div className="shell">
        <main className="stage">
          {headline && (
            <section
              className={`page-head ${hasSearch ? "page-head--has-results" : ""}`}
              aria-labelledby="page-title"
            >
              <div>
                <p className="label">{t(headline.kicker)}</p>
                <h1 id="page-title" className="page-head__title">
                  {t(headline.title)}
                </h1>
                <p className="page-head__lead">{t(headline.lead)}</p>
              </div>
            </section>
          )}

          {view === "home" && <HomePage trackingCount={trackingCount} onNavigate={navigate} />}

          {(view === "explore" || view === "matrix") && (
            <TripForm
              key={query}
              initial={state}
              isCollapsible={hasSearch}
              submitLabel={view === "matrix" ? t("trip.matrix") : t("trip.search")}
              allowMultiCity={view !== "matrix"}
              onSubmit={(next) => update(next)}
            />
          )}

          {view === "explore" && (
            <ExploreView
              state={state}
              enabled={hasSearch}
              onChange={(next) => update(next)}
              onWatch={setWatchDraft}
            />
          )}
          {view === "matrix" && (
            <FareMatrix
              state={state}
              enabled={hasSearch}
              onPick={(dep, ret) =>
                update({ ...state, departure_date: dep, return_date: ret }, "explore")
              }
            />
          )}
          {view === "board" && (
            <Watchboard query={watchlists} onCreate={() => setWatchDraft({ trip: state })} />
          )}
        </main>
      </div>

      <Footer onNavigate={navigate} onOpenKey={openKeyDialog} />

      {watchDraft && (
        <WatchForm
          draft={watchDraft}
          onClose={() => setWatchDraft(null)}
          onCreated={() => {
            setWatchDraft(null);
            navigate("board");
          }}
        />
      )}

      {isKeyDialogOpen && (
        <ApiKeyDialog config={config.data} onClose={() => setIsKeyDialogOpen(false)} />
      )}
    </KeyDialogContext>
  );
}
