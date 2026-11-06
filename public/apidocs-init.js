/* 在繪製前先決定主題，避免閃爍 */
(function () {
  var mode = localStorage.getItem('duffel-theme-mode') || 'system';
  var dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.mode = mode;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();
