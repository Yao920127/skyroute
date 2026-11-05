/**
 * Google Identity Services（GIS）：載入官方腳本並繪製「使用 Google 帳號登入」按鈕。
 * 按鈕回傳的 credential 是 Google 簽發的 ID Token，交給後端驗章後建立工作階段。
 */

const GIS_SRC = "https://accounts.google.com/gsi/client";

type CredentialResponse = { credential?: string };

type GoogleId = {
  initialize: (options: {
    client_id: string;
    callback: (response: CredentialResponse) => void;
    ux_mode?: "popup";
    use_fedcm_for_button?: boolean;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, string | number>) => void;
  disableAutoSelect: () => void;
};

declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

let loading: Promise<GoogleId> | null = null;

export function loadGoogleIdentity(): Promise<GoogleId> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
  loading ??= new Promise<GoogleId>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GIS_SRC;
    script.async = true;
    script.onload = () =>
      window.google?.accounts?.id
        ? resolve(window.google.accounts.id)
        : reject(new Error("Google Identity Services unavailable"));
    script.onerror = () => {
      loading = null; // 允許下次重試
      reject(new Error("Failed to load Google Identity Services"));
    };
    document.head.append(script);
  });
  return loading;
}

export async function renderGoogleButton(
  parent: HTMLElement,
  clientId: string,
  locale: string,
  onCredential: (credential: string) => void,
): Promise<void> {
  const gis = await loadGoogleIdentity();
  gis.initialize({
    client_id: clientId,
    callback: (response) => response.credential && onCredential(response.credential),
    ux_mode: "popup",
    use_fedcm_for_button: true,
  });
  parent.replaceChildren();
  gis.renderButton(parent, {
    type: "standard",
    theme: "outline",
    size: "large",
    shape: "pill",
    text: "signin_with",
    logo_alignment: "left",
    locale,
    width: Math.min(parent.clientWidth || 320, 400),
  });
}

/** 登出後避免 Google 自動帶入上一個帳號 */
export function forgetGoogleSelection(): void {
  window.google?.accounts?.id?.disableAutoSelect();
}
