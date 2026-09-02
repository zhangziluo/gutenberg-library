/* ============================================================
   一堆古书 · 注释语言切换（简中 zh_cn / 繁中 zh_tw / English en）
   - 键：localStorage['annotation_lang']，默认 zh_tw（繁中注释，与繁体原文风格统一）
   - 用法：任意带注释的阅读页放置
       <span data-ann-lang-host></span>
     并引入本脚本；切换即保存 + 派发 'annlangchange' 事件（不刷新页面）。
   - 取文案：AnnLang.text(annotationEntry) → 按当前语言返回 entry[zh_cn/zh_tw/en]，
     缺失时返回 ''，由调用方回退为「拼音 + 待补」。
   - 样式：统一使用页面无衬线 UI 字体；激活态朱砂红 #9E2B25。
   - 兼容：与「选中文字入 AI 输入框(global-ai)」「点击字词弹注释卡」互不冲突：
     本模块只读 localStorage 与派发事件，不监听 copy/selection/click。
   ============================================================ */
(function () {
  'use strict';

  var KEY = 'annotation_lang';
  var DEFAULT_LANG = 'zh_tw';
  var LANGS = [
    { id: 'zh_cn', label: '简中', full: '简体中文注释' },
    { id: 'zh_tw', label: '繁中', full: '繁體中文注釋' },
    { id: 'en', label: 'English', full: 'English annotations' }
  ];

  function valid(l) {
    for (var i = 0; i < LANGS.length; i++) if (LANGS[i].id === l) return l;
    return null;
  }
  function get() {
    var v;
    try { v = localStorage.getItem(KEY); } catch (e) { v = null; }
    return valid(v) || DEFAULT_LANG;
  }
  function set(lang) {
    var l = valid(lang) || DEFAULT_LANG;
    try { localStorage.setItem(KEY, l); } catch (e) { /* 隐私模式忽略 */ }
    document.documentElement.setAttribute('data-ann-lang', l);
    document.dispatchEvent(new CustomEvent('annlangchange', { detail: { lang: l } }));
    return l;
  }
  function label(lang) {
    for (var i = 0; i < LANGS.length; i++) if (LANGS[i].id === lang) return LANGS[i].label;
    return lang;
  }
  /** 当前语言下该注释词条的释义文案；无则返回 ''（调用方显示 拼音+待补） */
  function text(entry) {
    if (!entry) return '';
    var l = get();
    var v = entry[l];
    return (typeof v === 'string' && v.trim()) ? v : '';
  }
  /** 缺失时回退展示：有释义用释义，否则 拼音 + 待补（按语言给不同占位文案） */
  function display(entry, fallbackPinyin) {
    var gloss = text(entry);
    if (gloss) return gloss;
    var py = (entry && entry.pinyin) ? entry.pinyin : '';
    var placeholder = get() === 'en' ? 'TBD' : get() === 'zh_cn' ? '待补' : '待補';
    return (py ? py + ' · ' : '') + placeholder;
  }

  // ---- 统一样式（注入一次） ----
  function ensureStyle() {
    if (document.getElementById('ann-lang-style')) return;
    var css = '' +
      '.reader-lang-wrap{display:inline-flex;align-items:center;margin:0 2px;}' +
      '.ann-lang{display:inline-flex;align-items:center;gap:2px;padding:2px;' +
      '  background:rgba(255,255,255,.55);border:1px solid var(--line,#d8cfba);border-radius:999px;' +
      '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;' +
      '  font-size:12px;line-height:1;vertical-align:middle;' +
      '  box-shadow:0 1px 3px rgba(0,0,0,.06);}' +
      '.ann-lang .ann-lang-cap{font-size:11px;color:#6b6152;padding:0 4px 0 2px;letter-spacing:.5px;}' +
      '.ann-lang button{border:1px solid transparent;background:transparent;color:#3a3226;' +
      '  padding:4px 8px;border-radius:999px;cursor:pointer;font:inherit;transition:background .18s,color .18s;}' +
      '.ann-lang button:hover{background:rgba(158,43,37,.08);}' +
      '.ann-lang button.active{background:#9E2B25;color:#fff;}' +
      'html[data-ann-lang] .ann-lang button.active{background:#9E2B25;color:#fff;}' +
      '';
    var st = document.createElement('style');
    st.id = 'ann-lang-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function mount(host) {
    if (!host || host.getAttribute('data-ann-mounted')) return;
    host.setAttribute('data-ann-mounted', '1');
    var cap = host.getAttribute('data-ann-label');
    var html = '<span class="ann-lang">';
    if (cap !== null) html += '<span class="ann-lang-cap">' + cap + '</span>';
    for (var i = 0; i < LANGS.length; i++) {
      html += '<button type="button" data-ann-lang="' + LANGS[i].id + '"' +
        ' title="' + LANGS[i].full + '">' + LANGS[i].label + '</button>';
    }
    html += '</span>';
    host.innerHTML = html;
    var cur = get();
    host.querySelectorAll('button').forEach(function (b) {
      var l = b.getAttribute('data-ann-lang');
      b.classList.toggle('active', l === cur);
      b.addEventListener('click', function () {
        cur = set(l);
        host.querySelectorAll('button').forEach(function (x) {
          x.classList.toggle('active', x.getAttribute('data-ann-lang') === cur);
        });
      });
    });
  }

  function mountAll() {
    ensureStyle();
    document.documentElement.setAttribute('data-ann-lang', get());
    var hosts = document.querySelectorAll('[data-ann-lang-host]');
    for (var i = 0; i < hosts.length; i++) mount(hosts[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountAll);
  } else {
    mountAll();
  }

  window.AnnLang = {
    KEY: KEY, DEFAULT_LANG: DEFAULT_LANG, LANGS: LANGS,
    get: get, set: set, label: label, text: text, display: display, mountAll: mountAll
  };
})();
