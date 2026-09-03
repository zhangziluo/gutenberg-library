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

  // ---- 注释层：读取当前书 annotations（顶层数组：word/pinyin/zh_cn/zh_tw/en/…）----
  const annList = book.annotations || [];
  const annMap = new Map();
  (annList || []).forEach(function (a) { if (a && a.word) annMap.set(a.word, a); });
  // 贪心匹配键：按长度降序，避免长词被其中的单字注释截胡
  const annKeys = Array.from(annMap.keys()).sort(function (x, y) { return y.length - x.length; });
  // 首字索引：正文按首字取候选词，避免逐位置遍历整表
  const annFirst = new Map();
  annKeys.forEach(function (w) {
    const c = w.charAt(0);
    const arr = annFirst.get(c);
    if (arr) arr.push(w); else annFirst.set(c, [w]);
  });

  function annLangNow() {
    try { if (window.AnnLang) return AnnLang.get(); } catch (e) { /* 脚本未加载时走兜底 */ }
    try {
      const v = localStorage.getItem('annotation_lang');
      return (v === 'zh_cn' || v === 'zh_tw' || v === 'en') ? v : 'zh_tw';
    } catch (e) { return 'zh_tw'; }
  }
  function annGlossText(entry) {
    if (!entry) return '';
    const v = entry[annLangNow()];
    return (typeof v === 'string' && v.trim()) ? v : '';
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
  /** 段落 HTML：按注释词表贪心打标；原文（繁/简视 textMode）不动，仅加包裹 span */
  function buildParaHtml(orig) {
    if (!orig) return '';
    if (!annKeys.length) return esc(convertText(orig));
    let out = '', i = 0, n = orig.length;
    while (i < n) {
      let hit = null;
      const cands = annFirst.get(orig.charAt(i));
      if (cands) {
        for (let k = 0; k < cands.length; k++) {
          const w = cands[k];
          if (orig.startsWith(w, i)) { hit = w; break; }
        }
      }
      if (hit) {
        const e = annMap.get(hit);
        if (annLevelAllows(e)) {
          out += '<span class="ann-word' + (e && e.is_difficult ? ' ann-hard' : '')
            + (e && e.rare ? ' ann-rare' : '') + '" data-ann="' + esc(hit) + '">'
            + esc(convertText(hit)) + '</span>';
        } else {
          out += esc(convertText(hit));
        }
        i += hit.length;
      } else {
        out += esc(convertText(orig[i]));
        i += 1;
      }
    }
    return out;
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

    // 供 goAIMode 使用：始终送原文（简繁转换不影响 AI 对话）
    window.__readerOriginal = { title: sec.title, paras: origParas };

    // 同步简繁按钮高亮
    document.querySelectorAll('.textmode-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === textMode);
    });
  }

  renderReader();

  // ---- 注释小卡：点击正文注释词弹出；切语言仅更新文案，不刷新页面 ----
  const annPopEl = document.createElement('div');
  annPopEl.className = 'ann-pop';
  document.body.appendChild(annPopEl);
  let annPopWord = null;

  function fillAnnPop(word, entry) {
    const gloss = annGlossText(entry);
    const py = (entry && entry.pinyin) ? entry.pinyin : '';
    annPopEl.textContent = '';
    const head = document.createElement('div');
    head.className = 'ann-pop-head';
    const w = document.createElement('b');
    w.textContent = word;
    head.appendChild(w);
    if (py) { const p = document.createElement('span'); p.className = 'ann-pop-py'; p.textContent = py; head.appendChild(p); }
    const lg = document.createElement('span'); lg.className = 'ann-pop-lang'; lg.textContent = annLangLabel(); head.appendChild(lg);
    annPopEl.appendChild(head);
    const body = document.createElement('div');
    body.className = 'ann-pop-body';
    if (annLevelFullGloss(entry)) {
      body.textContent = gloss || (py ? py + ' · ' + annPlaceholder() : annPlaceholder());
    } else {
      // 进阶档：常见多音字只给注音提示，不展开释义
      body.textContent = (entry && entry.note) || '多音字，讀音須依文意而定。';
    }
    annPopEl.appendChild(body);
    if (entry && entry.rare) {
      const tag = document.createElement('div'); tag.className = 'ann-pop-tag'; tag.textContent = '重難字';
      annPopEl.appendChild(tag);
    } else if (entry && entry.multi) {
      const tag = document.createElement('div'); tag.className = 'ann-pop-tag'; tag.textContent = '多音字';
      annPopEl.appendChild(tag);
    }
    annPopEl.classList.add('show');
  }
  function showAnnPopByWord(word) {
    const entry = annMap.get(word);
    if (!entry) return;
    annPopWord = word;
    fillAnnPop(word, entry);
  }
  function hideAnnPop() { annPopWord = null; annPopEl.classList.remove('show'); }

  reader.addEventListener('click', function (e) {
    const w = e.target.closest('.ann-word');
    if (w) { showAnnPopByWord(w.getAttribute('data-ann')); }
    else if (!e.target.closest('.ann-pop')) { hideAnnPop(); }
  });
  document.addEventListener('scroll', hideAnnPop, true);
  // 切注释语言 → 已打开的小卡即时换文案（正文/页面不刷新）
  document.addEventListener('annlangchange', function () {
    if (annPopWord && annMap.has(annPopWord)) showAnnPopByWord(annPopWord);
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

  // ---- 阅读设置：字体 / 配色 / 背景字色（与 AI 阅读器共用 gjs:reading） ----
  const READING_KEY = 'gjs:reading';
  const readerArticle = document.querySelector('.reader');

  let reading = { fontSize: 17, bg: '#f5ead0', fg: '#3a3226' };

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
    // 羊皮纸材质：仅默认羊皮纸色 #f5ead0 启用纹理，自定义色保持纯色
    const paper = reading.bg.toLowerCase() === '#f5ead0';
    // 自定义背景铺满整个阅读区（顶部导航栏以下）：header 为不透明渐变保持不变，
    // body 仅设 background-color，让 .reading-paper 的纹理渐变可叠加显示
    document.body.style.backgroundColor = reading.bg;
    document.body.classList.toggle('reading-paper', paper);
    // 设置栏标签 / 页脚文字跟随字色，避免深色背景下看不清（顶部导航不受影响）
    document.body.style.setProperty('--rs-fg', reading.fg);
    if (readerArticle && curBody) {
      readerArticle.style.backgroundColor = reading.bg;
      readerArticle.classList.toggle('reading-paper', paper);
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

  // 恢复上次设置（与 AI 阅读器共用，跨页同步）
  try {
    const saved = JSON.parse(localStorage.getItem(READING_KEY) || '{}');
    if (typeof saved.fontSize === 'number') reading.fontSize = Math.max(12, Math.min(40, saved.fontSize));
    if (saved.bg && /^#[0-9a-fA-F]{6}$/.test(saved.bg)) reading.bg = saved.bg;
    if (saved.fg && /^#[0-9a-fA-F]{6}$/.test(saved.fg)) reading.fg = saved.fg;
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

  // （AI 阅读模式已由 reader.html 内联 goAIMode() + onclick 处理，此处不再重复绑定）

  window.scrollTo(0, 0);
})();
