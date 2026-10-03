/* ============================================================
   查词面板 · 端到端测试（jsdom + 真实 Pages Function，无外网）
   ------------------------------------------------------------
   跑法：JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/dict-panel-e2e-test.js
   验证（多源回退 + 翻译 Tab + 更多词典 + 缓存）：
     1) 单字：离线（康熙/说文）常显；在线链 萌典 → 中文 Wiktionary（被墙跳过）→ Unihan
     2) 中文 Wiktionary 默认**不发请求**（白名单闸门），面板标注「（跳过）」
     3) 萌典成功 → 「来源：萌典」+ 拼音 + 释义；萌典挂掉 → 「在线释义暂不可用」+ 离线仍在
     4) 全部失败 → 「未找到释义」（绝不空白）
     5) 多字（2–5 汉字）→ 中文词语链（萌典），不碰英文源
     6) 6+ 字符 → 自动切「翻译」Tab + 释义 Tab 逐词查 + 请求 /api/translate
     7) 所有请求只打同域（/api/* 与 _site_data/*），绝不直连第三方
     8) 更多词典：默认 2 条（新窗口）；开「容错外链」后 3 条
     9) 缓存：同一字第二次点开不再发请求
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const ROOT = path.resolve(__dirname, '../../网站');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';
const { JSDOM, VirtualConsole } = require(JSDOM_PATH);
const BOOK = process.env.BOOK || '論語';
const FALLBACK_KEY = 'guoxue_dict_fallback_links';

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ---------- 上游桩：按目标站点分流 ---------- */
const up = { moedict: 'ok', freedict: 'ok', wiki: 'ok', translate: 'ok', unihan: 'ok' };
const upstreamCalls = [];

function upstreamStub(url) {
  upstreamCalls.push(url);
  if (url.indexOf('/_site_data/') !== -1) {                       // Unihan 自取本站分片
    if (up.unihan === 'fail') return new Response('{"error":"nope"}', { status: 404 });
    const rel = decodeURIComponent(url.replace(/^.*?\/_site_data\//, '_site_data/'));
    try {
      return new Response(fs.readFileSync(path.join(ROOT, rel), 'utf8'), { status: 200 });
    } catch (e) {
      return new Response('{"error":"not found"}', { status: 404 });
    }
  }
  if (url.indexOf('moedict.tw') !== -1) {
    if (up.moedict === 'fail') throw new Error('simulated moedict down');
    if (up.moedict === 'notfound') return new Response('{"title":"x"}', { status: 200 });
    return new Response(JSON.stringify({
      title: '之',
      heteronyms: [{ bopomofo: 'ㄓ', pinyin: 'zhī',
                     meanings: [{ def: '往、到' }, { def: '的、此' }] }],
    }), { status: 200 });
  }
  if (url.indexOf('dictionaryapi.dev') !== -1) {
    if (up.freedict === 'fail') {
      return new Response('{"title":"No Definitions Found"}', { status: 404 });
    }
    return new Response(JSON.stringify([{
      word: 'hello',
      phonetics: [{ text: '/həˈləʊ/' }],
      meanings: [{ partOfSpeech: 'noun', definitions: [{ definition: 'an utterance of hello' }] }],
    }]), { status: 200 });
  }
  if (url.indexOf('mymemory') !== -1) {
    if (up.translate === 'fail') return new Response('{"responseStatus":403}', { status: 200 });
    return new Response(JSON.stringify({
      responseStatus: 200,
      responseData: { translatedText: 'THE TRANSLATED SENTENCE', match: 0.85 },
    }), { status: 200 });
  }
  if (up.wiki === 'fail') return new Response('boom', { status: 500 });   // wiki 源
  return new Response(JSON.stringify({
    query: { pages: { '1': { pageid: 1, title: '仁', extract: '儒家核心概念，指愛人。' } } },
  }), { status: 200 });
}


/* ---------- 打开阅读页（注入真实 Function） ---------- */
async function openReader(fns, opts) {
  opts = opts || {};
  const vc = new VirtualConsole();
  const errors = [];
  vc.on('jsdomError', function (e) {
    const m = e.message || String(e);
    if (/Not implemented/.test(m)) return;        // jsdom 能力所限，不算应用错误
    errors.push(m);
  });
  const html = fs.readFileSync(path.join(ROOT, 'reader.html'), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: 'http://localhost/reader.html?book=' + encodeURIComponent(BOOK) + '&index=0',
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
  });
  const window = dom.window, doc = window.document, pageCalls = [];
  window.matchMedia = function (q) {
    return { matches: /min-width:\s*1100px/.test(q), media: q,
             addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} };
  };
  if (opts.fallback) { try { window.localStorage.setItem(FALLBACK_KEY, '1'); } catch (e) {} }
  window.fetch = function (u) {
    const url = String(u);
    pageCalls.push(url);
    const req = function () { return new Request('https://myfami.cn' + url); };
    if (url.indexOf('/api/dict?') === 0) return fns.dict.onRequest({ request: req() });
    if (url.indexOf('/api/dict-links') === 0) return fns.links.onRequest({ request: req() });
    if (url.indexOf('/api/translate') === 0) return fns.translate.onRequest({ request: req() });
    return new Promise(function (res) {
      fs.readFile(path.join(ROOT, decodeURIComponent(url.split('?')[0])), 'utf8', function (err, data) {
        if (err) return res({ ok: false, status: 404, json: async () => ({}) });
        return res({ ok: true, status: 200, json: async () => JSON.parse(data) });
      });
    });
  };
  ['common.js', 'vocab-matcher.js', 'annotation-lang.js',
   'dict-links.js', 'dict-api.js', 'reader.js'].forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });
  return { window: window, doc: doc, calls: pageCalls, errors: errors, dom: dom };
}

async function waitFor(fn, tries) {
  for (let i = 0; i < (tries || 300); i++) { if (fn()) return true; await sleep(20); }
  return false;
}

/** 等阅读页打标出 <wise> */
async function waitWise(P) {
  let wise = [];
  for (let i = 0; i < 240; i++) {
    wise = P.doc.querySelectorAll('wise');
    if (wise.length) break;
    await sleep(50);
  }
  return wise;
}

function singleCharWise(wise) {
  return Array.prototype.find.call(wise, function (w) {
    return (w.getAttribute('data-word') || '').length === 1;
  });
}

function clickWord(P, el) {
  el.dispatchEvent(new P.window.MouseEvent('click', { bubbles: true }));
}

function dpText(P) {
  const dp = P.doc.getElementById('dp-body');
  return dp ? dp.textContent : '';
}

function panelFetches(P) {
  return P.calls.filter(function (u) { return u.indexOf('/api/dict?') === 0; });
}

function srcList(P) {
  return panelFetches(P).map(function (u) {
    const m = u.match(/source=([a-z]+)/);
    return m ? m[1] : '?';
  });
}

/* ---------------- 主流程 ---------------- */
(async function main() {
  const fn = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict.js')).href);
  const fnLinks = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict-links.js')).href);
  const fnTr = await import(pathToFileURL(path.join(ROOT, 'functions/api/translate.js')).href);
  const fns = { dict: fn, links: fnLinks, translate: fnTr };
  globalThis.fetch = async function (u) { return upstreamStub(String(u)); };

  console.log('A. 单字：离线常显 + 回退链（萌典命中）');
  const P = await openReader(fns, {});
  const wise = await waitWise(P);
  ok(wise.length > 0, '阅读页渲染并打标出 <wise>（' + wise.length + ' 个）');
  const one = singleCharWise(wise);
  ok(!!one, '找到单个汉字的 <wise>');
  clickWord(P, one);
  await waitFor(function () { return /来源：|未找到释义/.test(dpText(P)); });
  let body = dpText(P);
  ok(/来源：萌典/.test(body), '命中萌典并标注「来源：萌典」', body.slice(0, 100));
  ok(/zhī/.test(body), '显示萌典拼音');
  ok(/往、到/.test(body), '显示萌典释义条目');
  ok(/康熙字典/.test(body) && /说文解字/.test(body), '离线区常显 康熙字典 / 说文解字');
  const srcs = srcList(P);
  ok(srcs.indexOf('moedict') >= 0, '按回退链请求了 source=moedict（' + srcs.join(',') + '）');
  ok(srcs.indexOf('wiktionary') < 0, '中文 Wiktionary 默认**不发请求**（白名单闸门）');
  ok(P.calls.every(function (u) { return u.indexOf('/api/') === 0 || u.indexOf('_site_data/') === 0; }),
     '所有请求只打同域（/api/* 与 _site_data/*）');
  ok(P.errors.length === 0, '无 JS 运行时错误', P.errors.slice(0, 2).join(' | '));

  const n1 = panelFetches(P).length;
  clickWord(P, one);
  await sleep(500);
  ok(panelFetches(P).length === n1, '同一字第二次点开命中缓存（' + n1 + ' → ' + panelFetches(P).length + ' 次请求）');

  const links = Array.from(P.doc.querySelectorAll('#dp-body .dl-list a'));
  ok(links.length === 3, '「更多词典」默认 3 条（漢典 / 萌典 / 教育部辞典）（实际 ' + links.length + '）');
  ok(links.every(function (a) {
    return a.getAttribute('target') === '_blank' && /noopener/.test(a.getAttribute('rel') || '');
  }), '更多词典链接均 target=_blank rel=noopener');
  ok(links.every(function (a) { return a.getAttribute('href').indexOf('zh.wiktionary.org') < 0; }),
     '更多词典里没有被墙的中文 Wiktionary');
  await waitFor(function () { return /已隐藏 3 个不可用源/.test(dpText(P)); });
  ok(/已隐藏 3 个不可用源/.test(dpText(P)), '面板写明「已隐藏 3 个不可用源」');
  ok(P.doc.querySelectorAll('#dp-body .dp-wordbox').length === 0, '单字走回退链，不做逐词查');
  ok(!!P.doc.querySelector('#dp-body .dp-tabs .dp-tab.is-active'), '面板有 Tab 且「释义」为当前页');
  P.dom.window.close();

  console.log('\nB. 在线全挂 → 降级（绝不空白）');
  up.moedict = 'fail';
  up.unihan = 'fail';
  const P2 = await openReader(fns, {});
  const wise2 = await waitWise(P2);
  const one2 = singleCharWise(wise2);
  clickWord(P2, one2);
  await waitFor(function () { return /未找到释义|来源：/.test(dpText(P2)); });
  body = dpText(P2);
  ok(/未找到释义/.test(body), '全部在线源失败 → 「未找到释义」', body.slice(0, 90));
  ok(/在线释义暂不可用/.test(body), '同时提示「在线释义暂不可用」');
  ok(/康熙字典/.test(body) && /说文解字/.test(body), '降级后离线词典仍在');
  ok(/（跳过）/.test(body) && /被墙/.test(body), '面板标注了被闸门跳过的源（被墙 / 被拦）');
  ok(/moedict[\s\S]{0,4}✗|萌典✗/.test(body) || /✗/.test(body), '标注了失败的源（✗）');
  P2.dom.window.close();
  up.moedict = 'ok';
  up.unihan = 'ok';

  console.log('\nC. 开「容错外链」→ 中文 Wiktionary 进入回退链');
  up.moedict = 'notfound';                       // 逼出下一级
  const P3 = await openReader(fns, { fallback: true });
  const wise3 = await waitWise(P3);
  clickWord(P3, singleCharWise(wise3));
  await waitFor(function () { return /来源：|未找到释义/.test(dpText(P3)); });
  body = dpText(P3);
  ok(srcList(P3).indexOf('wiktionary') >= 0, '容错外链开启后请求了 source=wiktionary');
  ok(/来源：中文 Wiktionary/.test(body), '命中中文 Wiktionary 并标注来源', body.slice(0, 100));
  ok(/儒家核心概念/.test(body), '显示 Wiktionary 摘要（截取后）');
  const links3 = Array.from(P3.doc.querySelectorAll('#dp-body .dl-list a'));
  ok(links3.length === 4, '更多词典变为 4 条（含中文 Wiktionary）(' + links3.length + ')');
  P3.dom.window.close();
  up.moedict = 'ok';

  console.log('\nD. 多字（2–5 汉字）：中文词语链');
  const P4 = await openReader(fns, {});
  const wise4 = await waitWise(P4);
  const two = Array.prototype.find.call(wise4, function (w) {
    const t = w.getAttribute('data-word') || '';
    const n = Array.from(t).length;
    return n >= 2 && n <= 5 && /^[\u4e00-\u9fff]+$/.test(t);
  });
  ok(!!two, '找到 2–5 字的中文 <wise>');
  if (two) {
    clickWord(P4, two);
    await waitFor(function () { return /来源：|未找到释义|未收录/.test(dpText(P4)); });
    const b4 = dpText(P4);
    ok(srcList(P4).indexOf('moedict') >= 0, '多字走中文词语链（萌典）');
    ok(/CC-CEDICT|离线字典/.test(b4), '离线区按「词语」口径（CC-CEDICT）');
    ok(srcList(P4).indexOf('freedict') < 0, '多字不碰英文源（freedict）');
  }
  P4.dom.window.close();

  console.log('\nE. 6+ 字符 / 整句：自动切「翻译」Tab + 逐词查');
  const P5 = await openReader(fns, {});
  await waitWise(P5);
  const para = Array.prototype.find.call(P5.doc.querySelectorAll('#reader p'), function (p) {
    return (p.textContent || '').trim().length >= 6;
  });
  ok(!!para, '找到一段正文用于长选择');
  if (para) {
    const rng = P5.doc.createRange();
    rng.selectNodeContents(para);
    const sel = P5.window.getSelection();
    sel.removeAllRanges();
    sel.addRange(rng);
    P5.doc.dispatchEvent(new P5.window.Event('selectionchange'));
    await waitFor(function () { return /逐词查/.test(dpText(P5)); });
    const b5 = dpText(P5);
    ok(/逐词查/.test(b5), '释义 Tab 改为逐词查');
    const boxes = P5.doc.querySelectorAll('#dp-body .dp-wordbox');
    ok(boxes.length > 0, '逐词查列出若干词条（' + boxes.length + '）');
    const panes = P5.doc.querySelectorAll('#dp-body .dp-pane');
    ok(panes.length === 2 && panes[1].hidden === false && panes[0].hidden === true,
       '6+ 字符自动切到「翻译」Tab');
    await waitFor(function () {
      return P5.calls.some(function (u) { return u.indexOf('source=translate') > 0; });
    });
    ok(P5.calls.some(function (u) { return u.indexOf('source=translate') > 0; }),
       '长文本自动请求翻译接口（同域 /api/dict?source=translate）');
    await waitFor(function () { return /THE TRANSLATED SENTENCE/.test(dpText(P5)); });
    ok(/THE TRANSLATED SENTENCE/.test(dpText(P5)), '翻译结果渲染进面板');
    ok(P5.calls.every(function (u) {
      return u.indexOf('/api/') === 0 || u.indexOf('_site_data/') === 0;
    }), '长文本下所有请求仍只打同域');
    ok(P5.errors.length === 0, '长文本无 JS 运行时错误', P5.errors.slice(0, 2).join(' | '));
  }
  P5.dom.window.close();

  console.log('\n' + (failed.length
    ? '❌ 失败 ' + failed.length + ' 项（通过 ' + pass + '）'
    : '🎉 全部通过（' + pass + ' 项）'));
  if (failed.length) {
    failed.forEach(function (f) { console.log('   - ' + f); });
    process.exit(1);
  }
})();
