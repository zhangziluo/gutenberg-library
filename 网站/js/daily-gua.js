/* ============================================================
   ☯ 今日一卦（首页右下角胶囊按钮）
   - 数据：assets/data/daily.json（gua 64 卦 + astro 天文记录 11 条 + yao 六爻映射表）
   - 混合池 = [...gua, ...astro]（共 75 条）
   - 每日稳定：用本地日期 YYYY-MM-DD 做 djb2 种子从混合池取一条，同一天不变
   - 手动「换一个」：Math.random 从混合池随机取，可连续点击（仅本次会话）
   - 浮层按类型动态渲染：
       gua   → ☯ 第N卦 卦名 卦符 + 卦辞 + ——《易经》
       astro → ✨ 天文书 + 原文 + ——出处
   - 点击「关闭」或浮层外部区域关闭；浮层出现时 200ms 淡入
   - 🪙 摇一卦：全屏遮罩 + 铜钱 3D 翻飞 6 次（每次 rotateY 300ms + 停顿 200ms），
     六爻自下而上组成卦象，按 6 位二进制（阳=1 阴=0，自下而上读）查 yao 映射表；
     每次落地由 Math.random() < 0.5 决定阳/阴；可「再看一次」或点遮罩随时关闭
   ============================================================ */
'use strict';

(function () {
  var DATA_URL = 'assets/data/daily.json';
  var CACHE_PREFIX = 'daily_gua_';

  var pool = [];        // 混合池
  var current = null;   // 当前展示条目
  var yaoMap = {};      // 六爻映射表：6位二进制串（自下而上）→ {unicode, name, fullName, tuan}

  // 本地日期 YYYY-MM-DD（每日一签以本地天为准）
  var d = new Date();
  var dateStr = d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');

  function $(id) { return document.getElementById(id); }

  function djb2(str) {
    var h = 5381;
    for (var i = 0; i < str.length; i++) {
      h = ((h << 5) + h) + str.charCodeAt(i);
      h = h | 0;
    }
    return h >>> 0;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function isGua(rec) { return !!(rec && rec.id != null && rec.unicode); }

  // 根据条目类型动态渲染浮层内容
  function render(rec) {
    var pop = $('gua-pop');
    if (!pop) return;
    if (!rec) {
      pop.innerHTML = '<div class="gua-body">今日无签，明日再试。</div>';
      return;
    }
    var title, body, src;
    if (isGua(rec)) {
      title = '☯ 第' + rec.id + '卦 ' + esc(rec.fullName) +
        ' <span class="gua-glyph">' + esc(rec.unicode) + '</span>';
      body = rec.tuan;
      src = '——《易经》';
    } else {
      title = '✨ 天文书';
      body = rec.text;
      src = '——' + rec.source;
    }
    pop.innerHTML =
      '<div class="gua-type">' + title + '</div>' +
      '<div class="gua-body">' + esc(body) + '</div>' +
      '<div class="gua-src">' + esc(src) + '</div>' +
      '<div class="gua-actions">' +
        '<button type="button" id="gua-shake">🪙 摇一卦</button>' +
        '<button type="button" id="gua-again">换一个</button>' +
        '<button type="button" id="gua-close">关闭</button>' +
      '</div>';
    $('gua-shake').addEventListener('click', startShake);
    $('gua-again').addEventListener('click', function () { pickRandom(); });
    $('gua-close').addEventListener('click', hide);
  }

  function show() { var pop = $('gua-pop'); if (pop) pop.hidden = false; }
  function hide() { var pop = $('gua-pop'); if (pop) pop.hidden = true; }

  function toggle() {
    var pop = $('gua-pop');
    if (!pop) return;
    if (pop.hidden) {
      if (!current) {
        ensureData().then(function () { pickDaily(); show(); }).catch(showFail);
      } else {
        show();
      }
    } else {
      hide();
    }
  }

  function ensureData() {
    if (pool.length) return Promise.resolve(pool);
    return fetch(DATA_URL)
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (data) {
        var gua = Array.isArray(data.gua) ? data.gua : [];
        var astro = Array.isArray(data.astro) ? data.astro : [];
        pool = gua.concat(astro).filter(function (x) { return x; });
        yaoMap = (data && data.yao && typeof data.yao === 'object') ? data.yao : {};
        if (!pool.length) throw new Error('empty');
        return pool;
      });
  }

  // 每日稳定：djb2(YYYY-MM-DD) 取一条，并缓存到当天，同一天不变
  function pickDaily() {
    var rec = null;
    try { rec = JSON.parse(localStorage.getItem(CACHE_PREFIX + dateStr)); } catch (e) { /* 忽略 */ }
    if (!(rec && (isGua(rec) || rec.text))) {
      rec = pool[djb2(dateStr) % pool.length];
      try { localStorage.setItem(CACHE_PREFIX + dateStr, JSON.stringify(rec)); } catch (e) { /* 忽略 */ }
    }
    current = rec;
    render(current);
  }

  // 手动切换：Math.random 随机取一条，可连续点击
  function pickRandom() {
    if (!pool.length) return;
    current = pool[Math.floor(Math.random() * pool.length)];
    render(current);
  }

  function showFail() {
    var pop = $('gua-pop');
    if (pop) pop.innerHTML = '<div class="gua-body">今日一卦加载失败，请稍后再试。</div>';
  }

  // ================= 🪙 摇一卦 =================
  var shakeTimer = null;   // 摇卦定时器（关闭遮罩时清理）
  var shakeDeg = 0;        // 铜钱累计旋转角度
  var SHAKE_FLIP_MS = 300; // 每次 3D 翻转时长
  var SHAKE_PAUSE_MS = 200;// 落地后停顿

  function shakeReset() {
    if (shakeTimer) { clearTimeout(shakeTimer); shakeTimer = null; }
    shakeDeg = 0;
    var lines = $('shake-lines'), result = $('shake-result'),
        actions = $('shake-actions'), coin = $('shake-coin');
    if (lines) lines.innerHTML = '';
    if (result) result.hidden = true;
    if (actions) actions.hidden = true;
    if (coin) {
      coin.style.transition = 'none';
      coin.style.transform = 'rotateY(0deg)';
    }
  }

  // 第 turn 次摇卦（0 起）：阳=1 阴=0，lines 依次记录（第1次=初爻，自下而上）
  function shakeThrow(turn, lines) {
    var isYang = Math.random() < 0.5;
    lines.push(isYang ? '1' : '0');
    var coin = $('shake-coin');
    if (coin) {
      // 阳 → 文面朝上（整转 360°），阴 → 素面朝上（整转 540°）
      shakeDeg += isYang ? 360 : 540;
      coin.style.transition = 'transform ' + SHAKE_FLIP_MS + 'ms cubic-bezier(.45,.05,.55,.95)';
      coin.style.transform = 'rotateY(' + shakeDeg + 'deg)';
    }
    shakeTimer = setTimeout(function () {
      // 落地：在下方显示本次结果（新爻插入最前 → 六爻自下而上排列）
      var linesEl = $('shake-lines');
      if (linesEl) {
        var div = document.createElement('div');
        div.className = 'yao-line ' + (isYang ? 'yang' : 'yin');
        div.innerHTML = isYang ? '<span></span>' : '<span></span><span></span>';
        linesEl.insertBefore(div, linesEl.firstChild);
      }
      shakeTimer = setTimeout(function () {
        if (turn < 5) {
          shakeThrow(turn + 1, lines);
        } else {
          shakeFinish(lines);
        }
      }, SHAKE_PAUSE_MS);
    }, SHAKE_FLIP_MS);
  }

  // 六次完成：按 6 位二进制（自下而上）查 64 卦映射表并展示结果
  function shakeFinish(lines) {
    var key = lines.join('');
    var gua = yaoMap[key] || null;
    var u = $('shake-unicode'), n = $('shake-name'), t = $('shake-tuan');
    if (gua) {
      if (u) u.textContent = gua.unicode;
      if (n) n.textContent = gua.fullName;
      if (t) t.textContent = gua.tuan;
    } else {
      if (u) u.textContent = '';
      if (n) n.textContent = '';
      if (t) t.textContent = '未找到对应卦象（' + key + '）';
    }
    var result = $('shake-result');
    if (result) result.hidden = false;
    var actions = $('shake-actions');
    if (actions) actions.hidden = false;
  }

  function closeShake() {
    if (shakeTimer) { clearTimeout(shakeTimer); shakeTimer = null; }
    var overlay = $('shake-overlay');
    if (overlay) overlay.hidden = true;
  }

  function startShake() {
    var overlay = $('shake-overlay');
    if (!overlay) return;
    hide(); // 先关闭今日一卦浮层
    ensureData().then(function () {
      overlay.hidden = false;
      shakeReset();
      // 先让复位状态绘制完成，再开始翻飞
      shakeTimer = setTimeout(function () { shakeThrow(0, []); }, 40);
    }).catch(function () {
      overlay.hidden = false;
      var t = $('shake-tuan');
      if (t) t.textContent = '摇卦数据加载失败，请稍后再试。';
      var result = $('shake-result');
      if (result) result.hidden = false;
      var actions = $('shake-actions');
      if (actions) actions.hidden = false;
    });
  }

  function init() {
    var btn = $('gua-btn');
    var pop = $('gua-pop');
    if (!btn || !pop) return;

    btn.addEventListener('click', function (e) { e.stopPropagation(); toggle(); });

    // 点击浮层外部区域关闭
    document.addEventListener('click', function (e) {
      var root = $('gua-root');
      if (!root || root.contains(e.target)) return;
      hide();
    });

    // 🪙 摇一卦遮罩：点击遮罩（非内容区）随时关闭；「再看一次」重播；「关闭」退出
    var overlay = $('shake-overlay');
    if (overlay) {
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeShake();
      });
      var againBtn = $('shake-again');
      if (againBtn) againBtn.addEventListener('click', function () {
        shakeReset();
        shakeTimer = setTimeout(function () { shakeThrow(0, []); }, 40);
      });
      var closeBtn = $('shake-close');
      if (closeBtn) closeBtn.addEventListener('click', closeShake);
    }

    // 提前加载数据并预渲染（不影响页面其他内容）；加载失败等用户点击时再提示
    ensureData().then(function () {
      if (!current) pickDaily();
    }).catch(function () { /* 忽略，点击时再提示 */ });
  }

  init();
})();
