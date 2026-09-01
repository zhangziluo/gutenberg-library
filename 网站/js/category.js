/* ============================================================
   分类页渲染器（/category/*.html）
   读取统一数据源 books-data.json，按 body[data-cat] 过滤展示。
   集部按 subcategory 分为「古典文學 / 現代文學」两个子区块；
   无书分类显示空状态。
   ============================================================ */
'use strict';
(function () {
  var cat = document.body.getAttribute('data-cat') || 'jing';
  var PART = { jing: '經部', shi: '史部', zi: '子部', ji: '集部', cong: '叢部' };
  var titleEl = document.getElementById('cat-title');
  var descEl = document.getElementById('cat-desc');
  var bodyEl = document.getElementById('cat-body');

  titleEl.textContent = PART[cat] || '';

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function cardHTML(b) {
    var dynTag = b.dynasty ? '<span class="cat-tag cat-dyn">' + esc(b.dynasty) + '</span>' : '';
    var meta = b.sections ? '共 ' + b.sections + ' 篇' : '';
    return '<a class="lib-book" href="/book.html?book=' + encodeURIComponent(b.title) + '">' +
      '<div class="lib-book-head"><span class="lib-book-name">' + esc(b.title) + '</span>' + dynTag + '</div>' +
      '<div class="lib-book-author">' + esc(b.author) + ' 著</div>' +
      (b.description ? '<p class="lib-book-intro">' + esc(b.description) + '</p>' : '') +
      '<div class="lib-book-meta">' + meta + '</div>' +
      '<span class="lib-book-enter">進入閱讀 →</span></a>';
  }

  fetch('../assets/data/books-data.json')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      descEl.textContent = (data.categories && data.categories[cat]) || '';
      var books = (data.books || []).filter(function (b) { return b.category === cat; });
      if (!books.length) {
        bodyEl.innerHTML = '<div class="cat-empty">' + PART[cat] + '藏書整理中，敬請期待 🌳</div>';
        return;
      }
      var groups;
      if (cat === 'ji') {
        var classic = books.filter(function (b) { return b.subcategory !== 'modern'; });
        var modern = books.filter(function (b) { return b.subcategory === 'modern'; });
        groups = [];
        if (classic.length) groups.push(['古典文學', classic]);
        if (modern.length) groups.push(['現代文學', modern]);
      } else {
        groups = [[PART[cat], books]];
      }
      bodyEl.innerHTML = groups.map(function (g) {
        var name = g[0], items = g[1];
        return '<section class="lib-part">' +
          '<div class="lib-part-head">' +
          '<span class="lib-part-name">' + esc(name) + '</span>' +
          '<span class="lib-part-desc">' + (cat === 'ji' && name === '現代文學' ? '近現代白話文學與新文學作品' : '') + '</span>' +
          '<span class="lib-part-count">' + items.length + ' 種</span></div>' +
          '<div class="lib-books">' + items.map(cardHTML).join('') + '</div>' +
          '</section>';
      }).join('');
    })
    .catch(function () {
      bodyEl.innerHTML = '<div class="cat-empty">載入失敗，請刷新重試</div>';
    });
})();
