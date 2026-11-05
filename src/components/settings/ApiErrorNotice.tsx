import { useI18n } from "../../i18n/i18n.ts";
import { ApiError } from "../../lib/api.ts";
import { useOpenKeyDialog } from "./keyDialogContext.ts";

type Props = {
  error: Error;
  prefix?: string;
  onRetry?: () => void;
};

/** 錯誤提示；若是金鑰問題，附上「設定 API 金鑰」按鈕 */
export function ApiErrorNotice({ error, prefix, onRetry }: Props) {
  const { t } = useI18n();
  const openKeyDialog = useOpenKeyDialog();
  const needsKey = error instanceof ApiError && error.needsApiKey;
  return (
    <div className="notice notice--action" role="alert">
      <span>
        {prefix}
        {error.message}
      </span>
      {needsKey ? (
        <button type="button" className="btn btn--primary" onClick={openKeyDialog}>
          {t("key.setKey")}
        </button>
      ) : (
        onRetry && (
          <button type="button" className="btn" onClick={onRetry}>
            {t("common.retry")}
          </button>
        )
      )}
    </div>
  );
}
