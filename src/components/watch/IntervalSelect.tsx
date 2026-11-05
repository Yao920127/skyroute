import { useI18n } from "../../i18n/i18n.ts";
import {
  INTERVAL_OPTIONS,
  intervalKey,
  intervalLabel,
  isIntervalAllowed,
  parseIntervalKey,
} from "../../lib/schedule.ts";
import { Select } from "../ui/Select.tsx";

type Props = {
  value: number | null;
  hasOwnKey: boolean;
  onChange: (minutes: number | null) => void;
};

/** 巡檢頻率：30 分鐘以內的選項需要使用者自己的 Duffel 金鑰，否則顯示但不可選 */
export function IntervalSelect({ value, hasOwnKey, onChange }: Props) {
  const { t } = useI18n();
  return (
    <Select
      value={intervalKey(value)}
      onValueChange={(v) => onChange(parseIntervalKey(v))}
      ariaLabel={t("watch.interval")}
      options={INTERVAL_OPTIONS.map((minutes) => {
        const isAllowed = isIntervalAllowed(minutes, hasOwnKey);
        return {
          value: intervalKey(minutes),
          label: intervalLabel(minutes, t),
          description: isAllowed ? undefined : t("schedule.ownKeyOnly"),
          disabled: !isAllowed,
        };
      })}
    />
  );
}
