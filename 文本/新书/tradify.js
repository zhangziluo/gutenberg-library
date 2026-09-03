#!/usr/bin/env node
/* 简→繁（台湾常用）批量转换助手：fill_glosses.py 以 node 子进程调用。
   输入 stdin：JSON 数组 [{ "id": <int>, "text": "简体文本" }]
   输出 stdout：{ "<id>": "繁体文本" } */
'use strict';
const OpenCC = require('./node_modules/opencc-js/dist/umd/full.js');

let input = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', d => { input += d; });
process.stdin.on('end', () => {
  let items;
  try {
    items = JSON.parse(input);
  } catch (e) {
    process.stderr.write('bad input: ' + e.message + '\n');
    process.exit(1);
  }
  const converter = new OpenCC.Converter({ from: 'cn', to: 'tw' });
  const out = {};
  for (const it of items) {
    const t = (it.text || '').trim();
    out[it.id] = t ? converter(t) : '';
  }
  process.stdout.write(JSON.stringify(out));
});
