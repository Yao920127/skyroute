import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";

import { useI18n } from "../../i18n/i18n.ts";
import { api } from "../../lib/api.ts";
import type { Watchlist, WatchlistUpdate } from "../../lib/types.ts";
import { Sheet } from "../ui/Sheet.tsx";
import { IntervalSelect } from "./IntervalSelect.tsx";

type Props = {
  watch: Watchlist;
  onClose: () => void;
};

const LABEL_MAX = 100;

/** 編輯追蹤：名稱直接覆寫舊名稱；巡檢頻率改了會從現在起重新排定 */
export function EditWatchDialog({ watch, onClose }: Props) {
  const { t } = useI18n();
  const labelId = useId();
  const queryClient = useQueryClient();
  const [label, setLabel] = useState(watch.label ?? "");
  const [interval, setInterval] = useState<number | null>(watch.patrol_interval_minutes);
  const isTracking = watch.status === "TRACKING";

  const save = useMutation({
    mutationFn: (patch: WatchlistUpdate) => api.updateWatchlist(watch.id, patch),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      onClose();
    },
  });

  const patch: WatchlistUpdate = {};
  if (label.trim() !== (watch.label ?? "")) patch.label = label.trim();
  if (isTracking && interval !== watch.patrol_interval_minutes) {
    patch.patrol_interval_minutes = interval;
  }
  const hasChanges = Object.keys(patch).length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (hasChanges) save.mutate(patch);
  };

  return (
    <Sheet
      title={t("edit.title")}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            form={`${labelId}-form`}
            className="btn btn--primary"
            disabled={!hasChanges || save.isPending}
          >
            {save.isPending ? t("edit.saving") : t("edit.save")}
          </button>
        </>
      }
    >
      <form id={`${labelId}-form`} className="edit-watch" onSubmit={handleSubmit}>
        <label className="field" htmlFor={labelId}>
          <span>{t("edit.label")}</span>
          <input
            id={labelId}
            className="input"
            value={label}
            maxLength={LABEL_MAX}
            placeholder={`${watch.origin} → ${watch.destination}`}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <div className="field">
          <span>{t("watch.interval")}</span>
          {isTracking ? (
            <IntervalSelect
              value={interval}
              hasOwnKey={watch.uses_own_key}
              onChange={setInterval}
            />
          ) : (
            <p className="edit-watch__note">{t("edit.intervalEnded")}</p>
          )}
        </div>
        {isTracking && <p className="edit-watch__note">{t("watch.intervalHint")}</p>}
        {save.isError && (
          <p className="notice" role="alert">
            {save.error.message}
          </p>
        )}
      </form>
    </Sheet>
  );
}
