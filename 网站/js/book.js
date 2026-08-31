/* ============================================================
   书目页 · 某本书的篇目列表（按分类分组 + 搜索）
   ============================================================ */
'use strict';

(async function () {
  const bookName = getParam('book') || '';
  const loading = document.getElementById('loading');
  const errorBox = document.getElementById('error');
  const searchInput = document.getElementById('search');
  const catList = document.getElementById('cat-list');
  const stat = document.getElementById('stat');

  if (!bookName) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = '缺少 book 参数，请从书架进入。';
    return;
  }

  let book;
  try {
    book = await loadBook(bookName);
  } catch (e) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent =
      '无法加载《' + bookName + '》：' + e.message +
      '。请确认文本/_site_data/' + bookName + '.json 存在，并通过本地 HTTP 服务器访问。';
    return;
  }

  loading.hidden = true;
  document.title = book.title + ' · 书目 · 古籍文库';
  document.getElementById('book-title').textContent = book.title;
  document.getElementById('crumb-book').textContent = book.title;
  document.getElementById('header-book').textContent = '《' + book.title + '》';

  const sections = book.sections || [];
  stat.textContent = `共 ${sections.length} 篇`;

  function render(filter) {
    const keyword = (filter || '').trim();
    const q = keyword ? keyword.toLowerCase() : '';
    let shown = 0;

    const blocks = (book.categories || []).map(cat => {
      let items = sections.filter(s => s.category_label === cat);
      items.sort((a, b) => {
        const aNum = a.number, bNum = b.number;
        if (aNum != null && bNum != null) return aNum - bNum;
        if (aNum != null) return -1;
        if (bNum != null) return 1;
        return (a.title < b.title ? -1 : a.title > b.title ? 1 : 0);
      });

      if (q) {
        items = items.filter(s => s.title.toLowerCase().includes(q));
      }
      if (!items.length) return '';

      shown += items.length;
      const lis = items.map(s => `
        <li class="section-item">
          <a href="reader.html?book=${encodeURIComponent(bookName)}&index=${encodeURIComponent(orderedSections(book).indexOf(s))}">
            ${s.number != null
              ? `<span class="section-num">第${cnNum(s.number)}</span>`
              : '<span class="section-num"></span>'}
            <span>${esc(s.title)}${s.source ? `<span class="section-source"> · ${esc(s.source)}</span>` : ''}</span>
          </a>
        </li>`).join('');

      return `
        <section class="cat-block" data-cat="${esc(cat)}">
          <div class="cat-block-header">
            <span class="cat-block-name">${esc(cat)}</span>
            <span class="cat-block-count">${items.length} 篇</span>
            <span class="cat-tag cat-${catStyle(cat)}">${esc(cat)}</span>
          </div>
          <ul class="section-list">${lis}</ul>
        </section>`;
    }).join('');

    catList.innerHTML = blocks ||
      '<div class="notice">没有匹配「' + esc(keyword) + '」的篇目。</div>';
    stat.textContent = q
      ? `共 ${sections.length} 篇，匹配 ${shown} 篇`
      : `共 ${sections.length} 篇`;
  }

  searchInput.addEventListener('input', () => render(searchInput.value));
  render('');

  // ---- 下载全书 TXT ----
  document.getElementById('download-book').addEventListener('click', () => {
    const ordered = orderedSections(book);
    const parts = [book.title, ''];
    ordered.forEach(s => {
      parts.push('===== ' + s.title + ' =====', '');
      (s.paragraphs || []).forEach(p => parts.push(p));
      parts.push('');
    });
    const filename = book.title.replace(/[\\/:*?"<>|]/g, '_') + '.txt';
    downloadText(filename, parts.join('\n'));
  });
})();
