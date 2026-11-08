(function () {
  var html = document.documentElement;
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var total = slides.length;
  var current = 0;

  var counterEl = document.getElementById('slide-counter');
  var progressEl = document.getElementById('progress-fill');
  var prevBtn = document.getElementById('prev-btn');
  var nextBtn = document.getElementById('next-btn');
  var modeBtns = Array.prototype.slice.call(document.querySelectorAll('.js-mode-btn'));
  var fullscreenBtn = document.getElementById('fs-btn');
  var tocBtn = document.getElementById('toc-btn');
  var tocCloseBtn = document.getElementById('toc-close');
  var tocBackdrop = document.getElementById('toc-backdrop');
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-link'));
  var dotContainer = document.getElementById('slide-dots');

  var prefsBtn = document.getElementById('prefs-btn');
  var prefsCloseBtn = document.getElementById('prefs-close');
  var prefsBackdrop = document.getElementById('prefs-backdrop');

  // 建立底部圓點導覽
  if (dotContainer) {
    slides.forEach(function (slide, idx) {
      var dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'slide-dot';
      var title = slide.getAttribute('data-title') || ('第 ' + (idx + 1) + ' 頁');
      dot.setAttribute('aria-label', '跳至第 ' + (idx + 1) + ' 頁：' + title);
      dot.setAttribute('title', (idx + 1 < 10 ? '0' + (idx + 1) : idx + 1) + ' · ' + title);
      dot.addEventListener('click', function () {
        goTo(idx);
      });
      dotContainer.appendChild(dot);
    });
  }
  var dots = dotContainer ? Array.prototype.slice.call(dotContainer.querySelectorAll('.slide-dot')) : [];

  function pad(n) {
    return n < 10 ? '0' + n : String(n);
  }

  function isDeckMode() {
    return html.getAttribute('data-view-mode') === 'deck';
  }

  // 簡報模式自動縮放：在「內容不超出可視高度」的前提下，找出最大的放大倍率
  var DECK_ZOOM_MAX = 2.2;
  var DECK_ZOOM_MIN = 1;
  var DECK_ZOOM_STEP = 0.05;
  var DECK_MIN_UNIT_WIDTH = 900; // 放大後內容區至少保留的寬度（CSS px）
  var DECK_MIN_VIEWPORT = 900; // 小於此寬度不放大（平板直向、手機）
  var topbarEl = document.querySelector('.topbar');
  var bottombarEl = document.querySelector('.bottombar');

  function fitDeck() {
    var slide = slides[current];
    if (!isDeckMode() || !slide || window.innerWidth < DECK_MIN_VIEWPORT) {
      html.style.removeProperty('--deck-zoom');
      return;
    }
    var chrome = (topbarEl ? topbarEl.offsetHeight : 0) + (bottombarEl ? bottombarEl.offsetHeight : 0);
    var available = window.innerHeight - chrome - 16;
    var ceiling = Math.min(DECK_ZOOM_MAX, window.innerWidth / DECK_MIN_UNIT_WIDTH);
    var zoom = ceiling;

    slide.style.minHeight = '0';
    for (; zoom > DECK_ZOOM_MIN; zoom -= DECK_ZOOM_STEP) {
      html.style.setProperty('--deck-zoom', zoom.toFixed(2));
      if (slide.getBoundingClientRect().height <= available) break;
    }
    zoom = Math.max(DECK_ZOOM_MIN, zoom);
    html.style.setProperty('--deck-zoom', zoom.toFixed(2));
    slide.style.minHeight = '';
  }

  var fitQueued = false;
  function queueFit() {
    if (fitQueued) return;
    fitQueued = true;
    requestAnimationFrame(function () {
      fitQueued = false;
      fitDeck();
    });
  }

  function updateUI() {
    if (counterEl) {
      counterEl.textContent = pad(current + 1) + ' / ' + pad(total);
    }
    if (progressEl) {
      var pct = total > 1 ? ((current + 1) / total) * 100 : 100;
      progressEl.style.width = pct.toFixed(2) + '%';
    }
    if (prevBtn) prevBtn.disabled = current <= 0;
    if (nextBtn) nextBtn.disabled = current >= total - 1;

    slides.forEach(function (s, idx) {
      var active = idx === current;
      s.classList.toggle('is-active', active);
      if (isDeckMode()) {
        s.setAttribute('aria-hidden', active ? 'false' : 'true');
      } else {
        s.removeAttribute('aria-hidden');
      }
    });

    tocLinks.forEach(function (link, idx) {
      link.classList.toggle('is-active', idx === current);
    });

    dots.forEach(function (dot, idx) {
      dot.classList.toggle('is-active', idx === current);
      dot.setAttribute('aria-current', idx === current ? 'step' : 'false');
    });

    fitDeck();
  }

  function goTo(index, fromScroll) {
    if (index < 0) index = 0;
    if (index >= total) index = total - 1;
    current = index;
    updateUI();

    var target = slides[current];
    if (!target) return;

    if (isDeckMode()) {
      target.scrollTop = 0;
      window.scrollTo({ top: 0, behavior: 'auto' });
    } else if (!fromScroll) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (history.replaceState && target.id) {
      history.replaceState(null, '', '#' + target.id);
    }
  }

  function setViewMode(mode) {
    var next = mode === 'scroll' ? 'scroll' : 'deck';
    html.setAttribute('data-view-mode', next);
    try {
      localStorage.setItem('skyroute.pres.mode', next);
    } catch (e) {}
    modeBtns.forEach(function (btn) {
      var labelEl = btn.querySelector('.mode-label');
      if (labelEl) {
        labelEl.textContent = next === 'deck' ? '簡報模式' : '長頁閱讀';
      }
      btn.setAttribute('aria-pressed', next === 'deck' ? 'true' : 'false');
    });
    updateUI();
    if (next === 'scroll' && slides[current]) {
      slides[current].scrollIntoView({ behavior: 'auto', block: 'start' });
    } else {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
  }

  // 初始化檢視模式（手機預設長頁閱讀，平板與桌機預設簡報模式）
  (function initMode() {
    var saved = null;
    try {
      saved = localStorage.getItem('skyroute.pres.mode');
    } catch (e) {}
    var initial = saved || (window.innerWidth <= 640 ? 'scroll' : 'deck');
    setViewMode(initial);
  })();

  // 從 URL Hash 初始化頁碼
  if (location.hash) {
    var hashId = location.hash.slice(1);
    slides.forEach(function (s, idx) {
      if (s.id === hashId) current = idx;
    });
  }
  updateUI();

  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      goTo(current - 1);
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      goTo(current + 1);
    });
  }
  modeBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      setViewMode(isDeckMode() ? 'scroll' : 'deck');
    });
  });

  // 目錄抽屜控制
  function setTocOpen(open) {
    if (open) setPrefsOpen(false);
    document.body.classList.toggle('toc-open', open);
    if (tocBtn) tocBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (tocBtn) {
    tocBtn.addEventListener('click', function () {
      setTocOpen(!document.body.classList.contains('toc-open'));
    });
  }
  if (tocCloseBtn) {
    tocCloseBtn.addEventListener('click', function () {
      setTocOpen(false);
    });
  }
  if (tocBackdrop) {
    tocBackdrop.addEventListener('click', function () {
      setTocOpen(false);
    });
  }
  tocLinks.forEach(function (link, idx) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      setTocOpen(false);
      goTo(idx);
    });
  });

  // 手機／平板底部設定抽屜控制
  function setPrefsOpen(open) {
    if (open) setTocOpen(false);
    document.body.classList.toggle('prefs-open', open);
    if (prefsBtn) prefsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (prefsBtn) {
    prefsBtn.addEventListener('click', function () {
      setPrefsOpen(!document.body.classList.contains('prefs-open'));
    });
  }
  if (prefsCloseBtn) {
    prefsCloseBtn.addEventListener('click', function () {
      setPrefsOpen(false);
    });
  }
  if (prefsBackdrop) {
    prefsBackdrop.addEventListener('click', function () {
      setPrefsOpen(false);
    });
  }

  // 全螢幕切換
  if (fullscreenBtn) {
    fullscreenBtn.addEventListener('click', function () {
      if (!document.fullscreenElement) {
        if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(function () {});
        }
      } else if (document.exitFullscreen) {
        document.exitFullscreen().catch(function () {});
      }
    });
  }

  // 主題切換（與主系統 skyroute.theme 同步）
  var themeBtns = Array.prototype.slice.call(document.querySelectorAll('[data-theme-set]'));
  function getStoredMode() {
    try {
      var v = localStorage.getItem('skyroute.theme');
      if (v === 'light' || v === 'dark') return v;
    } catch (e) {}
    return 'system';
  }
  function applyTheme(mode) {
    try {
      if (mode === 'system') {
        localStorage.removeItem('skyroute.theme');
      } else {
        localStorage.setItem('skyroute.theme', mode);
      }
    } catch (e) {}
    var dark =
      mode === 'dark' ||
      (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var resolved = dark ? 'dark' : 'light';
    html.dataset.theme = resolved;
    html.dataset.themeMode = mode;
    html.style.colorScheme = resolved;
    themeBtns.forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-theme-set') === mode ? 'true' : 'false');
    });
  }
  applyTheme(getStoredMode());
  themeBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      applyTheme(btn.getAttribute('data-theme-set') || 'system');
    });
  });
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (getStoredMode() === 'system') applyTheme('system');
    });
  }

  window.addEventListener('resize', queueFit);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(queueFit);
  }

  // 鍵盤快捷鍵
  window.addEventListener('keydown', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable)) {
      return;
    }
    if (e.key === 'Escape') {
      if (document.body.classList.contains('toc-open')) setTocOpen(false);
      if (document.body.classList.contains('prefs-open')) setPrefsOpen(false);
      return;
    }
    if (e.key === 'ArrowRight' || e.key === 'PageDown') {
      e.preventDefault();
      goTo(current + 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      e.preventDefault();
      goTo(current - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      goTo(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      goTo(total - 1);
    } else if (e.key === 'm' || e.key === 'M') {
      setViewMode(isDeckMode() ? 'scroll' : 'deck');
    }
  });

  // 觸控滑動換頁（僅在簡報模式下，且未在橫向表格內捲動時觸發）
  var touchStartX = 0;
  var touchStartY = 0;
  var touchInScrollable = false;

  window.addEventListener(
    'touchstart',
    function (e) {
      if (!isDeckMode() || e.touches.length !== 1) return;
      var el = e.target;
      touchInScrollable = Boolean(el && el.closest && el.closest('.table-scroll, .matrix-scroll, pre'));
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
    },
    { passive: true }
  );

  window.addEventListener(
    'touchend',
    function (e) {
      if (!isDeckMode() || touchInScrollable || e.changedTouches.length !== 1) return;
      var dx = e.changedTouches[0].clientX - touchStartX;
      var dy = e.changedTouches[0].clientY - touchStartY;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.6) {
        if (dx < 0) goTo(current + 1);
        else goTo(current - 1);
      }
    },
    { passive: true }
  );

  // 長頁閱讀模式下，根據捲動位置更新目前頁碼
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(
      function (entries) {
        if (isDeckMode()) return;
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            var idx = slides.indexOf(entry.target);
            if (idx !== -1 && idx !== current) {
              current = idx;
              updateUI();
            }
          }
        });
      },
      { threshold: 0.25 }
    );
    slides.forEach(function (s) {
      io.observe(s);
    });
  }
})();
