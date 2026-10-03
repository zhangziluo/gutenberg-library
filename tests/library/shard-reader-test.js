/* ============================================================
   超大字书分片 · 前端读取测试（jsdom）
   ------------------------------------------------------------
   跑法：JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/shard-reader-test.js
   背景：Cloudflare Pages 单文件 ≤ 25 MiB，永樂大典等大部头改为
         `_site_data/{书名}.json`（目录+注释）+ `_site_data/{书名}/{k}.json`（正文分片）。
   验证：
     1) 阅读页读取分片书的第 N 篇时，只请求对应分片文件
     2) 正文渲染出段落（不是空壳）
     3) 篇目总数/标题正确
     4) 书页（book.html）篇目列表也能用轻主文件渲染
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '../../网站');
const JSDOM_PATH = process.env.JSDOM_PATH || 'jsdom';
const { JSDOM } = require(JSDOM_PATH);
const BOOK = process.env.BOOK || '永樂大典';

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

function makeDom(page, query) {
  const html = fs.readFileSync(path.join(ROOT, page), 'utf8')
    .replace(/<script src="https:[^"]*"><\/script>/g, '');
  const dom = new JSDOM(html, {
    url: 'http://localhost/' + page + (query || ''),
    runScripts: 'dangerously', pretendToBeVisual: true,
  });
  const { window } = dom;
  const calls = [];
  window.fetch = function (u) {
    const url = String(u);
    calls.push(url);
    const file = path.join(ROOT, '_site_data',
      decodeURIComponent(url.replace(/^_site_data\//, '')));
    return new Promise(function (res) {
      fs.readFile(file, 'utf8', function (err, data) {
        if (err) return res({ ok: false, status: 404, json: async () => ({}) });
        return res({ ok: true, status: 200, json: async () => JSON.parse(data) });
      });
    });
  };
  window.__errors = [];
  window.addEventListener('error', e => window.__errors.push(String(e.message)));
  return { dom, window, doc: window.document, calls };
}

function inject(doc, files) {
  files.forEach(function (f) {
    const s = doc.createElement('script');
    s.textContent = fs.readFileSync(path.join(ROOT, 'js', f), 'utf8');
    doc.head.appendChild(s);
  });
}

(async function main() {
  // 主文件确认是分片形态
  const main = JSON.parse(fs.readFileSync(path.join(ROOT, '_site_data', BOOK + '.json'), 'utf8'));
  ok(main.sharded === true && main.part_size > 0,
     '主文件标记分片（part_size=' + main.part_size + '，共 ' + main.section_count + ' 篇）');
  ok((main.sections || []).length === main.section_count, '主文件仍带全部篇目（用于目录/计数）');
  ok((main.sections || []).every(s => !(s.paragraphs || []).length),
     '主文件的篇目**不含** paragraphs（正文已挪进分片）',
     '首条段落数=' + ((main.sections[0] || {}).paragraphs || []).length);

  const pad = ': ' + 'X'.repeat(0); void pad;
  const INDEX = Math.min(100, (main.section_count || 1) - 1);
  const part = Math.floor(INDEX / main.part_size);

  const env = makeDom('reader.html',
    '?book=' + encodeURIComponent(BOOK) + '&index=' + INDEX);
  inject(env.doc, ['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js']);

  // 等正文渲染
  let body = '';
  for (let i = 0; i < 120; i++) {
    body = (env.doc.getElementById('reader-body') || {}).textContent || '';
    if (body.length > 200) break;
    await sleep(50);
  }

  const partUrl = '_site_data/' + BOOK + '/' + part + '.json';
  ok(env.calls.some(u => decodeURIComponent(u).indexOf(partUrl) !== -1),
     '按需请求了正文分片 ' + partUrl, env.calls.filter(u => u.indexOf('/') > -1).slice(-3).join(' | '));
  ok(body.length > 200, '正文渲染出段落（' + body.length + ' 字）', body.slice(0, 60));
  ok(env.window.__errors.length === 0, '无 JS 报错', env.window.__errors.join(' / '));

  // 翻到另一个分片，确认换片也正常
  const far = Math.min(INDEX + main.part_size * 2, main.section_count - 1);
  const env2 = makeDom('reader.html',
    '?book=' + encodeURIComponent(BOOK) + '&index=' + far);
  inject(env2.doc, ['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js']);
  let body2 = '';
  for (let i = 0; i < 120; i++) {
    body2 = (env2.doc.getElementById('reader-body') || {}).textContent || '';
    if (body2.length > 200) break;
    await sleep(50);
  }
  ok(body2.length > 200, '跨分片（第 ' + far + ' 篇）也能渲染（' + body2.length + ' 字）');
  ok(body2 !== body, '不同篇目内容不同（未串片）');

  // 锚点定位：分片书主文件带 anchors（每篇首个有内容段落的前 60 字）→ ?anchor= 也能直达
  const partData = JSON.parse(fs.readFileSync(
    path.join(ROOT, '_site_data', BOOK, part + '.json'), 'utf8'));
  const local = INDEX - part * main.part_size;
  const target = partData.sections[local];
  const clean = p => String(p || '').replace(/[\u200b-\u200f\u2060\ufeff]/g, '').trim();
  const head = (target.paragraphs || []).map(clean).filter(p => p.length >= 4)[0] || '';
  const anchorText = head.slice(0, 24);
  ok(anchorText.length >= 6, '取出该篇锚点文本：' + anchorText);
  ok((main.anchors || []).some(h => h && h.indexOf(anchorText) >= 0),
     '主文件 anchors 表里能找到该锚点');

  const envA = makeDom('reader.html',
    '?book=' + encodeURIComponent(BOOK) + '&anchor=' + encodeURIComponent(anchorText));
  inject(envA.doc, ['common.js', 'vocab-matcher.js', 'annotation-lang.js', 'reader.js']);
  let titleA = '';
  for (let i = 0; i < 120; i++) {
    const t = envA.doc.querySelector('.reader-title');
    titleA = t ? t.textContent : '';
    if (titleA) break;
    await sleep(50);
  }
  ok(titleA === target.title,
     '?anchor= 在分片书里定位到正确篇目（' + titleA + '）', target.title);

  // 书页：轻主文件也应能列出篇目
  const env3 = makeDom('book.html', '?book=' + encodeURIComponent(BOOK));
  inject(env3.doc, ['common.js', 'book.js']);
  let stat = '';
  for (let i = 0; i < 120; i++) {
    stat = (env3.doc.getElementById('stat') || {}).textContent || '';
    if (stat) break;
    await sleep(50);
  }
  ok(/共\s*\d+\s*篇/.test(stat), '书页显示篇数：' + stat.trim(), stat);

  console.log('\n结果：' + pass + ' 通过 / ' + failed.length + ' 失败');
  if (failed.length) failed.forEach(f => console.log('   ✗ ' + f));
  process.exit(failed.length ? 1 : 0);
})().catch(e => {
  console.error('测试异常：', e);
  process.exit(2);
});
