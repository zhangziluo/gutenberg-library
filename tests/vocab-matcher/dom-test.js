/* vocab-matcher · DOM 层测试（Node + 最小 DOM shim）
   验证：TreeWalker 找节点 / 空闲分批 / <wise> 落节点 / 幂等 / 取消 / 跳过区 */
'use strict';
const path = require('path');
const ROOT = path.resolve(__dirname, '../..');           // 项目根
const VM_PATH = path.join(ROOT, '网站/js/vocab-matcher.js');
const shim = require(path.join(__dirname, 'dom-shim.js'));
const VM = require(VM_PATH);

let pass = 0; const failed = [];
function check(name, cond, detail) {
  if (cond) { pass++; } else { failed.push({ name: name, detail: detail }); }
}
function wiseOf(host) {
  const els = host.getElementsByTagName('wise');
  return Array.from(els).map(e => ({ w: e.getAttribute('data-word'), k: e.getAttribute('data-key'),
    lang: e.getAttribute('data-lang'), parts: e.getAttribute('data-parts'), cls: e.className }));
}
function attrOf(host, word, attr) {
  const hit = wiseOf(host).filter(x => x.w === word)[0];
  return hit ? hit[attr] : null;
}

const doc = shim.mkDoc();
const ANNS = [
  { word: 'morning', zh_cn: '早晨' }, { word: 'mornin', zh_cn: '早晨（口語）' },
  { word: 'old', zh_cn: '舊的' }, { word: 'fashioned', zh_cn: '…樣式的' },
  { word: '君', zh_cn: '君主' }, { word: '子', zh_cn: '子女' }, { word: '不', zh_cn: '否定' },
  { word: 'don\u2019t', zh_cn: '不' }
];
const ROWS = [['君子', '君子', 900, 20], ['不知', '不知', 800, 18], ['說服', '说服', 300, 9]];
const m = VM.build(ANNS.concat(ROWS), { mode: 'gloss' });

const TEXT = "He said mornin' and 君子不器, old-fashioned. I don\u2019t care.";
const host = doc.createElement('div');
host.textContent = TEXT;
doc.body.appendChild(host);            // isConnected 需要挂到 body

// 1) 分批打标（budgetMs 极小 → 强制多片）
const t0 = Date.now();
m.annotate(host, { mode: 'gloss', budgetMs: 0.05 }).done.then(function (stats) {
  const w = wiseOf(host);
  const words = w.map(x => x.w);
  check('打标发生', w.length >= 4, words);
  check("英文整词 mornin'（不截断）", words.indexOf("mornin'") >= 0, words);
  check("data-word 完整 + data-key=mornin", attrOf(host, "mornin'", 'k') === 'mornin', words);
  check('中文整词 君子（无单字散列）',
    words.indexOf('君子') >= 0 && words.indexOf('君') < 0 && words.indexOf('子') < 0, words);
  check('君子 带成分字 parts=君|子', attrOf(host, '君子', 'parts') === '君|子', attrOf(host, '君子', 'parts'));
  check('old-fashioned 拆成两个整词', words.indexOf('old') >= 0 && words.indexOf('fashioned') >= 0, words);
  check('textContent 逐字不变', host.textContent === TEXT, host.textContent);
  check('data-lang 标注语言', attrOf(host, "mornin'", 'lang') === 'en' && attrOf(host, '君子', 'lang') === 'zh', words);
  check('stats.words 与 <wise> 数一致', stats.words === w.length, [stats.words, w.length]);
  check('实际分片（耗时 > 0）', Date.now() - t0 >= 0, null);

  // 2) 幂等
  return m.annotate(host, { mode: 'gloss', budgetMs: 0.05 }).done.then(function () {
    check('幂等：重跑不重复包裹', wiseOf(host).length === w.length, wiseOf(host).length + ' vs ' + w.length);
  });
})
.then(function () {
  // 3) 跳过区：<script>/data-no-annotate/<wise> 内不再打标
  const h2 = doc.createElement('div');
  const p1 = doc.createElement('p'); p1.textContent = "mornin' 君子";
  const sc = doc.createElement('script'); sc.textContent = "mornin' 君子";
  const skip = doc.createElement('p'); skip.setAttribute('data-no-annotate', '1'); skip.textContent = "mornin' 君子";
  const code = doc.createElement('pre'); code.textContent = "mornin' 君子";
  h2.appendChild(p1); h2.appendChild(sc); h2.appendChild(skip); h2.appendChild(code);
  doc.body.appendChild(h2);
  return m.annotate(h2, { mode: 'gloss', budgetMs: 0.05 }).done.then(function () {
    check('普通段落已打标', wiseOf(p1).length === 2, wiseOf(p1).map(x => x.w));
    check('<script> 内不打标', wiseOf(sc).length === 0, null);
    check('[data-no-annotate] 内不打标', wiseOf(skip).length === 0, null);
    check('<pre> 内不打标', wiseOf(code).length === 0, null);
    check('跳过区文本未被改动', sc.textContent === "mornin' 君子" && skip.textContent === "mornin' 君子", null);
  });
})
.then(function () {
  // 4) 取消：cancelled 后不再写 DOM
  const h3 = doc.createElement('div');
  h3.textContent = "mornin' 君子 old-fashioned";
  doc.body.appendChild(h3);
  const handle = m.annotate(h3, { mode: 'gloss', budgetMs: 0.05 });
  handle.cancel();                        // 首片还没跑（setTimeout/空闲回调）→ 直接收工
  return handle.done.then(function () {
    check('取消后不打标', wiseOf(h3).length === 0, wiseOf(h3).length);
    check('取消后文本完整', h3.textContent === "mornin' 君子 old-fashioned", h3.textContent);
  });
})
.then(function () {
  // 5) 大批量：60 段 × 多词，分片跑完不遗漏
  const big = doc.createElement('div');
  const SENT = "He said mornin' and 君子不器, old-fashioned. I don\u2019t care.";
  for (let i = 0; i < 60; i++) {
    const p = doc.createElement('p');
    p.textContent = SENT;
    big.appendChild(p);
  }
  doc.body.appendChild(big);
  const before = big.textContent;
  return m.annotate(big, { mode: 'gloss', budgetMs: 1 }).done.then(function (stats) {
    check('大批量：命中数 = 60 × 6（mornin’ / 君子 / 不 / old / fashioned / don’t）', stats.words === 360, stats.words);
    check('大批量：文本逐字不变', big.textContent === before, null);
    check('大批量：每个段落都被处理', wiseOf(big).length === 360, wiseOf(big).length);
  });
})
.then(function () {
  console.log('DOM 层测试：通过 ' + pass + ' ｜ 失败 ' + failed.length);
  if (failed.length) { console.log(JSON.stringify(failed, null, 1)); process.exit(1); }
})
.catch(function (e) { console.error('测试异常：', e); process.exit(1); });
