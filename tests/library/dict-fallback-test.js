/* ============================================================
   多源回退 + 翻译 · 单元测试（纯 Node，无外网）
   ------------------------------------------------------------
   跑法：node tests/library/dict-fallback-test.js
   覆盖：
     A. 输入分类 classify（中文单字 / 中文词语 / 英文单词 / 多语种 / 6+ 长文本）
     B. 回退链 chainOf（顺序 + 白名单门禁）
     C. DictApi.lookup：逐级回退、门禁跳过、超时降级、全部失败、缓存（TTL 7 天）
     D. 英文 / 多语种链
     E. splitWords（长文本逐词切分）
     F. links：Worker 模板 + 白名单过滤 + 本地兜底
     G. translate：成功 / 配额用尽 / 缓存
     H. 三个 Pages Function：/api/dict（moedict·freedict·unihan）· /api/dict-links · /api/translate
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { pathToFileURL } = require('url');

const ROOT = path.resolve(__dirname, '../../网站');
const FALLBACK_KEY = 'guoxue_dict_fallback_links';

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}

/** 造一个 localStorage 替身（够 DictApi 用） */
function makeStore(pre) {
  const store = Object.assign({}, pre || {});
  const ls = {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
    key: i => Object.keys(store)[i],
    get length() { return Object.keys(store).length; },
  };
  return { store, ls };
}

/** 在 VM 里加载 js/dict-api.js（浏览器全局 + 假 fetch） */
function loadApi(opts) {
  opts = opts || {};
  const { store, ls } = makeStore(opts.fallback ? { [FALLBACK_KEY]: '1' } : {});
  const calls = [];
  const win = {
    localStorage: ls,
    DictLinks: opts.dictLinks || {
      hiddenHosts: function () {
        return opts.gateOpen ? [] : ['zh.wiktionary.org', 'www.guoxuedashi.net', 'www.zhonghuadiancang.com'];
      },
      hostHidden: function (h) { return this.hiddenHosts().indexOf(h) >= 0; },
      visible: function () { return opts.fallback ? [] : []; },
    },
  };
  const ctx = {
    window: win,
    localStorage: ls,
    console: console,
    AbortController: AbortController,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: function (url, o) {
      const u = String(url);
      calls.push(u);
      if (!opts.fetch) return Promise.reject(new Error('no fetch in test'));
      return opts.fetch(u, o);
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'js', 'dict-api.js'), 'utf8'), ctx);
  return { api: win.DictApi, store: store, calls: calls };
}

function jsonRes(obj, status) {
  return Promise.resolve({
    ok: (status || 200) < 400,
    status: status || 200,
    json: async () => obj,
  });
}

/* ---------------- A. 分类 ---------------- */
function testClassify() {
  console.log('\nA. 输入分类 classify');
  const { api } = loadApi();
  const c = (t, lang) => api.classify(t, lang);

  ok(c('仁').kind === 'zh-char', '单字「仁」→ zh-char');
  ok(c('之').kind === 'zh-char' && c('之').lang === 'zh', '单字语言定为 zh');
  ok(c('論語').kind === 'zh-word', '两字「論語」→ zh-word');
  ok(c('論語述而').kind === 'zh-word', '四字「論語述而」→ zh-word');
  ok(c('論語述而篇第一').kind === 'long', '6 字 → long');
  ok(c('hello').kind === 'en-word' && c('hello').lang === 'en', '英文单词 → en-word');
  ok(c("don't").kind === 'en-word', '带撇号 → en-word');
  ok(c('well-known').kind === 'en-word', '连字符复合词 → en-word');
  ok(c('bonjour', 'fr').kind === 'x-word' && c('bonjour', 'fr').lang === 'fr', '法语词 → x-word(fr)');
  ok(c('König', 'de').kind === 'x-word' && c('König', 'de').lang === 'de', '德语带变音符 → x-word(de)');
  ok(c('привет', 'ru').kind === 'x-word' && c('привет', 'ru').lang === 'ru', '西里尔字母 → x-word(ru)');
  ok(c('子曰學而時習之').kind === 'long', '整句 → long');
  ok(c('  ').kind === 'long' && c('  ').text === '', '空白 → long 且 text 为空');
  ok(c('\u200b仁\u200b').kind === 'zh-char', '零宽字符被清掉后仍是单字');
}

/* ---------------- B. 回退链 ---------------- */
function testChain() {
  console.log('\nB. 回退链 chainOf（顺序 + 门禁）');
  const { api } = loadApi();
  const ids = list => list.map(s => s.source + (s.lang ? ':' + s.lang : '')).join(' → ');

  ok(ids(api.chainOf('zh-char', 'zh')) === 'offline → moedict:zh → wiktionary:zh → unihan:zh',
     '中文单字：离线 → 萌典 → 中文 Wiktionary → Unihan', ids(api.chainOf('zh-char', 'zh')));
  ok(ids(api.chainOf('zh-word', 'zh')) === 'offline → moedict:zh → wiktionary:zh',
     '中文词语：离线 → 萌典 → 中文 Wiktionary');
  ok(ids(api.chainOf('en-word', 'en')) === 'freedict:en → wiktionary:en',
     '英文单词：Free Dictionary → en.wiktionary');
  ok(ids(api.chainOf('x-word', 'fr')) === 'wiktionary:fr → freedict:fr → offline',
     '多语种：{lang}.wiktionary → Free Dictionary({lang}) → 离线兜底');
  ok(api.chainOf('long', 'zh').length === 0, '6+ 长文本不进释义回退链');
  const zhChain = api.chainOf('zh-char', 'zh');
  ok(zhChain[2].host === 'zh.wiktionary.org', '中文 Wiktionary 带 host 供门禁判断');
  ok(!zhChain[1].host && !zhChain[3].host, '萌典 / Unihan 不受门禁限制');
}


/* ---------------- C. lookup：逐级回退 / 门禁 / 超时 / 缓存 ---------------- */
async function testLookup() {
  console.log('\nC. DictApi.lookup（回退与缓存）');

  // C1 离线命中即停（默认链）
  {
    const { api, calls } = loadApi();
    api.configure({ offline: function () { return { pinyin: 'rén', text: '【康熙】仁，親也。' }; } });
    const r = await api.lookup('仁', { lang: 'zh' });
    ok(r.ok && r.source === 'offline', '离线命中即停（来源 offline）');
    ok(r.value.pinyin === 'rén' && /康熙/.test(r.value.text), '离线拼音与释义带出');
    ok(calls.length === 0, '离线命中时**不发任何在线请求**');
  }

  // C2 skipOffline：走在线链，萌典命中
  {
    const { api, calls } = loadApi({
      fetch: function (u) {
        if (u.indexOf('source=moedict') >= 0) {
          return jsonRes({ source: 'moedict', query: '之',
                           result: { word: '之', heteronyms: [{ bopomofo: 'ㄓ', pinyin: 'zhī',
                                     meanings: [{ def: '往、到' }] }] } });
        }
        return jsonRes({ error: 'not found' });
      },
    });
    const r = await api.lookup('之', { lang: 'zh', skipOffline: true });
    ok(r.ok && r.source === 'moedict', 'skipOffline 时走在线链并命中萌典');
    ok(r.value.phonetic === 'ㄓ' && r.value.pinyin === 'zhī', '萌典注音 / 拼音归一正确');
    ok(r.value.senses.length === 1 && r.value.senses[0].defs[0] === '往、到', '萌典释义列表归一正确');
    ok(r.label === '萌典', '带可显示的来源标注（萌典）');
    ok(calls[0].indexOf('/api/dict?source=moedict') === 0, '首个在线请求就是萌典（同域代理）');
    ok(calls.every(u => u.indexOf('http') !== 0), '全程只打同域相对路径');
  }

  // C3 门禁：中文 Wiktionary 默认跳过且不发请求
  {
    const { api, calls } = loadApi({
      gateOpen: false,
      fetch: function () { return jsonRes({ error: 'not found' }); },
    });
    const r = await api.lookup('之', { lang: 'zh', skipOffline: true });
    ok(!r.ok, '全部失败 → ok:false（UI 显示未找到释义）');
    const w = r.tried.filter(t => t.source === 'wiktionary')[0];
    ok(w && w.skipped === true, '中文 Wiktionary 被标记 skipped');
    ok(calls.every(u => u.indexOf('source=wiktionary') < 0),
       '被墙源**一次请求都没发**（共 ' + calls.length + ' 次）');
    ok(r.tried.some(t => t.source === 'moedict' && t.ok === false), '萌典失败被记录');
    ok(r.tried.some(t => t.source === 'unihan'), 'Unihan 作为最后一级被尝试');
  }

  // C4 门禁开启（容错外链）→ 会请求 wiktionary
  {
    const { api, calls } = loadApi({
      gateOpen: true, fallback: true,
      fetch: function (u) {
        if (u.indexOf('source=wiktionary') >= 0) {
          return jsonRes({ source: 'wiktionary', title: '之', extract: '往也。',
                           result: { extract: '往也。' } });
        }
        return jsonRes({ error: 'not found' });
      },
    });
    const r = await api.lookup('之', { lang: 'zh', skipOffline: true });
    ok(calls.some(u => u.indexOf('source=wiktionary') >= 0), '开「容错外链」后才会请求 wiktionary');
    ok(r.ok && r.source === 'wiktionary', '命中中文 Wiktionary');
    ok(/往也/.test(r.value.text), 'wiki 摘要进了 text 字段');
  }

  // C5 超时 → 立即降级
  {
    const { api } = loadApi({
      fetch: function (u) {
        if (u.indexOf('source=moedict') >= 0) {
          const e = new Error('aborted');
          e.name = 'AbortError';
          return Promise.reject(e);
        }
        return jsonRes({ source: 'unihan', query: '之',
                         result: { char: '之', pinyin: 'zhī', radical: '丿', strokes: 4 } });
      },
    });
    const r = await api.lookup('之', { lang: 'zh', skipOffline: true });
    const m = r.tried.filter(t => t.source === 'moedict')[0];
    ok(m && m.error === 'timeout', '超时记为 timeout 并降级到下一源');
    ok(r.ok && r.source === 'unihan', '降级后 Unihan 接住');
    ok(r.value.extra === '部首 丿 · 4 画', 'Unihan 归一为「部首 · 笔画」');
    ok(api.TIMEOUT_MS === 3000, '在线超时常量 = 3 秒（需求）');
  }

  // C6 缓存：第二次不再请求；TTL 过期后重新请求
  {
    let n = 0;
    const { api, store } = loadApi({
      fetch: function () {
        n++;
        return jsonRes({ source: 'moedict', query: '之',
                         result: { word: '之',
                                   heteronyms: [{ pinyin: 'zhī', meanings: [{ def: '往、到' }] }] } });
      },
    });
    await api.lookup('之', { lang: 'zh', skipOffline: true });
    await api.lookup('之', { lang: 'zh', skipOffline: true });
    ok(n === 1, '同一查询第二次命中 localStorage 缓存（请求数 ' + n + '）');
    const key = 'gjs:dict:moedict:zh:之';
    ok(!!store[key], '缓存键为 `${source}:${lang}:${query}`（' + key + '）');
    const rec = JSON.parse(store[key]);
    rec.t = Date.now() - 8 * 24 * 3600 * 1000;
    store[key] = JSON.stringify(rec);
    await api.lookup('之', { lang: 'zh', skipOffline: true });
    ok(n === 2, '缓存过期（TTL 7 天）后重新请求');
    ok(api.CACHE_TTL === 7 * 24 * 3600 * 1000, '缓存 TTL = 7 天');
  }
}

/* ---------------- D. 英文 / 多语种链 ---------------- */
async function testEnX() {
  console.log('\nD. 英文 / 多语种回退');
  {
    const { api, calls } = loadApi({
      fetch: function (u) {
        if (u.indexOf('source=freedict&lang=en') >= 0) {
          return jsonRes({ source: 'freedict', query: 'hello',
                           result: { word: 'hello', phonetics: ['/həˈləʊ/'],
                                     meanings: [{ partOfSpeech: 'noun', definitions: ['a greeting'] }] } });
        }
        return jsonRes({ error: 'not found' });
      },
    });
    const r = await api.lookup('hello', { lang: 'en' });
    ok(r.ok && r.source === 'freedict', '英文单词命中 Free Dictionary');
    ok(r.value.phonetic === '/həˈləʊ/' && r.value.senses[0].pos === 'noun', '英释义结构归一（音标 + 词性）');
    ok(calls[0].indexOf('source=freedict&lang=en') > 0, '英文链先打 freedict');
    ok(calls.every(u => u.indexOf('lang=en') > 0), '英文链只带 lang=en');
  }
  {
    const { api, calls } = loadApi({
      fetch: function (u) {
        if (u.indexOf('source=wiktionary&lang=fr') >= 0) return jsonRes({ error: 'not found' });
        if (u.indexOf('source=freedict&lang=fr') >= 0) {
          return jsonRes({ source: 'freedict', query: 'bonjour',
                           result: { word: 'bonjour', phonetics: [],
                                     meanings: [{ partOfSpeech: '', definitions: ['hello'] }] } });
        }
        return jsonRes({ error: 'nope' });
      },
    });
    const r = await api.lookup('bonjour', { lang: 'fr' });
    ok(calls[0].indexOf('source=wiktionary&lang=fr') > 0, '法语链先打 fr.wiktionary');
    ok(r.ok && r.source === 'freedict', 'fr.wiktionary 失败后降级到 Free Dictionary(fr)');
  }
}

/* ---------------- E. 长文本逐词切分 ---------------- */
function testSplit() {
  console.log('\nE. splitWords（6+ 字符逐词查）');
  const { api } = loadApi();
  ok(api.splitWords('子曰學而時習之').join(',') === '子曰,學而,時習,之',
     '纯中文按 2 字滑窗：' + api.splitWords('子曰學而時習之').join(','));
  ok(api.splitWords('hello world').join(',') === 'hello,world', '英文按词切');
  ok(api.splitWords('子曰 hello 學而').join(',') === '子曰,hello,學而', '中英混排各自成段');
  ok(api.splitWords('子曰學而時習之不亦說乎有朋自遠方來').length === 8, '最多切 8 段（防请求风暴）');
  const { api: api2 } = loadApi();
  api2.configure({ segmenter: function () { return ['子曰', '學而時習之']; } });
  ok(api2.splitWords('子曰學而時習之').join(',') === '子曰,學而時習之', '注入的分词器优先（词表最长匹配）');
  const { api: api3 } = loadApi();
  api3.configure({ segmenter: function () { throw new Error('boom'); } });
  ok(api3.splitWords('子曰學而').join(',') === '子曰,學而', '分词器抛错时回退朴素切分');
}

/* ---------------- F. 更多词典外链（模板 + 白名单过滤） ---------------- */
async function testLinks() {
  console.log('\nF. DictApi.links（外链过滤）');
  {
    const { api } = loadApi({
      gateOpen: false,
      fetch: function () {
        return jsonRes({ lang: 'zh', query: '之', links: [
          { name: '漢典', host: 'www.zdic.net', url: 'https://www.zdic.net/hans/%E4%B9%8B', note: '' },
          { name: '中文 Wiktionary', host: 'zh.wiktionary.org',
            url: 'https://zh.wiktionary.org/wiki/%E4%B9%8B', note: '' },
        ] });
      },
    });
    const r = await api.links('zh', '之');
    ok(r.ok && r.links.length === 1, '被墙源被过滤掉，只剩 1 条（' + r.links.length + '）');
    ok(r.links[0].name === '漢典', '保留的是漢典');
  }
  {
    const { api } = loadApi({ gateOpen: true, fallback: true, fetch: function () { return jsonRes({ error: 'x' }); } });
    const r = await api.links('zh', '之');
    ok(!r.ok && !r.fromApi, '接口不可用时标记 fromApi=false');
    ok(Array.isArray(r.links), '仍返回数组（绝不 undefined，UI 不会崩）');
  }
}

/* ---------------- G. 翻译 ---------------- */
async function testTranslate() {
  console.log('\nG. DictApi.translate（MyMemory 同域代理）');
  {
    let n = 0;
    const { api } = loadApi({
      fetch: function () {
        n++;
        return jsonRes({ query: '子曰', source: 'zh-TW', target: 'en',
                         translatedText: 'The Master said', match: 0.9 });
      },
    });
    const r = await api.translate('子曰', { from: 'zh-Hant', to: 'en' });
    ok(r.ok && r.text === 'The Master said', '翻译成功返回文本');
    ok(r.match === 0.9, '带匹配度');
    await api.translate('子曰', { from: 'zh-Hant', to: 'en' });
    ok(n === 1, '翻译结果同样进缓存（请求数 ' + n + '）');
  }
  {
    const { api } = loadApi({
      fetch: function () { return jsonRes({ error: 'no translation', detail: 'quota' }, 502); },
    });
    const r = await api.translate('子曰', {});
    ok(!r.ok && r.error === 'no translation', '配额用尽 → 结构化错误（UI 显示翻译暂不可用）');
    ok((await api.translate('', {})).ok === false, '空文本直接返回失败，不发请求');
  }
}

/* ---------------- H. Pages Function 三接口 ---------------- */
async function testFunctions() {
  console.log('\nH. Worker 接口（/api/dict · /api/dict-links · /api/translate）');
  const dict = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict.js')).href);
  const linksFn = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict-links.js')).href);
  const trFn = await import(pathToFileURL(path.join(ROOT, 'functions/api/translate.js')).href);
  const origFetch = globalThis.fetch;
  const urls = [];
  const call = (fn, qs, env) =>
    fn.onRequest({ request: new Request('https://myfami.cn/api/x?' + qs), env: env });
  const assetsEnv = {
    ASSETS: {
      fetch: async (req) => {
        const rel = decodeURIComponent(new URL(req.url).pathname).replace(/^\//, '');
        try {
          return new Response(fs.readFileSync(path.join(ROOT, rel), 'utf8'), { status: 200 });
        } catch (e) { return new Response('{}', { status: 404 }); }
      },
    },
  };

  // H1 萌典
  globalThis.fetch = async (u) => {
    urls.push(String(u));
    return new Response(JSON.stringify({
      title: '之', heteronyms: [{ bopomofo: 'ㄓ', pinyin: 'zhī', meanings: [{ def: '往、到' }] }],
    }), { status: 200 });
  };
  let r = await call(dict, 'source=moedict&q=' + encodeURIComponent('之'));
  let d = await r.json();
  ok(r.status === 200 && d.source === 'moedict' && d.query === '之', 'moedict：返回 {source, query, result}');
  ok(d.result.heteronyms[0].pinyin === 'zhī', 'moedict：heteronyms 解析正确');
  ok(urls[urls.length - 1].indexOf('moedict.tw/a/') !== -1, 'moedict：转发到 www.moedict.tw/a/{q}.json');
  ok(r.headers.get('cache-control') === 'public, max-age=86400', 'moedict：带 1 天缓存头');
  ok(r.headers.get('Access-Control-Allow-Origin') === '*', 'moedict：带 CORS 头');

  // H1b 萌典**真实**结构（紧凑键 t/h/b/p/d[].f + translation.English）也要认得
  globalThis.fetch = async () => new Response(JSON.stringify({
    t: '之',
    h: [{ '=': '4215', b: 'ㄓ', p: 'zhī',
          d: [{ f: '`的~、`底~。', q: ['《論語》'] }, { f: '`於~。' }] }],
    translation: { English: '(possessive particle, literary equivalent of 的)' },
  }), { status: 200 });
  r = await call(dict, 'source=moedict&q=' + encodeURIComponent('之'));
  d = await r.json();
  ok(d.title === '之' && d.result.word === '之', 'moedict：真实结构的 t=标题 能读到');
  ok(d.result.heteronyms[0].bopomofo === 'ㄓ' && d.result.heteronyms[0].pinyin === 'zhī',
     'moedict：真实结构 b/p → 注音/拼音');
  ok(d.result.heteronyms[0].meanings[0] === '的、底。',
     'moedict：真实结构 d[].f → 释义，且去掉 ` ~ 行内标记',
     d.result.heteronyms[0].meanings[0]);
  ok(/possessive particle/.test(d.result.en), 'moedict：translation.English → en 字段');

  // H2 Free Dictionary：未命中是 404 JSON（不是空数组）
  globalThis.fetch = async () => new Response('{"title":"No Definitions Found"}', { status: 404 });
  r = await call(dict, 'source=freedict&lang=en&q=zzzz');
  d = await r.json();
  ok(r.status === 200 && d.error === 'not found', 'freedict：404 归一成 not found（前端可继续降级）');

  // H3 Free Dictionary：正常
  globalThis.fetch = async () => new Response(JSON.stringify([{
    word: 'hello', phonetics: [{ text: '/həˈləʊ/' }],
    meanings: [{ partOfSpeech: 'noun', definitions: [{ definition: 'a greeting' }] }],
  }]), { status: 200 });
  r = await call(dict, 'source=freedict&lang=en&q=hello');
  d = await r.json();
  ok(d.result.word === 'hello' && d.result.phonetics[0] === '/həˈləʊ/', 'freedict：音标解析正确');
  ok(d.result.meanings[0].partOfSpeech === 'noun' && d.result.meanings[0].definitions[0] === 'a greeting',
     'freedict：词性 + 释义解析正确');

  // H4 Unihan：走本站静态分片（env.ASSETS，零网络）
  r = await call(dict, 'source=unihan&q=' + encodeURIComponent('之'), assetsEnv);
  d = await r.json();
  ok(r.status === 200 && d.result && d.result.pinyin === 'zhī', 'unihan：读到拼音（本地分片）');
  ok(d.result.radical === '丿' && d.result.strokes === 4, 'unihan：读到部首 + 笔画');
  r = await call(dict, 'source=unihan&q=' + encodeURIComponent('🀄'), assetsEnv);
  d = await r.json();
  ok(d.error === 'not found', 'unihan：库里没有的字 → not found（前端继续降级）');

  // H5 上游异常 / 超时
  globalThis.fetch = async () => { throw new Error('boom'); };
  r = await call(dict, 'source=moedict&q=x');
  d = await r.json();
  ok(r.status === 502 && d.error === 'fetch failed', '上游异常 → 502 fetch failed（不抛给前端）');
  globalThis.fetch = async (u, o) => new Promise((_, rej) => {
    o.signal.addEventListener('abort', () => {
      const e = new Error('aborted');
      e.name = 'AbortError';
      rej(e);
    });
  });
  r = await call(dict, 'source=moedict&q=x');
  d = await r.json();
  ok(r.status === 502 && d.detail === 'timeout', '上游超时 → 502 detail=timeout（前端 3s 内可降级）');

  // H6 参数校验
  ok((await call(dict, 'source=moedict')).status === 400, '缺 q → 400');
  ok((await call(dict, 'source=nope&q=x')).status === 400, '非法 source → 400');
  ok((await call(dict, 'source=moedict&lang=zh;drop&q=x')).status === 400, '非法 lang → 400');

  // H7 dict-links：各语言表 + URL 编码
  const lr = await linksFn.onRequest({
    request: new Request('https://myfami.cn/api/dict-links?lang=zh&q=' + encodeURIComponent('之')),
  });
  const ld = await lr.json();
  ok(ld.links.length === 4, 'dict-links：zh 返回 4 条（漢典 / 萌典 / 教育部 / Wiktionary）');
  ok(ld.links.every(x => /^https:\/\//.test(x.url) && !!x.host), 'dict-links：每条都带 url 与 host');
  ok(ld.links.some(x => x.url.indexOf(encodeURIComponent('之')) > 0), 'dict-links：q 已编码进 URL');
  ok(/zdic\.net/.test(ld.links[0].url), 'dict-links：zh 首选漢典');
  const ed = await (await linksFn.onRequest({
    request: new Request('https://myfami.cn/api/dict-links?lang=en&q=hello'),
  })).json();
  ok(ed.links.length === 4 && /merriam-webster/.test(ed.links[0].url), 'dict-links：en 首选 Merriam-Webster');
  const rd = await (await linksFn.onRequest({
    request: new Request('https://myfami.cn/api/dict-links?lang=sv&q=' + encodeURIComponent('hus')),
  })).json();
  ok(rd.links.some(x => x.host === 'sv.wiktionary.org'), 'dict-links：未知语种先给该语言 Wiktionary');
  ok(rd.links.some(x => x.group === 'en'), 'dict-links：未知语种再挂英文兜底');
  const ru = await (await linksFn.onRequest({
    request: new Request('https://myfami.cn/api/dict-links?lang=ru&q=' + encodeURIComponent('дом')),
  })).json();
  ok(ru.links[0].host === 'ru.wiktionary.org', 'dict-links：已知语种（ru）走自己的表');
  ok(linksFn.buildDictLinks('zh', '之').length === 4, 'buildDictLinks() 可独立调用');

  // H8 translate：语言码归一 + 解析 + 配额
  ok(trFn.mmLang('zh-Hant') === 'zh-TW' && trFn.mmLang('zh-Hans') === 'zh-CN' && trFn.mmLang('EN') === 'en',
     'translate：语言码归一（繁中→zh-TW / 简中→zh-CN）');
  globalThis.fetch = async (u) => {
    urls.push(String(u));
    return new Response(JSON.stringify({
      responseStatus: 200, responseData: { translatedText: 'hello there', match: 0.5 },
    }), { status: 200 });
  };
  r = await call(trFn, 'q=' + encodeURIComponent('你好') + '&from=zh-Hant&to=en');
  d = await r.json();
  ok(d.translatedText === 'hello there' && d.source === 'zh-TW' && d.target === 'en',
     'translate：返回译文 + 归一后的语言码');
  ok(urls[urls.length - 1].indexOf('api.mymemory.translated.net') !== -1, 'translate：走 MyMemory 上游');
  ok(urls[urls.length - 1].indexOf('langpair=zh-TW%7Cen') !== -1, 'translate：langpair 拼接正确');
  globalThis.fetch = async () => new Response(JSON.stringify({
    responseStatus: 403, responseDetails: 'QUOTA EXCEEDED',
  }), { status: 200 });
  r = await call(trFn, 'q=x&langpair=zh-TW|en');
  d = await r.json();
  ok(r.status === 502 && d.error === 'no translation', 'translate：配额用尽 → 502 no translation');
  ok((await call(trFn, 'from=en&to=zh-CN')).status === 400, 'translate：缺 q → 400');

  globalThis.fetch = origFetch;
}

/* ---------------- I. 根目录转发层（Pages 只从「项目根目录」的 functions/ 读 Functions） ---------------- */
async function testRootShims() {
  console.log('\nI. 根目录 functions/ 转发层');
  const ROOTDIR = path.resolve(__dirname, '../..');
  const names = ['dict', 'dict-links', 'translate'];
  for (const n of names) {
    const shimPath = path.join(ROOTDIR, 'functions/api', n + '.js');
    const realPath = path.join(ROOT, 'functions/api', n + '.js');
    ok(fs.existsSync(shimPath), '存在根目录转发层 functions/api/' + n + '.js');
    ok(fs.existsSync(realPath), '存在实现文件 网站/functions/api/' + n + '.js');
    if (!fs.existsSync(shimPath)) continue;
    const src = fs.readFileSync(shimPath, 'utf8');
    ok(/from '\.\.\/\.\.\/网站\/functions\/api\//.test(src),
       n + '：转发层只做 re-export（不重复实现）');
    const mod = await import(pathToFileURL(shimPath).href);
    ok(typeof mod.onRequest === 'function', n + '：转发层导出 onRequest（可被 Pages 调用）');
  }
  // 行为一致性：转发层与实现文件是同一个函数
  const shim = await import(pathToFileURL(path.join(ROOTDIR, 'functions/api/dict-links.js')).href);
  const real = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict-links.js')).href);
  ok(shim.onRequest === real.onRequest && shim.buildDictLinks === real.buildDictLinks,
     'dict-links：转发层与实现指向同一个函数（不会走偏）');
}

/* ---------------- 主流程 ---------------- */
(async function main() {
  testClassify();
  testChain();
  await testLookup();
  await testEnX();
  testSplit();
  await testLinks();
  await testTranslate();
  await testFunctions();
  await testRootShims();

  console.log('\n' + (failed.length
    ? '❌ 失败 ' + failed.length + ' 项（通过 ' + pass + '）'
    : '🎉 全部通过（' + pass + ' 项）'));
  if (failed.length) {
    failed.forEach(function (f) { console.log('   - ' + f); });
    process.exit(1);
  }
})();
