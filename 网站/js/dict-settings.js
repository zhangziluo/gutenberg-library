/* ============================================================
   设置页 · 词典外链卡片（ai-settings.html#dict-links）
   ------------------------------------------------------------
   只负责两件事：
     1) 「容错外链」开关 —— 读写 DictLinks 的同一个 localStorage key
     2) 把白名单里每个源的当前状态（展示 / 容错展示 / 隐藏）列出来，
        并写清「为什么隐藏」，避免用户以为站点坏了
   数据全部来自 js/dict-links.js（白名单 + _site_data/dict/dict_links.json 探活结论）。
   ============================================================ */
'use strict';

(function () {
  var cb = document.getElementById('fallbackLinks');
  var listEl = document.getElementById('dictLinksList');
  var stEl = document.getElementById('dictLinksStatus');
  if (!cb || !listEl || !window.DictLinks) return;

  var DL = window.DictLinks;
  var ZH = DL.SOURCES.filter(function (s) { return s.lang === 'zh'; });
  var TEXT = { enabled: '展示', fallback: '容错展示', hidden: '隐藏' };

  function paint() {
    DL.ready().then(function () {
      listEl.innerHTML = ZH.map(function (s) {
        var st = DL.stateOf(s.id);
        return '<div class="dl-row"><b>' + DL.esc(s.label) + '</b>' +
          '<i class="dl-state dl-state-' + DL.esc(st) + '">' + TEXT[st] + '</i>' +
          '<span class="dl-note">' + DL.esc(s.note || '') + '</span></div>';
      }).join('');
      var shown = DL.visible('zh').length;
      stEl.className = 'settings-status ok';
      stEl.textContent = '当前展示 ' + shown + ' 个源 · 隐藏 ' + (ZH.length - shown) + ' 个' +
        (DL.fallbackEnabled() ? '（容错外链已开启）' : '');
    });
  }

  cb.checked = DL.fallbackEnabled();
  cb.addEventListener('change', function () {
    DL.setFallback(cb.checked);
    paint();
  });
  paint();
})();
