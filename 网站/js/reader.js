/* ============================================================
   阅读页 · 显示篇目正文，上一篇/下一篇 + 字号调节 + 进度记忆
   ============================================================ */
'use strict';

const POS_PREFIX = 'gjs:pos:';

(async function () {
  const bookName = getParam('book') || '';
  const rawIndex = parseInt(getParam('index') || '0', 10);
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
      '。请确认文本/_site_data/' + bookName + '.json 存在，并通过本地 HTTP 服务器访问。';
    return;
  }

  const sections = orderedSections(book);
  if (!sections.length) {
    loading.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = '《' + bookName + '》暂无篇目数据。';
    return;
  }

  // 非法 index 时回退到上次读到的位置
  let index = (rawIndex >= 0 && rawIndex < sections.length) ? rawIndex : -1;
  if (index < 0) {
    const saved = parseInt(localStorage.getItem(POS_PREFIX + bookName) || '-1', 10);
    index = (saved >= 0 && saved < sections.length) ? saved : 0;
  }
  localStorage.setItem(POS_PREFIX + bookName, String(index));

  loading.hidden = true;
  const sec = sections[index];
  const bookUrl = 'book.html?book=' + encodeURIComponent(bookName);

  document.title = sec.title + ' · 古籍文库';
  document.getElementById('header-book').textContent = '《' + book.title + '》';
  document.getElementById('back-btn').href = bookUrl;

  // ---- 正文 ----
  const paras = (sec.paragraphs || []).map(p =>
    `<p>${esc(p)}</p>`).join('') || '<p>（本篇无正文）</p>';

  // 独立注释层：史記【索隱述贊】等卷末注，单独成块展示
  const notesHtml = (sec.notes && sec.notes.length) ? `
    <div class="reader-notes">
      <div class="reader-notes-title">〖索隱述贊〗卷末注疏 · 唐·司馬貞《史記索隱》</div>
      ${sec.notes.map(n => `<p>${esc(n.replace(/^【索隱述贊】\s*/, ''))}</p>`).join('')}
    </div>` : '';

  reader.innerHTML = `
    <div class="reader-head">
      <span class="reader-cat cat-tag cat-${catStyle(sec.category_label)}">${esc(sec.category_label || '未分类')}</span>
      <h2 class="reader-title">${esc(sec.title)}</h2>
      <div class="reader-meta">
        ${sec.source ? esc(sec.source) + ' · ' : ''}
        ${sec.number != null ? ordinal(sec.number) + ' · ' : ''}
        ${sec.char_count != null ? '约 ' + sec.char_count.toLocaleString() + ' 字 · ' : ''}
        ${sec.para_count != null ? sec.para_count + ' 段' : ''}
      </div>
    </div>
    <div class="reader-body" id="reader-body">${paras}</div>
    ${notesHtml}`;

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
  const body = document.getElementById('reader-body');

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
    if (readerArticle && body) {
      readerArticle.style.background = reading.bg;
      readerArticle.style.color = reading.fg;
      const rgb = hexToRgbArr(reading.fg);
      readerArticle.style.borderColor = 'rgba(' + rgb.join(',') + ', 0.3)';
      readerArticle.style.setProperty('--line', 'rgba(' + rgb.join(',') + ', 0.3)');
      body.style.fontSize = reading.fontSize + 'px';
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

  // ---- 下载本篇 TXT ----
  document.getElementById('download-txt').addEventListener('click', () => {
    const text = (sec.paragraphs || []).join('\n\n');
    const filename = sec.title.replace(/[\\/:*?"<>|]/g, '_') + '.txt';
    downloadText(filename, text);
  });

  // ---- 一键复制全文 ----
  document.getElementById('copy-text').addEventListener('click', async () => {
    const text = (sec.title || '') + '\n\n' + (sec.paragraphs || []).join('\n\n');
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
