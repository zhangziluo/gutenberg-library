/* 定点：验证 reader.js 词卡走「词表行 definition」兜底（vocab-matcher 的 definition → 词卡正文 + AI 待補 标签）
   只为覆盖 definition_fill.py 回填后的展示链路，跑法与 reader-smoke-test.js 相同。 */
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '../../网站');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';
const { JSDOM } = require(JSDOM_PATH);

const BOOK = process.env.BOOK || '論語';
let pass = 0; const failed = [];
function check(name, cond, detail) { if (cond) pass++; else failed.push({ name: name, detail: detail }); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

const html = fs.readFileSync(path.join(ROOT, 'reader.html'), 'utf8').replace(/<script src="https:[^"]*"><\/script>/g, '');
const dom = new JSDOM(html, {
  url: 'http://localhost/reader.html?book=' + encodeURIComponent(BOOK) + '&index=1',
  runScripts: 'dangerously', pretendToBeVisual: true
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
function inject(f) {
  const s = doc.createElement('script');
  s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
  doc.head.appendChild(s);
}
['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js'].forEach(inject);

const book = JSON.parse(fs.readFileSync(path.join(ROOT, '_site_data', BOOK + '.json'), 'utf8'));
const vocab = JSON.parse(fs.readFileSync(path.join(ROOT, '_site_data', 'vocab_final.json'), 'utf8'));
const defByKey = {};                       // 词表键 → 已回填的释义（占位「待补」不算）
const tbdByKey = {};
(vocab.zh || []).forEach(function (r) {
  if (!Array.isArray(r) || r.length !== 6) return;
  if (r[4] && r[4] !== '待补') defByKey[r[0]] = r[4];
  else if (r[4] === '待补') tbdByKey[r[0]] = 1;
});
const annKeys = {};                        // 本书注释（有 zh_cn 的词卡不看 definition）
(book.annotations || []).forEach(function (a) { if (a && a.word) annKeys[a.word] = 1; });

(async function run() {
  let wise = [];
  for (let i = 0; i < 200; i++) {
    wise = Array.from(doc.querySelectorAll('wise'));
    if (wise.length > 0) break;
    await sleep(50);
  }
  let prev = -1, stable = 0;
  for (let i = 0; i < 60; i++) {
    const n = doc.querySelectorAll('wise').length;
    stable = (n > 0 && n === prev) ? stable + 1 : 0;
    if (stable >= 3) break;
    prev = n; await sleep(250);
  }
  wise = Array.from(doc.querySelectorAll('wise'));

  // 只在词表里（本书无注释）、且释义由 definition_fill.py 回填的多字词
  const defs = wise.filter(function (el) {
    const k = el.getAttribute('data-key');
    return k && k.length > 1 && defByKey[k] && !annKeys[k] && !annKeys[el.getAttribute('data-word')];
  });
  const tbdHits = wise.filter(function (el) { return tbdByKey[el.getAttribute('data-key')]; });
  console.log('内嵌释义命中 ' + defs.length + '（例：' + defs.slice(0, 4).map(e => e.getAttribute('data-word')).join(', ')
    + '）｜ 待补词被误标 ' + tbdHits.length);
  check('词表 definition 使词表词可标（存在此类 <wise>）', defs.length > 0, defs.length);
  check('仅「待补」的词在 gloss 模式不被打标', tbdHits.length === 0, tbdHits.map(e => e.getAttribute('data-word')).slice(0, 5));

  const t = defs[0];
  if (t) {
    const key = t.getAttribute('data-key');
    t.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await sleep(50);
    const pop = doc.querySelector('.ann-pop');
    const body = pop.querySelector('.ann-pop-body').textContent;
    const tag = pop.querySelector('.ann-pop-tag');
    console.log('点击 ' + t.getAttribute('data-word') + ' → 词卡正文：' + body.slice(0, 46)
      + ' ｜ 标签：' + (tag ? tag.textContent : '（无）'));
    check('词卡正文 = 词表行 definition（无注释也无拼音时兜底）', body === defByKey[key], [body, defByKey[key]]);
    check('词卡标题仍为完整词形', pop.querySelector('.ann-pop-head b').textContent === t.getAttribute('data-word'), null);
    check('need_ai → 词卡标「AI 待補」', !!tag && tag.textContent === 'AI 待補', tag ? tag.textContent : null);
  }
  check('无未捕获脚本错误', window.__errors.length === 0, window.__errors);

  console.log('\n词表释义展示测试：通过 ' + pass + ' ｜ 失败 ' + failed.length);
  if (failed.length) { console.log(JSON.stringify(failed, null, 1)); process.exit(1); }
  process.exit(0);
})();
