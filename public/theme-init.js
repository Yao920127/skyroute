// 在畫面繪製前套用配色，避免暗色模式開頁閃白（規則與 src/lib/theme.ts 一致；CSP 禁止內嵌腳本，所以獨立成檔）
(function () {
  var mode = 'system';
  try {
    var saved = localStorage.getItem('skyroute.theme');
    if (saved === 'light' || saved === 'dark') mode = saved;
  } catch (e) {}
  var dark =
    mode === 'dark' ||
    (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  var theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
})();
