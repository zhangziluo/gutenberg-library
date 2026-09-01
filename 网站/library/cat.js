/* 分类页渲染：根据 body[data-cat] 显示对应部类书目 */
'use strict';
(function () {
  var cat = document.body.getAttribute('data-cat') || 'jing';
  var PART = { jing: '經部', shi: '史部', zi: '子部', ji: '集部', modern: '近現代文學' };
  var DESC = {
    jing: '易·書·詩·禮·春秋·四書·小學等',
    shi: '正史·編年·紀事本末·別史·雜史·傳記等',
    zi: '儒·道·法·兵·農·醫·天文算法·小說家等',
    ji: '楚辭·別集·總集·詩文評·詞曲等',
    modern: '晚清以降的現代白話與新文學作品'
  };
  var partName = PART[cat] || '經部';
  document.getElementById('cat-title').textContent = partName;
  document.getElementById('cat-desc').textContent = DESC[cat] || '';

  var list = document.getElementById('cat-books');
  var empty = document.getElementById('cat-empty');
  var DATA_BASE = '../../文本/_site_data/';

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  }); }

  Promise.all([
    fetch('../../assets/data/catalog.json').then(function (r) { return r.json(); }),
    fetch(DATA_BASE + 'books.json').then(function (r) { return r.json(); })
  ]).then(function (res) {
    var catalog = res[0], books = res[1];
    var part = (catalog.parts || []).filter(function (p) { return p.bu === partName; })[0];
    var items = (part && part.books) || [];
    if (!items.length) { empty.hidden = false; return; }
    list.innerHTML = items.map(function (b) {
      var meta = books[b.book] || {};
      var count = meta.section_count != null ? meta.section_count : '?';
      var missing = (meta.missing && meta.missing.length) ? ' · 缺 ' + meta.missing.length + ' 卷' : '';
      return '<a class="lib-book" href="../../book.html?book=' + encodeURIComponent(b.book) + '">' +
        '<div class="lib-book-head"><span class="lib-book-name">' + esc(b.book) + '</span>' +
        '<span class="cat-tag cat-lib">' + esc(b.cat || '') + '</span></div>' +
        '<div class="lib-book-author">' + esc(b.author || '佚名') + ' 著</div>' +
        '<p class="lib-book-intro">' + esc(b.intro || '') + '</p>' +
        '<div class="lib-book-meta">共 ' + count + ' 篇' + missing + '</div>' +
        '<span class="lib-book-enter">進入閱讀 →</span></a>';
    }).join('');
  }).catch(function () {
    empty.textContent = '載入失敗，請刷新重試';
    empty.hidden = false;
  });
})();
