/* ============================================================
   书库页「待入库」预览 · 本地冒烟测试（jsdom）
   ------------------------------------------------------------
   跑法（仓库无根 package.json，jsdom 装在 /tmp）：
     npm i --prefix /tmp/vmtest jsdom
     JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/library-pending-test.js
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');

const JSDOM_PATH = process.env.JSDOM_PATH || '/tmp/vmtest/node_modules/jsdom';
const { JSDOM } = require(JSDOM_PATH);

const ROOT = path.resolve(__dirname, '..', '..');
const SITE = path.join(ROOT, '网站');

let pass = 0;
let fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✅ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

const HTML = `<!DOCTYPE html><html><body>
  <p class="lib-sub" id="lib-sub"></p>
  <div class="lib-mode" id="lib-mode">
    <button class="lib-mode-btn is-active" type="button" data-mode="shelf">本站藏书</button>
    <button class="lib-mode-btn" type="button" data-mode="pending">待入库</button>
  </div>
  <div class="lib-toolbar">
    <div class="lib-tabs" id="lib-tabs"></div>
    <label id="lib-reconly-wrap" hidden><input type="checkbox" id="lib-reconly" checked></label>
    <select id="lib-sort"><option value="hot" selected>热门</option>
      <option value="title">书名</option></select>
    <input id="lib-search-input">
  </div>
  <div class="lib-grid" id="lib-grid"></div>
  <nav id="lib-pagination" hidden></nav>
  <div id="lib-error" hidden></div>
</body></html>`;

const dom = new JSDOM(HTML, {
  runScripts: 'dangerously',
  url: 'https://example.test/library.html',
  pretendToBeVisual: true,
});

const { window } = dom;

// 用文件系统冒充 fetch（数据源都在 网站/ 下）
window.fetch = async (url) => {
  const rel = String(url).replace(/^\.?\//, '');
  const p = path.join(SITE, rel.split('?')[0]);
  if (!fs.existsSync(p)) {
    return { ok: false, status: 404, json: async () => ({}) };
  }
  const text = fs.readFileSync(p, 'utf8');
  return { ok: true, status: 200, json: async () => JSON.parse(text) };
};
window.scrollTo = () => {};
window.history.replaceState = () => {};

// 剪贴板桩：navigator.clipboard 优先，退化到 execCommand
let copiedText = null;
try {
  Object.defineProperty(window.navigator, 'clipboard', {
    configurable: true,
    value: { writeText: (t) => { copiedText = t; return Promise.resolve(); } },
  });
} catch (e) {
  window.document.execCommand = () => true;
}

// 以 <script> 注入（保证是全局作用域；用 eval 会被文件里的 'use strict' 困在局部）
for (const f of ['js/common.js', 'js/library.js']) {
  const el = window.document.createElement('script');
  el.textContent = fs.readFileSync(path.join(SITE, f), 'utf8');
  window.document.head.appendChild(el);
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  await sleep(400);                       // 等 init() 完成
  const $ = (s) => window.document.querySelector(s);
  const cards = () => window.document.querySelectorAll('#lib-grid .book-card');

  ok(cards().length > 0, '本站藏书模式渲染出卡片（' + cards().length + '）');
  ok(window.document.querySelectorAll('.lib-tab').length === 6, '分类页签 6 个（全部+五部）');
  ok($('#lib-reconly-wrap').hidden === true, '藏书模式下「只看推荐」隐藏');

  // 切到「待入库」
  const btn = window.document.querySelector('.lib-mode-btn[data-mode="pending"]');
  btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await sleep(500);

  const pc = cards();
  ok(pc.length > 0, '待入库模式渲染出卡片（' + pc.length + '）');
  ok(pc.length <= 20, '待入库分页生效（每页 ≤20）');
  ok($('#lib-reconly-wrap').hidden === false, '待入库模式显示「只看推荐」');
  ok(btn.classList.contains('is-active'), '模式按钮高亮已切换');

  const first = pc[0].querySelector('.card-main') || pc[0];
  const href = first.getAttribute('href') || '';
  ok(href.indexOf('zh.wikisource.org') !== -1, '卡片链接指向维基文库：' + href.slice(0, 48));
  ok(pc[0].classList.contains('is-pending'), '卡片带 is-pending 样式类');

  // 「复制入库命令」按钮
  const cmdBtn = pc[0].querySelector('.card-cmd');
  ok(!!cmdBtn, '待入库卡片带「复制入库命令」按钮');
  ok(cmdBtn && cmdBtn.dataset.cmd.indexOf('wikisource_batch.py') !== -1,
     '命令内容含 wikisource_batch.py');
  ok(cmdBtn && cmdBtn.dataset.cmd.indexOf('ingest') !== -1,
     '命令同时包含 ingest（入库 + 释义回填）');
  if (cmdBtn) {
    cmdBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await sleep(80);
    ok(copiedText && copiedText.indexOf('wikisource_batch.py') !== -1,
       '点击后复制到剪贴板：' + String(copiedText).slice(0, 40) + '…');
    ok(cmdBtn.textContent.indexOf('已复制') !== -1, '按钮反馈「已复制」');
  }

  // 关掉「只看推荐」→ 数量应变多
  const rec = $('#lib-reconly');
  rec.checked = false;
  rec.dispatchEvent(new window.Event('change', { bubbles: true }));
  await sleep(200);
  const all = cards();
  ok($('#lib-sub').textContent.indexOf('只看推荐') === -1, '取消推荐过滤后提示文案更新');

  // 排序切「书名」不应报错
  const sort = $('#lib-sort');
  sort.value = 'title';
  sort.dispatchEvent(new window.Event('change', { bubbles: true }));
  await sleep(150);
  ok(cards().length > 0, '按书名排序后仍有卡片');

  ok($('#lib-error').hidden === true, '无错误提示');

  console.log('\n结果：' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => {
  console.error('测试异常：', e);
  process.exit(2);
});
