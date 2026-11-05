import { useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";

import "./watch.css";
import { useIsCompact } from "../../hooks/useMediaQuery.ts";
import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import type { PatrolReport, Watchlist } from "../../lib/types.ts";
import { WatchCard } from "./WatchCard.tsx";
import { Sheet } from "../ui/Sheet.tsx";
import { WatchDetail } from "./WatchDetail.tsx";
import { splitMessage, useConfirm } from "../ui/ConfirmDialog.tsx";
import { LoginPrompt } from "../auth/LoginPrompt.tsx";
import { routeText, watchLegs } from "../../lib/watchRoute.ts";

type Props = {
  query: UseQueryResult<Watchlist[]>;
  /** 已啟用 Google 登入但尚未登入：清單依帳號保存，先請使用者登入 */
  needsLogin: boolean;
  onCreate: () => void;
};

const STATUS_ORDER = { TRACKING: 0, EXPIRED: 1, CANCELLED: 2 } as const;

export function Watchboard({ query, needsLogin, onCreate }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const isCompact = useIsCompact();
  const { t } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();

  const patrol = useMutation<PatrolReport>({
    mutationFn: api.runPatrol,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });

  const items = [...(query.data ?? [])].sort(
    (a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      a.departure_date.localeCompare(b.departure_date),
  );
  const active = items.filter((w) => w.status === "TRACKING");
  const ended = items.filter((w) => w.status !== "TRACKING");
  const tracking = active.length;
  // 電腦版預設選第一檔追蹤中（沒有則第一筆）；平板／手機只有使用者點選時才開啟詳情抽屜
  const selected =
    items.find((w) => w.id === selectedId) ?? (isCompact ? undefined : (active[0] ?? items[0]));

  const purgeEnded = useMutation({
    mutationFn: api.purgeEndedWatchlists,
    onSuccess: async () => {
      setSelectedId(null);
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });
  const handlePurgeEnded = async () => {
    const ok = await confirm({
      ...splitMessage(t("board.purgeConfirm", { n: ended.length })),
      confirmLabel: t("board.purge"),
      tone: "danger",
    });
    if (ok) purgeEnded.mutate();
  };

  const renderCards = (list: Watchlist[]) =>
    list.map((w) => (
      <WatchCard
        key={w.id}
        watch={w}
        isSelected={w.id === selected?.id}
        onSelect={() => setSelectedId(w.id)}
      />
    ));

  return (
    <section className="board" aria-labelledby="board-heading">
      <header className="page-head">
        <div>
          <p className="label">{t("board.kicker")}</p>
          <h1 id="board-heading" className="page-head__title">
            {t("board.title")}
          </h1>
          <p className="page-head__lead">{t("board.lead", { n: tracking })}</p>
        </div>
        <div className="board__actions">
          <button
            type="button"
            className="btn"
            onClick={() => patrol.mutate()}
            disabled={patrol.isPending || tracking === 0}
          >
            {patrol.isPending ? t("board.patrolling") : t("board.patrol")}
          </button>
          <button type="button" className="btn btn--primary" onClick={onCreate}>
            {t("board.create")}
          </button>
        </div>
      </header>

      {needsLogin && <LoginPrompt />}
      {patrol.data && <PatrolSummary report={patrol.data} />}
      {patrol.isError && (
        <p className="notice" role="alert">
          {t("board.patrolFailed")}
          {patrol.error.message}
        </p>
      )}
      {query.isError && (
        <p className="notice" role="alert">
          {query.error.message}
        </p>
      )}

      {needsLogin ? null : query.isSuccess && items.length === 0 ? (
        <div className="empty">
          <p>{t("board.empty")}</p>
          <p>{t("board.emptyHint")}</p>
        </div>
      ) : (
        <div className="board__layout">
          <div className="board__lists">
            {active.length > 0 && (
              <section aria-labelledby="active-heading">
                {ended.length > 0 && (
                  <h3 id="active-heading" className="board__group">
                    {t("board.active")} <span className="mono">{active.length}</span>
                  </h3>
                )}
                <ul className="board__list" aria-label={t("board.active")}>
                  {renderCards(active)}
                </ul>
              </section>
            )}
            {ended.length > 0 && (
              <section aria-labelledby="ended-heading">
                <div className="board__group">
                  <h3 id="ended-heading">
                    {t("board.ended")} <span className="mono">{ended.length}</span>
                  </h3>
                  <button
                    type="button"
                    className="btn btn--ghost btn--danger"
                    onClick={handlePurgeEnded}
                    disabled={purgeEnded.isPending}
                  >
                    {purgeEnded.isPending ? t("board.purging") : t("board.purge")}
                  </button>
                </div>
                <ul className="board__list" aria-label={t("board.ended")}>
                  {renderCards(ended)}
                </ul>
              </section>
            )}
            {purgeEnded.isError && (
              <p className="notice" role="alert">
                {purgeEnded.error.message}
              </p>
            )}
          </div>
          {selected && !isCompact && (
            <WatchDetail key={selected.id} watch={selected} onDeleted={() => setSelectedId(null)} />
          )}
          {selected && isCompact && (
            <Sheet
              size="full"
              title={routeText(watchLegs(selected))}
              onClose={() => setSelectedId(null)}
            >
              <WatchDetail
                key={selected.id}
                watch={selected}
                isEmbedded
                onDeleted={() => setSelectedId(null)}
              />
            </Sheet>
          )}
        </div>
      )}
    </section>
  );
}

function PatrolSummary({ report }: { report: PatrolReport }) {
  const { t } = useI18n();
  if (report.skipped_locked) {
    return <p className="console">{t("board.patrolSkipped")}</p>;
  }
  const metrics: [string, number][] = [
    [t("board.m.active"), report.active],
    [t("board.m.groups"), report.route_groups],
    [t("board.m.calls"), report.api_calls],
    [t("board.m.prices"), report.prices_recorded],
    [t("board.m.alerts"), report.alerts_sent],
    [t("board.m.suppressed"), report.alerts_suppressed],
    [t("board.m.expired"), report.expired],
    [t("board.m.failures"), report.failures],
  ];
  return (
    <section className="console" role="status" aria-label={t("board.patrolAria")}>
      <p className="console__title">
        <span className="console__dot" aria-hidden="true" /> {t("board.patrolDone")}
      </p>
      <dl className="console__grid">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
