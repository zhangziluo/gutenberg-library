#!/usr/bin/env node
/* ============================================================
   将 gwz_full.json（222 篇）转换为站点书目数据：
   1. 输出 文本/_site_data/古文觀止.json —— 与史記.json 同构，
      供 book.html / reader.html 按「书」加载（书目页 + 逐篇阅读页）。
   2. 更新 文本/_site_data/books.json —— 首页书架数据，
      《古文觀止》置于首位（其余书目原样保留）。
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');

const GWZ_DIR = __dirname;                       // 文本/古文觀止
const FULL_IN = path.join(GWZ_DIR, 'gwz_full.json');
const DATA_DIR = path.join(GWZ_DIR, '..', '_site_data');
const BOOK_OUT = path.join(DATA_DIR, '古文觀止.json');
const BOOKS_OUT = path.join(DATA_DIR, 'books.json');

// ---- 读取全量篇章 ----
const chapters = JSON.parse(fs.readFileSync(FULL_IN, 'utf8'));
if (!Array.isArray(chapters) || !chapters.length) {
  console.error('gwz_full.json 为空或格式错误');
  process.exit(1);
}

// ---- 卷目录：按原书顺序（卷一..卷十二，仅保留实际有篇目的卷） ----
const VOLUMES = ['卷一', '卷二', '卷三', '卷四', '卷五', '卷六',
                 '卷七', '卷八', '卷九', '卷十', '卷十一', '卷十二'];

const volCount = {};
const sections = chapters.map(c => {
  const paragraphs = String(c.content || '')
    .split(/\r?\n/)
    .map(p => p.trim())
    .filter(Boolean);
  if (!paragraphs.length) console.warn('空正文，跳过：', c.title, c.source);
  volCount[c.volume] = (volCount[c.volume] || 0) + 1;
  return {
    book: '古文觀止',
    title: String(c.title || '').trim(),
    source: String(c.source || '').trim(),
    category: 'other',
    category_label: c.volume,
    number: volCount[c.volume],               // 卷内篇次：卷一 1..18、卷二 1..16 …
    paragraphs,
    char_count: paragraphs.join('').length,
    para_count: paragraphs.length
  };
});

const gwz = {
  title: '古文觀止',
  section_count: sections.length,
  categories: VOLUMES.filter(v => volCount[v]),
  sections
};

// ---- 输出单书文件 ----
fs.mkdirSync(DATA_DIR, { recursive: true });
fs.writeFileSync(BOOK_OUT, JSON.stringify(gwz, null, 2), 'utf8');
console.log('已输出单书：', BOOK_OUT, `(${gwz.section_count} 篇)`);

// ---- 更新 books.json（首页书架）：《古文觀止》置于首位 ----
const books = JSON.parse(fs.readFileSync(BOOKS_OUT, 'utf8'));
const rest = {};
for (const key of Object.keys(books)) {
  if (key !== '古文觀止') rest[key] = books[key];
}
const next = { '古文觀止': gwz, ...rest };
fs.writeFileSync(BOOKS_OUT, JSON.stringify(next, null, 2), 'utf8');
console.log('已更新书架：', BOOKS_OUT, '书目顺序 =', Object.keys(next).join(' → '));

// ---- 校验摘要 ----
console.log('---- 卷分布 ----');
for (const v of gwz.categories) {
  const n = gwz.sections.filter(s => s.category_label === v).length;
  console.log(`  ${v}: ${n} 篇`);
}
