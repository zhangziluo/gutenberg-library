/* 浏览器层冒烟测试（jsdom）：真实加载 reader.html + common.js + vocab-matcher.js + reader.js，
   fetch 打到本地 _site_data → 验证「渲染 → 空闲打标 → <wise> → 点击出词卡」整条链路。 */
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '../../网站');       // 网站根（项目根/网站）
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';     // jsdom：npm i --prefix <某目录> jsdom，再用环境变量指过去
const { JSDOM } = require(JSDOM_PATH);

const BOOK = process.env.BOOK || '論語';
let pass = 0; const failed = [];
function check(name, cond, detail) { if (cond) pass++; else failed.push({ name: name, detail: detail }); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

const html = fs.readFileSync(path.join(ROOT, 'reader.html'), 'utf8').replace(/<script src="https:[^"]*"><\/script>/g, '');
const dom = new JSDOM(html, {
  url: 'http://localhost/reader.html?book=' + encodeURIComponent(BOOK) + '&index=1',
  runScripts: 'dangerously',
  pretendToBeVisual: true
});
const { window } = dom;
const doc = window.document;

window.fetch = function (u) {
  const file = path.join(ROOT, '_site_data', decodeURIComponent(String(u).replace(/^_site_data\//, '')));
  return new Promise(function (res) {
    fs.readFile(file, 'utf8', function (err, data) {
      if (err) return res({ ok: false, status: 404, json: async function () { return {}; } });
      res({ ok: true, status: 200, json: async function () { return JSON.parse(data); } });
    });
  });
};
window.__errors = [];
window.addEventListener('error', e => window.__errors.push(String(e.message)));

// 以 <script> 注入（script 代码 → 顶层函数才是全局，和真浏览器一致；eval 会是局部作用域）
function inject(f) {
  const s = doc.createElement('script');
  s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
  doc.head.appendChild(s);
}
if (process.env.NO_VOCAB === '1') {                 // 健壮性：词表缺失 → 应静默降级为只用 annotations
  const s = doc.createElement('script');
  s.textContent = "window.VOCAB_FINAL_URL = '_site_data/__no_such_vocab__.json';";
  doc.head.appendChild(s);
}
if (process.env.VOCAB_WRAP) {                       // 密度开关：gloss（默认）/ all / rare
  const s = doc.createElement('script');
  s.textContent = "window.VOCAB_WRAP = '" + process.env.VOCAB_WRAP + "';";
  doc.head.appendChild(s);
}
['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js'].forEach(inject);

const book = JSON.parse(fs.readFileSync(path.join(ROOT, '_site_data', BOOK + '.json'), 'utf8'));
// reader.js 用 orderedSections 排序后才按 index 取篇 → 测试要跟着走同一条逻辑
const ordered = window.orderedSections(book);
const sec = ordered[1] || ordered[0];
const expectText = (sec.paragraphs || []).join('');
const expectTitle = sec.title;

(async function run() {
  let wise = [];
  for (let i = 0; i < 200; i++) {
    wise = doc.querySelectorAll('wise');
    if (wise.length > 0) break;
    await sleep(50);
  }
  // 等打标彻底跑完（<wise> 计数连续 3 次不变才算稳定，避免读到中途状态）
  let prev = -1, stable = 0;
  for (let i = 0; i < 60; i++) {
    const n = doc.querySelectorAll('wise').length;
    stable = (n > 0 && n === prev) ? stable + 1 : 0;
    if (stable >= 3) break;
    prev = n;
    await sleep(250);
  }

  wise = Array.from(doc.querySelectorAll('wise'));   // 打标完成后重新取快照（querySelectorAll 是静态列表）
  console.log('页面标题：' + doc.title);
  console.log('篇目：' + doc.querySelector('.reader-title').textContent + ' ｜ 段落 ' +
    doc.querySelectorAll('#reader-body p').length + ' ｜ <wise> ' + wise.length);

  check('篇目标题正确', doc.querySelector('.reader-title').textContent === expectTitle,
    doc.querySelector('.reader-title').textContent);
  check('打标完成（<wise> > 0）', wise.length > 0, wise.length);
  check('正文文本逐字一致（复制/下载/划选不受影响）',
    doc.getElementById('reader-body').textContent === expectText,
    doc.getElementById('reader-body').textContent.slice(0, 60));

  let badAttr = 0, noClass = 0, badLang = 0, multiChar = 0;
  Array.from(wise).forEach(function (el) {
    const w = el.getAttribute('data-word'), k = el.getAttribute('data-key'), l = el.getAttribute('data-lang');
    if (!w || !k || !l) badAttr++;
    if (!/ann-word/.test(el.className)) noClass++;
    if (l !== 'zh' && l !== 'en') badLang++;
    if (w.length > 1) multiChar++;
    if (el.textContent !== w) badAttr++;
  });
  check('每个 <wise> 都有 data-word/data-key/data-lang 且文本=完整词形', badAttr === 0, badAttr);
  check('保留 ann-word 类名（旧 CSS/点击逻辑兼容）', noClass === 0, noClass);
  check('data-lang 合法', badLang === 0, badLang);
  if (process.env.NO_VOCAB === '1') {
    check('词表缺失时降级为纯 annotations（仍能打标，只是没有多字词）', wise.length > 0, wise.length);
  } else {
    check('存在多字词级命中（非全单字散列）', multiChar > 0, multiChar);
  }

  const trie = window.VocabMatcher.build(book.annotations || [], { mode: 'all' }).trie;
  let fragmented = 0; const fragments = [];
  Array.from(wise).forEach(function (el) {
    const w = el.getAttribute('data-word');
    if (w.length !== 1) return;
    const p = el.parentNode;
    if (!p) return;
    const text = p.textContent;
    const at = text.indexOf(w);
    if (at < 0) return;
    for (let len = 4; len >= 2; len--) {
      const cand = text.substr(at, len);
      const t = trie.longest(cand, 0, len);
      if (cand.length === len && t && t.len === len) {
        fragmented++; fragments.push(cand + '（却只标了 ' + w + '）');
        break;
      }
    }
  });
  console.log('单字散列可疑片段：' + (fragments.slice(0, 4).join(' / ') || '无'));
  check('无「更长词表词被拆成单字」的情况', fragmented === 0, fragments.slice(0, 5));

  const target = Array.from(wise).filter(el => el.getAttribute('data-lang') === 'zh')[0] || wise[0];
  target.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(30);
  const pop = doc.querySelector('.ann-pop');
  const headWord = pop.querySelector('.ann-pop-head b').textContent;
  console.log('点击 ' + target.getAttribute('data-word') + ' → 词卡标题：' + headWord
    + ' ｜ 正文：' + pop.querySelector('.ann-pop-body').textContent.slice(0, 40));
  check('点击后词卡弹出', pop.classList.contains('show'), pop.className);
  check('词卡标题 = 完整词形（未截断）', headWord === target.getAttribute('data-word'), headWord);

  doc.querySelector('.level-btn[data-level="expert"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(1500);
  const wiseExpert = doc.querySelectorAll('wise').length;
  console.log('切「专家」档后 <wise> ' + wiseExpert + '（新手档 ' + wise.length + '）');
  check('换档后重新打标且数量更少/相等', wiseExpert > 0 && wiseExpert <= wise.length, [wiseExpert, wise.length]);
  check('换档后正文仍逐字一致', doc.getElementById('reader-body').textContent === expectText, null);

  doc.querySelector('.textmode-btn[data-mode="toSimple"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(1500);
  check('简繁切换后正文仍完整', doc.getElementById('reader-body').textContent === expectText, null);
  check('无未捕获脚本错误', window.__errors.length === 0, window.__errors);

  console.log('\n浏览器冒烟测试：通过 ' + pass + ' ｜ 失败 ' + failed.length);
  if (failed.length) { console.log(JSON.stringify(failed, null, 1)); process.exit(1); }
  process.exit(0);
})();
