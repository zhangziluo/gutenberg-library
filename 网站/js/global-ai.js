/* ============================================================
   古籍文库 · 全局 AI 助手（全站浮动）
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

  // 书名 → 作者（与 catalog.json 保持一致；用于章节页上下文）
  var AUTHORS = {
    '史記': '司馬遷', '漢書': '班固', '三國志': '陳壽',
    '三國演義': '羅貫中', '水滸傳': '施耐庵', '西遊記': '吳承恩',
    '紅樓夢': '曹雪芹', '古文觀止': '吳楚材、吳調侯'
  };

  var MODES = {
    chat: {
      system: '你是「古籍文库」（古登堡繁体古籍在线阅读站）的 AI 助手，精通中国古典文献：经史子集、二十四史、四大名著、古文選本。请用简体中文、简洁准确地回答；涉及原文时注明出处（书名·篇名）。'
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
        '<button type="button" id="gai-send">发送</button>' +
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

  var mode = 'chat';
  var history = [];          // {role, content}
  var ctx = detectContext();
  var open = false;

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
    open = true;
    panel.hidden = false;
    // 章节页正文为异步渲染，打开面板时重新检测上下文
    ctx = detectContext();
    showCtx();
    refreshKeyState();
    textEl.focus();
  }

  function closePanel() { open = false; panel.hidden = true; hideKeyTip(); }

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

  // 公开 API：阅读页选中文字时直接打开面板并预填输入框（可继续编辑或直接发送）
  window.GAI = {
    openWithText: function (text) {
      if (text) textEl.value = text;
      openPanel();
      try { textEl.setSelectionRange(textEl.value.length, textEl.value.length); } catch (e) { /* 忽略 */ }
      textEl.focus();
    }
  };

  showCtx();
})();

