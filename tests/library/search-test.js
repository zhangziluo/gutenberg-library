/* ============================================================
   检索页 search.html · 测试（索引数据 + 端到端 jsdom）
   ------------------------------------------------------------
   跑法：JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/search-test.js
   验证：
     A. 索引数据：meta/titles/snap 三者一致；每个 gIdx 恰好一片；篇序与阅读页一致
     B. 检索页端到端：
        ① 目录层：书名 + 篇目标题命中，链接带正确的 ?book= &index=
        ② 快照层：正文关键词命中 → 定位到篇（含片段高亮）
        ③ 离线查词：康熙 + CC-CEDICT 真实分片命中
        ④ 第三方词典：5 家外链（含维基词典），全部 target=_blank rel=noopener
        ⑤ 无命中 / 无查询不报错
     C. 首页搜索回车 → /search.html?q=…（触发导航）
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '../../网站');
const SD = path.join(ROOT, '_site_data');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 把 URL 映射到 网站/ 下的真实文件（模拟静态托管） */
function serve(url) {
  const clean = decodeURIComponent(String(url).split('?')[0]);
  const file = path.join(ROOT, clean);
  return new Promise(function (res) {
    fs.readFile(file, 'utf8', function (err, data) {
      if (err) return res({ ok: false, status: 404, json: async () => ({}) });
      return res({ ok: true, status: 200, json: async () => JSON.parse(data) });
    });
  });
}

function cleanText(t) {
  return String(t == null ? '' : t).replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, '')
    .replace(/[ \t\u3000\xa0]+/g, ' ').trim();
}

/* ---------------- A. 索引数据 ---------------- */
function testIndexData() {
  console.log('\nA. 索引数据一致性');
  const idx = path.join(SD, 'search');
  const meta = JSON.parse(fs.readFileSync(path.join(idx, 'meta.json'), 'utf8'));
  const titles = JSON.parse(fs.readFileSync(path.join(idx, 'titles.json'), 'utf8'));

  ok(meta.snap_shards > 0, 'meta.snap_shards 有效（' + meta.snap_shards + '）');
  ok(meta.books === titles.books.length, 'meta.books 与 titles.books 一致（' + meta.books + '）');
  ok(meta.sections === titles.sections.length, 'meta.sections 与 titles.sections 一致（' + meta.sections + '）');
  ok(titles.books.length > 100, '书目数量合理（' + titles.books.length + '）');

  // 每本书的篇数与 sections 索引一致
  const counts = {};
  titles.sections.forEach(function (s) { counts[s[0]] = (counts[s[0]] || 0) + 1; });
  const mismatch = titles.books.filter(function (b, i) { return (counts[i] || 0) !== b.n; });
  ok(mismatch.length === 0, '每本书篇数与索引一致',
    mismatch.length ? mismatch.slice(0, 3).map(b => b.t).join('、') : '');

  // 快照：覆盖完整、不重复、与 titles 对应
  const seen = new Set();
  let dup = 0, bad = 0, emptySnap = 0;
  for (let n = 0; n < meta.snap_shards; n++) {
    const rows = JSON.parse(fs.readFileSync(path.join(idx, 'snap', n + '.json'), 'utf8'));
    for (const r of rows) {
      if (seen.has(r[0])) dup++;
      seen.add(r[0]);
      const s = titles.sections[r[0]];
      if (!s || s[0] !== r[1] || s[1] !== r[2]) bad++;
      if (!r[3]) emptySnap++;
    }
  }
  ok(dup === 0, '快照无重复篇目', 'dup=' + dup);
  ok(bad === 0, '快照 gIdx ↔ (书, 篇) 一一对应', 'bad=' + bad);
  ok(seen.size === titles.sections.length, '全部篇目都有快照（' + seen.size + '/' + titles.sections.length + '）');
  ok(emptySnap === 0, '没有空快照', 'empty=' + emptySnap);

  // 与阅读页同序：抽 3 本，比对 common.js orderedSections 的篇目序列
  const ctx = { window: { location: { search: '' } }, document: {}, console: console };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'js', 'common.js'), 'utf8'), ctx);
  const ordered = ctx.orderedSections;
  ok(typeof ordered === 'function', 'common.js orderedSections 可复用');

  const sample = ['論語', '三國志', '永樂大典'].filter(function (t) {
    return titles.books.some(function (b) { return b.t === t; });
  });
  let seqBad = [];
  sample.forEach(function (t) {
    const bi = titles.books.findIndex(function (b) { return b.t === t; });
    const raw = JSON.parse(fs.readFileSync(path.join(SD, t + '.json'), 'utf8'));
    let secs = raw.sections || [];
    if (raw.sharded) {   // 分片书：按序拼回
      secs = [];
      for (let k = 0; ; k++) {
        const p = path.join(SD, t, k + '.json');
        if (!fs.existsSync(p)) break;

        secs = secs.concat(JSON.parse(fs.readFileSync(p, 'utf8')).sections || []);
      }
    }
    const expect = ordered({ categories: raw.categories || [], sections: secs })
      .map(function (s) { return cleanText(s.title); });
    const actual = titles.sections.filter(function (s) { return s[0] === bi; })
      .map(function (s) { return s[2]; });
    const same = expect.length === actual.length &&
      expect.every(function (x, i) { return x === actual[i]; });
    if (!same) seqBad.push(t + '(' + expect.length + ' vs ' + actual.length + ')');
  });
  ok(sample.length >= 2 && seqBad.length === 0, '篇目顺序与阅读页 orderedSections 一致（样本 ' + sample.join('、') + '）',
    seqBad.join('、'));
  return meta;
}

/* ---------------- B. 检索页端到端 ---------------- */
async function openPage(q, scripts) {
  const { JSDOM, VirtualConsole } = require(JSDOM_PATH);
  const vc = new VirtualConsole();
  const errors = [];
  vc.on('jsdomError', function (e) { errors.push(e.message || String(e)); });
  const html = fs.readFileSync(path.join(ROOT, 'search.html'), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const url = 'http://localhost/search.html' + (q == null ? '' : '?q=' + encodeURIComponent(q));
  const dom = new JSDOM(html, {
    url: url, runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
  });
  const window = dom.window, doc = window.document, calls = [];
  window.fetch = function (u) { calls.push(String(u)); return serve(u); };
  (scripts || ['common.js', 'dict-lookup.js', 'search.js']).forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });
  return { window: window, doc: doc, calls: calls, errors: errors, dom: dom };
}

async function waitFor(fn, tries) {
  for (let i = 0; i < (tries || 400); i++) { if (fn()) return true; await sleep(20); }
  return false;
}

/** href → { book, index } */
function parseReaderLink(href) {
  const u = new URL(href, 'http://localhost/');
  return { book: u.searchParams.get('book'), index: parseInt(u.searchParams.get('index'), 10) };
}

/** common.js 的 orderedSections（与阅读页同序） */
let orderedFn = null;
function loadOrdered() {
  if (!orderedFn) {
    const ctx = { window: { location: { search: '' } }, document: {}, console: console };
    vm.createContext(ctx);
    vm.runInContext(fs.readFileSync(path.join(ROOT, 'js', 'common.js'), 'utf8'), ctx);
    orderedFn = ctx.orderedSections;
  }
  return orderedFn;
}

/** 读某书 sections（分片书按序拼回） */
function readSections(title) {
  const raw = JSON.parse(fs.readFileSync(path.join(SD, title + '.json'), 'utf8'));
  let secs = raw.sections || [];
  if (raw.sharded) {
    secs = [];
    for (let k = 0; ; k++) {
      const p = path.join(SD, title, k + '.json');
      if (!fs.existsSync(p)) break;
      secs = secs.concat(JSON.parse(fs.readFileSync(p, 'utf8')).sections || []);
    }
  }
  return { raw: raw, secs: secs };
}


async function testPage(titles) {
  console.log('\nB. 检索页端到端');

  // ① 目录层：书名命中
  const P1 = await openPage('論語');
  await waitFor(function () { return P1.doc.getElementById('titles-count').textContent !== ''; });
  const tb1 = P1.doc.getElementById('titles-body').innerHTML;
  ok(!P1.doc.getElementById('block-titles').hidden, '书名命中时「书目·篇目」区块可见');
  ok(tb1.indexOf('book.html?book=' + encodeURIComponent('論語')) >= 0, '书名命中 → book.html?book=論語');
  ok(P1.doc.getElementById('titles-count').textContent !== '（无）',
    '书名命中计数=' + P1.doc.getElementById('titles-count').textContent);

  // ② 目录层：篇目标题命中 → 阅读页（并回查该 index 确实是这一篇）
  const P2 = await openPage('學而');
  await waitFor(function () { return P2.doc.getElementById('titles-count').textContent !== ''; });
  const a2 = Array.from(P2.doc.querySelectorAll('#titles-body a')).filter(function (a) {
    return /reader\.html/.test(a.getAttribute('href') || '');
  })[0];
  ok(!!a2, '篇目标题命中 → 阅读页链接');
  if (a2) {
    const r2 = parseReaderLink(a2.getAttribute('href'));
    const bi = titles.books.findIndex(function (b) { return b.t === r2.book; });
    const s = titles.sections.find(function (x) { return x[0] === bi && x[1] === r2.index; });
    ok(!!s && s[2].indexOf('學而') >= 0,
      '篇目链接回查正确（' + r2.book + ' #' + r2.index + ' = ' + (s ? s[2] : '?') + '）');
  }

  // ③ 快照层：正文关键词 → 篇
  const P3 = await openPage('子曰');
  const textDone = await waitFor(function () {
    return /已扫描/.test(P3.doc.getElementById('text-progress').textContent);
  }, 1500);
  ok(textDone, '快照层扫描完成（' + P3.doc.getElementById('text-progress').textContent + '）');
  ok(/<mark>子曰<\/mark>/.test(P3.doc.getElementById('text-body').innerHTML), '正文命中带 <mark> 高亮片段');
  const a3 = P3.doc.querySelector('#text-body a');
  ok(!!a3, '正文命中 → 阅读页链接');
  if (a3) {
    const r3 = parseReaderLink(a3.getAttribute('href'));
    const bs = readSections(r3.book);
    const sec = loadOrdered()({ categories: bs.raw.categories || [], sections: bs.secs })[r3.index] || {};
    const text = cleanText((sec.paragraphs || []).join(''));
    const snap = text.length <= 240 ? text : text.slice(0, 180) + ' … ' + text.slice(-60);
    ok(snap.indexOf('子曰') >= 0, '首条正文命中的篇确实含关键词（' + r3.book + ' #' + r3.index +
      '「' + cleanText(sec.title) + '」）');
  }
  ok(P3.doc.getElementById('text-count').textContent !== '（无）',
    '正文命中计数=' + P3.doc.getElementById('text-count').textContent);

  // ④ 离线查词 + 第三方词典
  const P4 = await openPage('仁');
  await waitFor(function () {
    return /康熙字典|未收录|读取失败/.test(P4.doc.getElementById('dict-body').innerHTML);
  }, 800);
  const db = P4.doc.getElementById('dict-body').innerHTML;
  ok(db.indexOf('康熙字典') >= 0, '离线查词：康熙字典命中「仁」');
  ok(db.indexOf('CC-CEDICT') >= 0, '离线查词：CC-CEDICT 命中「仁」');
  const kangxiCalls = P4.calls.filter(function (u) { return /dict\/kangxi\/\d+\.json/.test(u); });
  ok(kangxiCalls.length === 1, '康熙按分片取（只 1 片，不整包）', kangxiCalls.join('|'));
  ok(P4.calls.length > 0 && P4.calls.every(function (u) { return /^_site_data\//.test(u); }),
    '查词只请求同域 _site_data，不直连第三方');

  const wants = ['zdic.net/hans/', 'ctext.org/search.pl', 'zh.wiktionary.org/wiki/',
    'guoxuedashi.net', 'zhonghuadiancang.com'];
  const third = P4.doc.getElementById('third-body').innerHTML;
  wants.forEach(function (h) { ok(third.indexOf(h) >= 0, '第三方链接包含 ' + h); });
  const anchors = Array.from(P4.doc.querySelectorAll('#third-body a'));
  ok(anchors.length === 5, '第三方链接共 5 条（实际 ' + anchors.length + '）');
  ok(anchors.every(function (a) {
    return a.getAttribute('target') === '_blank' && /noopener/.test(a.getAttribute('rel') || '');
  }), '第三方链接均 target=_blank rel=noopener');
  ok(anchors.some(function (a) { return /仁/.test(decodeURIComponent(a.getAttribute('href'))); }),
    '第三方链接带上查询词');

  // 返回引用，供调用方关闭
  return [P1, P2, P3, P4];
}

/* ---------------- B2. 边界：无命中 / 无查询 ---------------- */
async function testEdge() {
  console.log('\nB2. 边界情况');

  const P5 = await openPage('zzzqqq');
  await waitFor(function () { return /已扫描/.test(P5.doc.getElementById('text-progress').textContent); }, 1500);
  ok(/没有命中/.test(P5.doc.getElementById('text-body').innerHTML), '正文无命中时给出说明');
  ok(P5.errors.length === 0, '检索无 JS 运行时错误', P5.errors.slice(0, 2).join(' | '));
  P5.dom.window.close();

  const P6 = await openPage(null);
  await sleep(400);
  ok(P6.doc.getElementById('block-titles').hidden && P6.doc.getElementById('block-dict').hidden &&
     P6.doc.getElementById('block-text').hidden, '无 ?q= 时结果区块全部隐藏');
  ok(P6.errors.length === 0, '无 ?q= 时不报错', P6.errors.slice(0, 2).join(' | '));
  P6.dom.window.close();
}

/* ---------------- C. 首页搜索 → 检索页 ---------------- */
async function testHomeSearch() {
  console.log('\nC. 首页搜索回车 → 检索页');

  const src = fs.readFileSync(path.join(ROOT, 'js', 'home-search.js'), 'utf8');
  ok(/location\.href = '\/search\.html\?q=' \+ encodeURIComponent\(q\)/.test(src),
    '回车跳转目标为 /search.html?q=…');
  ok((src.match(/e\.key === 'Enter'/g) || []).length === 2, '桌面 + 移动端都绑定了 Enter');
  ok(/class="s-more"/.test(src), '下拉里有「全站检索」入口');

  // 部署：search.html 必须进 dist（漏了会 404）
  const build = fs.readFileSync(path.join(__dirname, '..', '..', 'deploy', 'build.sh'), 'utf8');
  ok(/search\.html/.test(build), 'deploy/build.sh 会部署 search.html');

  const { JSDOM, VirtualConsole } = require(JSDOM_PATH);
  const vc = new VirtualConsole();
  const errors = [];
  vc.on('jsdomError', function (e) { errors.push(e.message || String(e)); });
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: 'http://localhost/index.html', runScripts: 'dangerously',
    pretendToBeVisual: true, virtualConsole: vc,
  });
  const doc = dom.window.document;
  dom.window.fetch = function () {
    return Promise.resolve({ ok: true, status: 200, json: async () => ({ books: [] }) });
  };
  ['common.js', 'home-search.js'].forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });
  const input = doc.getElementById('search-input');
  ok(!!input, '首页搜索框存在');
  if (input) {
    input.value = '論語';
    input.dispatchEvent(new dom.window.KeyboardEvent('keydown',
      { key: 'Enter', bubbles: true, cancelable: true }));
    await sleep(150);
    ok(errors.some(function (m) { return /navigation/i.test(m); }), '回车触发了整页跳转');
  }
  dom.window.close();
}

/* ---------------- 主流程 ---------------- */
(async function main() {
  const meta = testIndexData();
  const titles = JSON.parse(fs.readFileSync(path.join(SD, 'search', 'titles.json'), 'utf8'));
  const pages = await testPage(titles);
  pages.forEach(function (p) { p.dom.window.close(); });
  await testEdge();
  await testHomeSearch();

  console.log('\n' + (failed.length
    ? '❌ 失败 ' + failed.length + ' 项（通过 ' + pass + '）'
    : '🎉 全部通过（' + pass + ' 项）'));
  if (failed.length) {
    failed.forEach(function (f) { console.log('   - ' + f); });
    process.exit(1);
  }
})();

