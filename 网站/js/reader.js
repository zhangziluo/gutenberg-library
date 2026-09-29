/* ============================================================
   阅读页 · 显示篇目正文，上一篇/下一篇 + 字号调节 + 进度记忆
   ============================================================ */
'use strict';

const POS_PREFIX = 'gjs:pos:';

(async function () {
  const bookName = getParam('book') || '';
  const rawIndex = parseInt(getParam('index') || '0', 10);
  const anchorParam = getParam('anchor') || '';
  const loading = document.getElementById('loading');
  const errorBox = document.getElementById('error');
  const reader = document.getElementById('reader');

  if (!bookName) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = '缺少 book 参数，请从书目页进入。';
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

  const sections = orderedSections(book);
  if (!sections.length) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = '《' + bookName + '》暂无篇目数据。';
    return;
  }

  // 非法 index 时回退到上次读到的位置；anchor 定位优先（句子池跳转）
  let index = -1;
  if (anchorParam) {
    index = sections.findIndex(s => (s.paragraphs || []).some(p => p.indexOf(anchorParam) >= 0));
  }
  if (index < 0 && rawIndex >= 0 && rawIndex < sections.length) index = rawIndex;
  if (index < 0) {
    const saved = parseInt(localStorage.getItem(POS_PREFIX + bookName) || '-1', 10);
    index = (saved >= 0 && saved < sections.length) ? saved : 0;
  }
  localStorage.setItem(POS_PREFIX + bookName, String(index));

  loading.hidden = true;
  const sec = sections[index];
  const bookUrl = 'book.html?book=' + encodeURIComponent(bookName);

  document.title = sec.title + ' · 一堆古书';
  document.getElementById('header-book').textContent = '《' + book.title + '》';
  document.getElementById('back-btn').href = bookUrl;

  // ---- 简繁转换（opencc-js）：原文 / 繁→简 / 简→繁 ----
  const TEXT_MODE_KEY = 'textMode';
  const origParas = sec.paragraphs || [];
  const origNotes = sec.notes || [];

  // ---- 注释层：词汇表（vocab_final.json 提供词边界）+ 本书 annotations（提供释义）----
  //   打标由 vocab-matcher 负责：中文 Trie 最长前缀匹配、英文整词正则 →
  //   命中整体包 <wise data-word=完整词形 data-key=词典键>；空闲分批，不阻塞首屏。
  const annList = book.annotations || [];
  const annMap = new Map();                                   // 词典键 → 词条（释义兜底查这里）
  annList.forEach(function (a) { if (a && a.word) annMap.set(a.word, a); });
  let matcher = null, matcherPromise = null, annPassSeq = 0;

  /** 密度策略：gloss（默认，只标有释义的词）| all（词表命中全标）| rare（只标重难多音） */
  function wrapMode() {
    const m = window.VOCAB_WRAP;
    return (m === 'all' || m === 'rare' || m === 'gloss') ? m : 'gloss';
  }
  /** 词表条目：window.VOCAB_FINAL_URL === null 可显式关闭；缺失/离线静默降级为「只用 annotations」 */
  function loadVocabRows() {
    if (window.VOCAB_FINAL_URL === null) return Promise.resolve([]);
    if (window.VOCAB_FINAL) {
      const d = window.VOCAB_FINAL;
      return Promise.resolve(Array.isArray(d) ? d : [].concat(d.words || [], d.zh || [], d.en || []));
    }
    const url = typeof window.VOCAB_FINAL_URL === 'string' ? window.VOCAB_FINAL_URL : DATA_BASE + 'vocab_final.json';
    return loadJSON(url).then(function (d) {
      return Array.isArray(d) ? d : [].concat(d.words || [], d.zh || [], d.en || []);
    }).catch(function () { return []; });
  }
  /** annotations 词条：繁体单字键补简体形（opencc 兜底）→「繁→简」显示模式也能命中 */
  function annEntriesForMatcher() {
    const conv = ensureConverters().tw2cn;
    if (!conv) return annList;
    return annList.map(function (a) {
      if (!a || !a.word || a.simp || /[A-Za-z]/.test(a.word)) return a;
      let s = '';
      try { s = conv(a.word) || ''; } catch (e) { s = ''; }
      return (s && s !== a.word) ? Object.assign({}, a, { simp: s }) : a;
    });
  }
  function ensureMatcher() {
    if (matcherPromise) return matcherPromise;
    matcherPromise = loadVocabRows().then(function (rows) {
      if (!window.VocabMatcher) return null;                  // 脚本未加载 → 纯文本阅读
      matcher = VocabMatcher.build(annEntriesForMatcher().concat(rows), { mode: wrapMode() });
      return matcher;
    });
    return matcherPromise;
  }
  /** 渲染后空闲分批打标（重渲染/换档 → 代次 +1，旧任务自动作废） */
  function annotateBody() {
    const body = document.getElementById('reader-body');
    if (!body) return;
    let seq = ++annPassSeq;
    const idle = (window.requestIdleCallback || function (fn) { return setTimeout(fn, 16); });
    idle(function () {                                        // 建词表（~200ms）也让出首屏
      if (seq !== annPassSeq) return;
      ensureMatcher().then(function (m) {
        if (!m || seq !== annPassSeq) return;
        m.annotate(body, {
          mode: wrapMode(),
          maxWords: 4000,                                     // 单篇上限（防御性；超长正文不卡）
          allow: function (e) { return annLevelAllows(e); }
        });
      }).catch(function () { /* 打标失败不影响阅读 */ });
    });
  }

  function annLangNow() {
    try { if (window.AnnLang) return AnnLang.get(); } catch (e) { /* 脚本未加载时走兜底 */ }
    try {
      const v = localStorage.getItem('annotation_lang');
      return (v === 'zh_cn' || v === 'zh_tw' || v === 'en') ? v : 'zh_tw';
    } catch (e) { return 'zh_tw'; }
  }
  /** 释义占位值：这些不算「有释义」（与 vocab-matcher 的 PENDING_DEF 对齐） */
  const ANN_VAGUE_DEF = /^(待补|待補|TBD)$/;
  /** 词卡释义：当前语言槽（zh_cn/zh_tw/en）→ 词表行自带的 definition 兜底 */
  function annGlossText(entry) {
    if (!entry) return '';
    const v = entry[annLangNow()];
    if (typeof v === 'string' && v.trim()) return v;
    const d = entry.definition;                                // vocab_final.json 的 definition
    if (typeof d === 'string' && d.trim() && !ANN_VAGUE_DEF.test(d.trim())) return d;
    return '';
  }
  function annPlaceholder() {
    const l = annLangNow();
    return l === 'en' ? 'TBD' : l === 'zh_cn' ? '待补' : '待補';
  }
  function annLangLabel() {
    const l = annLangNow();
    return l === 'zh_cn' ? '简中' : l === 'en' ? 'EN' : '繁中';
  }

  // ---- 注释档位：新手/进阶/专家（字号 + 注释密度）----
  const ANN_LEVEL_KEY = 'annLevel';
  const ANN_LEVELS = {
    beginner:      { label: '新手', font: 20, title: '大字号 + 全注释' },
    intermediate:  { label: '进阶', font: 17, title: '中字号 + 多音注音/难字释义' },
    expert:        { label: '专家', font: 15, title: '小字号 + 仅标重难字' }
  };
  function annLevelNow() {
    try {
      const v = localStorage.getItem(ANN_LEVEL_KEY);
      if (v && ANN_LEVELS[v]) return v;
    } catch (e) { /* 忽略 */ }
    return 'beginner';
  }
  function annLevelSave(v) {
    try { localStorage.setItem(ANN_LEVEL_KEY, v); } catch (e) {}
  }
  /** 当前档位是否给该注释词加下划线 */
  function annLevelAllows(entry) {
    const lv = annLevelNow();
    if (lv === 'expert') return !!(entry && entry.rare);
    return true;
  }
  /** 当前档位下注释卡正文是否展示完整释义（否则只展示读音提示） */
  function annLevelFullGloss(entry) {
    const lv = annLevelNow();
    if (lv === 'intermediate') return !!(entry && entry.rare);
    return true;
  }
  /**
   * 段落 HTML：只做转义 + 简繁转换。
   * 打标（<wise>）由 vocab-matcher 在渲染后的 DOM 上做（TreeWalker + 最长匹配），
   * 这样不会再出现「按字符索引滑窗」把 mornin' 截成 mornin、把中文词拆成单字的问题。
   */
  function buildParaHtml(orig) {
    return orig ? esc(convertText(orig)) : '';
  }

  function loadTextMode() {
    try {
      const v = localStorage.getItem(TEXT_MODE_KEY);
      return (v === 'toSimple' || v === 'toTraditional') ? v : 'original';
    } catch (e) { return 'original'; }
  }
  function saveTextMode(v) {
    try { localStorage.setItem(TEXT_MODE_KEY, v); } catch (e) {}
  }

  let textMode = loadTextMode();
  let converters = null;
  function ensureConverters() {
    if (converters) return converters;
    converters = {};
    if (typeof OpenCC !== 'undefined' && OpenCC.Converter) {
      try {
        converters.tw2cn = new OpenCC.Converter({ from: 'tw', to: 'cn' });
        converters.cn2tw = new OpenCC.Converter({ from: 'cn', to: 'tw' });
      } catch (e) { /* 转换器创建失败则维持原文 */ }
    }
    return converters;
  }
  function convertText(s) {
    if (textMode === 'original' || !s) return s;
    const c = ensureConverters();
    try {
      if (textMode === 'toSimple' && c.tw2cn) return c.tw2cn(s);
      if (textMode === 'toTraditional' && c.cn2tw) return c.cn2tw(s);
    } catch (e) { /* 转换失败回退原文 */ }
    return s;
  }
  function displayParas() { return origParas.map(p => convertText(p)); }
  function displayTitle() { return convertText(sec.title); }

  // 正文渲染（正文 + 独立注释层），按 textMode 实时转换；原文始终只保留一份在内存
  function renderReader() {
    if (matcher) matcher.cancel();                            // 作废上一轮未跑完的打标
    const paras = origParas.map(p => `<p>${buildParaHtml(p)}</p>`).join('') || '<p>（本篇无正文）</p>';
    const notesHtml = (origNotes.length) ? `
      <div class="reader-notes">
        <div class="reader-notes-title">〖索隱述贊〗卷末注疏 · 唐·司馬貞《史記索隱》</div>
        ${origNotes.map(n => `<p>${esc(convertText(n.replace(/^【索隱述贊】\s*/, '')))}</p>`).join('')}
      </div>` : '';

    reader.innerHTML = `
      <div class="reader-head">
        <span class="reader-cat cat-tag cat-${catStyle(sec.category_label)}">${esc(sec.category_label || '未分类')}</span>
        <h2 class="reader-title">${esc(convertText(sec.title))}</h2>
        <div class="reader-meta">
          ${sec.source ? esc(sec.source) + ' · ' : ''}
          ${sec.number != null ? ordinal(sec.number) + ' · ' : ''}
          ${sec.char_count != null ? '约 ' + sec.char_count.toLocaleString() + ' 字 · ' : ''}
          ${sec.para_count != null ? sec.para_count + ' 段' : ''}
        </div>
      </div>
      <div class="reader-body" id="reader-body">${paras}</div>
      ${notesHtml}`;

    // 同步简繁按钮高亮
    document.querySelectorAll('.textmode-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === textMode);
    });

    annotateBody();                                           // 空闲分批打标（不阻塞渲染）
  }

  renderReader();

  // ---- 注释小卡：点击正文注释词弹出；切语言仅更新文案，不刷新页面 ----
  const annPopEl = document.createElement('div');
  annPopEl.className = 'ann-pop';
  document.body.appendChild(annPopEl);
  let annPopNode = null;                                       // 当前打开的 <wise>

  /** 词典键 / 显示词形 → 词条（先查本书 annotations，再查合并词表） */
  function annLookup(key, word) {
    if (key && annMap.has(key)) return annMap.get(key);
    if (word && annMap.has(word)) return annMap.get(word);
    if (matcher) {
      const e = matcher.lookup(key) || (word !== key ? matcher.lookup(word) : null);
      if (e) return e;
    }
    return null;
  }

  /** 词卡：data-word 是**完整词形**（含 mornin' 的词尾撇号），data-key 才是词典键 */
  function fillAnnPop(el) {
    const word = el.getAttribute('data-word') || '';
    const key = el.getAttribute('data-key') || word;
    const entry = annLookup(key, word);
    const freq = parseInt(el.getAttribute('data-freq') || '0', 10);
    const books = parseInt(el.getAttribute('data-books') || '0', 10);
    const parts = (el.getAttribute('data-parts') || '').split('|').filter(Boolean);
    const py = (entry && entry.pinyin) ? entry.pinyin : '';

    annPopEl.textContent = '';
    const head = document.createElement('div');
    head.className = 'ann-pop-head';
    const w = document.createElement('b');
    w.textContent = word;                                      // ← 完整词形（如 mornin'）
    head.appendChild(w);
    if (py) { const p = document.createElement('span'); p.className = 'ann-pop-py'; p.textContent = py; head.appendChild(p); }
    const lg = document.createElement('span'); lg.className = 'ann-pop-lang'; lg.textContent = annLangLabel(); head.appendChild(lg);
    annPopEl.appendChild(head);

    const body = document.createElement('div');
    body.className = 'ann-pop-body';
    if (entry && entry.note && !annLevelFullGloss(entry)) {
      body.textContent = entry.note;                           // 进阶档：多音字只给注音提示
    } else {
      const gloss = annGlossText(entry);
      if (gloss) {
        body.textContent = gloss + (key !== word ? '（詞形 ' + key + '）' : '');
      } else if (freq) {
        body.textContent = '全庫出現 ' + freq + ' 次 · 見於 ' + books + ' 本 · ' + annPlaceholder();
      } else {
        body.textContent = py ? py + ' · ' + annPlaceholder() : annPlaceholder();
      }
    }
    annPopEl.appendChild(body);

    if (parts.length) {                                        // 整词无释义 → 列成分字释义
      const box = document.createElement('div');
      box.className = 'ann-pop-parts';
      parts.forEach(function (pw) {
        const pe = annLookup(pw, pw);
        const line = document.createElement('div');
        line.className = 'ann-pop-part';
        const b = document.createElement('b');
        b.textContent = pw;
        line.appendChild(b);
        const t = document.createElement('span');
        const pg = annGlossText(pe);
        t.textContent = pg || (pe && pe.pinyin ? pe.pinyin + ' · ' + annPlaceholder() : annPlaceholder());
        line.appendChild(t);
        box.appendChild(line);
      });
      annPopEl.appendChild(box);
    }

    let tag = '';
    if (entry && entry.rare) tag = '重難字';
    else if (entry && entry.multi) tag = '多音字';
    else if (!annGlossText(entry) && freq) tag = '詞表詞';
    else if (entry && entry.need_ai) tag = 'AI 待補';   // 释义为逐字合成/缺失 → 标注待精修
    if (tag) {
      const t = document.createElement('div'); t.className = 'ann-pop-tag'; t.textContent = tag;
      annPopEl.appendChild(t);
    }
    annPopEl.classList.add('show');
  }
  function showAnnPop(el) {
    if (!el) return;
    annPopNode = el;
    fillAnnPop(el);
  }
  function hideAnnPop() { annPopNode = null; annPopEl.classList.remove('show'); }

  reader.addEventListener('click', function (e) {
    const el = e.target.closest ? e.target.closest('wise, .ann-word') : null;
    if (el) { showAnnPop(el); }
    else if (!e.target.closest('.ann-pop')) { hideAnnPop(); }
  });
  document.addEventListener('scroll', hideAnnPop, true);
  // 切注释语言 → 已打开的小卡即时换文案（正文/页面不刷新）
  document.addEventListener('annlangchange', function () {
    if (annPopNode && annPopNode.isConnected) fillAnnPop(annPopNode);
  });

  // anchor 高亮：滚动到包含该句的段落并短暂高亮（句子池跳转）
  if (anchorParam) {
    setTimeout(() => {
      const paras = document.querySelectorAll('#reader-body p');
      for (const p of paras) {
        if (p.textContent.indexOf(anchorParam) >= 0) {
          p.classList.add('anchor-flash');
          p.scrollIntoView({ block: 'center' });
          break;
        }
      }
    }, 60);
  }

  // 简繁切换：即时重渲染；原文只请求一次，切换为前端即时转换
  document.querySelectorAll('.textmode-btn').forEach(b => {
    b.addEventListener('click', () => {
      textMode = b.dataset.mode;
      saveTextMode(textMode);
      renderReader();
      applyReading();
    });
  });

  // 阅读模式切换（新手/进阶/专家：字号 + 注释密度）
  function syncLevelButtons() {
    const cur = annLevelNow();
    document.querySelectorAll('.level-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.level === cur);
    });
  }
  document.querySelectorAll('.level-btn').forEach(b => {
    b.addEventListener('click', () => {
      const lv = b.dataset.level;
      annLevelSave(lv);
      syncLevelButtons();
      const meta = ANN_LEVELS[lv];
      if (meta && reading) reading.fontSize = meta.font;
      hideAnnPop();
      renderReader();
      applyReading();
    });
  });
  syncLevelButtons();

  // ---- 上一篇 / 下一篇 ----
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');

  if (index > 0) {
    prevBtn.href = 'reader.html?book=' + encodeURIComponent(bookName) + '&index=' + (index - 1);
  } else {
    prevBtn.removeAttribute('href');
    prevBtn.style.opacity = '0.4';
    prevBtn.style.pointerEvents = 'none';
  }
  if (index < sections.length - 1) {
    nextBtn.href = 'reader.html?book=' + encodeURIComponent(bookName) + '&index=' + (index + 1);
  } else {
    nextBtn.removeAttribute('href');
    nextBtn.style.opacity = '0.4';
    nextBtn.style.pointerEvents = 'none';
  }

  // ---- 阅读设置：字体 / 配色 / 背景字色（gjs:reading） ----
  const READING_KEY = 'gjs:reading';
  const readerArticle = document.querySelector('.reader');

  let reading = { fontSize: 17, bg: '#faf8f5', fg: '#1a1a1a' };

  function hexToRgbArr(hex) {
    const m = String(hex).replace('#', '').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (!m) return [255, 255, 255];
    return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  }
  function hexToRgbStr(hex) { return hexToRgbArr(hex).join(','); }
  function rgbStrToHex(rgbStr) {
    const p = String(rgbStr).trim().split(/[,，\s]+/).map(x => parseInt(x, 10));
    if (p.length !== 3 || p.some(isNaN)) return null;
    return '#' + p.map(v => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('');
  }

  function applyReading() {
    const curBody = document.getElementById('reader-body');
    // 背景一律纯色，不叠加羊皮纸纹理（视觉规范：纯暖白或用户自定义色）
    document.body.style.backgroundColor = reading.bg;
    // 设置栏标签 / 页脚文字跟随字色，避免深色背景下看不清（顶部导航不受影响）
    document.body.style.setProperty('--rs-fg', reading.fg);
    if (readerArticle && curBody) {
      readerArticle.style.backgroundColor = reading.bg;
      readerArticle.style.color = reading.fg;
      const rgb = hexToRgbArr(reading.fg);
      readerArticle.style.borderColor = 'rgba(' + rgb.join(',') + ', 0.3)';
      readerArticle.style.setProperty('--line', 'rgba(' + rgb.join(',') + ', 0.3)');
      curBody.style.fontSize = reading.fontSize + 'px';
    }
    document.getElementById('fontSizeVal').textContent = reading.fontSize;
    document.getElementById('bgPicker').value = reading.bg;
    document.getElementById('bgHex').value = reading.bg;
    document.getElementById('bgRgb').value = hexToRgbStr(reading.bg);
    document.getElementById('fgPicker').value = reading.fg;
    document.getElementById('fgHex').value = reading.fg;
    document.getElementById('fgRgb').value = hexToRgbStr(reading.fg);
    document.querySelectorAll('.scheme-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.bg === reading.bg && b.dataset.fg === reading.fg);
    });
    try { localStorage.setItem(READING_KEY, JSON.stringify(reading)); } catch (e) {}
    // 全局 AI 助手与阅读页共用自定义模板：同页实时同步主题
    if (window.GAI && window.GAI.theme) window.GAI.theme();
  }

  // 恢复上次设置（与全局 AI 助手主题跨页同步）
  try {
    const saved = JSON.parse(localStorage.getItem(READING_KEY) || '{}');
    if (typeof saved.fontSize === 'number') reading.fontSize = Math.max(12, Math.min(40, saved.fontSize));
    if (saved.bg && /^#[0-9a-fA-F]{6}$/.test(saved.bg)) {
      // 旧版「羊皮纸 #f5ead0」→ 新暖白 #faf8f5（视觉统一迁移）
      reading.bg = (saved.bg.toLowerCase() === '#f5ead0') ? '#faf8f5' : saved.bg;
    }
    if (saved.fg && /^#[0-9a-fA-F]{6}$/.test(saved.fg)) {
      reading.fg = (saved.fg.toLowerCase() === '#3a3226') ? '#1a1a1a' : saved.fg;
    }
  } catch (e) {}
  applyReading();

  // 字体调节
  document.getElementById('fontMinus').addEventListener('click', () => {
    reading.fontSize = Math.max(12, reading.fontSize - 1);
    applyReading();
  });
  document.getElementById('fontPlus').addEventListener('click', () => {
    reading.fontSize = Math.min(40, reading.fontSize + 1);
    applyReading();
  });

  // 配色方案
  document.querySelectorAll('.scheme-btn').forEach(b => {
    b.addEventListener('click', () => {
      reading.bg = b.dataset.bg;
      reading.fg = b.dataset.fg;
      applyReading();
    });
  });

  // 背景：取色器 / HEX / RGB
  document.getElementById('bgPicker').addEventListener('input', e => { reading.bg = e.target.value; applyReading(); });
  document.getElementById('bgHex').addEventListener('change', e => {
    const v = e.target.value.trim();
    if (/^#?[0-9a-fA-F]{6}$/.test(v)) { reading.bg = (v.charAt(0) === '#' ? v : '#' + v); applyReading(); }
  });
  document.getElementById('bgRgb').addEventListener('change', e => {
    const hex = rgbStrToHex(e.target.value);
    if (hex) { reading.bg = hex; applyReading(); }
  });

  // 字色：取色器 / HEX / RGB
  document.getElementById('fgPicker').addEventListener('input', e => { reading.fg = e.target.value; applyReading(); });
  document.getElementById('fgHex').addEventListener('change', e => {
    const v = e.target.value.trim();
    if (/^#?[0-9a-fA-F]{6}$/.test(v)) { reading.fg = (v.charAt(0) === '#' ? v : '#' + v); applyReading(); }
  });
  document.getElementById('fgRgb').addEventListener('change', e => {
    const hex = rgbStrToHex(e.target.value);
    if (hex) { reading.fg = hex; applyReading(); }
  });

  // ---- 下载本篇 TXT（按当前简繁模式导出转换后文本） ----
  document.getElementById('download-txt').addEventListener('click', () => {
    const text = displayParas().join('\n\n');
    const filename = displayTitle().replace(/[\\/:*?"<>|]/g, '_') + '.txt';
    downloadText(filename, text);
  });

  // ---- 一键复制全文（复制转换后的文本） ----
  document.getElementById('copy-text').addEventListener('click', async () => {
    const text = displayTitle() + '\n\n' + displayParas().join('\n\n');
    const btn = document.getElementById('copy-text');
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      const old = btn.textContent;
      btn.textContent = '✅ 已复制';
      setTimeout(() => { btn.textContent = old; }, 1500);
    } catch (e) {
      alert('复制失败：' + e.message);
    }
  });

  window.scrollTo(0, 0);
})();
