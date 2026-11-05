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
  const [target, setTarget] = useState(
    watch.target_price ? String(Number(watch.target_price)) : "",
  );
  const [drop, setDrop] = useState(watch.drop_percent ? String(Number(watch.drop_percent)) : "");
  const isTracking = watch.status === "TRACKING";
  const currency = watch.currency ?? watch.stats.currency ?? "";
  const toNumber = (v: string) => (v.trim() ? Number(v) : null);
  const original = (v: string | null) => (v === null ? null : Number(v));

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
  if (toNumber(target) !== original(watch.target_price)) patch.target_price = toNumber(target);
  if (toNumber(drop) !== original(watch.drop_percent)) patch.drop_percent = toNumber(drop);
  const hasThreshold = Boolean(target.trim() || drop.trim());
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
            disabled={!hasChanges || !hasThreshold || save.isPending}
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
        <div className="edit-watch__grid">
          <label className="field">
            <span>{t("watch.target", { currency })}</span>
            <input
              className="input mono"
              type="number"
              inputMode="decimal"
              min={1}
              step="0.01"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t("watch.drop")}</span>
            <input
              className="input mono"
              type="number"
              inputMode="decimal"
              min={0.5}
              max={90}
              step="0.5"
              value={drop}
              onChange={(e) => setDrop(e.target.value)}
            />
          </label>
        </div>
        {!hasThreshold && <p className="notice">{t("edit.needThreshold")}</p>}
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
