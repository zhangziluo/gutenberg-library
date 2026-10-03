/* ============================================================
   查词 API 客户端（DictApi）—— 回退链 / 缓存 / 超时 / 分类
   ------------------------------------------------------------
   铁律：**所有在线请求只打同域 /api/**（Pages Function 代理），前端绝不直连第三方。
   三个接口：
     /api/dict?source=…&lang=…&q=…   在线词典（moedict / wiktionary / freedict / unihan）
     /api/dict-links?lang=…&q=…     「更多词典」新窗口链接模板（只返回 URL，不抓页面）
     /api/translate?q=…&from=…&to=…  MyMemory 翻译
   回退顺序（按输入类型）：
     中文单字   离线(词表+康熙+说文) → 萌典 → 中文 Wiktionary → Unihan（本地分片）
     中文词语   离线(CC-CEDICT)      → 萌典 → 中文 Wiktionary
     英文单词   Free Dictionary      → en.wiktionary
     其他语种   {lang}.wiktionary    → Free Dictionary({lang}) →（可选）离线词库
     6+ 字符    不进释义链：自动切「翻译」Tab；释义 Tab 改为逐词切开并列查
   失败语义：全部失败返回 { ok:false }，由 UI 显示「未找到释义」，**绝不空白**。
   ============================================================ */
'use strict';

window.DictApi = (function () {
  var DICT = '/api/dict';
  var LINKS = '/api/dict-links';
  // 翻译走 /api/dict?source=translate（与 /api/translate 同一实现；线上实测只有该路由能稳定访问上游）
  var TRANSLATE = '/api/dict?source=translate';

  var TIMEOUT_MS = 3000;                        // 需求：在线请求 3 秒超时，超时立即降级
  var TRANSLATE_TIMEOUT_MS = 3500;              // 翻译稍慢，仍留余量
  var CACHE_PREFIX = 'gjs:dict:';
  var CACHE_TTL = 7 * 24 * 3600 * 1000;         // 7 天
  var MAX_SPLIT = 8;                            // 长文本逐词查最多切几段

  var INVISIBLE = /[\u200b-\u200d\u2060\ufeff]/g;
  var HAN_SEQ = /^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+$/;
  var LATIN_WORD = /^[A-Za-z][A-Za-z'\u2019-]*$/;
  var ANY_WORD = /^\p{L}[\p{L}'\u2019-]*$/u;

  /** 可注入钩子：offline(离线查词，由阅读页提供) / segmenter(分词，长文本用) */
  var hooks = { offline: null, segmenter: null };
  function configure(h) {
    if (h) {
      if ('offline' in h) hooks.offline = h.offline;
      if ('segmenter' in h) hooks.segmenter = h.segmenter;
    }
    return hooks;
  }

  /* ---------------- 小工具 ---------------- */
  function clean(s) {
    return String(s == null ? '' : s).replace(INVISIBLE, '').replace(/\s+/g, ' ').trim();
  }
  function cps(s) { return Array.from(s); }
  function len(s) { return cps(s).length; }

  /** 繁 → 简（萌典/viktionary 返回繁体；页面若加载了 opencc-js 就转，没加载就用原文） */
  var t2s = null;
  function simplify(text) {
    var s = String(text == null ? '' : text);
    if (!s) return s;
    try {
      if (t2s === null) {
        t2s = (window.OpenCC && typeof window.OpenCC.Converter === 'function')
          ? new window.OpenCC.Converter({ from: 'tw', to: 'cn' })   // 与 reader.js 的简繁转换同款
          : false;
      }
      if (t2s) return t2s(s);
    } catch (e) { t2s = false; }
    return s;
  }

  function hostOf(url) {
    try { return new URL(url).host.toLowerCase(); } catch (e) { return ''; }
  }

  /** 该主机当前是否被白名单判为 hidden（被墙/被拦 → 不查、不预取） */
  function hostHidden(host) {
    var DL = window.DictLinks;
    if (!host || !DL) return false;
    if (typeof DL.hostHidden === 'function') return DL.hostHidden(host);
    if (typeof DL.hiddenHosts === 'function') return DL.hiddenHosts().indexOf(host) >= 0;
    return false;
  }

  /* ---------------- 输入分类 ---------------- */
  /**
   * @returns {{kind, text, lang, raw}}
   *   zh-char  1 个汉字
   *   zh-word  2–5 个汉字
   *   en-word  英文单词（含连字符复合词，**不限长度**）
   *   x-word   其他语种单词（按书籍 lang；西里尔/带变音符等）
   *   long     6+ 汉字的整句 / 含空格标点的多词文本 → 翻译 Tab + 逐词查
   */
  function classify(text, bookLang) {
    var t = clean(text);
    var n = len(t);
    var lang = String(bookLang || '').toLowerCase();
    var out = { kind: 'long', text: t, lang: lang === 'zh' ? 'zh' : (lang || 'zh'),
                raw: String(text == null ? '' : text) };
    if (!t) return out;

    // ① 汉字串：1 字 / 2–5 字 / 6+ 字
    if (HAN_SEQ.test(t)) {
      out.lang = 'zh';
      out.kind = (n === 1) ? 'zh-char' : (n <= 5 ? 'zh-word' : 'long');
      return out;
    }
    // ② 单个拉丁词：书籍语言不是中文时按该语种查（英文书 → en）
    if (LATIN_WORD.test(t)) {
      var bl = (lang && lang !== 'zh') ? lang : 'en';
      out.lang = bl;
      out.kind = (bl === 'en') ? 'en-word' : 'x-word';
      return out;
    }
    // ③ 其他文种单词（西里尔、希腊、带变音符…）
    if (ANY_WORD.test(t)) {
      out.lang = (lang && lang !== 'zh') ? lang : 'en';
      out.kind = 'x-word';
      return out;
    }
    // ④ 其余（含空格 / 标点 / 多词）→ 整句
    return out;
  }

  /* ---------------- 回退链定义 ---------------- */
  /**
   * @returns {Array<{source, lang?, label, host?}>}
   *   source: offline ｜ moedict ｜ wiktionary ｜ freedict ｜ unihan
   *   host 非空 → 先过白名单闸门（被墙/被拦的源直接跳过，不查也不预取）
   */
  function chainOf(kind, lang) {
    var zhWiki = { source: 'wiktionary', lang: 'zh', label: '中文 Wiktionary',
                   host: 'zh.wiktionary.org' };
    if (kind === 'zh-char') {
      return [
        { source: 'offline', label: '离线词典（本站词表 · 康熙 · 说文）' },
        { source: 'moedict', lang: 'zh', label: '萌典' },
        zhWiki,
        { source: 'unihan', lang: 'zh', label: 'Unihan（拼音 · 部首 · 笔画）' }
      ];
    }
    if (kind === 'zh-word') {
      return [
        { source: 'offline', label: '离线词典（CC-CEDICT）' },
        { source: 'moedict', lang: 'zh', label: '萌典' },
        zhWiki
      ];
    }
    if (kind === 'en-word') {
      return [
        { source: 'freedict', lang: 'en', label: 'Free Dictionary' },
        { source: 'wiktionary', lang: 'en', label: 'en.wiktionary', host: 'en.wiktionary.org' }
      ];
    }
    if (kind === 'x-word') {
      var l = lang || 'en';
      return [
        { source: 'wiktionary', lang: l, label: l + '.wiktionary', host: l + '.wiktionary.org' },
        { source: 'freedict', lang: l, label: 'Free Dictionary（' + l + '）' },
        { source: 'offline', label: '离线词典（如有该语种词库）' }
      ];
    }
    return [];                                                // long：释义 Tab 逐词查
  }

  /* ---------------- 缓存（localStorage，TTL 7 天） ---------------- */
  function cacheKey(source, lang, q) { return CACHE_PREFIX + source + ':' + lang + ':' + q; }

  function readCache(key) {
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return null;
      var rec = JSON.parse(raw);
      if (!rec || !rec.t || (Date.now() - rec.t) > CACHE_TTL) {
        localStorage.removeItem(key);
        return null;
      }
      return rec.v;
    } catch (e) { return null; }
  }

  function writeCache(key, value) {
    try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), v: value })); } catch (e) {}
  }

  function cacheClear() {
    try {
      var keys = [];
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf(CACHE_PREFIX) === 0) keys.push(k);
      }
      keys.forEach(function (k) { localStorage.removeItem(k); });
      return keys.length;
    } catch (e) { return 0; }
  }

  /* ---------------- 同域请求（带超时；失败一律转成结构化结果） ---------------- */
  function fetchTimeout(url, ms) {
    var ctl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, ms);
    return fetch(url, ctl ? { signal: ctl.signal } : {})
      .then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (d) { clearTimeout(timer); return d; },
            function (e) { clearTimeout(timer); throw e; });
  }

  /** 带缓存的同域 GET；返回值：{ok, value, error, ms, cached} */
  function cachedGet(path, key, ms) {
    var hit = readCache(key);
    if (hit !== null) return Promise.resolve({ ok: true, value: hit, cached: true, ms: 0 });
    var t0 = Date.now();
    return fetchTimeout(path, ms || TIMEOUT_MS).then(function (d) {
      var dt = Date.now() - t0;
      if (d && !d.error && (d.result !== undefined || d.translatedText !== undefined ||
                            Array.isArray(d.links))) {
        writeCache(key, d);
        return { ok: true, value: d, ms: dt };
      }
      return { ok: false, error: (d && d.error) || 'bad json', ms: dt };
    }).catch(function (e) {
      return { ok: false,
               error: (e && e.name === 'AbortError') ? 'timeout' : String((e && e.message) || e),
               ms: Date.now() - t0 };
    });
  }

  /* ---------------- 结果归一（把各源差异抹平成同一套字段） ---------------- */
  /** → {word, phonetic, pinyin, senses:[{pos, defs:[]}], extra, text} */
  function normalize(source, lang, d) {
    var r = (d && d.result) || {};
    var q = (d && d.query) || '';
    if (source === 'moedict') {
      var hs = r.heteronyms || [];
      var h0 = hs[0] || {};
      var extraBits = [];
      if (hs.length > 1) extraBits.push('共 ' + hs.length + ' 个读音');
      if (r.en) extraBits.push('英：' + r.en);
      return {
        word: simplify(r.word || q),
        phonetic: h0.bopomofo || '',
        pinyin: h0.pinyin || '',
        senses: hs.slice(0, 2).map(function (h) {
          return { pos: h.pinyin || '',
                   defs: (h.meanings || []).map(function (m) {
                     return simplify((m && m.def) ? m.def : m);      // 兼容「对象/字符串」两种形态
                   }) };
        }),
        extra: extraBits.join(' · '),
        text: '',
      };
    }
    if (source === 'freedict') {
      return {
        word: r.word || q,
        phonetic: (r.phonetics || [])[0] || '',
        pinyin: '',
        senses: (r.meanings || []).map(function (m) {
          return { pos: m.partOfSpeech || '', defs: (m.definitions || []).map(simplify) };
        }),
        extra: '',
        text: '',
      };
    }
    if (source === 'unihan') {
      return {
        word: r.char || q,
        phonetic: r.pinyin || '',
        pinyin: r.pinyin || '',
        senses: [],
        extra: [r.radical ? '部首 ' + r.radical : '',
                (r.strokes != null && r.strokes !== '') ? r.strokes + ' 画' : ''].filter(Boolean).join(' · '),
        text: '',
      };
    }
    if (source === 'wiktionary') {                            // wiki 源：摘要文本
      return {
        word: simplify(d.title || q), phonetic: '', pinyin: '',
        senses: [], extra: '',
        text: simplify(String(r.extract || '').trim()),
      };
    }
    return { word: (r && r.word) || q, phonetic: '', pinyin: '',
             senses: (r && r.senses) || [], extra: (r && r.extra) || '',
             text: (r && r.text) || '' };
  }

  /* ---------------- 主查词：按回退链逐源尝试，绝不抛错 ---------------- */
  /**
   * @param {string} text 选中的字/词/句
   * @param {{lang?:string}} [opts] 书籍语言（lang 字段）
   * @returns {Promise<{ok, kind, text, lang, source, label, value, tried:[…], chain}>}
   */
  function lookup(text, opts) {
    opts = opts || {};
    var c = classify(text, opts.lang);
    var chain = chainOf(c.kind, c.lang);
    var tried = [];
    var out = { ok: false, kind: c.kind, text: c.text, lang: c.lang, raw: c.raw,
                source: null, label: '', value: null, tried: tried, chain: chain };

    function stepAt(i) {
      if (i >= chain.length) return Promise.resolve(out);
      var st = chain[i];

      // 白名单闸门：被墙/被拦的源 —— 不查、不预取，只记一笔「跳过」
      if (st.host && hostHidden(st.host)) {
        tried.push({ source: st.source, label: st.label, ok: false, skipped: true,
                     error: '被墙/被拦源（可在设置里开启「容错外链」）', ms: 0 });
        return stepAt(i + 1);
      }

      // ① 离线（由阅读页注入的 hooks.offline 提供）
      if (st.source === 'offline') {
        if (opts.skipOffline) {          // 面板把离线单独渲染成一区 → 这里只跑在线链
          tried.push({ source: 'offline', label: st.label, ok: false, skipped: true,
                       error: '离线区单独展示', ms: 0 });
          return stepAt(i + 1);
        }
        if (typeof hooks.offline !== 'function') {
          tried.push({ source: 'offline', label: st.label, ok: false, skipped: true,
                       error: '无离线词典', ms: 0 });
          return stepAt(i + 1);
        }
        var t0 = Date.now();
        return Promise.resolve()
          .then(function () { return hooks.offline(c.kind, c.text); })
          .then(function (v) {
            var dt = Date.now() - t0;
            var hasText = !!(v && (v.text || (v.senses && v.senses.length)));
            if (hasText) {
              tried.push({ source: 'offline', label: st.label, ok: true, ms: dt });
              out.ok = true; out.source = 'offline'; out.label = st.label;
              out.value = { source: 'offline', label: st.label, word: c.text,
                            phonetic: (v && v.pinyin) || '', pinyin: (v && v.pinyin) || '',
                            senses: (v && v.senses) || [], extra: (v && v.extra) || '',
                            text: (v && v.text) || '' };
              return out;
            }
            tried.push({ source: 'offline', label: st.label, ok: false, error: '未收录', ms: dt });
            return stepAt(i + 1);
          })
          .catch(function (e) {
            tried.push({ source: 'offline', label: st.label, ok: false,
                         error: String((e && e.message) || e), ms: Date.now() - t0 });
            return stepAt(i + 1);
          });
      }

      // ② 在线：一律走同域代理 /api/dict（绝不直连第三方）
      var sl = st.lang || c.lang;
      var url = DICT + '?source=' + encodeURIComponent(st.source) +
                '&lang=' + encodeURIComponent(sl) + '&q=' + encodeURIComponent(c.text);
      return cachedGet(url, cacheKey(st.source, sl, c.text)).then(function (r) {
        tried.push({ source: st.source, label: st.label, ok: r.ok,
                     error: r.error || '', ms: r.ms, cached: !!r.cached });
        if (r.ok) {
          out.ok = true; out.source = st.source; out.label = st.label;
          out.value = Object.assign({ source: st.source, label: st.label },
                                    normalize(st.source, sl, r.value));
          return out;
        }
        return stepAt(i + 1);
      });
    }

    return stepAt(0);
  }

  /* ---------------- 翻译（MyMemory，走同域 /api/translate） ---------------- */
  /**
   * @param {string} text 6+ 字符 / 整句
   * @param {{from?:string, to?:string}} [opts]
   * @returns {Promise<{ok, text?, match?, error?, detail?, ms?}>}
   */
  function translate(text, opts) {
    opts = opts || {};
    var q = clean(text);
    if (!q) return Promise.resolve({ ok: false, error: 'empty' });
    var from = opts.from || 'zh-Hant';
    var to = opts.to || 'en';
    var url = TRANSLATE + (TRANSLATE.indexOf('?') >= 0 ? '&' : '?') +
              'q=' + encodeURIComponent(q.slice(0, 500)) +
              '&langpair=' + encodeURIComponent(from + '|' + to) +
              '&from=' + encodeURIComponent(from) + '&to=' + encodeURIComponent(to);
    return cachedGet(url, CACHE_PREFIX + 'translate:' + from + ':' + to + ':' + q,
                     TRANSLATE_TIMEOUT_MS)
      .then(function (r) {
        var v = (r.value && (r.value.result || r.value)) || {};
        if (r.ok && v.translatedText) {
          return { ok: true, text: String(v.translatedText), match: v.match || 0,
                   provider: v.provider || '', from: v.source || from, to: v.target || to,
                   url: v.url || '', cached: !!r.cached, ms: r.ms };
        }
        return { ok: false, error: (v && v.error) || r.error || 'fail',
                 detail: (v && v.detail) || '', ms: r.ms };
      });
  }

  /* ---------------- 「更多词典」外链（Worker 模板 + 白名单过滤） ---------------- */
  /** @returns {Promise<{ok, links, fromApi, error?}>} 只返回 URL，不抓第三方页面 */
  function links(lang, q) {
    var l = lang || 'zh';
    var query = clean(q);
    var url = LINKS + '?lang=' + encodeURIComponent(l) + '&q=' + encodeURIComponent(query);
    return cachedGet(url, CACHE_PREFIX + 'links:' + l + ':' + query).then(function (r) {
      var raw = (r.ok && r.value && Array.isArray(r.value.links)) ? r.value.links : [];
      var list = filterLinks(raw);
      if (!list.length) return { ok: false, links: fallbackLinks(query), fromApi: false,
                                 error: r.error || 'empty' };
      return { ok: true, links: list, fromApi: true };
    });
  }

  /** 白名单闸门：被墙/被拦的主机一律剔除（绝不渲染、绝不预取） */
  function filterLinks(list) {
    return (list || []).filter(function (it) {
      if (!it || !it.url) return false;
      return !hostHidden(it.host || hostOf(it.url));
    }).map(function (it) {
      return { name: it.name || hostOf(it.url), url: it.url,
               note: it.note || '', host: it.host || hostOf(it.url) };
    });
  }

  /** Worker 不可用时的本地兜底：用白名单模块自己的表（同样只有 enabled 的源） */
  function fallbackLinks(q) {
    var DL = window.DictLinks;
    if (!DL || typeof DL.visible !== 'function') return [];
    return DL.visible('zh').map(function (v) {
      var u = v.url(q || '');
      return { name: v.label, url: u, note: v.hint || '', host: hostOf(u) };
    });
  }

  /* ---------------- 长文本逐词切分（6+ 字符时用） ---------------- */
  /**
   * 优先用注入的分词器（词表最长匹配），否则：汉字按 2 字滑窗、西文按词切。
   * 最多切 MAX_SPLIT 段，避免请求风暴。
   */
  function splitWords(text, lang) {
    var t = clean(text);
    if (!t) return [];
    if (typeof hooks.segmenter === 'function') {
      try {
        var got = hooks.segmenter(t, { lang: lang });
        if (got && got.length) return got.slice(0, MAX_SPLIT);
      } catch (e) { /* 分词器出错 → 朴素切分 */ }
    }
    var out = [];
    var re = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+|[A-Za-z][A-Za-z'\u2019-]*|\p{L}[\p{L}'\u2019-]*/gu;
    var m;
    while ((m = re.exec(t)) !== null && out.length < MAX_SPLIT) {
      var seg = m[0];
      if (HAN_SEQ.test(seg)) {
        if (len(seg) <= 2) { out.push(seg); continue; }
        for (var i = 0; i < seg.length && out.length < MAX_SPLIT; i += 2) {
          out.push(seg.slice(i, i + 2));
        }
      } else {
        out.push(seg);
      }
    }
    return out;
  }

  return {
    DICT: DICT, LINKS: LINKS, TRANSLATE: TRANSLATE,
    TIMEOUT_MS: TIMEOUT_MS, TRANSLATE_TIMEOUT_MS: TRANSLATE_TIMEOUT_MS,
    CACHE_TTL: CACHE_TTL, CACHE_PREFIX: CACHE_PREFIX, MAX_SPLIT: MAX_SPLIT,
    classify: classify, chainOf: chainOf, lookup: lookup, normalize: normalize,
    translate: translate, links: links, filterLinks: filterLinks,
    splitWords: splitWords, simplify: simplify, hostHidden: hostHidden,
    configure: configure, cacheKey: cacheKey,
    readCache: readCache, writeCache: writeCache, cacheClear: cacheClear,
  };
})();
