import { Component, type ReactNode } from "react";

type Props = {
  /** 載入失敗時顯示的內容（通常是「請重新整理」提示） */
  fallback: ReactNode;
  children: ReactNode;
};

type State = { hasError: boolean };

/**
 * 包住延遲載入（lazy）的區塊：程式檔載入失敗或渲染出錯時，只換掉這一塊，不讓整頁變空白。
 * 常見情境：網站剛更新，舊分頁要去抓已經不存在的舊版程式檔。
 * React 19 仍只能用 class 元件攔截渲染錯誤。
 */
export class LoadBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
