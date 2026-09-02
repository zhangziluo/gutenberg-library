#!/usr/bin/env node
/* ============================================================
   pinyin 批处理助手：供 gutenberg_import.py 以 node 子进程调用。
   输入：stdin 一个 JSON 数组（去重后的汉字/词）
   输出：stdout { "<token>": { pinyin, multiple, readings? } }
     - pinyin   : pinyin-pro 带声调拼音（单字如 guān；词如 yin yue）
     - multiple : 单字是否多音字（候补读音 > 1）
     - readings : 单字候补读音（不带声调，去重后以 / 连接）
   依赖：同目录 node_modules/pinyin-pro（npm install pinyin-pro）
   ============================================================ */
'use strict';
const { pinyin } = require('./node_modules/pinyin-pro');

let input = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', d => { input += d; });
process.stdin.on('end', () => {
  let tokens = [];
  try {
    tokens = JSON.parse(input);
  } catch (e) {
    process.stderr.write('bad input: ' + e.message + '\n');
    process.exit(1);
  }
  const out = {};
  for (const t of tokens) {
    const py = pinyin(t, { toneType: 'symbol' });
    const cands = pinyin(t, { toneType: 'none', type: 'array', multiple: true });
    // 单字：cands 为候补读音数组（如 ["le","yue","yao","lao"]）；
    // 多字：cands 为逐字最佳读音，不视为多音候选
    const isSingle = [...t].length === 1;
    const readings = Array.isArray(cands) && isSingle
      ? [...new Set(cands)].join('/')
      : '';
    out[t] = {
      pinyin: py,
      multiple: isSingle && Array.isArray(cands) && new Set(cands).size > 1,
      readings,
    };
  }
  process.stdout.write(JSON.stringify(out));
});
