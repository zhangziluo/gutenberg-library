/* ============================================================
   站外词典白名单（dict-links）· 测试
   ------------------------------------------------------------
   跑法：JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/dict-links-test.js
   验证（对应需求）：
     A. 基线：漢典 / ctext 默认展示；國學大師 / 中華典藏 / 中文維基詞典 默认 hidden
     B. 检索页「更多词典」：只渲染 enabled；hidden **不出现在 DOM、不发请求、不预取**
     C. 阅读页面板：同上；且**在线摘要请求里绝不出现 source=wiktionary**
     D. 设置页「容错外链」开关：开启后维基词典才出现（仍新窗口打开）
     E. 探活脚本（不联网）：阿里云拦截页 → 失败；正常页 → 成功；状态机 2 次才翻转
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SITE = path.resolve(__dirname, '../../网站');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';
const FALLBACK_KEY = 'guoxue_dict_fallback_links';
const HIDDEN_HOSTS = ['www.guoxuedashi.net', 'www.zhonghuadiancang.com', 'zh.wiktionary.org'];

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 静态托管桩：可覆盖 dict_links.json（模拟探活结果） */
function serve(url, statusDoc) {
  const clean = decodeURIComponent(String(url).split('?')[0]);
  if (statusDoc && /_site_data\/dict\/dict_links\.json$/.test(clean)) {
    return Promise.resolve({ ok: true, status: 200, json: async () => statusDoc });
  }
  return new Promise(function (res) {
    fs.readFile(path.join(SITE, clean), 'utf8', function (err, data) {
      if (err) return res({ ok: false, status: 404, json: async () => ({}) });
      return res({ ok: true, status: 200, json: async () => JSON.parse(data) });
    });
  });
}

/** 打开某个页面（jsdom），返回 window/doc/请求列表 */
async function openPage(file, query, scripts, opts) {
  const { JSDOM, VirtualConsole } = require(JSDOM_PATH);
  opts = opts || {};
  const vc = new VirtualConsole();
  const errors = [];
  vc.on('jsdomError', function (e) { errors.push(e.message || String(e)); });
  const html = fs.readFileSync(path.join(SITE, file), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: 'http://localhost/' + file + (query == null ? '' : '?' + query),
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
  });
  const window = dom.window, doc = window.document, calls = [];
  if (opts.fallback) { try { window.localStorage.setItem(FALLBACK_KEY, '1'); } catch (e) {} }
  window.matchMedia = function (q) {
    return { matches: /min-width:\s*1100px/.test(q), media: q,
             addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} };
  };
  window.fetch = function (u) { calls.push(String(u)); return serve(u, opts.statusDoc); };
  (scripts || []).forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(SITE, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });
  return { window: window, doc: doc, calls: calls, errors: errors, dom: dom };
}

async function waitFor(fn, tries) {
  for (let i = 0; i < (tries || 400); i++) { if (fn()) return true; await sleep(20); }
  return false;
}

/** 在 Node VM 里跑 js/dict-links.js（无 DOM），用于纯逻辑断言 */
function loadDictLinks(statusDoc, fallbackOn) {
  const store = {};
  if (fallbackOn) store[FALLBACK_KEY] = '1';
  const ls = {
    getItem: function (k) { return (k in store) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; }
  };
  const win = {
    localStorage: ls,
    loadJSON: function () { return Promise.resolve(statusDoc || { sources: {} }); }
  };
  const ctx = { window: win, localStorage: ls, console: console, Promise: Promise,
                encodeURIComponent: encodeURIComponent, fetch: function () {
                  return Promise.reject(new Error('no network in test'));
                } };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(SITE, 'js', 'dict-links.js'), 'utf8'), ctx);
  return { DictLinks: win.DictLinks, store: store };
}

/** 页面里出现的外站主机（用于「绝不请求外站」断言） */
function externalHosts(calls) {
  return calls.filter(function (u) { return /^https?:\/\//.test(u); });
}

/**
 * 页面里所有指向外站的 href / src（含 <a> <img> <link> <script src> <iframe>）。
 * 注意不能拿 outerHTML 判：测试是把 js 源码当内联脚本注进 DOM 的，
 * 源码里当然有白名单 URL —— 那不算「渲染出来」，更不算「预取」。
 */
function externalRefs(doc) {
  const out = [];
  Array.prototype.forEach.call(doc.querySelectorAll('[href],[src]'), function (el) {
    const v = el.getAttribute('href') || el.getAttribute('src') || '';
    if (/^https?:\/\//.test(v)) out.push(v);
  });
  return out;
}

/** 渲染区里是否出现了某个隐藏源（只查渲染出来的链接/文本容器） */
function panelText(root) {
  const hosts = externalRefs(root).join(' ');
  return hosts + ' ' + (root.textContent || '');
}


/* ---------------- A. 白名单基线 ---------------- */
const STATUS_DOC = JSON.parse(
  fs.readFileSync(path.join(SITE, '_site_data', 'dict', 'dict_links.json'), 'utf8'));

async function testBaseline() {
  console.log('\nA. 白名单基线');

  // A1 纯默认（探活文件为空）
  const d1 = loadDictLinks({ sources: {} }, false);
  const D1 = d1.DictLinks;
  ok(!!D1 && D1.SOURCES.length === 5, 'js/dict-links.js 可加载，白名单 5 个源');
  await D1.ready();
  ok(D1.stateOf('zdic') === 'enabled', '默认展示：漢典（zdic）');
  ok(D1.stateOf('ctext') === 'enabled', '默认展示：中國哲學書電子化計劃（ctext）');
  ok(D1.stateOf('wiktionary-zh') === 'hidden', '默认隐藏：中文維基詞典');
  ok(D1.stateOf('guoxuedashi') === 'hidden', '默认隐藏：國學大師');
  ok(D1.stateOf('zhonghuadiancang') === 'hidden', '默认隐藏：中華典藏');
  ok(D1.visible('zh').length === 2, '默认可见源 = 2 个（实际 ' + D1.visible('zh').length + '）');
  ok(D1.urlOf('guoxuedashi', '仁') === null, 'hidden 源的 urlOf() 返回 null（绝不建链）');
  ok(/zdic\.net/.test(D1.urlOf('zdic', '仁') || ''), 'enabled 源的 urlOf() 正常');
  ok(D1.hiddenHosts().sort().join(',') ===
     ['www.guoxuedashi.net', 'www.zhonghuadiancang.com', 'zh.wiktionary.org'].sort().join(','),
     'hiddenHosts() 覆盖三家：' + D1.hiddenHosts().join('、'));

  // A2 开启容错外链 → 中文维基词典变成 fallback（仍不算 enabled）
  const d2 = loadDictLinks({ sources: {} }, true);
  const D2 = d2.DictLinks;
  await D2.ready();
  ok(D2.stateOf('wiktionary-zh') === 'fallback', '开「容错外链」后：中文維基詞典 = fallback');
  ok(D2.visible('zh').some(function (v) { return v.id === 'wiktionary-zh'; }), 'fallback 源进入可见列表');
  ok(D2.stateOf('guoxuedashi') === 'hidden', '开「容错外链」不会放出國學大師（那是探活的事）');
  D2.setFallback(true);
  ok(d2.store[FALLBACK_KEY] === '1', 'setFallback() 写入同一个 key');

  // A3 真实探活文件（当前状态）
  const d3 = loadDictLinks(STATUS_DOC, false);
  const D3 = d3.DictLinks;
  await D3.ready();
  ok(STATUS_DOC.policy.promote_after_ok === 2 && STATUS_DOC.policy.demote_after_fail === 2,
     '策略：连续 2 次成功才启用 / 连续 2 次失败才隐藏');
  ['guoxuedashi', 'zhonghuadiancang'].forEach(function (id) {
    ok(STATUS_DOC.sources[id] && STATUS_DOC.sources[id].state === 'hidden',
       'dict_links.json 现状：' + id + ' = hidden');
  });
  ok(D3.stateOf('guoxuedashi') === 'hidden' && D3.stateOf('zhonghuadiancang') === 'hidden',
     '按探活文件：國學大師 / 中華典藏 均不展示');
  ok(D3.stateOf('zdic') === 'enabled' && D3.stateOf('ctext') === 'enabled',
     '按探活文件：漢典 / ctext 照常展示');

  // A4 探活结论可以自动放出来
  const d4 = loadDictLinks({ sources: { guoxuedashi: { state: 'enabled', streak_ok: 2 } } }, false);
  await d4.DictLinks.ready();
  ok(d4.DictLinks.stateOf('guoxuedashi') === 'enabled', '探活连续 2 次成功 → 自动展示國學大師');
  ok(d4.DictLinks.visible('zh').length === 3, '此时可见源 3 个');

  // A5 维基词典不受探活影响：仍要用户手动开
  const d5 = loadDictLinks({ sources: { 'wiktionary-zh': { state: 'enabled' } } }, false);
  await d5.DictLinks.ready();
  ok(d5.DictLinks.stateOf('wiktionary-zh') === 'hidden',
     '维基词典即使被探活标成 enabled，未开「容错外链」也不展示');
  const d6 = loadDictLinks({ sources: { 'wiktionary-zh': { state: 'hidden' } } }, true);
  await d6.DictLinks.ready();
  ok(d6.DictLinks.stateOf('wiktionary-zh') === 'hidden',
     '反之：探活说 hidden 时，开了「容错外链」也不放出来（以探活为准）');
  // A6 真实探活文件里 wiktionary-zh 没有结论（state: null，因为不探活）
  const d7 = loadDictLinks(STATUS_DOC, true);
  await d7.DictLinks.ready();
  ok(d7.DictLinks.stateOf('wiktionary-zh') === 'fallback',
     '真实 dict_links.json：wiktionary-zh 无探活结论（state:null）→ 开「容错外链」即可用');
}

/* ---------------- B. 检索页「更多词典」 ---------------- */
async function testSearchPage() {
  console.log('\nB. 检索页「更多词典」');
  const scripts = ['common.js', 'dict-links.js', 'dict-lookup.js', 'search.js'];
  const q = 'q=' + encodeURIComponent('仁');
  const ready = function (P) {
    return waitFor(function () {
      return /s-third-link|dl-empty/.test(P.doc.getElementById('third-body').innerHTML);
    });
  };

  // B1 默认：只渲染 2 条
  const P = await openPage('search.html', q, scripts);
  await ready(P);
  const box = P.doc.getElementById('third-body');
  const anchors = Array.from(box.querySelectorAll('a'));
  ok(anchors.length === 2, '默认只渲染 2 条外链（实际 ' + anchors.length + '）');
  ok(/zdic\.net\/hans\//.test(box.innerHTML), '含 漢典 链接');
  ok(/ctext\.org\/search\.pl/.test(box.innerHTML), '含 ctext 链接');
  const refs = externalRefs(P.doc).join(' ');
  HIDDEN_HOSTS.forEach(function (h) {
    ok(refs.indexOf(h) < 0, '页面没有任何指向隐藏源的引用（不渲染 / 不预取）：' + h,
       refs.slice(0, 120));
  });
  ok(externalHosts(P.calls).length === 0, '没有任何外站请求（隐藏源未被预取/请求）',
     externalHosts(P.calls).join(' | '));
  ok(P.calls.every(function (u) { return /^_site_data\//.test(u); }), '只请求同域 _site_data');
  const preLinks = Array.from(P.doc.querySelectorAll('link[rel]')).filter(function (l) {
    return /prefetch|preconnect|dns-prefetch/i.test(l.getAttribute('rel') || '');
  });
  ok(preLinks.length === 0, '页面没有 prefetch / preconnect / dns-prefetch');
  ok(P.errors.length === 0, '检索页无 JS 运行时错误', P.errors.slice(0, 2).join(' | '));
  P.dom.window.close();

  // B2 开启「容错外链」→ 多出中文维基词典（带「容错」标记，仍新窗口）
  const P2 = await openPage('search.html', q, scripts, { fallback: true });
  await ready(P2);
  const box2 = P2.doc.getElementById('third-body');
  const a2 = Array.from(box2.querySelectorAll('a'));
  ok(a2.length === 3, '开启「容错外链」后 3 条（实际 ' + a2.length + '）');
  ok(box2.innerHTML.indexOf('zh.wiktionary.org') >= 0, '出现中文维基词典');
  ok(/<i class="dl-tag">容错<\/i>/.test(box2.innerHTML), '维基词典带「容错」标记');
  ok(a2.every(function (a) {
    return a.getAttribute('target') === '_blank' && /noopener/.test(a.getAttribute('rel') || '');
  }), '全部新窗口打开（target=_blank + rel=noopener）');
  ['guoxuedashi.net', 'zhonghuadiancang.com'].forEach(function (h) {
    ok(box2.innerHTML.indexOf(h) < 0, '开启容错也不会放出未过探活的源：' + h);
  });
  ok(externalHosts(P2.calls).length === 0, '开启容错后仍未预览/预取任何外站');
  P2.dom.window.close();

  // B3 探活把國學大師标成 enabled → 自动展示
  const P3 = await openPage('search.html', q, scripts, {
    statusDoc: { sources: { guoxuedashi: { state: 'enabled', streak_ok: 2 } } }
  });
  await ready(P3);
  const box3 = P3.doc.getElementById('third-body');
  ok(box3.innerHTML.indexOf('guoxuedashi.net') >= 0, '探活 enabled → 國學大師 自动出现');
  ok(box3.innerHTML.indexOf('zhonghuadiancang') < 0, '未过探活的源仍不出现');
  ok(externalHosts(P3.calls).length === 0, '自动出现也不预取（仍是纯链接）');
  P3.dom.window.close();

  // B4 维基词典即使被探活 enabled，没开「容错外链」也不出现
  const P4 = await openPage('search.html', q, scripts, {
    statusDoc: { sources: { 'wiktionary-zh': { state: 'enabled' } } }
  });
  await ready(P4);
  ok(P4.doc.getElementById('third-body').innerHTML.indexOf('zh.wiktionary.org') < 0,
     '维基词典受「容错外链」闸门管：探活 enabled 也不自动出现');
  P4.dom.window.close();

  // B5 静态扫描：全站页面 / 脚本都没有 preconnect / prefetch / dns-prefetch
  const files = fs.readdirSync(SITE).filter(function (f) { return /\.(html|js)$/.test(f); })
    .map(function (f) { return path.join(SITE, f); })
    .concat(fs.readdirSync(path.join(SITE, 'js')).map(function (f) {
      return path.join(SITE, 'js', f);
    }));
  const withPrefetch = files.filter(function (fp) {
    return /rel\s*=\s*["']?(preconnect|prefetch|dns-prefetch)/i.test(fs.readFileSync(fp, 'utf8'));
  });
  ok(withPrefetch.length === 0, '全站没有 preconnect/prefetch/dns-prefetch',
     withPrefetch.map(function (f) { return path.basename(f); }).join('、'));
}

/* ---------------- C. 阅读页查词面板（选词时同样只给可用源） ---------------- */
async function testReaderPage() {
  console.log('\nC. 阅读页查词面板');
  const BOOK = process.env.BOOK || '論語';
  const scripts = ['common.js', 'vocab-matcher.js', 'annotation-lang.js',
                   'dict-links.js', 'dict-api.js', 'reader.js'];

  async function clickFirstSingle(fallback) {
    const P = await openPage('reader.html',
      'book=' + encodeURIComponent(BOOK) + '&index=0', scripts, { fallback: fallback });
    let wise = [];
    for (let i = 0; i < 300; i++) {
      wise = P.doc.querySelectorAll('wise');
      if (wise.length) break;
      await sleep(50);
    }
    const single = Array.prototype.find.call(wise, function (w) {
      return (w.getAttribute('data-word') || '').length === 1;
    });
    if (!single) return { P: P, single: null };
    single.dispatchEvent(new P.window.MouseEvent('click', { bubbles: true }));
    // 等面板里「更多词典」渲染出来
    await waitFor(function () {
      return /dl-item|dl-empty/.test(P.doc.getElementById('dp-body').innerHTML);
    });
    return { P: P, single: single };
  }

  // C1 默认：只给 漢典 + ctext；在线摘要不碰 wiktionary
  const c1 = await clickFirstSingle(false);
  ok(!!c1.single, '阅读页打标出单字 <wise> 并点开面板');
  const dpBody = c1.P.doc.getElementById('dp-body');
  const links = Array.from(dpBody.querySelectorAll('.dl-list a'));
  ok(links.length === 2, '面板「更多词典」默认 2 条（实际 ' + links.length + '）');
  ok(links.every(function (a) {
    return a.getAttribute('target') === '_blank' && /noopener/.test(a.getAttribute('rel') || '');
  }), '面板外链均新窗口打开');
  const refs1 = externalRefs(c1.P.doc).join(' ');
  HIDDEN_HOSTS.forEach(function (h) {
    ok(refs1.indexOf(h) < 0, '面板没有指向隐藏源的引用：' + h, refs1.slice(0, 120));
  });
  const apiCalls = c1.P.calls.filter(function (u) { return u.indexOf('/api/dict?') === 0; });
  ok(apiCalls.every(function (u) { return u.indexOf('source=wiktionary') < 0; }),
     '默认态绝不请求 source=wiktionary（被墙源，共 ' + apiCalls.length + ' 次请求）',
     apiCalls.join(' | '));
  ok(apiCalls.every(function (u) { return u.indexOf('/api/dict?source=') === 0; }),
     '在线请求一律走同域 /api/dict（回退链）');
  ok(externalHosts(c1.P.calls).length === 0, '阅读页没有向外站发任何请求');
  await waitFor(function () { return /已隐藏/.test(dpBody.textContent); });
  ok(/已隐藏 3 个不可用源/.test(dpBody.textContent), '面板写明「已隐藏 3 个不可用源」',
     dpBody.textContent.slice(-70));
  c1.P.dom.window.close();

  // C2 开「容错外链」→ 维基词典出现；但自动摘要仍不碰它
  const c2 = await clickFirstSingle(true);
  const links2 = Array.from(c2.P.doc.getElementById('dp-body').querySelectorAll('.dl-list a'));
  ok(links2.length === 3, '开启「容错外链」后面板 3 条（实际 ' + links2.length + '）');
  ok(c2.P.doc.getElementById('dp-body').innerHTML.indexOf('zh.wiktionary.org') >= 0,
     '面板出现中文维基词典');
  ok(c2.P.calls.some(function (u) { return u.indexOf('source=wiktionary') >= 0; }),
     '开了「容错外链」后，回退链才会请求 wiktionary（默认态绝不请求）');
  c2.P.dom.window.close();
}

/* ---------------- D. 设置页「容错外链」开关 ---------------- */
async function testSettingsPage() {
  console.log('\nD. 设置页「容错外链」');
  const P = await openPage('ai-settings.html', null, ['dict-links.js', 'dict-settings.js']);
  const cb = P.doc.getElementById('fallbackLinks');
  const list = P.doc.getElementById('dictLinksList');
  const st = P.doc.getElementById('dictLinksStatus');
  ok(!!cb && !!list, '设置页有「容错外链」复选框与源状态表');
  await waitFor(function () { return /dl-row/.test(list.innerHTML); });
  ok(!cb.checked, '默认未勾选（容错外链默认关闭）');
  const rows = list.querySelectorAll('.dl-row');
  ok(rows.length === 5, '列出白名单全部 5 个源（含隐藏的，写明原因）(' + rows.length + ')');
  const hiddenRows = Array.from(list.querySelectorAll('.dl-state-hidden'));
  ok(hiddenRows.length === 3, '3 个源标为「隐藏」（实际 ' + hiddenRows.length + '）');
  ok(/当前展示 2 个源/.test(st.textContent), '状态行：当前展示 2 个源', st.textContent);
  ok(/未备案/.test(list.textContent) && /域名/.test(list.textContent),
     '隐藏原因写清楚（未备案 / 域名失效）');

  cb.checked = true;
  cb.dispatchEvent(new P.window.Event('change', { bubbles: true }));
  await waitFor(function () { return /容错外链已开启/.test(st.textContent); });
  ok(P.window.localStorage.getItem(FALLBACK_KEY) === '1', '勾选后写入 localStorage：' + FALLBACK_KEY);
  ok(P.window.DictLinks.stateOf('wiktionary-zh') === 'fallback', '维基词典变为「容错展示」');
  ok(Array.from(list.querySelectorAll('.dl-state-hidden')).length === 2, '隐藏源从 3 个减到 2 个');
  ok(P.errors.length === 0, '设置页无 JS 运行时错误', P.errors.slice(0, 2).join(' | '));
  P.dom.window.close();
}

/* ---------------- E. 探活脚本（不联网；fetch 打桩） ---------------- */
async function testProbeScript() {
  console.log('\nE. 探活脚本（每周一次 HEAD）');
  const probe = require(path.resolve(__dirname, '..', '..', 'deploy', 'dict_links_probe.js'));
  const gx = probe.PROBED.filter(function (s) { return s.id === 'guoxuedashi'; })[0];
  const zh = probe.PROBED.filter(function (s) { return s.id === 'zhonghuadiancang'; })[0];
  const noDns = { dns: function () { return Promise.resolve(''); } };

  ok(probe.PROBED.length === 2, '只探活 2 个源（实际 ' + probe.PROBED.length + '）');
  ok(!!gx && !!zh, '探活对象是 國學大師 / 中華典藏');
  ok(probe.STATUS_FILE.indexOf(path.join('_site_data', 'dict', 'dict_links.json')) >= 0,
     '状态文件写在 _site_data/dict/dict_links.json');
  ok(gx.kind === 'keyword' && zh.kind === 'dns', '国学大师查状态码+关键字；中华典藏查解析+200');

  // 与前端白名单对齐（防两边 id 漂移）
  const DL = loadDictLinks(STATUS_DOC, false).DictLinks;
  probe.PROBED.forEach(function (s) {
    ok(DL.SOURCES.some(function (x) { return x.id === s.id; }),
       '探活源在前端白名单里存在：' + s.id);
  });

  const origFetch = globalThis.fetch;

  // E1 阿里云拦截页 → 失败
  globalThis.fetch = async function () {
    return new Response('<html>该网站未备案，已被阿里云拦截</html>', { status: 200 });
  };
  const r1 = await probe.probeOne(gx, noDns);
  ok(!r1.ok && /拦截|未备案/.test(r1.detail), '阿里云拦截页 → 探活失败', r1.detail);

  // E2 正常页（含站点关键字）→ 成功
  globalThis.fetch = async function () {
    return new Response('<html><title>國學大師 古籍字典</title>國學大師</html>', { status: 200 });
  };
  const r2 = await probe.probeOne(gx, noDns);
  ok(r2.ok, '正常页 → 探活成功', r2.detail);
  ok(r2.status === 200, '记录 HTTP 状态码（' + r2.status + '）');

  // E3 200 但没有站点关键字（跳转壳页）→ 失败
  globalThis.fetch = async function () {
    return new Response('<html><script src="/js/welcome.js"></script></html>', { status: 200 });
  };
  const r3 = await probe.probeOne(gx, noDns);
  ok(!r3.ok && /关键字/.test(r3.detail), '200 但无站点关键字 → 判失败（挡跳转壳页）', r3.detail);

  // E4 域名不可达 → 失败
  globalThis.fetch = async function () { throw new Error('getaddrinfo ENOTFOUND'); };
  const r4 = await probe.probeOne(zh, noDns);
  ok(!r4.ok && /请求失败/.test(r4.detail), '域名不可达 → 探活失败', r4.detail);

  // E5 404 → 失败
  globalThis.fetch = async function () { return new Response('', { status: 404 }); };
  const r5 = await probe.probeOne(gx, noDns);
  ok(!r5.ok && /404/.test(r5.detail), 'HTTP 404 → 探活失败', r5.detail);

  globalThis.fetch = origFetch;

  // E6 状态机：连续 2 次才翻转
  const s1 = probe.applyStreak({ state: 'hidden', streak_ok: 0, streak_fail: 1 }, { ok: true, detail: 'ok' });
  ok(s1.state === 'hidden' && s1.streak_ok === 1, '第 1 次成功：保持 hidden（观察中）');
  const s2 = probe.applyStreak(s1, { ok: true, detail: 'ok' });
  ok(s2.state === 'enabled' && s2.streak_ok === 2, '连续 2 次成功 → enabled（自动展示）');
  const f1 = probe.applyStreak(s2, { ok: false, detail: 'down' });
  ok(f1.state === 'enabled' && f1.streak_fail === 1, '失败 1 次不会立刻隐藏');
  const f2 = probe.applyStreak(f1, { ok: false, detail: 'down' });
  ok(f2.state === 'hidden' && f2.streak_fail === 2, '连续 2 次失败 → hidden');
  ok(f2.streak_ok === 0, '失败会清零成功计数');
  ok(/^\d{4}-\d{2}-\d{2}$/.test(f2.checked_at), '记录探活日期 checked_at=' + f2.checked_at);

  // E7 命令行参数
  const A = probe.parseArgs(['--dry-run', '--only', 'guoxuedashi', '--quiet']);
  ok(A.dryRun && A.only === 'guoxuedashi' && A.quiet, 'parseArgs：--dry-run / --only / --quiet');
  const B = probe.parseArgs(['--push']);
  ok(B.push && B.commit, '--push 隐含 --commit');
  ok(probe.parseArgs(['--timeout', '3']).timeout === 3000, '--timeout 秒 → 毫秒');
  ok(probe.parseArgs(['-h']).help === true, '-h / --help 可查用法');

  // E8 默认策略与状态文件一致
  ok(probe.DEFAULT_POLICY.promote_after_ok === STATUS_DOC.policy.promote_after_ok &&
     probe.DEFAULT_POLICY.demote_after_fail === STATUS_DOC.policy.demote_after_fail,
     '脚本默认策略与 dict_links.json 一致（2 次 / 2 次）');
}

/* ---------------- 主流程 ---------------- */
(async function main() {
  await testBaseline();
  await testSearchPage();
  await testReaderPage();
  await testSettingsPage();
  await testProbeScript();

  console.log('\n' + (failed.length
    ? '❌ 失败 ' + failed.length + ' 项（通过 ' + pass + '）'
    : '🎉 全部通过（' + pass + ' 项）'));
  if (failed.length) {
    failed.forEach(function (f) { console.log('   - ' + f); });
    process.exit(1);
  }
})();
