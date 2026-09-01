/* ============================================================
   今日一句 · 全站句子池
   - 每日 localStorage 缓存键 daily_sentence_YYYY-MM-DD，命中直接渲染
   - 未命中：fetch manifest → djb2(日期) 选分类 → fetch 分类文件
     → 同一哈希取模选句 → 存入 localStorage
   - 「換一句」：从已加载分类文件纯随机选另一条
   - 降级：分类加载失败 fallback 另一分类；manifest 失败显示「今日暂无推荐」
   ============================================================ */
'use strict';

(function () {
  var MANIFEST_URL = '/library/sentence-manifest.json';
  var SENT_URL = '/library/sentences/';
  var CACHE_PREFIX = 'daily_sentence_';

  // 本地日期 YYYY-MM-DD（每日一换以本地天为准）
  var d = new Date();
  var dateStr = d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');

  var catData = null;   // 当前分类已加载的句子数组（供換一句）

  function $(id) { return document.getElementById(id); }

  // djb2 哈希（32 位无符号）
  function djb2(str) {
    var h = 5381;
    for (var i = 0; i < str.length; i++) {
      h = ((h << 5) + h) + str.charCodeAt(i);
      h = h | 0;
    }
    return h >>> 0;
  }

  function render(rec) {
    if (!rec || !rec.text) return;
    $('daily-text').textContent = rec.text;
    var src = rec.book || '';
    if (rec.chapter && rec.chapter !== rec.book) src += ' · ' + rec.chapter;
    $('daily-source').textContent = '—— ' + src;
    $('daily-loading').hidden = true;
    $('daily-empty').hidden = true;
    $('daily-content').hidden = false;
  }

  function showEmpty() {
    $('daily-loading').hidden = true;
    $('daily-content').hidden = true;
    $('daily-empty').hidden = false;
  }

  async function loadCat(cat) {
    var resp = await fetch(SENT_URL + encodeURIComponent(cat) + '.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var arr = await resp.json();
    if (!Array.isArray(arr) || !arr.length) throw new Error('empty');
    return arr;
  }

  // 确保 catData 已加载（manifest 选分类 → 拉取；失败按序 fallback 另一分类）
  async function ensureCatData() {
    if (catData && catData.length) return;
    var hash = djb2(dateStr);
    var manifest;
    try {
      manifest = await (await fetch(MANIFEST_URL)).json();
    } catch (e) {
      throw new Error('manifest');
    }
    var cats = (manifest.categories || []).filter(function (c) { return c.count > 0; });
    if (!cats.length) throw new Error('no cats');
    var tries = 0;
    while (tries < cats.length) {
      var cat = cats[(hash + tries) % cats.length];
      try {
        catData = await loadCat(cat.category);
        return;
      } catch (e) {
        tries++;   // fallback 到另一分类
      }
    }
    throw new Error('no cat data');
  }

  function init() {
    // 1) localStorage 命中直接渲染
    var cached = null;
    try { cached = JSON.parse(localStorage.getItem(CACHE_PREFIX + dateStr)); } catch (e) { /* 忽略 */ }
    if (cached && cached.text) {
      render(cached);
      // 后台预载分类数据，供「換一句」使用
      ensureCatData().catch(function () { /* 忽略 */ });
      return;
    }
    // 2) 未命中：按日期哈希选分类选句
    ensureCatData().then(function () {
      var rec = catData[djb2(dateStr) % catData.length];
      if (!rec) { showEmpty(); return; }
      try { localStorage.setItem(CACHE_PREFIX + dateStr, JSON.stringify(rec)); } catch (e) { /* 忽略 */ }
      render(rec);
    }).catch(function () {
      showEmpty();   // manifest 失败 → 今日暂无推荐
    });
  }

  // 換一句：从已加载分类纯随机选另一条
  function doShuffle() {
    if (!catData || !catData.length) return;
    var cur = $('daily-text').textContent;
    var idx = Math.floor(Math.random() * catData.length);
    var guard = 0;
    while (catData[idx] && catData[idx].text === cur && guard++ < catData.length) {
      idx = (idx + 1) % catData.length;
    }
    if (catData[idx]) render(catData[idx]);
  }

  var shuffleBtn = $('daily-shuffle');
  if (shuffleBtn) {
    shuffleBtn.addEventListener('click', function () {
      if (catData && catData.length) { doShuffle(); }
      else { ensureCatData().then(doShuffle).catch(function () { /* 忽略 */ }); }
    });
  }

  init();
})();
