/* ============================================================
   书目页 · 某本书的篇目列表（按分类分组 + 搜索）
   ============================================================ */
'use strict';

// 大封面 hero 用：分类中文名 / 分类底色 class
const BOOK_CATS = { jing: '經部', shi: '史部', zi: '子部', ji: '集部', cong: '叢部' };

// 从 books-data.json 取本书元数据（category/commentator/summary/highlights/source…）。
// 尽力而为：取不到返回 null，hero 降级为只用 _site_data 里的 title。
async function loadBookMeta(title) {
  try {
    const data = await loadJSON('assets/data/books-data.json');
    const list = data.books || data || [];
    return list.find(b => b.title === title) || null;
  } catch (e) {
    return null;
  }
}

// 书目详情页左栏：大封面（纯 CSS）+ 书名/作者/批注者 + 简介 + 本版特色标签 + 开始阅读
function heroHTML(book, meta) {
  const m = meta || {};
  const catCls = BOOK_CATS[m.category] ? 'cover-' + m.category : 'cover-all';
  const author = m.author || '';
  const authorLine = m.commentator
    ? esc(author) + ' 著 · ' + esc(m.commentator) + ' 批注'
    : esc(author) + ' 著';
  const isWiki = (m.source || '').indexOf('维基') !== -1;
  const badge = isWiki ? '📘' : '📗';
  const tags = []
    .concat(m.highlights || [])
    .concat(BOOK_CATS[m.category] ? [BOOK_CATS[m.category]] : [])
    .concat(m.source ? [m.source] : [])
    .concat(m.license ? [m.license] : [])
    .map(t => `<span>${esc(t)}</span>`).join('');
  const titleCls = book.title.length > 6 ? 'cover-title long' : 'cover-title';
  return `<div class="book-hero-cover ${catCls}">
      <div class="${titleCls}">${esc(book.title)}</div>
      <div class="cover-author">${esc(author)}</div>
      <span class="cover-badge" title="${isWiki ? '维基文库' : '古登堡计划'}">${badge}</span>
    </div>
    <div class="book-hero-info">
      <h1 class="book-hero-title">${esc(book.title)}</h1>
      ${author ? `<div class="book-hero-author">${authorLine}</div>` : ''}
      ${m.summary ? `<p class="book-hero-summary">${esc(m.summary)}</p>` : ''}
      ${tags ? `<div class="book-hero-tags">${tags}</div>` : ''}
      <div class="book-hero-actions">
        <a class="btn-read" href="reader.html?book=${encodeURIComponent(book.title)}&index=0">📖 开始阅读</a>
      </div>
    </div>`;
}

(async function () {
  const bookName = getParam('book') || '';
  const loading = document.getElementById('loading');
  const errorBox = document.getElementById('error');
  const searchInput = document.getElementById('search');
  const catList = document.getElementById('cat-list');
  const stat = document.getElementById('stat');
  const heroEl = document.getElementById('book-hero');

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
      '。请确认 _site_data/' + bookName + '.json 存在，并通过本地 HTTP 服务器访问。';
    return;
  }

  loading.hidden = true;
  document.title = book.title + ' · 书目 · 一堆古书';
  document.getElementById('book-title').textContent = book.title;
  document.getElementById('crumb-book').textContent = book.title;
  document.getElementById('header-book').textContent = '《' + book.title + '》';

  const sections = book.sections || [];
  stat.textContent = `共 ${sections.length} 篇`;

  // ---- 大封面 hero（元数据取自 books-data.json，取不到则降级） ----
  if (heroEl) {
    const meta = await loadBookMeta(bookName);
    heroEl.innerHTML = heroHTML(book, meta);
  }

  // ---- 缺篇标注（数据来自每书的 missing 字段） ----
  const missing = book.missing || [];
  const missingByCat = {};
  missing.forEach(m => {
    missingByCat[m.category] = (missingByCat[m.category] || 0) + 1;
  });

  function missingNoticeHtml() {
    if (!missing.length) return '';
    const groups = (book.categories || [])
      .map(cat => ({ cat, items: missing.filter(m => m.category === cat) }))
      .filter(g => g.items.length);
    const lis = groups.map(g => {
      const nums = g.items.map(i => i.number).filter(Boolean).sort((a, b) => a - b);
      const numStr = nums.length >= 2 ? `（卷 ${nums[0]}–${nums[nums.length - 1]}）`
        : (nums.length ? `（卷 ${nums[0]}）` : '');
      const titles = g.items.map(i => i.title).join('、');
      if (g.items.length > 8) {
        return `
          <details open>
            <summary><span class="missing-cat">${esc(g.cat)}</span> 缺 ${g.items.length} 卷 ${numStr}</summary>
            <div class="missing-titles">${esc(titles)}</div>
          </details>`;
      }
      return `
        <div class="missing-group">
          <span class="missing-cat">${esc(g.cat)}</span> 缺 ${g.items.length} 卷 ${numStr}：
          <span class="missing-titles">${esc(titles)}</span>
        </div>`;
    }).join('');
    return `
      <div class="missing-notice">
        <div class="missing-title">⚠ 版本缺篇说明</div>
        <div class="missing-body">
          本版《${esc(book.title)}》收录 ${book.section_count} 篇。对照通行本尚缺 ${missing.length} 卷（本版暂未收录）：
        </div>
        ${lis}
      </div>`;
  }

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
            <span class="cat-block-count">${items.length} 篇${missingByCat[cat] ? ` · 另缺 ${missingByCat[cat]} 卷` : ''}</span>
            <span class="cat-tag cat-${catStyle(cat)}">${esc(cat)}</span>
          </div>
          <ul class="section-list">${lis}</ul>
        </section>`;
    }).join('');

    catList.innerHTML = missingNoticeHtml() +
      (blocks || '<div class="notice">没有匹配「' + esc(keyword) + '」的篇目。</div>');
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
