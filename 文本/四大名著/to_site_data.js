#!/usr/bin/env node
/* ============================================================
   四大名著 JSON（parse_novels.py 产出）→ 站点书目数据
   1. 输出 文本/_site_data/{书名}.json（与史記.json 同构，供 book.html / reader.html 加载）
   2. 更新 文本/_site_data/books.json（追加四本，置于 三國志 之后）
   注意：在 export_json.py + 古文觀止/to_site_data.js 之后运行
   ============================================================ */
'use strict';
const fs = require('fs');
const path = require('path');

const BASE = __dirname;                                  // 文本/四大名著
const DATA_DIR = path.join(BASE, '..', '_site_data');
const BOOKS_PATH = path.join(DATA_DIR, 'books.json');

const NOVELS = [
  { key: 'sanguo-yanyi', title: '三國演義', author: '羅貫中',
    intro: '中国古典四大名著之一：从桃园三结义到三分归晋，一部波澜壮阔的英雄史诗。' },
  { key: 'shuihu-zhuan', title: '水滸傳', author: '施耐庵',
    intro: '中国古典四大名著之一：一百零八好汉聚义梁山，替天行道，快意恩仇。' },
  { key: 'xiyou-ji', title: '西遊記', author: '吳承恩',
    intro: '中国古典四大名著之一：唐僧师徒西天取经，历经九九八十一难的魔幻长篇。' },
  { key: 'honglou-meng', title: '紅樓夢', author: '曹雪芹',
    intro: '中国古典四大名著之首：以"一把辛酸泪"，写尽贾府兴衰与宝黛情缘。' },
];

// 与 export_json.py 相同的分段逻辑：按空行分段，连续非空行合并；剥离全角空格缩进
// 对超长段落（如紅樓夢程乙本连排无空行）再按句末标点拆成自然段
function splitParagraphs(text) {
  const paras = [];
  let cur = [];
  for (const line of String(text).split(/\r?\n/)) {
    const s = line.trim();
    if (!s) {
      if (cur.length) { paras.push(cur.join('')); cur = []; }
    } else {
      cur.push(s);
    }
  }
  if (cur.length) paras.push(cur.join(''));

  // 超长段 → 按句末标点拆分
  const MAX = 1000;
  const SENT = /[。．！？；]/;
  const out = [];
  for (const p of paras) {
    if (p.length <= MAX) { out.push(p); continue; }
    let buf = '';
    for (const ch of p) {
      buf += ch;
      if (buf.length >= MAX && SENT.test(ch)) { out.push(buf); buf = ''; }
    }
    if (buf.trim()) out.push(buf);
  }
  return out.filter(p => p.length > 1);
}

function buildBook(novel) {
  const raw = JSON.parse(fs.readFileSync(path.join(BASE, novel.key + '.json'), 'utf8'));
  const chapters = raw.chapters || [];
  const sections = chapters.map((c, i) => {
    const paras = splitParagraphs(c.content || '');
    return {
      book: novel.title,
      title: (c.title || '').trim(),
      category: 'other',
      category_label: '回目',
      number: i + 1,
      paragraphs: paras,
      char_count: paras.join('').length,
      para_count: paras.length
    };
  });
  return {
    title: novel.title,
    author: novel.author,
    intro: novel.intro,
    section_count: sections.length,
    categories: ['回目'],
    sections
  };
}

// ---- 写单书文件 + 更新 books.json ----
const books = JSON.parse(fs.readFileSync(BOOKS_PATH, 'utf8'));
for (const novel of NOVELS) {
  const book = buildBook(novel);
  fs.writeFileSync(path.join(DATA_DIR, novel.title + '.json'), JSON.stringify(book, null, 2), 'utf8');
  books[novel.title] = book;
  console.log(`已输出：${novel.title}.json（${book.section_count} 回，${book.sections.reduce((n, s) => n + s.char_count, 0).toLocaleString()} 字）`);
}
fs.writeFileSync(BOOKS_PATH, JSON.stringify(books, null, 2), 'utf8');
console.log('已更新书架，书目顺序 =', Object.keys(books).join(' → '));
