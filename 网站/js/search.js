/* ============================================================
   检索页 search.html —— 目录层 + 快照层 + 离线查词 + 第三方链接
   ------------------------------------------------------------
   · 目录层：_site_data/search/titles.json（书名/作者/分类 + 全部篇目标题）→ 秒回
   · 快照层：_site_data/search/snap/<n>.json（每篇正文前 H 字 + 尾 T 字）
             64 片并行 fetch，边到边扫；关键词命中 → 定位到「书 → 篇」
   · 离线查词：DictLookup（康熙 / 说文 / 本站词表 / CC-CEDICT）
   · 第三方词典：只给外链，不在本站展示结果
   ============================================================ */
'use strict';

(function () {
  var SEARCH_BASE = '_site_data/search/';
  var MAX_TEXT_HITS = 100;      // 正文命中上限（避免刷屏）
  var SNIP = 26;                // 片段前后各留字数

  var qInput = document.getElementById('q');
  var form = document.getElementById('search-form');
  var errEl = document.getElementById('search-error');

  var Q = (typeof getParam === 'function' ? (getParam('q') || '') : '').trim();
  qInput.value = Q;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function low(s) { return String(s == null ? '' : s).toLowerCase(); }
  function show(el, on) { if (el) el.hidden = !on; }

  /** 片段：命中位置前后各 SNIP 字，命中词加 <mark> */
  function snippet(text, needle) {
    var p = low(text).indexOf(low(needle));
    if (p < 0) return esc(text.slice(0, SNIP * 2)) + '…';
    var s = Math.max(0, p - SNIP), e = Math.min(text.length, p + needle.length + SNIP);
    return (s > 0 ? '…' : '') + esc(text.slice(s, p)) +
      '<mark>' + esc(text.substr(p, needle.length)) + '</mark>' +
      esc(text.slice(p + needle.length, e)) + (e < text.length ? '…' : '');
  }

  /* ---------------- 第三方词典（只给链接） ---------------- */
  var THIRD = [
    { label: '漢典', hint: '字 · 词', url: function (q) { return 'https://www.zdic.net/hans/' + encodeURIComponent(q); } },
    { label: '中國哲學書電子化計劃', hint: '全文检索', url: function (q) { return 'https://ctext.org/search.pl?if=gb&searchu=' + encodeURIComponent(q); } },
    { label: '維基詞典', hint: '词条', url: function (q) { return 'https://zh.wiktionary.org/wiki/' + encodeURIComponent(q); } },
    // 以下两家站内搜索 URL 会被其反爬/跳转挡住，无法在本机确证：國學大師用其站内检索写法的常见形式；
    // 中華典藏本机完全不可达 → 退回首页（点进去用站内搜索）。若日后确认了直达参数，改这里一行即可。
    { label: '國學大師', hint: '站内搜索', url: function (q) { return 'https://www.guoxuedashi.net/so.php?q=' + encodeURIComponent(q); } },
    { label: '中華典藏', hint: '打开站点搜索', url: function () { return 'https://www.zhonghuadiancang.com/'; } }
  ];

  function renderThird(q) {
    var box = document.getElementById('third-body');
    box.innerHTML = THIRD.map(function (t) {
      return '<a class="s-third-link" href="' + esc(t.url(q)) + '" target="_blank" rel="noopener">' +
        '<b>' + esc(t.label) + '</b><span>' + esc(t.hint) + '</span></a>';
    }).join('');
    show(document.getElementById('block-third'), true);
  }

  /* ---------------- 离线查词 ---------------- */
  function renderDict(q) {
    var body = document.getElementById('dict-body');
    if (!window.DictLookup) return;
    show(document.getElementById('block-dict'), true);
    body.innerHTML = '<p class="s-dim">查询中…</p>';
    DictLookup.lookup(q).then(function (r) {
      var items = (r && r.items) || [];
      var parts = ((r && r.parts) || []).filter(function (p) { return p.text; });
      if (!items.length && !parts.length) {
        body.innerHTML = '<p class="s-dim">离线词典中未收录「' + esc(q) + '」，可试试下方第三方词典。</p>';
        document.getElementById('dict-count').textContent = '';
        return;
      }
      var html = items.map(function (it) {
        var tag = it.needAI ? '<span class="s-tag">AI 待精修</span>' : '';
        var meta = it.freq ? '<span class="s-dim">全库 ' + it.freq + ' 次 · ' + (it.books || 0) + ' 本</span>' : '';
        return '<div class="s-dict-item"><h3>' + esc(it.label) + tag + meta + '</h3><p>' +
          esc(it.text || '（空）') + '</p></div>';
      }).join('');
      if (parts.length) {
        html += '<div class="s-dict-parts"><h3>成分字</h3>' + parts.map(function (p) {
          return '<div class="s-part"><b>' + esc(p.char) + '</b><span>' + esc(p.text) + '</span></div>';
        }).join('') + '</div>';
      }
      body.innerHTML = html;
      document.getElementById('dict-count').textContent = '（' + items.length + ' 条）';
    }).catch(function (e) {
      body.innerHTML = '<p class="s-dim">离线词典读取失败：' + esc(e.message) + '</p>';
    });
  }

  /* ---------------- 目录层（书目 + 篇目标题） ---------------- */
  var titlesPromise = null;
  function loadTitles() {
    if (!titlesPromise) titlesPromise = loadJSON(SEARCH_BASE + 'titles.json');
    return titlesPromise;
  }

  function renderTitles(t, res) {
    var body = document.getElementById('titles-body');
    var total = res.books.length + res.secs.length;
    document.getElementById('titles-count').textContent = total ? '（' + total + '）' : '（无）';
    show(document.getElementById('block-titles'), true);
    if (!total) {
      body.innerHTML = '<p class="s-dim">书名 / 作者 / 分类 / 篇目标题都没有命中。</p>';
      return;
    }
    var html = '';
    res.books.slice(0, 30).forEach(function (x) {
      var b = x.b;
      html += '<a class="s-item" href="book.html?book=' + encodeURIComponent(b.t) + '">' +
        '<div class="s-item-name">📚 ' + esc(b.t) + (b.a ? '<small>' + esc(b.a) + '</small>' : '') + '</div>' +
        '<div class="s-item-meta">' + [b.c, b.s, b.n ? '共 ' + b.n + ' 篇' : ''].filter(Boolean).map(esc).join(' · ') + '</div></a>';
    });
    if (res.books.length > 30) html += '<p class="s-dim">（书名命中还有 ' + (res.books.length - 30) + ' 条，已截断）</p>';
    res.secs.slice(0, 60).forEach(function (s) {
      var b = t.books[s[0]];
      if (!b) return;
      html += '<a class="s-item" href="reader.html?book=' + encodeURIComponent(b.t) + '&index=' + s[1] + '">' +
        '<div class="s-item-name">📄 ' + esc(s[2]) + '<small>' + esc(b.t) + '</small></div>' +
        '<div class="s-item-meta">' + [b.c, s[3]].filter(Boolean).map(esc).join(' · ') + '</div></a>';
    });
    if (res.secs.length > 60) html += '<p class="s-dim">（篇目命中还有 ' + (res.secs.length - 60) + ' 条，已截断）</p>';
    body.innerHTML = html;
  }

  function searchTitles(q) {
    return loadTitles().then(function (t) {
      var lq = low(q), books = [], secs = [];
      (t.books || []).forEach(function (b, i) {
        if (low(b.t).indexOf(lq) >= 0 || low(b.a).indexOf(lq) >= 0 ||
            low(b.c).indexOf(lq) >= 0 || low(b.s).indexOf(lq) >= 0) books.push({ i: i, b: b });
      });
      (t.sections || []).forEach(function (s) {
        if (s[2] && low(s[2]).indexOf(lq) >= 0) secs.push(s);
      });
      return { books: books, secs: secs, t: t };
    });
  }

  /* ---------------- 快照层（正文关键词 → 「书 → 篇」） ---------------- */
  var metaPromise = null;
  function loadMeta() {
    if (!metaPromise) {
      metaPromise = loadJSON(SEARCH_BASE + 'meta.json')
        .catch(function () { return { snap_shards: 64 }; });
    }
    return metaPromise;
  }

  function searchText(q, onProgress) {
    var lq = low(q);
    return loadMeta().then(function (m) {
      var N = m.snap_shards || 64;
      var hits = [], done = 0, truncated = false;
      var prog = document.getElementById('text-progress');
      if (prog) prog.textContent = '正在载入正文快照（' + N + ' 片）…';
      var jobs = [];
      for (var n = 0; n < N; n++) {
        jobs.push((function (idx) {
          return loadJSON(SEARCH_BASE + 'snap/' + idx + '.json').then(function (rows) {
            for (var i = 0; i < rows.length; i++) {
              var r = rows[i], txt = r[3] || '';
              if (low(txt).indexOf(lq) < 0) continue;
              if (hits.length >= MAX_TEXT_HITS) { truncated = true; continue; }
              hits.push({ g: r[0], b: r[1], i: r[2], txt: txt });
            }
          }).catch(function () { /* 单片失败不影响整体 */ }).then(function () {
            done++;
            if (prog) prog.textContent = '正在载入正文快照… ' + done + ' / ' + N + ' 片';
          });
        })(n));
      }
      return Promise.all(jobs).then(function () {
        hits.sort(function (a, b) { return a.g - b.g; });
        return { hits: hits, truncated: truncated, shards: N, total: m.sections };
      });
    });
  }

  function renderText(t, res, q) {
    var body = document.getElementById('text-body');
    var prog = document.getElementById('text-progress');
    var n = res.hits.length;
    document.getElementById('text-count').textContent =
      n ? '（' + n + (res.truncated ? '+' : '') + ' 条）' : '（无）';
    if (prog) prog.textContent = '已扫描 ' + res.shards + ' 片 · 全库 ' + (res.total || '?') + ' 篇';
    show(document.getElementById('block-text'), true);
    if (!n) {
      body.innerHTML = '<p class="s-dim">正文快照中没有命中。' +
        '（快照只覆盖每篇的<b>开头与结尾</b>；中段关键词可能漏检，可到篇内用浏览器查找。）</p>';
      return;
    }
    body.innerHTML = res.hits.map(function (h) {
      var s = (t.sections || [])[h.g] || [];
      var b = t.books[h.b] || t.books[s[0]] || { t: '' };
      var si = s.length ? s[1] : h.i;
      var title = s[2] || ('第 ' + (si + 1) + ' 篇');
      return '<a class="s-item" href="reader.html?book=' + encodeURIComponent(b.t) + '&index=' + si + '">' +
        '<div class="s-item-name">📄 ' + esc(title) + '<small>' + esc(b.t) + '</small></div>' +
        '<div class="s-item-snip">' + snippet(h.txt, q) + '</div></a>';
    }).join('') + (res.truncated
      ? '<p class="s-dim">命中过多，只列前 ' + MAX_TEXT_HITS + ' 条（按书序）。</p>' : '');
  }

  /* ---------------- 启动 ---------------- */
  function run(q) {
    if (!q) { qInput.focus(); return; }
    document.title = '「' + q + '」检索 · 一堆古书';
    errEl.hidden = true;
    renderThird(q);
    renderDict(q);
    searchTitles(q).then(function (res) {
      renderTitles(res.t, res);
      return searchText(q).then(function (tr) { renderText(res.t, tr, q); });
    }).catch(function (e) {
      errEl.textContent = '检索失败：' + (e && e.message ? e.message : e);
      errEl.hidden = false;
    });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var v = qInput.value.trim();
    if (!v) return;
    // 换 URL 即整页重载：直接跳，保证 ?q= 可分享 / 可回退
    location.href = 'search.html?q=' + encodeURIComponent(v);
  });

  run(Q);
})();
