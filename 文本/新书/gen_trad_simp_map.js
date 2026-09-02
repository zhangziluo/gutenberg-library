#!/usr/bin/env node
/* 生成 trad_simp_map.json：扫描 文本/新书/raw/*.txt 的全部汉字，
   用 opencc-js(繁→简) 映射，仅保留「简 ≠ 繁」的字。
   用法：node gen_trad_simp_map.js   （依赖同目录 node_modules/opencc-js）
   产出：文本/新书/trad_simp_map.json（供 gutenberg_import.py 常用字判定去繁体化） */
'use strict';
const fs = require('fs');
const path = require('path');
const { Converter } = require('opencc-js');

const DIR = __dirname;
const RAW = path.join(DIR, 'raw');
const OUT = path.join(DIR, 'trad_simp_map.json');

const cjk = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const seen = new Set();
for (const f of fs.readdirSync(RAW)) {
  if (!f.endsWith('.txt')) continue;
  let text = '';
  try { text = fs.readFileSync(path.join(RAW, f), 'utf-8'); } catch (e) { continue; }
  for (const ch of text) if (cjk.test(ch)) seen.add(ch);
}
const conv = Converter({ from: 'tw', to: 'cn' });
const map = {};
for (const ch of seen) {
  const s = conv(ch);
  if (s && s !== ch) map[ch] = s;
}
fs.writeFileSync(OUT, JSON.stringify(map), 'utf-8');
console.log('raw 汉字集:', seen.size, '| 繁→简不同:', Object.keys(map).length, '→', OUT);
