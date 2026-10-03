/* ============================================================
   查词面板 · 端到端测试（jsdom + 真实 Pages Function，无外网）
   ------------------------------------------------------------
   跑法：JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/dict-panel-e2e-test.js
   验证：
     1) 单字查词只请求**同域** /api/dict，绝不直连 zh.wikipedia/wiktionary
     2) 在线成功 → 面板出现摘要
     3) 在线失败 → 面板兜底「在线释义暂不可用」，且离线康熙/说文仍在
     4) 选中多字 → 跳过在线请求，只走离线
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const ROOT = path.resolve(__dirname, '../../网站');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';
const { JSDOM } = require(JSDOM_PATH);
const BOOK = process.env.BOOK || '論語';

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async function main() {
  // ---- 真实 Pages Function ----
  const fn = await import(pathToFileURL(path.join(ROOT, 'functions/api/dict.js')).href);

  // ---- 上游（维基）桩：Function 内部用的是 Node 全局 fetch ----
  const upstream = { mode: 'ok' };
  const upstreamCalls = [];
  globalThis.fetch = async (url) => {
    upstreamCalls.push(String(url));
    if (upstream.mode === 'fail') throw new Error('simulated upstream down');
    if (upstream.mode === 'notfound') {
      return new Response(JSON.stringify({ query: { pages: { '-1': { title: 'x', missing: '' } } } }), { status: 200 });
    }
    return new Response(JSON.stringify({
      query: { pages: { '1': { pageid: 1, title: '仁', extract: '儒家核心概念，指愛人。' } } },
    }), { status: 200 });
  };

  // ---- 页面 ----
  const html = fs.readFileSync(path.join(ROOT, 'reader.html'), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: 'http://localhost/reader.html?book=' + encodeURIComponent(BOOK) + '&index=1',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const doc = window.document;

  // 面板只在桌面端启用 → 让 matchMedia 命中 min-width:1100px
  window.matchMedia = function (q) {
    return { matches: /min-width:\s*1100px/.test(q), media: q,
             addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} };
  };

  const pageCalls = [];
  window.fetch = function (u) {
    const url = String(u);
    pageCalls.push(url);
    if (url.indexOf('/api/dict') === 0) {                 // 同域代理 → 真实 Function
      return fn.onRequest({ request: new Request('https://myfami.cn' + url) });
    }
    const file = path.join(ROOT, '_site_data',
      decodeURIComponent(url.replace(/^_site_data\//, '')));
    return new Promise(function (res) {
      fs.readFile(file, 'utf8', function (err, data) {
        if (err) return res({ ok: false, status: 404, json: async () => ({}) });
        return res({ ok: true, status: 200, json: async () => JSON.parse(data) });
      });
    });
  };

  ['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js'].forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });

  // 等正文打标
  let wise = [];
  for (let i = 0; i < 200; i++) {
    wise = doc.querySelectorAll('wise');
    if (wise.length) break;
    await sleep(50);
  }
  ok(wise.length > 0, '阅读页渲染并打标出 <wise>（' + wise.length + ' 个）');

  const dp = doc.getElementById('dict-panel');
  const dpBody = doc.getElementById('dp-body');
  ok(!!dp && !!dpBody, '存在 #dict-panel / #dp-body');

  const single = Array.prototype.find.call(wise, function (w) {
    return (w.getAttribute('data-word') || '').length === 1;
  });
  ok(!!single, '找到单个汉字的 <wise>');
  if (!single) return finish();


  // ---- 1) 单字点击 → 同域 /api/dict ----
  const nApiBefore = pageCalls.filter(u => u.indexOf('/api/dict') === 0).length;
  single.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(600);

  const apiCalls = pageCalls.filter(u => u.indexOf('/api/dict') === 0);
  ok(apiCalls.length > nApiBefore,
     '点击单字后请求了同域 /api/dict（' + (apiCalls.length - nApiBefore) + ' 次）',
     apiCalls.slice(-2).join(' | '));
  ok(/\/api\/dict\?source=(wikipedia|wiktionary)&lang=zh&q=/.test(apiCalls[apiCalls.length - 1] || ''),
     '请求形如 /api/dict?source=…&lang=zh&q=…', apiCalls[apiCalls.length - 1]);
  ok(pageCalls.every(u => u.indexOf('//zh.wikipedia.org') === -1 &&
                          u.indexOf('//zh.wiktionary.org') === -1),
     '页面从未直连 zh.wikipedia.org / zh.wiktionary.org');
  ok(upstreamCalls.length > 0 && upstreamCalls.every(u => u.indexOf('origin=*') !== -1),
     '代理转发一律带 origin=*');

  // ---- 2) 在线成功 → 摘要出现 ----
  ok(dpBody.textContent.indexOf('儒家核心概念') !== -1, '在线成功时面板显示摘要',
     dpBody.textContent.slice(0, 80));
  ok(dpBody.textContent.indexOf('在线释义暂不可用') === -1, '成功时不显示兜底提示');

  // ---- 3) 在线失败 → 兜底提示 + 离线词典仍在 ----
  upstream.mode = 'fail';
  single.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(800);
  ok(dpBody.textContent.indexOf('在线释义暂不可用') !== -1, '在线失败时显示「在线释义暂不可用」',
     dpBody.textContent.slice(-60));
  ok(/康熙字典|說文解字|说文解字/.test(dpBody.textContent),
     '失败时离线词典（康熙/说文）仍在面板中');

  // ---- 4) 选中多字 → 跳过在线 ----
  const nApiNow = pageCalls.filter(u => u.indexOf('/api/dict') === 0).length;
  const para = Array.prototype.find.call(doc.querySelectorAll('#reader p'),
    p => (p.textContent || '').trim().length >= 6);
  if (para) {
    const r = doc.createRange();
    r.selectNodeContents(para);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
    doc.dispatchEvent(new window.Event('selectionchange'));
    await sleep(800);
    const nApiAfter = pageCalls.filter(u => u.indexOf('/api/dict') === 0).length;
    ok(nApiAfter === nApiNow, '选中多字时**不再**请求在线（' + nApiNow + ' → ' + nApiAfter + '）');
    ok(dpBody.textContent.indexOf('本站释义') !== -1, '多字时仍走离线（本站释义区在）');
  } else {
    ok(false, '未找到可选的正文段落（多字测试跳过）');
  }

  finish();

  function finish() {
    console.log('\n结果：' + pass + ' 通过 / ' + failed.length + ' 失败');
    if (failed.length) failed.forEach(f => console.log('   ✗ ' + f));
    process.exit(failed.length ? 1 : 0);
  }
})().catch(e => {
  console.error('测试异常：', e);
  process.exit(2);
});
