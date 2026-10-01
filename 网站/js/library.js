/* ============================================================
   一堆古书 · 书库（封面网格）—— 交互逻辑
   数据源：assets/data/books-data.json（静态 JSON，即「API」；
   换 FastAPI 后端时只需改 DATA_URL 一处，返回格式见文件头注释）。

   后端 /api/books 返回格式（JSON）示例：
   {
     "books": [
       {
         "book_id": "yijing",
         "title": "易經",
         "author": "佚名",
         "commentator": "",
         "category": "jing",
         "subcategory": "易",
         "summary": "群經之首，中華文化的源頭。",
         "highlights": ["繁體", "全文注音"],
         "source": "古登堡计划",
         "source_url": "https://www.gutenberg.org/ebooks/25501",
         "license": "公有领域",
         "chapter_count": 69,
         "added_at": "2026-09-01",
         "read_count": 1234
       }
     ]
   }

   书库页禁用装饰性动画：仅卡片悬停 transform 0.2s、点击反馈。
   ============================================================ */
'use strict';

(function () {
  // 数据源（换成后端接口时只需改这里）
  const DATA_URL = 'assets/data/books-data.json';
  const PER_PAGE = 20;

  const CATS = { jing: '經部', shi: '史部', zi: '子部', ji: '集部', cong: '叢部' };
  const ORDER = ['jing', 'shi', 'zi', 'ji', 'cong'];

  const gridEl = document.getElementById('lib-grid');
  const paginationEl = document.getElementById('lib-pagination');
  const subEl = document.getElementById('lib-sub');
  const errEl = document.getElementById('lib-error');
  const tabsEl = document.getElementById('lib-tabs');
  const sortEl = document.getElementById('lib-sort');
  const searchInput = document.getElementById('lib-search-input');

  let books = [];        // 全量（normalize 后）
  let curCat = 'all';    // 当前分类
  let curSort = 'hot';   // 热门 | 最新 | 书名
  let curQuery = '';     // 搜索词
  let curPage = 1;       // 当前页

  const collator = new Intl.Collator('zh'); // 中文（拼音）排序

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // 稳定的字符串哈希（用于静态站派生占位的 read_count / added_at）
  function stableHash(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
    return h;
  }

  function placeholderReadCount(id) {
    return stableHash('rc:' + id) % 900 + 10;
  }

  function placeholderAddedAt(id) {
    const m = stableHash('at:' + id) % 12 + 1;
    const d = stableHash('ad:' + id) % 28 + 1;
    return '2026-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  }

  // 原始字段 → 目标 schema（前端容错：新字段缺失时优雅回退）
  function normalizeBook(b) {
    const book_id = b.book_id || b.id || '';
    return {
      book_id: book_id,
      title: b.title || '',
      author: b.author || '',
      commentator: b.commentator || '',
      category: b.category || '',
      subcategory: b.subcategory || '',
      summary: b.summary || b.description || '',
      highlights: b.highlights || [],
      source: b.source || '',
      source_url: b.source_url || '',
      license: b.license || '',
      chapter_count: b.chapter_count != null ? b.chapter_count : (b.sections || 0),
      // 静态站无服务端累计，用 book_id 派生稳定占位值；后端接入后直读接口字段
      added_at: b.added_at || placeholderAddedAt(book_id),
      read_count: b.read_count != null ? b.read_count : placeholderReadCount(book_id),
    };
  }

  // 过滤（分类 + 搜索词）
  function filtered() {
    const q = curQuery.trim().toLowerCase();
    return books.filter(b => {
      if (curCat !== 'all' && b.category !== curCat) return false;
      if (q) {
        const hay = (b.title + ' ' + b.author + ' ' + b.commentator).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  // 排序（热门=阅读量 / 最新=加入时间 / 书名=拼音）
  function sorted(list) {
    const arr = list.slice();
    if (curSort === 'hot') {
      arr.sort((a, b) => b.read_count - a.read_count);
    } else if (curSort === 'new') {
      arr.sort((a, b) => String(b.added_at).localeCompare(String(a.added_at)));
    } else {
      arr.sort((a, b) => collator.compare(a.title, b.title));
    }
    return arr;
  }

  function srcBadge(source) {
    // 📘 维基文库 / 📗 古登堡计划
    return (source || '').indexOf('维基') !== -1 ? '📘' : '📗';
  }

  function coverClass(cat, isAll) {
    if (isAll || !CATS[cat]) return 'cover-all';
    return 'cover-' + cat;
  }

  function cardHTML(b) {
    const catName = CATS[b.category] || '';
    const author = b.commentator ? (b.author + '（' + b.commentator + '批注）') : b.author;
    const titleCls = b.title.length > 6 ? 'cover-title long' : 'cover-title';
    const badgeTitle = (b.source || '').indexOf('维基') !== -1 ? '维基文库' : '古登堡计划';
    const summary = b.summary ? esc(b.summary) : '';
    return `<a class="book-card" href="book.html?book=${encodeURIComponent(b.title)}">
      <div class="book-card-cover ${coverClass(b.category, curCat === 'all')}">
        <div class="${titleCls}">${esc(b.title)}</div>
        <div class="cover-author">${esc(b.author)}</div>
        ${catName ? `<div class="cover-cat">${esc(catName)}</div>` : ''}
        <span class="cover-badge" title="${badgeTitle}">${srcBadge(b.source)}</span>
        ${summary ? `<div class="book-card-summary">${summary}</div>` : ''}
      </div>
      <div class="book-card-body">
        <div class="book-card-name">${esc(b.title)}</div>
        <div class="book-card-meta">${esc(author)}${b.source ? ' · <span class="src-tag">' + esc(b.source) + '</span>' : ''}</div>
      </div>
    </a>`;
  }

  function renderGrid(list) {
    if (!list.length) {
      gridEl.innerHTML = '<div class="lib-empty">没有符合条件的典籍。</div>';
      return;
    }
    gridEl.innerHTML = list.map(cardHTML).join('');
  }

  function renderPagination(totalPages) {
    if (totalPages <= 1) {
      paginationEl.hidden = true;
      paginationEl.innerHTML = '';
      return;
    }
    paginationEl.hidden = false;
    const parts = [];
    parts.push(`<button class="page-btn" data-page="prev" aria-label="上一页"${curPage <= 1 ? ' disabled' : ''}>‹</button>`);
    for (let p = 1; p <= totalPages; p++) {
      parts.push(`<button class="page-num${p === curPage ? ' is-active' : ''}" data-page="${p}">${p}</button>`);
    }
    parts.push(`<button class="page-btn" data-page="next" aria-label="下一页"${curPage >= totalPages ? ' disabled' : ''}>›</button>`);
    parts.push(`<span class="page-total">${curPage} / ${totalPages} 页</span>`);
    paginationEl.innerHTML = parts.join('');
  }

  function syncURL() {
    const params = new URLSearchParams();
    if (curCat !== 'all') params.set('cat', curCat);
    if (curSort !== 'hot') params.set('sort', curSort);
    if (curPage > 1) params.set('page', curPage);
    if (curQuery) params.set('q', curQuery);
    const qs = params.toString();
    const url = qs ? 'library.html?' + qs : 'library.html';
    history.replaceState(null, '', url);
  }

  function render() {
    const list = sorted(filtered());
    const totalPages = Math.max(1, Math.ceil(list.length / PER_PAGE));
    if (curPage > totalPages) curPage = totalPages;
    const start = (curPage - 1) * PER_PAGE;
    renderGrid(list.slice(start, start + PER_PAGE));
    renderPagination(totalPages);
    subEl.textContent = '五部分類 · 共 ' + list.length + ' 種典籍';
    syncURL();
  }

  function goToPage(p) {
    const totalPages = Math.max(1, Math.ceil(sorted(filtered()).length / PER_PAGE));
    if (p < 1 || p > totalPages) return;
    curPage = p;
    render();
    // 切换页面滚动回书库顶部
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  function readURLParams() {
    const params = new URLSearchParams(window.location.search);
    const cat = params.get('cat');
    if (cat === 'all' || CATS[cat]) curCat = cat || 'all';
    const sort = params.get('sort');
    if (['hot', 'new', 'title'].indexOf(sort) !== -1) curSort = sort;
    const page = parseInt(params.get('page'), 10);
    if (!isNaN(page) && page > 0) curPage = page;
    curQuery = params.get('q') || '';
    if (searchInput) searchInput.value = curQuery;
  }

  function renderTabs() {
    const items = [['all', '全部']].concat(ORDER.map(c => [c, CATS[c]]));
    tabsEl.innerHTML = items.map(([key, name]) =>
      `<button class="lib-tab${curCat === key ? ' is-active' : ''}" data-cat="${key}">${esc(name)}</button>`
    ).join('');
  }

  function bindEvents() {
    tabsEl.addEventListener('click', e => {
      const tab = e.target.closest('.lib-tab');
      if (!tab) return;
      curCat = tab.dataset.cat;
      curPage = 1;
      renderTabs();
      render();
    });

    sortEl.addEventListener('change', () => {
      curSort = sortEl.value;
      curPage = 1;
      render();
    });

    let debounceTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        curQuery = searchInput.value;
        curPage = 1;
        render();
      }, 200);
    });

    paginationEl.addEventListener('click', e => {
      const btn = e.target.closest('[data-page]');
      if (!btn || btn.disabled) return;
      const val = btn.dataset.page;
      if (val === 'prev') goToPage(curPage - 1);
      else if (val === 'next') goToPage(curPage + 1);
      else goToPage(parseInt(val, 10));
    });
  }

  async function init() {
    readURLParams();
    renderTabs();
    sortEl.value = curSort;
    try {
      const data = await loadJSON(DATA_URL);
      books = (data.books || data || []).map(normalizeBook);
      render();
      bindEvents();
    } catch (e) {
      errEl.hidden = false;
      errEl.textContent = '无法加载藏书目录：' + e.message +
        '。请通过本地 HTTP 服务器访问（python3 -m http.server）。';
    }
  }

  init();
})();
