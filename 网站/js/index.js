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

// 古文觀止 · AI 领读范本：加载 JSON 渲染列表，点击进入 AI 阅读器（学习模式）
(async function () {
  const grid = document.getElementById('gwz-samples');
  if (!grid) return;
  let samples = [];
  try { samples = await loadJSON('assets/data/gwz-samples.json'); } catch (e) { return; }
  if (!Array.isArray(samples)) return;
  grid.innerHTML = samples.map((s, i) =>
    `<button class="sample-item" data-index="${i}">
       <span class="sample-no">${String(i + 1).padStart(2, '0')}</span>
       <span class="sample-title">${esc(s.title)}</span>
       <span class="sample-source">${esc(s.source)}</span>
     </button>`
  ).join('');
  grid.addEventListener('click', function (e) {
    const btn = e.target.closest('.sample-item');
    if (!btn) return;
    const s = samples[parseInt(btn.dataset.index, 10)];
    if (!s) return;
    try {
      sessionStorage.setItem('lib_selected', JSON.stringify({
        title: s.title + '（' + s.source + '）',
        text: s.content,
        source: '古文觀止 · ' + s.volume,
        pos: ''
      }));
    } catch (err) { /* 隐私模式忽略 */ }
    window.location.href = '/reader/shiji_reader.html';
  });
})();
