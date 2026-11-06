/* ---------- 主題切換：系統 / 亮色 / 暗色 ---------- */
(function () {
  var root = document.documentElement;
  var mq = matchMedia('(prefers-color-scheme: dark)');
  var buttons = document.querySelectorAll('.theme-switch button');
  function apply(mode) {
    var dark = mode === 'dark' || (mode === 'system' && mq.matches);
    root.dataset.mode = mode;
    root.dataset.theme = dark ? 'dark' : 'light';
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.set === mode)); });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      localStorage.setItem('duffel-theme-mode', b.dataset.set);
      apply(b.dataset.set);
    });
  });
  mq.addEventListener('change', function () { if (root.dataset.mode === 'system') apply('system'); });
  apply(root.dataset.mode);
})();

/* ---------- 簡易語法上色 ---------- */
(function () {
  var esc = function (s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  var PY_KW = /^(?:and|as|assert|break|class|continue|def|del|elif|else|except|finally|for|from|if|import|in|is|lambda|not|or|pass|raise|return|try|while|with|yield|True|False|None)$/;
  var PY_BUILTIN = /^(?:print|len|float|int|str|min|max|sum|any|all|range|enumerate|isinstance|super|Decimal|requests)$/;
  function highlightPython(src) {
    var re = /(#[^\n]*)|([rRfFbB]{0,2}(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'))|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z_0-9]*)(\s*\()?/g;
    var out = '', last = 0, m;
    while ((m = re.exec(src))) {
      out += esc(src.slice(last, m.index)); last = re.lastIndex;
      if (m[1]) out += '<span class="c">' + esc(m[1]) + '</span>';
      else if (m[2]) out += '<span class="s">' + esc(m[2]) + '</span>';
      else if (m[3]) out += '<span class="n">' + m[3] + '</span>';
      else {
        var w = m[4];
        if (PY_KW.test(w)) out += '<span class="k">' + w + '</span>' + esc(m[5] || '');
        else if (m[5] || PY_BUILTIN.test(w)) out += '<span class="f">' + w + '</span>' + esc(m[5] || '');
        else out += esc(w);
      }
    }
    return out + esc(src.slice(last));
  }
  function highlightJson(src) {
    var re = /(\/\*[\s\S]*?\*\/|\/\/[^\n]*)|("(?:\\.|[^"\\])*")(\s*:)?|(-?\b\d+(?:\.\d+)?\b)|\b(true|false|null)\b/g;
    var out = '', last = 0, m;
    while ((m = re.exec(src))) {
      out += esc(src.slice(last, m.index)); last = re.lastIndex;
      if (m[1]) out += '<span class="c">' + esc(m[1]) + '</span>';
      else if (m[2]) out += m[3] ? '<span class="p">' + esc(m[2]) + '</span>' + m[3] : '<span class="s">' + esc(m[2]) + '</span>';
      else if (m[4]) out += '<span class="n">' + m[4] + '</span>';
      else out += '<span class="k">' + m[5] + '</span>';
    }
    return out + esc(src.slice(last));
  }
  function highlightBash(src) {
    return src.split('\n').map(function (l) {
      return /^\s*#/.test(l) ? '<span class="c">' + esc(l) + '</span>' : esc(l);
    }).join('\n');
  }
  document.querySelectorAll('pre[data-lang]').forEach(function (pre) {
    var src = pre.textContent, lang = pre.dataset.lang;
    pre.innerHTML = '<code>' + (lang === 'python' ? highlightPython(src) : lang === 'json' ? highlightJson(src) : highlightBash(src)) + '</code>';
  });
})();

/* ---------- 複製按鈕（clipboard API 失敗時退回 execCommand） ---------- */
function copyText(text) {
  var viaExec = function () {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok ? Promise.resolve() : Promise.reject(new Error('copy failed'));
  };
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text).catch(viaExec);
  }
  return viaExec();
}
document.querySelectorAll('.code button.copy').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var text = btn.closest('.code').querySelector('pre').textContent;
    var flash = function (msg) { btn.textContent = msg; setTimeout(function () { btn.textContent = '複製'; }, 1400); };
    copyText(text).then(function () { flash('已複製'); }, function () { flash('複製失敗'); });
  });
});

/* ---------- 側欄：篩選、目前章節標示、行動版開關 ---------- */
(function () {
  var side = document.getElementById('side');
  var links = Array.prototype.slice.call(side.querySelectorAll('a'));
  var filter = document.getElementById('nav-filter');
  filter.addEventListener('input', function () {
    var q = filter.value.trim().toLowerCase();
    links.forEach(function (a) { a.classList.toggle('hidden', q && a.textContent.toLowerCase().indexOf(q) === -1); });
    side.querySelectorAll('h4').forEach(function (h) {
      var el = h.nextElementSibling, any = false;
      while (el && el.tagName === 'A') { if (!el.classList.contains('hidden')) any = true; el = el.nextElementSibling; }
      h.classList.toggle('hidden', !any);
    });
  });
  var map = {};
  links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting && map[e.target.id]) {
        links.forEach(function (a) { a.classList.remove('active'); });
        map[e.target.id].classList.add('active');
      }
    });
  }, { rootMargin: '-80px 0px -70% 0px' });
  document.querySelectorAll('section.guide').forEach(function (s) { io.observe(s); });
  document.getElementById('menu-btn').addEventListener('click', function () { document.body.classList.toggle('nav-open'); });
  side.addEventListener('click', function (e) { if (e.target.tagName === 'A') document.body.classList.remove('nav-open'); });
})();
