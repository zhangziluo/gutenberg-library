/* ============================================================
   站外词典白名单（DictLinks）—— 检索页 / 阅读页 / 设置页共用
   ------------------------------------------------------------
   为什么要有这一层：不是所有外链词典在境内都能用 ——
     · 國學大師（guoxuedashi）    ：未备案，被阿里云拦截 → 默认 hidden
     · 中華典藏（zhonghuadiancang）：域名失效 / 服务器宕机 → 默认 hidden
     · 中文維基詞典（zh.wiktionary.org）：境内直连被阻断（白屏）→ 默认 hidden
   状态分两层：
     ① **默认状态**写在下面 SOURCES（改这里＝改基线）
     ② **探活结论**写在 _site_data/dict/dict_links.json（由 deploy/dict_links_probe.js
        每周探活一次：连续 2 次成功才 enabled / 连续 2 次失败回到 hidden）
   三条硬规则：
     1) hidden 的源**不渲染按钮、不构建 URL、不预取（prefetch）、不请求**
     2) 只有 enabled（或用户手动开了「容错外链」的 fallback 源）才进「更多词典」面板
     3) 所有外链一律新窗口打开：target="_blank" rel="noopener"（页面无 preconnect/dns-prefetch）
   ============================================================ */
'use strict';

window.DictLinks = (function () {
  var STATUS_URL = '_site_data/dict/dict_links.json';
  var FALLBACK_KEY = 'guoxue_dict_fallback_links';   // 「容错外链」开关（仅本机浏览器）
  var SETTINGS_HREF = 'ai-settings.html#dict-links';

  /** 站外词典白名单（zh）。hidden=true → 基线不展示，等探活结论 / 用户开关 */
  var SOURCES = [
    {
      id: 'zdic', label: '漢典', hint: '字 · 词', lang: 'zh', priority: 1,
      hidden: false, note: '首选：速度最快、字词资料全',
      url: function (q) { return 'https://www.zdic.net/hans/' + encodeURIComponent(q); }
    },
    {
      id: 'ctext', label: '中國哲學書電子化計劃', hint: '古籍全文出处检索', lang: 'zh', priority: 2,
      hidden: false, note: '首选：支持古籍全文出处检索',
      url: function (q) { return 'https://ctext.org/search.pl?if=gb&searchu=' + encodeURIComponent(q); }
    },
    {
      id: 'wiktionary-zh', label: '維基詞典（中文）', hint: '容错外链 · 新窗口打开', lang: 'zh', priority: 3,
      hidden: true, needsFallback: true,
      note: '境内直连被阻断（白屏）；仅当在设置里开启「容错外链」才显示，且永不参与自动摘要请求',
      url: function (q) { return 'https://zh.wiktionary.org/wiki/' + encodeURIComponent(q); }
    },
    {
      id: 'guoxuedashi', label: '國學大師', hint: '站内搜索', lang: 'zh', priority: 4,
      hidden: true, probe: true,
      note: '未备案被阿里云拦截；探活连续 2 次成功才自动展示',
      url: function (q) { return 'https://www.guoxuedashi.net/so.php?q=' + encodeURIComponent(q); }
    },
    {
      id: 'zhonghuadiancang', label: '中華典藏', hint: '站内搜索', lang: 'zh', priority: 5,
      hidden: true, probe: true,
      note: '域名失效 / 服务器宕机；探活连续 2 次成功才自动展示',
      url: function () { return 'https://www.zhonghuadiancang.com/'; }
    }
  ];

  var byId = {};
  SOURCES.forEach(function (s) { byId[s.id] = s; });

  var statusPromise = null;      // 探活状态（只拉一次；失败＝空 → 用基线）
  var statusMap = {};

  function loadStatus() {
    if (!statusPromise) {
      var p = (typeof window.loadJSON === 'function')
        ? window.loadJSON(STATUS_URL)
        : fetch(STATUS_URL).then(function (r) { return r.json(); });
      statusPromise = Promise.resolve(p).then(function (d) {
        statusMap = (d && d.sources) || {};
        return statusMap;
      }).catch(function () {
        statusMap = {};                 // 文件缺失/损坏 → 用基线，绝不报错
        return statusMap;
      });
    }
    return statusPromise;
  }

  /* ---------- 「容错外链」开关（设置页与本模块共用同一个 key） ---------- */
  function fallbackEnabled() {
    try { return localStorage.getItem(FALLBACK_KEY) === '1'; } catch (e) { return false; }
  }
  function setFallback(on) {
    try { localStorage.setItem(FALLBACK_KEY, on ? '1' : '0'); } catch (e) { /* 隐私模式忽略 */ }
  }

  /* ---------- 状态判定 ---------- */
  /** 'enabled' 展示 ｜ 'fallback' 仅在开了容错外链时展示 ｜ 'hidden' 不展示且绝不请求 */
  function stateOf(id) {
    var s = byId[id];
    if (!s) return 'hidden';
    var st = statusMap[id] || {};
    var on = (st.state === 'enabled') ? true : (st.state === 'hidden') ? false : !s.hidden;
    if (s.needsFallback) {
      // 「被墙源」不但要看探活，还要用户手动点头：
      //   · 探活明确说 hidden（或还没有结论）→ 一律不给（连容错开关也不放）
      //   · 探活没判死 → 由「容错外链」开关决定
      if (st.state === 'hidden') return 'hidden';
      return fallbackEnabled() ? 'fallback' : 'hidden';
    }
    return on ? 'enabled' : 'hidden';
  }

  /** 可展示的源（按 priority 排好） */
  function visible(lang) {
    return SOURCES.filter(function (s) { return !lang || s.lang === lang; })
      .map(function (s) { return { src: s, state: stateOf(s.id) }; })
      .filter(function (x) { return x.state !== 'hidden'; })
      .sort(function (a, b) { return a.src.priority - b.src.priority; })
      .map(function (x) {
        return { id: x.src.id, label: x.src.label, hint: x.src.hint, note: x.src.note,
                 state: x.state, url: x.src.url };
      });
  }

  /** 单个源的链接；**hidden 一律返回 null**（调用方据此绝不建链、绝不请求） */
  function urlOf(id, q) {
    var s = byId[id];
    if (!s || stateOf(id) === 'hidden') return null;
    return s.url(q == null ? '' : String(q));
  }

  /** 全部外链主机（探活 / 审计用） */
  function hosts() {
    return ['www.zdic.net', 'ctext.org', 'zh.wiktionary.org',
            'www.guoxuedashi.net', 'www.zhonghuadiancang.com'];
  }

  /** 默认隐藏、**绝不允许预取 / 预连接**的主机 */
  function hiddenHosts() {
    return SOURCES.filter(function (s) { return s.hidden; }).map(function (s) {
      return s.url('x').replace(/^https?:\/\//, '').split('/')[0];
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /**
   * 渲染「更多词典」面板：只渲染 enabled / fallback；hidden 连元素都不生成。
   * @param {HTMLElement} el  容器
   * @param {string} q        查询词
   * @param {Object} [opts]   { itemClass:'dl-item', emptyText:'…' }
   * @returns {number} 渲染出的链接数
   */
  function render(el, q, opts) {
    if (!el) return 0;
    opts = opts || {};
    var itemClass = opts.itemClass || 'dl-item';
    var list = visible('zh');
    if (!list.length) {
      el.innerHTML = '<p class="dl-empty">' +
        esc(opts.emptyText || '暂无可用的站外词典（都在探活观察中）') + '</p>';
      return 0;
    }
    el.innerHTML = list.map(function (it) {
      var tag = it.state === 'fallback' ? '<i class="dl-tag">容错</i>' : '';
      var title = it.note || ('在新窗口打开：' + it.label);
      return '<a class="' + esc(itemClass) + '" href="' + esc(it.url(q)) + '"' +
        ' target="_blank" rel="noopener" title="' + esc(title) + '"' +
        ' data-dict-link="' + esc(it.id) + '"><b>' + esc(it.label) + tag + '</b>' +
        '<span>' + esc(it.hint) + '</span></a>';
    }).join('');
    return list.length;
  }

  return {
    SOURCES: SOURCES, FALLBACK_KEY: FALLBACK_KEY, SETTINGS_HREF: SETTINGS_HREF,
    ready: loadStatus, stateOf: stateOf, visible: visible, urlOf: urlOf,
    hosts: hosts, hiddenHosts: hiddenHosts,
    fallbackEnabled: fallbackEnabled, setFallback: setFallback,
    render: render, esc: esc
  };
})();
