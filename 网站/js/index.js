/* ============================================================
   首页 · 书架
   ============================================================ */
'use strict';

(async function () {
  const shelf = document.getElementById('book-shelf');
  const loading = document.getElementById('loading');
  const errorBox = document.getElementById('error');

  try {
    const books = await loadJSON(DATA_BASE + 'books.json');
    const names = Object.keys(books);

    shelf.innerHTML = names.map(name => {
      const b = books[name] || {};
      const cats = (b.categories || [])
        .map(c => `<span class="cat-tag cat-${catStyle(c)}">${esc(c)}</span>`)
        .join('');
      return `
        <a class="book-card" href="book.html?book=${encodeURIComponent(name)}">
          <div class="book-card-title">${esc(name)}</div>
          <div class="book-card-meta">共 ${b.section_count != null ? b.section_count : '?'} 篇</div>
          <div class="book-card-cats">${cats}</div>
        </a>`;
    }).join('') || '<div class="notice">书库为空，请先运行 export_json.py 导出数据。</div>';

    loading.hidden = true;
  } catch (e) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent =
      '无法加载书目数据：' + e.message +
      '。请通过本地 HTTP 服务器访问（在项目根目录运行 python3 -m http.server，' +
      '然后访问 http://localhost:8000/网站/index.html），不要直接用文件方式打开。';
  }
})();
