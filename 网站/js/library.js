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
  // 维基文库「待入库」预览数据（build_wikisource_index.py 生成）
  const PENDING_URL = 'assets/data/wikisource-pending.json';
  const BU_KEY = { '經部': 'jing', '史部': 'shi', '子部': 'zi', '集部': 'ji',
                   '叢部': 'cong', '近現代文學': 'ji' };

  const gridEl = document.getElementById('lib-grid');
  const paginationEl = document.getElementById('lib-pagination');
  const subEl = document.getElementById('lib-sub');
  const errEl = document.getElementById('lib-error');
  const tabsEl = document.getElementById('lib-tabs');
  const sortEl = document.getElementById('lib-sort');
  const searchInput = document.getElementById('lib-search-input');
  const modeEl = document.getElementById('lib-mode');
  const recOnlyWrap = document.getElementById('lib-reconly-wrap');
  const recOnlyInput = document.getElementById('lib-reconly');

  let books = [];        // 本站藏书（normalize 后）
  let pendingBooks = []; // 待入库（维基文库）
  let pendingLoaded = false;
  let pendingMeta = null;
  let curMode = 'shelf';  // shelf | pending
  let recOnly = true;     // 待入库模式下：只看推荐 ⭐
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

  // 复制到剪贴板（旧环境回退 execCommand）
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        resolve();
      } catch (e) {
        reject(e);
      }
      document.body.removeChild(ta);
    });
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

  // 待入库条目 → 同一套卡片 schema（_pending 标记用于渲染差异）
  function normalizePending(b) {
    return {
      book_id: 'ws:' + (b.page || b.title),
      title: b.title || '',
      author: b.author || '',
      commentator: '',
      category: BU_KEY[b.bu] || '',
      subcategory: b.sub || '',
      bu: b.bu || '',
      summary: '',
      highlights: [],
      source: '维基文库',
      source_url: b.url || '',
      license: '',
      chapter_count: 0,
      added_at: '',
      read_count: b.size_kb || 0,
      _pending: true,
      _page: b.page || '',
      _url: b.url || '',
      _rec: !!b.recommended,
      _size: b.size_kb || 0,
    };
  }

  function activeBooks() {
    return curMode === 'pending' ? pendingBooks : books;
  }

  // 过滤（分类 + 搜索词；待入库模式另按「只看推荐」）
  function filtered() {
    const q = curQuery.trim().toLowerCase();
    return activeBooks().filter(b => {
      if (curMode === 'pending' && recOnly && !b._rec) return false;
      if (curCat !== 'all' && b.category !== curCat) return false;
      if (q) {
        const hay = (b.title + ' ' + b.author + ' ' + b.commentator + ' ' +
                     (b.bu || '') + ' ' + (b.subcategory || '')).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  // 排序（热门=阅读量 / 最新=加入时间 / 书名=拼音）
  function sorted(list) {
    const arr = list.slice();
    if (curMode === 'pending') {
      if (curSort === 'title') arr.sort((a, b) => collator.compare(a.title, b.title));
      else arr.sort((a, b) => (b._size - a._size) || collator.compare(a.title, b.title));
      return arr;
    }
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

  // 待入库卡片：不跳站内阅读页，而是跳维基文库原页；另附「复制入库命令」
  function pendingCardHTML(b) {
    const catName = CATS[b.category] || b.bu || '';
    const titleCls = b.title.length > 6 ? 'cover-title long' : 'cover-title';
    const star = b._rec ? '<span class="cover-star" title="推荐优先">⭐</span>' : '';
    const size = b._size ? (b._size + ' KB') : '';
    const sub = b.subcategory || b.bu || '';
    const cmd = '.venv/bin/python 文本/新书/wikisource_batch.py fetch --page "' +
      b._page + '" --retry-failed && .venv/bin/python 文本/新书/wikisource_batch.py ' +
      'ingest --page "' + b._page + '"';
    return `<div class="book-card is-pending">
      <a class="card-main" href="${esc(b._url)}" target="_blank" rel="noopener" title="在维基文库查看：${esc(b._page)}">
        <div class="book-card-cover ${coverClass(b.category, curCat === 'all')}">
          <div class="${titleCls}">${esc(b.title)}</div>
          <div class="cover-author">${esc(b.author || '佚名')}</div>
          ${catName ? `<div class="cover-cat">${esc(catName)}</div>` : ''}
          <span class="cover-badge" title="来源：维基文库">📥</span>
          ${star}
        </div>
        <div class="book-card-body">
          <div class="book-card-name">${esc(b.title)}</div>
          <div class="book-card-meta">${esc(b.author || '佚名')}${sub ? ' · <span class="src-tag">' + esc(sub) + '</span>' : ''}${size ? ' · ' + size : ''}</div>
        </div>
      </a>
      <button class="card-cmd" type="button" data-cmd="${esc(cmd)}" title="复制本机的抓取+入库命令（含智能分章与释义回填）">📋 复制入库命令</button>
    </div>`;
  }

  function cardHTML(b) {
    if (b._pending) return pendingCardHTML(b);
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
    if (curMode !== 'shelf') params.set('mode', curMode);
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
    subEl.textContent = curMode === 'pending'
      ? ('维基文库待入库 · 当前 ' + list.length + ' 种' +
         (pendingMeta ? '（候选 ' + pendingMeta.total + '，推荐 ⭐ ' +
          pendingMeta.recommended_total + '）' : '') +
         (recOnly ? ' · 只看推荐' : ''))
      : ('五部分類 · 共 ' + list.length + ' 種典籍');
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
    if (params.get('mode') === 'pending') curMode = 'pending';
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

  function renderModeButtons() {
    if (!modeEl) return;
    Array.prototype.forEach.call(modeEl.querySelectorAll('.lib-mode-btn'), btn => {
      btn.classList.toggle('is-active', btn.dataset.mode === curMode);
    });
    if (recOnlyWrap) recOnlyWrap.hidden = curMode !== 'pending';
    if (recOnlyInput) recOnlyInput.checked = recOnly;
  }

  async function loadPending() {
    if (pendingLoaded) return;
    const data = await loadJSON(PENDING_URL);
    pendingMeta = data;
    pendingBooks = (data.books || []).map(normalizePending);
    pendingLoaded = true;
  }

  async function setMode(mode) {
    if (mode === curMode) return;
    curMode = mode;
    curPage = 1;
    try {
      if (curMode === 'pending') await loadPending();
    } catch (e) {
      errEl.hidden = false;
      errEl.textContent = '无法加载维基文库待入库数据：' + e.message;
      return;
    }
    renderModeButtons();
    renderTabs();
    render();
  }

  function bindEvents() {
    // 「复制入库命令」（待入库卡片）
    gridEl.addEventListener('click', e => {
      const btn = e.target.closest('.card-cmd');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      const orig = btn.getAttribute('data-label') || btn.textContent;
      btn.setAttribute('data-label', orig);
      copyText(btn.dataset.cmd || '').then(() => {
        btn.classList.add('is-copied');
        btn.textContent = '✅ 已复制';
        setTimeout(() => {
          btn.classList.remove('is-copied');
          btn.textContent = orig;
        }, 1600);
      }).catch(() => {
        btn.textContent = '复制失败（请手动复制菜单里的命令）';
      });
    });

    if (modeEl) {
      modeEl.addEventListener('click', e => {
        const btn = e.target.closest('.lib-mode-btn');
        if (btn) setMode(btn.dataset.mode);
      });
    }
    if (recOnlyInput) {
      recOnlyInput.addEventListener('change', () => {
        recOnly = recOnlyInput.checked;
        curPage = 1;
        render();
      });
    }
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
    renderModeButtons();
    sortEl.value = curSort;
    try {
      const data = await loadJSON(DATA_URL);
      books = (data.books || data || []).map(normalizeBook);
      if (curMode === 'pending') await loadPending();
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
