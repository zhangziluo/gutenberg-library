/* 集成测试：用真实书 JSON + 真实 vocab_final.json 走一遍 reader.js 的接线逻辑
   （annotations 补简体形 → 建词表 → 在「原文 / 繁→简」两种显示模式的正文上打标） */
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '../..');           // 项目根
const VM_PATH = path.join(ROOT, '网站/js/vocab-matcher.js');
const SITE_PATH = path.join(ROOT, '网站/_site_data/');
const OPENCC_PATH = path.join(ROOT, '文本/新书/node_modules/opencc-js');
const VM = require(VM_PATH);
const SITE = SITE_PATH;
const OpenCC = require(OPENCC_PATH);

let pass = 0; const failed = [];
function check(name, cond, detail) { if (cond) pass++; else failed.push({ name: name, detail: detail }); }
const tw2cn = OpenCC.Converter({ from: 'tw', to: 'cn' });

/** 复刻 reader.js：annotations 单字键补简体形（opencc 兜底） */
function annEntriesForMatcher(annList) {
  return annList.map(a => {
    if (!a || !a.word || a.simp || /[A-Za-z]/.test(a.word)) return a;
    let s = '';
    try { s = tw2cn(a.word) || ''; } catch (e) { s = ''; }
    return (s && s !== a.word) ? Object.assign({}, a, { simp: s }) : a;
  });
}
function loadBook(name) { return JSON.parse(fs.readFileSync(SITE + name + '.json', 'utf8')); }
function parasOf(book, maxSections) {
  const out = [];
  (book.sections || []).slice(0, maxSections || 1e9).forEach(s => (s.paragraphs || []).forEach(p => out.push(p)));
  return out;
}
const vocab = JSON.parse(fs.readFileSync(SITE + 'vocab_final.json', 'utf8'));

/* ---------- A. 中文书（論語）原文 / 繁→简 两种显示模式 ---------- */
(function zhongwen() {
  const book = loadBook('論語');
  const paras = parasOf(book);
  const m = VM.build(annEntriesForMatcher(book.annotations || []).concat(vocab.zh), { mode: 'gloss' });

  function scan(texts, label) {
    let hits = 0, single = 0, multi = 0, noGloss = 0, bad = 0, covered = 0, total = 0;
    const samples = [];
    texts.forEach(t => {
      total += t.length;
      const segs = m.plan(t, { mode: 'gloss' });
      let re = '';
      segs.forEach(sg => {
        re += sg.word || sg.text;
        if (sg.word) {
          hits++; covered += sg.word.length;
          if (sg.word.length === 1) single++; else multi++;
          if (!VM.isGloss(sg.entry) && !(sg.parts && sg.parts.length)) noGloss++;
          if (samples.length < 5 && sg.word.length > 1) samples.push(sg.word + '=' + sg.key);
        }
      });
      if (re !== t) bad++;
    });
    console.log('  [' + label + '] 命中 ' + hits + '（多字词 ' + multi + ' / 单字 ' + single + '）｜ 无释义又无成分字 '
      + noGloss + ' ｜ 重建失败 ' + bad + ' ｜ 覆盖 ' + (covered / total * 100).toFixed(1) + '% ｜ 例：' + samples.join(' '));
    return { hits: hits, multi: multi, single: single, noGloss: noGloss, bad: bad };
  }

  console.log('A. 論語（繁体原文 + 繁→简显示）');
  const r1 = scan(paras, '原文');
  const r2 = scan(paras.map(p => tw2cn(p)), '繁→简');
  check('原文命中 > 0', r1.hits > 0, r1);
  check('原文：多字词命中 > 0（词级成段）', r1.multi > 0, r1);
  check('原文：无「既不释义也无成分字」的空标注', r1.noGloss === 0, r1);
  check('原文：逐段重建无失败', r1.bad === 0, r1);
  check('繁→简：命中数量与原文相当（简体键生效）', r2.hits >= r1.hits * 0.9, [r1.hits, r2.hits]);
  check('繁→简：重建无失败', r2.bad === 0, r2);
  check('繁→简：多字词仍成段', r2.multi > 0, r2);

  const hits = m.plan('不亦樂乎，君子務本', { mode: 'gloss' }).filter(s => s.word).map(s => s.word);
  check('定点：不亦樂乎 整词成段（非单字散列）', hits.indexOf('不亦樂乎') >= 0, hits);
  check('定点：君子務本 无释义 → 不散成单字（不标/整词标，绝无 君、子 单字）',
    hits.indexOf('君') < 0 && hits.indexOf('子') < 0, hits);
  // 論語 真实案例：`人不知` 无整词释义，但成分字「不」有释义；词表行若已回填 definition（definition_fill.py），
  // 则整词自带释义 → 两种情况下都必须整词一个 <wise>，而不是只标中间的「不」→「中文不再被单字切分」的核心效果。
  const renSegs = m.plan('人不知而不慍', { mode: 'gloss' }).filter(s => s.word);
  check('定点：人不知 整词成段（带 parts 或 definition）',
    renSegs.length > 0 && renSegs[0].word === '人不知'
    && (!!renSegs[0].parts || VM.hasDef(renSegs[0].entry)), renSegs.map(s => s.word));
  check('定点：人不知 的词内不再单独出现「不」',
    m.plan('人不知而不慍', { mode: 'gloss' }).filter(s => s.word).indexOf('不') < 0,
    m.plan('人不知而不慍', { mode: 'gloss' }).filter(s => s.word).map(s => s.word));
  const singleHits = m.plan('君子不器', { mode: 'gloss' }).filter(s => s.word).map(s => s.word);
  check('定点：君子不器 → 只留真注释字「不」，无 君 / 子 散列',
    singleHits.indexOf('君') < 0 && singleHits.indexOf('子') < 0 && singleHits.indexOf('不') >= 0, singleHits);

  /* D. 词表内嵌释义（definition / need_ai，由 文本/新书/definition_fill.py 回填） */
  const annWords = {};
  (book.annotations || []).forEach(a => { if (a && a.word) annWords[a.word] = 1; });
  const rows6 = (vocab.zh || []).filter(r => Array.isArray(r) && r.length === 6);
  const withDef = rows6.filter(r => VM.hasDef({ definition: r[4] }));
  const tbd = rows6.filter(r => r[4] === '待补');
  console.log('D. 词表内嵌释义：6 元行 ' + rows6.length + ' / ' + (vocab.zh || []).length
    + ' ｜ 有释义 ' + withDef.length + ' ｜ 待补 ' + tbd.length
    + ' ｜ need_ai ' + rows6.filter(r => r[5] === true).length);
  check('词表行已是 6 元（definition + need_ai）', rows6.length === (vocab.zh || []).length, rows6.length);
  check('待补行不计入 isGloss（不给无释义词打标）',
    tbd.every(r => !VM.isGloss({ definition: r[4] })) && withDef.length > 0, [withDef.length, tbd.length]);
  const rowWithDef = withDef.filter(r => !annWords[r[0]])[0];
  check('词表 definition/need_ai 进入匹配条目（读真实 vocab_final.json）', (function () {
    if (!rowWithDef) return false;
    const e = m.lookup(rowWithDef[0]);
    return !!e && e.definition === rowWithDef[4] && e.need_ai === !!rowWithDef[5] && VM.isGloss(e);
  })(), rowWithDef);
})();

/* ---------- B. 英文书（Walden / Dracula）整词匹配 ---------- */
(function yingwen() {
  ['Walden', 'Dracula'].forEach(function (name) {
    const book = loadBook(name);
    const paras = parasOf(book, 12);
    const m = VM.build(book.annotations || [], { mode: 'gloss' });
    let hits = 0, badBound = 0, badKey = 0, noGloss = 0, bad = 0;
    const samples = [], apos = [];
    paras.forEach(t => {
      const segs = m.plan(t, { mode: 'gloss' });
      let re = '', at = 0;
      segs.forEach(sg => {
        const surf = sg.word || sg.text;
        re += surf;
        if (sg.word) {
          hits++;
          const before = at > 0 ? t.charAt(at - 1) : '';
          const after = at + surf.length < t.length ? t.charAt(at + surf.length) : '';
          if (VM.isLatin(before) || VM.isLatin(after)) badBound++;
          const norm = VM.normalizeEn(surf);
          if (norm !== sg.key && norm.replace(/[']+$/, '') !== sg.key && norm.replace(/'s$/, '') !== sg.key) badKey++;
          if (!VM.isGloss(sg.entry)) noGloss++;
          if (samples.length < 4) samples.push(surf);
          if (/['\u2019]/.test(surf)) apos.push(surf);
        }
        at += surf.length;
      });
      if (re !== t) bad++;
    });
    console.log('B. ' + name + '：命中 ' + hits + ' ｜ 边界违例 ' + badBound + ' ｜ 键不符 ' + badKey
      + ' ｜ 无释义 ' + noGloss + ' ｜ 重建失败 ' + bad + ' ｜ 例：' + samples.join(', ')
      + (apos.length ? ' ｜ 撇号词：' + apos.slice(0, 6).join(', ') : ''));
    check(name + '：命中 > 0', hits > 0, hits);
    check(name + '：英文命中均为最大词形（前后不接拉丁字母）', badBound === 0, badBound);
    check(name + '：命中键与词形一致（大小写/撇号归一）', badKey === 0, badKey);
    check(name + '：逐段重建无失败', bad === 0, bad);
  });
})();

/* ---------- C. 缩写/所有格定点（旧 bug 现场） ---------- */
(function fixed() {
  const books = ['Walden', 'Dracula'].map(loadBook);
  const m = VM.build([].concat(books[0].annotations || [], books[1].annotations || []), { mode: 'gloss' });
  const s = "Mornin' he said, an' I don't know; Lear's daughter.";
  const got = m.plan(s, { mode: 'gloss' }).filter(x => x.word).map(x => ({ w: x.word, k: x.key }));
  console.log('C. 缩写定点："Mornin\' he said, an\' I don\'t know; Lear\'s daughter."');
  console.log('   → ' + JSON.stringify(got));
  // 所有命中都必须是「完整词形」：不得只覆盖词的一部分（新算法由词形边界保证）
  got.forEach(function (h) {
    const at = s.indexOf(h.w);
    check('定点：' + h.w + ' 为完整词形（前后非拉丁字母）',
      !VM.isLatin(s.charAt(at - 1)) && !VM.isLatin(s.charAt(at + h.w.length)), h);
  });
  const words = got.map(x => x.w);
  const badTrunc = words.filter(function (w) {
    return s.indexOf(w + "'") >= 0 || (s.indexOf(w) >= 0 && VM.isLatin(s.charAt(s.indexOf(w) + w.length)));
  });
  check('定点：无「截断成字母组合」的命中（如 mornin ← mornin\'）', badTrunc.length === 0, badTrunc);
})();

console.log('\n集成测试：通过 ' + pass + ' ｜ 失败 ' + failed.length);
if (failed.length) { console.log(JSON.stringify(failed, null, 1)); process.exit(1); }
