/* ============================================================
   一堆古书 · 公共模块
   数据目录：_site_data/
   ============================================================ */
'use strict';

const DATA_BASE = '_site_data/';

/** 加载 JSON（带错误信息） */
async function loadJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}：${url}`);
  }
  return resp.json();
}

/** 按书名加载某本书的数据 */
function loadBook(name) {
  return loadJSON(DATA_BASE + encodeURIComponent(name) + '.json');
}

/**
 * 篇目逻辑排序：按书目声明的分类顺序，分类内按编号升序；
 * 无编号的按标题排。返回新数组。
 */
function orderedSections(book) {
  const result = [];
  const catOrder = book.categories || [];
  const sections = book.sections || [];

  for (const cat of catOrder) {
    const items = sections.filter(s => s.category_label === cat);
    items.sort((a, b) => {
      const aNum = a.number, bNum = b.number;
      if (aNum != null && bNum != null) return aNum - bNum;
      if (aNum != null) return -1;
      if (bNum != null) return 1;
      return (a.title < b.title ? -1 : a.title > b.title ? 1 : 0);
    });
    result.push(...items);
  }

  // 兜底：未匹配任何分类的篇目放到最后
  const seen = new Set(result);
  for (const s of sections) {
    if (!seen.has(s)) result.push(s);
  }
  return result;
}

/** 读取 URL 查询参数 */
function getParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

/** HTML 转义 */
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

/** 分类 → 样式 key（对应 CSS 里的 cat-* 类） */
function catStyle(label) {
  const map = {
    '本紀': 'benji', '表': 'biao', '書': 'shu',
    '世家': 'shijia', '列傳': 'liezhuan',
    '紀': 'ji', '志': 'zhi', '傳': 'zhuan',
    '魏書': 'wei', '蜀書': 'shu', '吳書': 'wu'
  };
  return map[label] || 'other';
}

/** 分类徽标 HTML */
function catBadge(label) {
  if (!label) return '';
  return `<span class="cat-tag cat-${catStyle(label)}">${esc(label)}</span>`;
}

/** 把数字转成「第X」中文序数；无编号返回空串 */
function ordinal(n) {
  if (n == null) return '';
  return '第' + cnNum(n);
}

/** 下载文本文件（带 BOM，Windows 记事本可正常显示中文） */
function downloadText(filename, text) {
  const blob = new Blob(['\uFEFF' + text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
function cnNum(n) {
  if (n <= 0) return String(n);
  if (n < 10) return CN_DIGITS[n];
  if (n === 10) return '十';
  if (n < 20) return '十' + CN_DIGITS[n - 10];
  if (n < 100) {
    const tens = Math.floor(n / 10);
    const ones = n % 10;
    return CN_DIGITS[tens] + '十' + (ones ? CN_DIGITS[ones] : '');
  }
  if (n < 1000) {
    const hundreds = Math.floor(n / 100);
    const rest = n % 100;
    let s = CN_DIGITS[hundreds] + '百';
    if (rest) {
      if (rest < 10) s += CN_DIGITS[rest];
      else if (rest === 10) s += '十';
      else if (rest < 20) s += '十' + CN_DIGITS[rest - 10];
      else s += CN_DIGITS[Math.floor(rest / 10)] + '十' + (rest % 10 ? CN_DIGITS[rest % 10] : '');
    }
    return s;
  }
  return String(n);
}
