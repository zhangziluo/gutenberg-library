/* ============================================================
   首页搜索：书名 / 作者 / 分类 匹配
   - 桌面：点击 🔍 展开输入框（约 200px），输入即时下拉
   - 移动端：点击 🔍 弹出搜索浮层
   ============================================================ */
'use strict';

(function () {
  var toggle = document.getElementById('search-toggle');
  var input = document.getElementById('search-input');
  var dropdown = document.getElementById('search-dropdown');
  var overlay = document.getElementById('search-overlay');
  var inputM = document.getElementById('search-input-m');
  var resultsM = document.getElementById('search-results-m');
  var closeM = document.getElementById('search-close-m');

  var items = [];      // { book, author, cat, part, count }
  var isMobile = false;

  function isSmall() { return window.innerWidth <= 640; }

  function buildIndex(catalog, books) {
    var parts = catalog.parts || [];
    var known = {};
    parts.forEach(function (p) {
      (p.books || []).forEach(function (b) {
        known[b.book] = true;
        items.push({
          book: b.book,
          author: b.author || '',
          cat: b.cat || '',
          part: p.bu || '',
          count: (books[b.book] || {}).section_count
        });
      });
    });
    Object.keys(books).forEach(function (k) {
      if (known[k]) return;
      items.push({ book: k, author: '', cat: '', part: '', count: books[k].section_count });
    });
  }

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  }); }

  function search(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    return items.filter(function (it) {
      var hay = (it.book + ' ' + it.author + ' ' + it.cat + ' ' + it.part).toLowerCase();
      return hay.indexOf(q) >= 0;
    });
  }

  function itemHtml(it) {
    var tags = [];
    if (it.part) tags.push(it.part);
    if (it.cat) tags.push(it.cat);
    return '<a href="book.html?book=' + encodeURIComponent(it.book) + '">' +
      '<div class="s-name">' + esc(it.book) + (it.author ? '<small>' + esc(it.author) + '</small>' : '') + '</div>' +
      '<div class="s-meta">' + esc(tags.join(' · ')) + (it.count != null ? ' · 共 ' + it.count + ' 篇' : '') + '</div></a>';
  }

  // ---- 桌面下拉 ----
  function doDesktopSearch(q) {
    var list = search(q);
    if (!q || !isMobile) {
      if (!q) { dropdown.hidden = true; return; }
      dropdown.innerHTML = list.length
        ? list.slice(0, 12).map(itemHtml).join('')
        : '<div class="s-empty">未找到匹配的書目</div>';
      dropdown.hidden = false;
    }
  }

  toggle.addEventListener('click', function () {
    if (isSmall()) {
      overlay.classList.add('open');
      inputM.value = '';
      resultsM.innerHTML = '';
      inputM.focus();
      return;
    }
    var opening = !input.classList.contains('open');
    input.classList.toggle('open', opening);
    if (opening) { input.focus(); doDesktopSearch(input.value); }
    else { dropdown.hidden = true; }
  });

  input.addEventListener('input', function () { doDesktopSearch(input.value); });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { input.classList.remove('open'); dropdown.hidden = true; }
  });
  input.addEventListener('blur', function () {
    setTimeout(function () { dropdown.hidden = true; }, 150);
  });

  // ---- 移动端浮层 ----
  inputM.addEventListener('input', function () {
    var list = search(inputM.value);
    resultsM.innerHTML = inputM.value.trim()
      ? (list.length ? list.slice(0, 30).map(itemHtml).join('') : '<div class="s-empty">未找到匹配的書目</div>')
      : '<div class="s-empty">輸入書名 / 作者 / 分類</div>';
  });
  inputM.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeM.click();
  });
  closeM.addEventListener('click', function () { overlay.classList.remove('open'); });

  // ---- 初始化 ----
  var DATA_BASE = '../文本/_site_data/';
  Promise.all([
    fetch('assets/data/catalog.json').then(function (r) { return r.json(); }),
    fetch(DATA_BASE + 'books.json').then(function (r) { return r.json(); })
  ]).then(function (res) {
    buildIndex(res[0], res[1]);
  }).catch(function () { /* 搜索不可用则静默 */ });

  window.addEventListener('resize', function () { isMobile = isSmall(); });
  isMobile = isSmall();
})();
