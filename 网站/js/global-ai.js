/* ============================================================
   一堆古书 · 全局 AI 助手（全站浮动）
   - 通用问答 / 翻译 / 书籍推荐（DeepSeek，用户自填 Key）
   - 章节阅读页自动携带 当前章节标题 + 作者 + 书名 作为上下文
   - Key 复用 AI 阅读器存储键 guoxue_api_key（仅存浏览器本地）
   引入：<script src="js/global-ai.js"></script>（放在 </body> 前）
   ============================================================ */
(function () {
  'use strict';

  var KEY_STORAGE = 'guoxue_api_key';
  var API_URL = 'https://api.deepseek.com/v1/chat/completions';
  var MODEL = 'deepseek-chat';
  var READING_KEY = 'gjs:reading';  // 阅读页自定义模板键（与阅读页 / AI 阅读器共用）
  var PAPER_BG = '#f5ead0';         // 默认羊皮纸底色
  var PAPER_FG = '#3a3226';         // 默认墨色文字

  // 书名 → 作者（与 catalog.json 保持一致；用于章节页上下文）
  var AUTHORS = {
    '史記': '司馬遷', '漢書': '班固', '三國志': '陳壽',
    '三國演義': '羅貫中', '水滸傳': '施耐庵', '西遊記': '吳承恩',
    '紅樓夢': '曹雪芹', '古文觀止': '吳楚材、吳調侯'
  };

  var MODES = {
    chat: {
      system: '你是「一堆古书」（古登堡繁体古籍在线阅读站）的 AI 助手，精通中国古典文献：经史子集、二十四史、四大名著、古文選本。请用简体中文、简洁准确地回答；涉及原文时注明出处（书名·篇名）。'
    },
    translate: {
      system: '你是古籍白话翻译助手。把用户给出的繁体/文言原文逐句翻译成现代白话，语言通顺自然，人名、地名、典故保留原名，必要时用括号补充说明，不做额外发挥。'
    },
    recommend: {
      system: '你是古籍书单推荐助手。根据用户的兴趣、水平、阅读目的，推荐合适的中国古典文献（经史子集、古典小说、诗文选本等），说明推荐理由与适合读者；如与本站在线书库相关可顺带提及书名。'
    }
  };

  // ---------- 上下文：章节阅读页自动携带 ----------
  function detectContext() {
    var ctx = { page: '本站页面', book: '', author: '', chapter: '' };
    var titleEl = document.querySelector('.reader-title');
    var bookEl = document.getElementById('header-book');
    if (titleEl) { ctx.chapter = (titleEl.textContent || '').trim(); ctx.page = '章节阅读页'; }
    if (bookEl) {
      var raw = (bookEl.textContent || '').replace(/[《》]/g, '').trim();
      if (raw) { ctx.book = raw; ctx.author = AUTHORS[raw] || ''; }
    }
    return ctx;
  }

  function contextPrompt(ctx) {
    if (!ctx || !ctx.book) return '';
    var parts = ['正在阅读《' + ctx.book + '》'];
    if (ctx.author) parts.push('作者：' + ctx.author);
    if (ctx.chapter) parts.push('当前章节：' + ctx.chapter);
    return parts.join('；') + '。用户在章节页向你提问时，请优先结合该章节内容回答。';
  }

  // ---------- DOM 注入 ----------
  var root = document.createElement('div');
  root.id = 'gai-root';
  root.innerHTML =
    '<button id="gai-fab" type="button" title="全局 AI 助手 · 通用问答/翻译/书籍推荐">🤖</button>' +
    '<div id="gai-panel" hidden>' +
      '<div class="gai-head">' +
        '<span class="gai-title">AI 助手 <span class="gai-model">DeepSeek</span></span>' +
        '<button type="button" class="gai-close" id="gai-close" title="收起">✕</button>' +
      '</div>' +
      '<div class="gai-ctx" id="gai-ctx" hidden></div>' +
      '<div class="gai-modes">' +
        '<button type="button" data-mode="chat" class="gai-mode active">💬 通用问答</button>' +
        '<button type="button" data-mode="translate" class="gai-mode">🈷 翻译</button>' +
        '<button type="button" data-mode="recommend" class="gai-mode">📚 书籍推荐</button>' +
      '</div>' +
      '<div class="gai-msgs" id="gai-msgs"></div>' +
      '<div class="gai-tip" id="gai-tip" hidden>' +
        '<span class="gai-tip-icon">💡</span>' +
        '<span class="gai-tip-text">您尚未设置 API key，请点击 <a href="/ai-guide.html">新手指南</a> 链接指导您申请</span>' +
      '</div>' +
      '<div class="gai-input">' +
        '<textarea id="gai-text" rows="2" placeholder="问点什么…（Enter 发送，Shift+Enter 换行）"></textarea>' +
        '<div class="gai-input-btns">' +
          '<button type="button" id="gai-note" title="📝 保存为笔记">📝</button>' +
          '<button type="button" id="gai-send">发送</button>' +
        '</div>' +
      '</div>' +
      '<div class="gai-note" id="gai-note-editor" hidden>' +
        '<div class="gai-note-head">📝 保存为笔记</div>' +
        '<div class="gai-note-label">原文</div>' +
        '<div class="gai-note-src" id="gai-note-src"></div>' +
        '<div class="gai-note-label">批注</div>' +
        '<textarea id="gai-note-cmt" rows="2" placeholder="写点批注……"></textarea>' +
        '<div class="gai-note-actions">' +
          '<button type="button" id="gai-note-save">保存</button>' +
          '<button type="button" id="gai-note-cancel">取消</button>' +
        '</div>' +
      '</div>' +
      '<div class="gai-foot">' +
        '<a href="/ai-settings.html">⚙ AI 设置</a>' +
        '<a href="/ai-guide.html">📖 AI 新手指南</a>' +
        '<button type="button" id="gai-clear">清空对话</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(root);

  var fab = document.getElementById('gai-fab');
  var panel = document.getElementById('gai-panel');
  var closeBtn = document.getElementById('gai-close');
  var ctxBar = document.getElementById('gai-ctx');
  var msgsEl = document.getElementById('gai-msgs');
  var textEl = document.getElementById('gai-text');
  var sendBtn = document.getElementById('gai-send');
  var clearBtn = document.getElementById('gai-clear');
  var tipEl = document.getElementById('gai-tip');
  var noteBtn = document.getElementById('gai-note');
  var noteEl = document.getElementById('gai-note-editor');
  var noteSrcEl = document.getElementById('gai-note-src');
  var noteCmtEl = document.getElementById('gai-note-cmt');
  var noteSaveBtn = document.getElementById('gai-note-save');
  var noteCancelBtn = document.getElementById('gai-note-cancel');

  // ---------- 主题：跟随阅读页自定义模板（gjs:reading 的 bg/fg），默认羊皮纸 ----------
  function hexToRgbArr(hex) {
    var m = String(hex).replace('#', '').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (!m) return [245, 234, 208];
    return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  }
  function rgbaStr(rgb, a) { return 'rgba(' + rgb.join(',') + ',' + a + ')'; }

  function applyTheme() {
    var bg = PAPER_BG, fg = PAPER_FG;
    try {
      var saved = JSON.parse(localStorage.getItem(READING_KEY) || '{}');
      if (saved && saved.bg && /^#[0-9a-fA-F]{6}$/.test(saved.bg)) bg = saved.bg;
      if (saved && saved.fg && /^#[0-9a-fA-F]{6}$/.test(saved.fg)) fg = saved.fg;
    } catch (e) { /* 解析失败则用默认羊皮纸 */ }
    var rgbBg = hexToRgbArr(bg);
    var lum = 0.299 * rgbBg[0] + 0.587 * rgbBg[1] + 0.114 * rgbBg[2];
    var dark = lum < 128;                 // 深色主题（墨夜/黑底）反色适配
    var paper = bg.toLowerCase() === PAPER_BG;
    root.style.setProperty('--gai-bg', bg);
    root.style.setProperty('--gai-fg', fg);
    root.style.setProperty('--gai-line', rgbaStr(hexToRgbArr(fg), 0.3));
    root.style.setProperty('--gai-bubble-bg', dark ? 'rgba(255,255,255,0.16)' : '#ffffff');
    root.style.setProperty('--gai-bubble-fg', fg);
    root.style.setProperty('--gai-input-bg', dark ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.85)');
    root.style.setProperty('--gai-msg-bg', dark ? 'rgba(0,0,0,0.18)' : 'rgba(255,255,255,0.45)');
    root.style.setProperty('--gai-ctx-bg', dark ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.35)');
    root.style.setProperty('--gai-ctx-fg', dark ? 'rgba(255,255,255,0.85)' : '#6d5320');
    root.classList.toggle('gai-dark', dark);
    root.classList.toggle('gai-paper', paper);  // 默认羊皮纸底色 → 叠加羊皮纸纹理
  }

  // 其他标签页修改阅读模板时实时同步（同页内由阅读页 applyReading 主动调用 GAI.theme）
  window.addEventListener('storage', function (e) {
    if (e.key === READING_KEY) applyTheme();
  });

  var mode = 'chat';
  var history = [];          // {role, content}
  var ctx = detectContext();
  var open = false;
  var selectedText = '';     // 选中文字暂存（选中时即时填入输入框；打开对话框时兜底再填一次）

  // ---------- 选中正文 → 即时填入 AI 输入框 ----------
  // 监听 selectionchange（mouseup / 键盘 Shift+方向键 均会触发），完全不依赖、不劫持 copy(Ctrl+C)。
  // 不 preventDefault、不写剪贴板 → 系统复制行为不受任何干扰。
  // 普通点击（含未来的「点击字词弹注释卡」）选区为空 → 直接跳过，二者互不冲突；
  // 注释卡等浮层如需显式豁免，给元素加 class .word-card / .ann-card 或 data-ai-no-fill 即可。
  var gaiFillTimer = null;
  function captureSelection() {
    if (open) return;                       // AI 面板展开期间不改写用户正在输入的内容
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;    // 纯点击 / 无选中 → 不处理
    var txt = sel.toString().trim();
    if (txt.length < 2) return;             // 长度不足 2 不记录
    var n = sel.anchorNode;
    var el = (n && n.nodeType === 1) ? n : (n && n.parentElement);
    if (!el) return;
    // 跳过：AI 面板/搜索框等表单控件内部、以及未来的注释卡浮层内的选中
    if (el.closest && el.closest('#gai-root, input, textarea, select, .word-card, .ann-card, [data-ai-no-fill]')) return;
    if (txt === selectedText && txt === textEl.value) return;  // 同一段文字已填入过 → 不重复提示
    selectedText = txt;
    textEl.value = txt;                     // ① 即时填入 AI 输入框
    gaiToast('已复制到 AI 助手…', 2000);     // ② 页面下方 Toast，约 2 秒自动消失
  }
  // 拖动/键盘逐字改变选区时会连续触发 selectionchange → 去抖到稳定后取值一次
  document.addEventListener('selectionchange', function () {
    if (gaiFillTimer) clearTimeout(gaiFillTimer);
    gaiFillTimer = setTimeout(captureSelection, 90);
  });
  // mouseup 兜底（个别浏览器在选区拖动刚结束时 selectionchange 滞后一拍）
  document.addEventListener('mouseup', captureSelection);

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function getKey() {
    try { return (localStorage.getItem(KEY_STORAGE) || '').trim(); } catch (e) { return ''; }
  }

  function ctxText() {
    if (!ctx || !ctx.book) return '';
    var s = '📖 ' + ctx.book;
    if (ctx.author) s += ' · ' + ctx.author;
    if (ctx.chapter) s += ' · ' + ctx.chapter;
    return s;
  }

  function addMsg(role, text) {
    var d = document.createElement('div');
    d.className = 'gai-msg ' + (role === 'user' ? 'gai-user' : 'gai-ai');
    d.innerHTML = (role === 'user' ? '' : '<span class="gai-ai-name">AI</span>') +
      '<div class="gai-bubble">' + esc(text).replace(/\n/g, '<br>') + '</div>';
    msgsEl.appendChild(d);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return d;
  }

  function setHint(html) {
    msgsEl.innerHTML = '<div class="gai-hint">' + html + '</div>';
  }

  function showCtx() {
    var t = ctxText();
    if (t) { ctxBar.textContent = t; ctxBar.hidden = false; }
    else ctxBar.hidden = true;
  }

  function refreshKeyState() {
    if (!open || msgsEl.children.length) return;
    if (getKey()) {
      setHint('你好！我是 AI 助手。可以问我古文翻译、古籍常识，也可以帮你推荐书目。<br>在章节阅读页打开时，我会自动带上当前章节与作者作为上下文。');
    } else {
      setHint('还没有配置 API Key。请先到 <a href="ai-settings.html"><b>⚙ AI 设置</b></a> 填入你的 DeepSeek Key（仅保存在本地），再回来提问。<br>获取 Key：<a href="https://platform.deepseek.com/" target="_blank" rel="noopener">platform.deepseek.com</a>');
    }
  }

  function openPanel() {
    applyTheme(); // 每次打开面板时同步阅读页自定义模板
    open = true;
    panel.hidden = false;
    // 章节页正文为异步渲染，打开面板时重新检测上下文
    ctx = detectContext();
    showCtx();
    refreshKeyState();
    // 打开面板兜底：选中文字已即时填入过输入框，这里再确认一次（未选中则保持空白，正常聊天）
    if (selectedText) {
      textEl.value = selectedText;
      selectedText = '';
    }
    textEl.focus();
  }

  function closePanel() {
    open = false;
    panel.hidden = true;
    hideKeyTip();
    if (noteEl) noteEl.hidden = true;   // 收起时同时收起笔记编辑区
  }

  // 未配置 Key 时：输入文字自动触发 💡 灯泡提示（自动消失，不阻断）
  var tipTimer = null, lastTipAt = 0;
  function hideKeyTip() {
    if (tipEl) { tipEl.hidden = true; clearTimeout(tipTimer); }
  }
  function showKeyTip() {
    if (!tipEl || getKey()) return;
    tipEl.hidden = false;
    clearTimeout(tipTimer);
    tipTimer = setTimeout(function () { tipEl.hidden = true; lastTipAt = Date.now(); }, 5000);
  }
  textEl.addEventListener('input', function () {
    if (getKey()) { hideKeyTip(); return; }
    if (tipEl && tipEl.hidden === false) return;         // 已在显示中
    if (Date.now() - lastTipAt < 10000) return;          // 冷却：避免每次按键都闪
    if (textEl.value.trim()) showKeyTip();
  });

  fab.addEventListener('click', function () { open ? closePanel() : openPanel(); });
  closeBtn.addEventListener('click', closePanel);

  document.querySelectorAll('.gai-mode').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.gai-mode').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      mode = btn.dataset.mode;
      textEl.focus();
    });
  });

  clearBtn.addEventListener('click', function () { history = []; refreshKeyState(); });

  // ---------- 📝 保存为笔记（纯前端，互不影响正常 AI 对话） ----------
  var noteSrcText = '';    // 打开笔记区时「原文」的定格快照（保存用同一份）

  function openNoteEditor() {
    noteSrcText = textEl.value.trim();               // 原文 = 当前输入框中的文字（即刚才选中的文字）
    noteSrcEl.textContent = noteSrcText || '暂无选中文字';
    noteCmtEl.value = '';
    noteEl.hidden = false;
    noteCmtEl.focus();
  }

  function closeNoteEditor() {
    noteEl.hidden = true;
    noteCmtEl.value = '';
  }

  function pad2(n) { return String(n).padStart(2, '0'); }

  function saveNote() {
    var cmt = noteCmtEl.value.trim();
    var body = '【原文】\n' + noteSrcText + '\n\n【批注】\n' + cmt + '\n\n——来自「一堆古书」\n';
    var d = new Date();
    var fileName = '笔记_' + d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      '_' + pad2(d.getHours()) + '-' + pad2(d.getMinutes()) + '-' + pad2(d.getSeconds()) + '.txt';
    var blob = new Blob([body], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    // 下载完成后关闭笔记区，并清空 AI 输入框
    closeNoteEditor();
    textEl.value = '';
  }

  noteBtn.addEventListener('click', openNoteEditor);
  noteSaveBtn.addEventListener('click', saveNote);
  noteCancelBtn.addEventListener('click', closeNoteEditor);   // 取消：不下载、不清除输入框

  function buildSystem() {
    var base = MODES[mode] ? MODES[mode].system : MODES.chat.system;
    var extra = contextPrompt(ctx);
    return extra ? base + '\n\n' + extra : base;
  }

  async function send() {
    var text = textEl.value.trim();
    if (!text) return;
    var key = getKey();
    if (!key) { hideKeyTip(); refreshKeyState(); textEl.value = ''; return; }
    addMsg('user', text);
    history.push({ role: 'user', content: text });
    textEl.value = '';
    var loading = addMsg('ai', '…');

    var messages = [{ role: 'system', content: buildSystem() }].concat(history);
    var body = JSON.stringify({ model: MODEL, temperature: 0.7, messages: messages });

    try {
      var resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key },
        body: body
      });
      var data = {};
      try { data = await resp.json(); } catch (e) { /* 非 JSON */ }
      if (!resp.ok) {
        var msg = (data.error && (data.error.message || data.error)) || ('AI 请求失败 HTTP ' + resp.status);
        throw new Error(msg);
      }
      var content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
      if (content == null) throw new Error('AI 返回异常，请重试。');
      loading.remove();
      addMsg('ai', content);
      history.push({ role: 'assistant', content: content });
    } catch (err) {
      loading.remove();
      addMsg('ai', '⚠ ' + err.message + '（可在 ⚙ AI 设置 中检查 Key，或查看 📖 AI 新手指南）');
    }
  }

  sendBtn.addEventListener('click', send);
  textEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  // 轻量 toast（预填确认提示）
  var gaiToastEl = null, gaiToastTimer = null;
  function gaiToast(msg, ms) {
    if (!gaiToastEl) {
      gaiToastEl = document.createElement('div');
      gaiToastEl.className = 'gai-toast';
      document.body.appendChild(gaiToastEl);
    }
    gaiToastEl.textContent = msg;
    gaiToastEl.classList.add('show');
    clearTimeout(gaiToastTimer);
    gaiToastTimer = setTimeout(function () { gaiToastEl.classList.remove('show'); }, ms || 1800);
  }

  // 公开 API
  window.GAI = {
    theme: applyTheme,
    openWithText: function (text) {
      selectedText = '';   // 显式指定文本时，不再带入此前全站选中的文字
      if (text) textEl.value = text;
      openPanel();
      try { textEl.setSelectionRange(textEl.value.length, textEl.value.length); } catch (e) { /* 忽略 */ }
      textEl.focus();
    },
    // 只预填输入框，不打开面板、不抢焦点（保留页面选中，右键菜单可正常复制）
    setDraft: function (text) {
      if (text) textEl.value = text;
    },
    toast: gaiToast
  };

  applyTheme();
  showCtx();
})();

