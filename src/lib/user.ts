const STORAGE_KEY = "skyroute.user-id";

/** 本系統沒有帳號登入：以瀏覽器本地產生的匿名識別碼區分每位使用者的自選清單。 */
export function getUserId(): string {
  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const created = `user-${crypto.randomUUID().slice(0, 12)}`;
  localStorage.setItem(STORAGE_KEY, created);
  return created;
}
