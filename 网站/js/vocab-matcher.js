/* ============================================================
   一堆古书 · 词汇匹配与动态标注（vocab-matcher）
   ------------------------------------------------------------
   替换 reader.js 旧的「按字符索引 + 定长滑动」匹配（会把英文截断成字母组合，
   把中文词按单字打散）。本模块做三件事：

     ① 词形切分
        · 英文：正则**整词**匹配（词形前后边界锚定），绝不吐字母残片
          —— `mornin'` 取整词 `mornin'`（旧实现只取到 `mornin`）；
        · 中文：预生成词汇表（vocab_final.json）建 **Trie**，最长前缀匹配（Max Match）。
     ② 打标：命中词整体包裹为 <wise data-word="完整词形" data-key="词典键">…
        同段文字永远优先最长词（不知 > 不 + 知），词内不再散成单字。
     ③ 性能：TreeWalker 收集文本节点 → requestIdleCallback 分批写 DOM（每片约 6 ms），
        重渲染/切档即时取消；只替换「确有命中」的文本节点，移动端不被过度拆分。

   硬保证（VocabMatcher.selftest() 逐条断言）
     · 分段拼回 == 原文本（textContent 不变 → 复制/下载/划选/AI 全不受影响）
     · 英文命中必须「最大词形」：前后紧邻不再是拉丁字母（截断必被抓出）
     · 中文命中必须落在同一 CJK 连续段内（不跨标点粘连）
     · 命中只来自词表；词内不再产生单字散列打标
     · 重叠永远取最长

   数据契约（两种来源都吃，可混用）
     · 词表（vocab_final.json，可选）
         { "words": [["君子","君子",8478,43], …] } ｜ { "zh": [[…]], "en": [[…]] } ｜ [[…]]
         行 = [词形, 简体形(可空), 全库词次, 出现书数, definition, need_ai]（4 元行仍兼容）
           definition : 释义字符串（由 文本/新书/definition_fill.py 回填）；占位「待补」= 尚未查到
           need_ai    : true = 释义缺失或仅为逐字合成，待 AI 精修（只作提示，不影响匹配）
     · 释义表（书的 annotations）
         [{ word, pinyin, zh_cn, zh_tw, en, note, is_difficult, multi, rare, src }, …]

   用法
     const m = VocabMatcher.build(annList.concat(vocabRows), { mode: 'gloss' });
     const h = m.annotate(readerBody, { mode: 'gloss', allow: e => … });   // 空闲分批
     await h.done;            // 打标完成（重渲染前调 m.cancel() 即可取消）
     m.lookup(key)            // 词条（已合并词表频次与释义）
     m.plan(text, opts)       // 纯函数：文本 → 分段计划（Node 里可直接自测）
   ============================================================ */
'use strict';

(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module && module.exports) module.exports = api;   // Node（自检/单测）
  if (!root) return;
  root.VocabMatcher = api;                                                             // 浏览器
  // 自检入口：reader.html?vmselftest=1 → 控制台打印（纯函数 + DOM 两套），结果挂 window.__vmSelftest
  if (root.location && /[?&]vmselftest=1/.test(root.location.search) && root.console) {
    function log(label, r) {
      var ok = !r.fail;
      (root.console[ok ? 'log' : 'error'] || root.console.log)(
        '[vocab-matcher] ' + label + ' ' + (ok ? 'OK' : 'FAIL') +
        ' ｜ 通过 ' + r.pass + ' ｜ 失败 ' + r.fail, r.failed || '');
    }
    var pure = api.selftest();
    root.__vmSelftest = { pure: pure };
    log('selftest(纯函数)', pure);
    api.domSelftest().then(function (r) {
      root.__vmSelftest.dom = r;
      log('selftest(DOM)', r);
    });
  }
})(typeof window !== 'undefined' ? window
  : (typeof globalThis !== 'undefined' ? globalThis : null), function () {

  /* ---------- 常量：与 文本/新书/vocab_extract.py 的词形定义严格对齐 ---------- */

  // 拉丁字母（含变音符：quâ / nè / ḥū）；与 Python 侧 unicodedata L* 生成的集合等价（略多 2 个符号，无碍）
  var LATIN = 'A-Za-z\\u00c0-\\u024f\\u0250-\\u02af\\u1e00-\\u1eff\\u2c60-\\u2c7f\\ua720-\\ua7ff\\ufb00-\\ufb06';
  // CJK 统一表意文字（BMP）：扩展 A + 基本区 + 兼容区（与 Python CJK_PAT 一致）
  var CJK = '\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff';
  var APOS = '\\u0027\\u2019\\u02bc';                 // 撇号：' ’ ʼ
  var HYPH = '\\u002d\\u2010\\u2011';                 // 连字符：- ‐ ‑  （破折号 — – 不并入词内）
  var JOIN = APOS + HYPH;                             // 词内连接符类
  var CJK_CHAR_RE = new RegExp('[' + CJK + ']');
  var LATIN_CHAR_RE = new RegExp('[' + LATIN + ']');
  // 英文词单元：字母串 + 词内连接符；**允许词尾省略撇号**（mornin' / somethin'）→ 整词不截断
  var EN_UNIT_SRC = '[' + LATIN + ']+(?:[' + JOIN + '][' + LATIN + ']+)*[' + APOS + ']?';
  var RE_EN_UNIT = new RegExp(EN_UNIT_SRC, 'g');
  var RE_EN_PIECE = new RegExp('[' + LATIN + ']+', 'g');   // 连字符/撇号拆段用（保偏移）
  var RE_TAIL_APOS = new RegExp('[' + APOS + ']+$');
  var RE_POSSESSIVE = new RegExp('[' + APOS + ']s$');

  var SHOW_TEXT = 4;                 // NodeFilter.SHOW_TEXT
  var FILTER_ACCEPT = 1, FILTER_REJECT = 2;
  // 默认跳过（不在这类节点里打标）
  var SKIP_SELECTOR = 'wise, script, style, code, pre, kbd, samp, textarea, [data-no-annotate], .no-annotate';

  /* ---------- 归一化 ---------- */

  /** 英文归一：小写 + 弯撇号→直撇号 + 真连字符→ASCII '-'（与 Python normalize_en 一致） */
  function normalizeEn(s) {
    return String(s).toLowerCase()
      .replace(/[\u2019\u02bc]/g, "'")
      .replace(/[\u2010\u2011]/g, '-');
  }

  function isLatin(ch) { return !!ch && LATIN_CHAR_RE.test(ch); }
  function isCjk(ch) { return !!ch && CJK_CHAR_RE.test(ch); }
  /** definition 的占位值（尚无释义）：这些值不算「有释义」，避免给无释义的词打标 */
  var PENDING_DEF = { '\u5f85\u8865': 1, '\u5f85\u88dc': 1, 'TBD': 1 };
  /** definition 是否为**可用**释义（非空且非占位） */
  function hasDef(e) {
    var d = e && e.definition;
    return typeof d === 'string' && !!d.trim() && !PENDING_DEF[d.trim()];
  }
  /** 词条是否有可展示释义：annotations 的 zh_cn/zh_tw/en **或**词表行的 definition */
  function isGloss(e) { return !!(e && (e.zh_cn || e.zh_tw || e.en || hasDef(e))); }
  /** 调外部转换器（如 opencc 繁→简）失败/无变化都返回 ''（调用方按「无简体形」处理） */
  function safeConv(fn, s) {
    try {
      var r = fn(s);
      return (typeof r === 'string' && r && r !== s) ? r : '';
    } catch (e) { return ''; }
  }


  /* ---------- 词条归一化与合并 ---------- */

  /**
   * 把各种形态的输入归一为词条对象。
   *   字符串      → { word }
   *   紧凑数组行  → [词形, 简体形, 全库词次, 出现书数]（vocab_final.json 的行格式）
   *   对象        → 兼容 annotations（word/pinyin/zh_cn/zh_tw/en/note/is_difficult/multi/rare）
   *                 与短键（w/s/t/b）
   */
  function normalizeEntry(raw) {
    if (raw == null) return null;
    if (typeof raw === 'string') {
      return raw ? { word: raw, simp: '', pinyin: '', zh_cn: '', zh_tw: '', en: '', note: '',
        definition: '', need_ai: false,
        freq: 0, books: 0, is_difficult: false, multi: false, rare: false, vocabOnly: true } : null;
    }
    if (Object.prototype.toString.call(raw) === '[object Array]') {
      var w = raw[0] == null ? '' : String(raw[0]);
      if (!w) return null;
      return { word: w, simp: raw[1] ? String(raw[1]) : '', pinyin: '',
        zh_cn: '', zh_tw: '', en: '', note: '',
        definition: raw[4] ? String(raw[4]) : '', need_ai: !!raw[5],
        freq: +raw[2] || 0, books: +raw[3] || 0,
        is_difficult: false, multi: false, rare: false, vocabOnly: true };
    }
    var word = raw.word != null ? String(raw.word) : (raw.w != null ? String(raw.w) : '');
    if (!word) return null;
    return {
      word: word,
      simp: raw.simp ? String(raw.simp) : (raw.s != null ? String(raw.s) : ''),
      pinyin: raw.pinyin || raw.py || '',
      zh_cn: raw.zh_cn || raw.zh || '',
      zh_tw: raw.zh_tw || raw.zhT || '',
      en: raw.en || '',
      note: raw.note || '',
      definition: raw.definition || raw.def || '',
      need_ai: !!raw.need_ai,
      freq: +raw.freq || +raw.frequency || +raw.t || 0,
      books: +raw.book_count || +raw.books_count || +raw.b || 0,
      is_difficult: !!raw.is_difficult,
      multi: !!raw.multi,
      rare: !!raw.rare,
      vocabOnly: raw.is_difficult == null
    };
  }

  /**
   * 就地合并同形词条（保持对象身份 → 免去 trie.get 回读，建表快一倍）：
   * 释义/拼音优先取已有的，词频与书数取最大（词表条目只补数字，不覆盖释义）。
   * 注意：调用方传进来的都是 normalizeEntry 新建的副本，就地改安全。
   */
  function mergeInto(a, b) {
    if (!a) return b;
    if (!b) return a;
    a.word = a.word || b.word;
    a.simp = a.simp || b.simp;
    a.pinyin = a.pinyin || b.pinyin;
    a.zh_cn = a.zh_cn || b.zh_cn;
    a.zh_tw = a.zh_tw || b.zh_tw;
    a.en = a.en || b.en;
    a.note = a.note || b.note;
    a.definition = a.definition || b.definition;
    a.need_ai = !!(a.need_ai || b.need_ai);       // 任一来源标「待 AI」→ 词条仍标（仅提示，不影响匹配）
    if ((b.freq || 0) > (a.freq || 0)) a.freq = b.freq;
    if ((b.books || 0) > (a.books || 0)) a.books = b.books;
    a.is_difficult = !!(a.is_difficult || b.is_difficult);
    a.multi = !!(a.multi || b.multi);
    a.rare = !!(a.rare || b.rare);
    if (a.zh_cn || a.zh_tw || a.en || hasDef(a)) a.vocabOnly = false;
    return a;
  }

  /* ---------- Trie（中文及含 CJK 的词形） ---------- */

  function Trie() { this.root = Object.create(null); this.keys = 0; }

  Trie.prototype.add = function (key, entry) {
    var node = this.root;
    for (var i = 0; i < key.length; i++) {
      var c = key.charAt(i);
      node = node[c] || (node[c] = Object.create(null));
    }
    if (node.$) node.$ = mergeInto(node.$, entry);
    else { node.$ = entry; this.keys++; }
    return node.$;
  };

  /**
   * 该位置的所有词表命中（由短到长）——供「整词不标时挑词内可标子单元」使用。
   * @returns {Array<{len:number, key:string, entry:Object}>}
   */
  Trie.prototype.candidates = function (text, i, end) {
    var node = this.root, out = [];
    for (var j = i; j < end; j++) {
      node = node[text.charAt(j)];
      if (!node) break;
      if (node.$) out.push({ len: j - i + 1, key: text.slice(i, j + 1), entry: node.$ });
    }
    return out;
  };

  /**
   * 最长前缀匹配（Max Match）：在 [i, end) 内取**最长**的词表命中。
   * end 由调用方限定为「同一 CJK 连续段」的右界 → 命中永不跨标点/夹带非汉字。
   * @returns {?{len:number, key:string, entry:Object}}
   */
  Trie.prototype.longest = function (text, i, end) {
    var node = this.root, best = null;
    for (var j = i; j < end; j++) {
      node = node[text.charAt(j)];
      if (!node) break;
      if (node.$) best = { len: j - i + 1, key: text.slice(i, j + 1), entry: node.$ };
    }
    return best;
  };

  /** 取词表里某个键的**合并后**词条（trie.add 归并后要回读，避免拿到旧对象） */
  Trie.prototype.get = function (key) {
    var node = this.root;
    for (var i = 0; i < key.length; i++) {
      node = node[key.charAt(i)];
      if (!node) return null;
    }
    return node.$ || null;
  };

  /* ---------- Vocabulary：词表 + 释义表（合一配对） ---------- */

  function Vocabulary(defaults) {
    this.trie = new Trie();               // 中文及含 CJK 的词形
    this.en = Object.create(null);        // 英文：归一化词形 → 词条
    this.byKey = Object.create(null);     // 原文键（繁/简/英）→ 词条（lookup 用）
    this.opts = defaults || {};
    this.rows = 0;                        // 输入行数
    this.count = 0;                       // 词条数（去重前）
    this._seq = 0;                        // 打标代次（取消上一轮用）
  }

  /** 加一条词（字符串 / 紧凑数组行 / 对象词条都吃） */
  Vocabulary.prototype.add = function (raw) {
    this.rows++;
    var e = normalizeEntry(raw);
    if (!e) return this;
    var key = e.word;
    if (CJK_CHAR_RE.test(key)) {
      this.byKey[key] = this.trie.add(key, e);
      // 简体键：词表行自带 simp；没有时向外部转换器（opencc）要一次 → 简中显示模式也能命中
      var simp = e.simp || (typeof this.opts.tradToSimp === 'function' && key.length <= 8
        ? safeConv(this.opts.tradToSimp, key) : '');
      if (simp && simp !== key) this.byKey[simp] = this.trie.add(simp, e);
    } else {
      var k = normalizeEn(key);
      this.en[k] = this.byKey[key] = mergeInto(this.en[k], e);      // 释义优先、词频取最大
      if (e.simp) this.byKey[e.simp] = this.en[k];
    }
    this.count++;
    return this;
  };

  /** 批量加入：数组 / {words:[…]} / {zh:[…],en:[…]} / 书的 annotations 数组 */
  Vocabulary.prototype.addList = function (list) {
    if (!list) return this;
    if (Object.prototype.toString.call(list) === '[object Array]') {
      for (var i = 0; i < list.length; i++) this.add(list[i]);
    } else if (list.words) {
      this.addList(list.words);
    } else if (list.zh || list.en) {
      this.addList(list.zh || []);
      this.addList(list.en || []);
    }
    return this;
  };

  /** 按「显示词形 / 词典键」取词条（含省略撇号、所有格、单字回退） */
  Vocabulary.prototype.lookup = function (key) {
    if (!key) return null;
    if (this.byKey[key]) return this.byKey[key];
    var hit = this._enLookup(key);
    if (hit) return hit.entry;
    if (this.trie.root[key.charAt(0)]) {
      var t = this.trie.longest(key, 0, key.length);
      if (t && t.len === key.length) return t.entry;
    }
    return null;
  };

  /** 英文查找：整词 → 去词尾省略撇号（mornin'）→ 去所有格（Lear's） */
  Vocabulary.prototype._enLookup = function (unit) {
    var k = normalizeEn(unit);
    if (this.en[k]) return { key: k, entry: this.en[k] };
    if (RE_TAIL_APOS.test(k)) {
      k = k.replace(RE_TAIL_APOS, '');
      if (k && this.en[k]) return { key: k, entry: this.en[k] };
    }
    if (RE_POSSESSIVE.test(k)) {
      var p = k.replace(RE_POSSESSIVE, '');
      if (p && this.en[p]) return { key: p, entry: this.en[p] };
    }
    return null;
  };

  /** 密度策略：'gloss'（默认，只标有释义的词）| 'all'（词表命中全标）| 'rare'（只标重难多音） */
  Vocabulary.prototype._allow = function (entry, mode, o, info) {
    if (!entry) return false;
    var ok;
    if (mode === 'all') ok = true;
    else if (mode === 'rare') ok = !!(entry.rare || entry.is_difficult);
    else ok = isGloss(entry);
    if (ok && typeof o.allow === 'function') ok = !!o.allow(entry, info);
    return ok;
  };

  /** 中文单元：命中的词整体成段；整词不标但**词内子单元**有释义 → 整词成段并附子单元（不散成单字） */
  Vocabulary.prototype._resolveCjk = function (surface, entry, o, mode, minLenZh) {
    if (surface.length < minLenZh) return null;
    if (this._allow(entry, mode, o, { surface: surface, lang: 'zh' })) {
      return { word: surface, key: (entry && entry.word) || surface, lang: 'zh', entry: entry };
    }
    if (surface.length > 1 && o.parts !== false) {
      var parts = this._glossedParts(surface, o, mode);
      if (parts.length) {
        return { word: surface, key: (entry && entry.word) || surface, lang: 'zh',
                 entry: entry || null, fromParts: true, parts: parts };
      }
    }
    return null;
  };

  /** 词内子单元（长度严格小于整词；用于「整词无释义但成分有释义」） */
  Vocabulary.prototype._glossedParts = function (surface, o, mode) {
    var out = [], i = 0, n = surface.length;
    while (i < n) {
      var cands = this.trie.candidates(surface, i, n), pick = null;
      for (var c = cands.length - 1; c >= 0; c--) {          // 从最长候选起挑「可标」的
        if (cands[c].len < n
            && this._allow(cands[c].entry, mode, o, { surface: cands[c].key, lang: 'zh' })) {
          pick = cands[c];
          break;
        }
      }
      if (pick) out.push({ word: pick.key, key: pick.entry.word, entry: pick.entry });
      i += pick ? pick.len : 1;
    }
    return out;
  };

  /** 英文单元：整词命中 → 整个词（含词尾撇号）成段；否则仅在连接符处拆段（绝不在字母中间切） */
  Vocabulary.prototype._resolveEn = function (unit, o, mode, minLenEn) {
    var whole = this._enLookup(unit);
    if (whole && unit.length >= minLenEn
        && this._allow(whole.entry, mode, o, { surface: unit, lang: 'en' })) {
      return [{ word: unit, key: whole.key, lang: 'en', entry: whole.entry }];
    }
    var out = [], last = 0, m;
    RE_EN_PIECE.lastIndex = 0;
    while ((m = RE_EN_PIECE.exec(unit))) {
      var sub = m[0];
      if (m.index > last) out.push({ text: unit.slice(last, m.index) });
      var hit = this._enLookup(sub);
      if (hit && sub.length >= minLenEn && this._allow(hit.entry, mode, o, { surface: sub, lang: 'en' })) {
        out.push({ word: sub, key: hit.key, lang: 'en', entry: hit.entry });
      } else {
        out.push({ text: sub });
      }
      last = m.index + sub.length;
    }
    if (last < unit.length) out.push({ text: unit.slice(last) });
    return out.length ? out : [{ text: unit }];
  };

  /**
   * 纯函数：文本 → 分段计划（Node 里可直接自测；DOM 层只负责把计划落成节点）
   *   [{ text:'…' } | { word, key, lang, entry, [parts] }]
   * 保证：各段 text/word 顺序拼接 **逐字等于**原文本（selftest 断言）。
   */
  Vocabulary.prototype.plan = function (text, opts) {
    var o = opts || this.opts || {};
    var mode = o.mode || 'gloss';
    var minLenZh = o.minLenZh == null ? 1 : o.minLenZh;
    var minLenEn = o.minLenEn == null ? 1 : o.minLenEn;
    var src = text == null ? '' : String(text);
    var n = src.length, i = 0, segs = [], buf = '';

    function flush() { if (buf) { segs.push({ text: buf }); buf = ''; } }

    while (i < n) {
      var c = src.charAt(i);
      if (CJK_CHAR_RE.test(c)) {
        // CJK 连续段：切词只在这段内进行（跨标点不粘连）
        var runEnd = i + 1;
        while (runEnd < n && CJK_CHAR_RE.test(src.charAt(runEnd))) runEnd++;
        while (i < runEnd) {
          var hit = this.trie.longest(src, i, runEnd);
          var len = hit ? hit.len : 1;
          var surface = src.substr(i, len);
          var seg = this._resolveCjk(surface, hit ? hit.entry : null, o, mode, minLenZh);
          if (seg) { flush(); segs.push(seg); } else { buf += surface; }
          i += len;
        }
      } else if (LATIN_CHAR_RE.test(c)) {
        RE_EN_UNIT.lastIndex = i;
        var m = RE_EN_UNIT.exec(src);
        if (!m || m.index !== i) { buf += c; i++; continue; }
        var unit = m[0];
        var parts = this._resolveEn(unit, o, mode, minLenEn);
        for (var k = 0; k < parts.length; k++) {
          if (parts[k].word) { flush(); segs.push(parts[k]); } else { buf += parts[k].text; }
        }
        i = m.index + unit.length;
      } else {
        buf += c; i++;
      }
    }
    flush();
    return segs;
  };

  /* ---------- DOM 层：TreeWalker 收文本节点 + requestIdleCallback 分批落节点 ---------- */

  function isSkippable(parent) {
    if (!parent || parent.nodeType !== 1) return false;
    var tag = parent.nodeName;
    if (tag === 'WISE' || tag === 'SCRIPT' || tag === 'STYLE' || tag === 'CODE' || tag === 'PRE'
        || tag === 'TEXTAREA' || tag === 'KBD' || tag === 'SAMP') return true;
    if (parent.getAttribute && parent.getAttribute('data-no-annotate') != null) return true;
    return false;
  }

  /** 收集可打标的文本节点（跳过 <wise>/脚本/预格式/显式排除区；空白节点直接丢） */
  function collectTextNodes(rootEl, o) {
    o = o || {};
    var doc = rootEl.ownerDocument, out = [];
    var skip = o.skipSelector === undefined ? SKIP_SELECTOR : o.skipSelector;
    function accept(parent) {
      if (isSkippable(parent)) return false;
      if (skip && parent && parent.closest && parent.closest(skip)) return false;
      return true;
    }
    if (doc.createTreeWalker) {
      var walker = doc.createTreeWalker(rootEl, SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue || !node.nodeValue.trim()) return FILTER_REJECT;
          return accept(node.parentNode) ? FILTER_ACCEPT : FILTER_REJECT;
        }
      }, false);
      var n;
      while ((n = walker.nextNode())) out.push(n);
    } else {                                  // 极老浏览器兜底（手写遍历）
      (function walk(el) {
        var kids = el.childNodes || [];
        for (var i = 0; i < kids.length; i++) {
          var c = kids[i];
          if (c.nodeType === 3) {
            if (c.nodeValue && c.nodeValue.trim()) out.push(c);
          } else if (c.nodeType === 1 && accept(c)) { walk(c); }
        }
      })(rootEl);
    }
    return out;
  }

  /** 命中 → <wise data-word="完整词形" data-key="词典键" data-lang… class="ann-word …"> */
  function buildWise(s, doc) {
    var el = doc.createElement('wise');
    var e = s.entry || {};
    el.setAttribute('data-word', s.word);              // 显示用**完整词形**（不截断）
    el.setAttribute('data-key', s.key || s.word);      // 词典键（释义查这个）
    el.setAttribute('data-lang', s.lang || 'zh');
    var cls = 'ann-word';
    if (e.is_difficult) cls += ' ann-hard';
    if (e.rare) cls += ' ann-rare';
    if (e.multi) cls += ' ann-multi';
    if (!isGloss(e)) cls += ' ann-vocab';              // 词表词（暂无释义）→ 样式可区分
    el.className = cls;
    if (s.parts && s.parts.length) {
      var ws = [];
      for (var i = 0; i < s.parts.length; i++) ws.push(s.parts[i].word);
      el.setAttribute('data-parts', ws.join('|'));     // 卡内展示成分字释义
    }
    if (e.freq) el.setAttribute('data-freq', e.freq);
    if (e.books) el.setAttribute('data-books', e.books);
    el.textContent = s.word;
    return el;
  }

  /** 落节点：一个文本节点一次 replaceChild（移动端不产生多余空文本节点） */
  function applyPlan(node, segs, doc) {
    var frag = doc.createDocumentFragment();
    for (var i = 0; i < segs.length; i++) {
      var s = segs[i];
      frag.appendChild(s.word ? buildWise(s, doc) : doc.createTextNode(s.text));
    }
    if (node.parentNode) node.parentNode.replaceChild(frag, node);
  }

  function hasWord(segs) {
    for (var i = 0; i < segs.length; i++) if (segs[i].word) return true;
    return false;
  }

  function nowMs() {
    return (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  }

  function scheduleIdle(fn) {
    if (typeof requestIdleCallback === 'function') return requestIdleCallback(function () { fn(); }, { timeout: 200 });
    return setTimeout(fn, 8);
  }

  /**
   * 动态标注（异步 · 空闲分批 · 可取消）
   *   const h = m.annotate(readerBody, { mode:'gloss', allow: e => … });
   *   m.cancel();          // 重渲染/换档前取消上一轮
   *   await h.done;        // 完成（stats）
   */
  Vocabulary.prototype.annotate = function (rootEl, opts) {
    var o = opts || {};
    var self = this, seq = ++this._seq, doc = rootEl.ownerDocument;
    var nodes = collectTextNodes(rootEl, o);
    var stats = { nodes: nodes.length, scanned: 0, nodesTouched: 0, words: 0, chars: 0, skipped: 0 };
    var budget = o.budgetMs == null ? 6 : o.budgetMs;
    var maxWords = o.maxWords == null ? 20000 : o.maxWords;
    var i = 0, finished = false, doneResolve;
    var done = new Promise(function (res) { doneResolve = res; });

    function finish() {
      if (finished) return;
      finished = true;
      if (typeof o.onDone === 'function') {
        try { o.onDone(stats); } catch (err) { /* 回调异常不影响阅读 */ }
      }
      doneResolve(stats);
    }

    function slice() {
      if (seq !== self._seq) { finish(); return; }
      var t1 = nowMs() + budget;
      while (i < nodes.length) {
        if (stats.words >= maxWords) { stats.skipped++; i = nodes.length; break; }
        var node = nodes[i++];
        if (!node || !node.isConnected || node.nodeValue == null) { stats.skipped++; continue; }
        var text = node.nodeValue;
        if (!CJK_CHAR_RE.test(text) && !LATIN_CHAR_RE.test(text)) continue;
        var segs = self.plan(text, o);
        if (!hasWord(segs)) continue;
        var n = 0;
        for (var k = 0; k < segs.length; k++) if (segs[k].word) { n++; stats.chars += segs[k].word.length; }
        applyPlan(node, segs, doc);
        stats.nodesTouched++; stats.words += n; stats.scanned++;
        if (nowMs() >= t1) break;              // 本片预算用完 → 让出主线程，下个空闲片继续
      }
      if (i < nodes.length) scheduleIdle(slice);
      else finish();
    }

    // 首片也走空闲回调：不阻塞首屏渲染
    scheduleIdle(slice);

    return {
      done: done,
      stats: stats,
      cancel: function () { self.cancel(); }
    };
  };

  /** 取消所有排队中的打标任务（代次 +1 → 旧 slice 直接收工） */
  Vocabulary.prototype.cancel = function () { this._seq++; return this; };

  /** 便捷：只取命中（词形 + 键 + 语言），统计与自测用 */
  Vocabulary.prototype.match = function (text, opts) {
    return this.plan(text, opts).filter(function (s) { return !!s.word; })
      .map(function (s) { return { word: s.word, key: s.key, lang: s.lang }; });
  };

  /* ---------- 自检：对抗性样例（Node 与浏览器均可跑） ---------- */

  function selftest() {
    var pass = 0, failed = [];
    function check(name, cond, detail) {
      if (cond) { pass++; } else { failed.push({ name: name, detail: detail }); }
    }
    function ws(segs) {
      var out = [];
      for (var i = 0; i < segs.length; i++) if (segs[i].word) out.push(segs[i].word);
      return out;
    }
    function hits(segs) {                      // 命中 + 在原文中的位置/长度
      var out = [], at = 0;
      for (var i = 0; i < segs.length; i++) {
        var len = segs[i].word ? segs[i].word.length : segs[i].text.length;
        if (segs[i].word) out.push({ word: segs[i].word, start: at, end: at + len, seg: segs[i] });
        at += len;
      }
      return out;
    }
    function rebuild(segs) {
      var s = '';
      for (var i = 0; i < segs.length; i++) s += (segs[i].word ? segs[i].word : segs[i].text);
      return s;
    }
    function words(text, opts) { return ws(m.plan(text, opts || { mode: 'all' })).join(','); }

    var anns = [
      { word: '說', zh_cn: '講話', is_difficult: true, multi: true },
      { word: '學', zh_cn: '學習' },
      { word: '君', zh_cn: '君主' }, { word: '子', zh_cn: '子女' },
      { word: '不', zh_cn: '否定' }, { word: '知', zh_cn: '知道' },
      { word: '觳', zh_cn: '量器', rare: true, is_difficult: true },
      { word: 'morning', zh_cn: '早晨' }, { word: 'mornin', zh_cn: '早晨（口語）' },
      { word: "don't", zh_cn: '不' }, { word: 'old', zh_cn: '舊的' },
      { word: 'fashioned', zh_cn: '…樣式的' }, { word: 'lear', zh_cn: '李爾' }
    ];
    var rows = [['君子', '君子', 900, 20], ['不知', '不知', 800, 18], ['學者', '学者', 120, 5],
                ['說服', '说服', 300, 9], ['仁義', '仁义', 40, 3], ['Buda-Pesth', 'Buda-Pesth', 12, 1]];
    var m = build(anns.concat(rows), { mode: 'gloss' });
    var texts = ["He said mornin' and left.", 'Good morning, all.', 'old-fashioned ways',
                 'I don\u2019t know.', 'Buda-Pesth was a city.', "Lear's daughter", 'untouched',
                 '君子不器。', '不知為不知，是知也。', '仁。義', '說服他人', '说服他人', '', '   ', '123 456'];

    check('词表构建（trie 有键 / 英文表非空 / 词条可查）',
      m.trie.keys > 0 && !!m.en['mornin'] && !!m.lookup('說服'), { keys: m.trie.keys });
    check('词表行与释义合并（說服 频次合进来）',
      !!m.lookup('說服') && m.lookup('說服').freq === 300, m.lookup('說服'));

    // ① 不变式：分段拼回 == 原文本；英文命中为「最大词形」；中文命中不夹非汉字；命中不重叠
    for (var t = 0; t < texts.length; t++) {
      var text = texts[t], segs = m.plan(text, { mode: 'all' }), hs = hits(segs);
      check('原样重建 #' + t, rebuild(segs) === text, text);
      for (var h = 0; h < hs.length; h++) {
        var w = hs[h];
        if (w.seg.lang === 'en') {
          var before = w.start > 0 ? text.charAt(w.start - 1) : '';
          var after = w.end < text.length ? text.charAt(w.end) : '';
          check('英文命中为最大词形 #' + t + ':' + w.word,
            !isLatin(before) && !isLatin(after), text + ' → ' + w.word);
        } else {
          var allCjk = true;
          for (var c = 0; c < w.word.length; c++) if (!isCjk(w.word.charAt(c))) allCjk = false;
          check('中文命中全 CJK（同段）#' + t + ':' + w.word, allCjk, text);
        }
      }
      for (var q = 1; q < hs.length; q++) {
        check('命中不重叠 #' + t, hs[q - 1].end <= hs[q].start, text);
      }
    }

    // ② 旧 bug 回归：mornin' 必须整词（不得截成 mornin）
    var s1 = hits(m.plan("He said mornin' and left.", { mode: 'all' }));
    check("省略撇号整词 mornin'", s1.length === 1 && s1[0].word === "mornin'", words("He said mornin'"));
    check('词典键 = mornin', s1[0] && s1[0].seg.key === 'mornin', s1[0] && s1[0].seg.key);
    check('morning 不命中 mornin（禁止前缀截断）',
      words('Good morning, all.') === 'morning', words('Good morning, all.'));
    check('untouched 不命中词中片段', words('untouched') === '', words('untouched'));
    check('old-fashioned 只在连接符处拆成两个整词',
      words('old-fashioned ways') === 'old,fashioned', words('old-fashioned ways'));
    check('弯撇号 don\u2019t 整词命中且键归一为直撇号', (function () {
      var d = hits(m.plan('I don\u2019t know.', { mode: 'all' }));
      return d.length === 1 && d[0].word === 'don\u2019t' && d[0].seg.key === "don't";
    })(), hits(m.plan('I don\u2019t know.', { mode: 'all' })));
    var leap = hits(m.plan("Lear's daughter", { mode: 'all' }));
    check("所有格 Lear's 整词命中（键 lear）",
      leap[0] && leap[0].word === "Lear's" && leap[0].seg.key === 'lear', leap[0]);

    // ③ 中文：最长优先 + 词内不散单字（「严禁单字散列匹配」）
    var bz = hits(m.plan('不知為不知，是知也。', { mode: 'all' }));
    check('最长优先 不知 > 不 + 知', bz[0] && bz[0].word === '不知', words('不知為不知，是知也。'));
    var jzSegs = m.plan('君子不器。', { mode: 'gloss' });
    var jzW = ws(jzSegs);
    check('词内不散单字：君子 整词命中（gloss 模式）', jzW[0] === '君子', jzW);
    check('君子 无释义 → 卡内带成分字（parts）',
      !!jzSegs[0].parts && jzSegs[0].parts.length === 2, jzSegs[0].parts);
    check('君 / 子 不再单独成段（严禁单字散列）',
      jzW.indexOf('君') < 0 && jzW.indexOf('子') < 0, jzW);
    check('all 模式：君子 整词命中',
      ws(m.plan('君子不器。', { mode: 'all' }))[0] === '君子', ws(m.plan('君子不器。', { mode: 'all' })));
    check('跨标点不粘连（仁義 ≠ 仁。義）', words('仁。義') === '', words('仁。義'));
    check('繁体原文命中 說服（整词，不散成 說）', words('說服他人') === '說服', words('說服他人'));
    var sf = hits(m.plan('说服他人', { mode: 'all' }));
    check('简中显示模式命中繁体键（说 → 說服）', sf[0] && sf[0].seg.key === '說服', sf[0]);

    // ④ 密度策略 / 档位过滤
    check('mode=rare 只标重难字', words('君子觳', { mode: 'rare' }) === '觳', words('君子觳', { mode: 'rare' }));
    check('allow 过滤生效（只留多音字）',
      words('君子說', { mode: 'all', allow: function (e) { return !!e.multi; } }) === '說',
      words('君子說', { mode: 'all', allow: function (e) { return !!e.multi; } }));
    check('gloss 模式不标无释义的词表词（Buda-Pesth）',
      words('Buda-Pesth was a city.', { mode: 'gloss' }) === '',
      words('Buda-Pesth was a city.', { mode: 'gloss' }));
    check('all 模式整词优先（Buda-Pesth > Buda + Pesth）',
      words('Buda-Pesth was a city.', { mode: 'all' }).split(',')[0] === 'Buda-Pesth',
      words('Buda-Pesth was a city.', { mode: 'all' }));

    // ⑤ 边界情况
    check('空串/纯空白/纯数字不产出命中',
      m.plan('').length === 0 && m.plan('   ').length === 1 && words('123 456') === '',
      m.plan('   '));
    check('无空段（相邻文本段已合并）', (function () {
      var segs = m.plan('好。君子不器。', { mode: 'all' });
      for (var i = 0; i < segs.length; i++) {
        if (segs[i].word ? !segs[i].word : !segs[i].text) return false;
      }
      return true;
    })(), m.plan('好。君子不器。', { mode: 'all' }));
    check('lookup 兼容显示形/词典键/省略撇号',
      !!m.lookup('mornin') && !!m.lookup("mornin'") && !!m.lookup('lear') && m.lookup('nope') === null,
      [!!m.lookup('mornin'), !!m.lookup("mornin'"), m.lookup('nope')]);

    // ⑥ 外部繁→简兜底（opencc）：单字键也能生成简体键；转换器抛错不影响构建
    var t2s = function (s) { return ({ '\u8aaa': '\u8bf4', '\u5b78': '\u5b66' })[s] || s; };
    var m2 = build([{ word: '\u8aaa', zh_cn: '講話' }, { word: '\u5b78', zh_cn: '學習' }],
      { mode: 'gloss', tradToSimp: t2s });
    var m2w = ws(m2.plan('\u8bf4\u5b66', { mode: 'gloss' })).join(',');
    check('opencc 兜底：简体键由转换器生成（说 / 学）', m2w === '\u8bf4,\u5b66', m2w);
    check('转换器抛错时静默降级（无简体键，但原键可用）', (function () {
      var m3 = build([{ word: '\u8aaa', zh_cn: 'x' }],
        { tradToSimp: function () { throw new Error('boom'); } });
      return !!m3.lookup('\u8aaa') && !m3.lookup('\u8bf4');
    })());

    // ⑦ 词表行内嵌释义（definition / need_ai）：raw[4] → definition、raw[5] → need_ai
    var defRows = [['君子', '君子', 900, 20, '君：君主；子：子女', true],
                   ['仁義', '仁义', 40, 3, '仁爱与正义', false],
                   ['獃獃', '獃獃', 3, 1, '待补', true]];
    var md = build(anns.concat(defRows), { mode: 'gloss' });
    check('词表行 definition 被解析（不再错读成 pinyin）', (function () {
      var e = md.lookup('仁義');
      return !!e && e.definition === '仁爱与正义' && e.pinyin === '' && e.need_ai === false;
    })(), md.lookup('仁義'));
    check('need_ai 解析为布尔（raw[5] → true）',
      !!md.lookup('君子') && md.lookup('君子').need_ai === true, md.lookup('君子'));
    check('definition 计入 isGloss，占位「待补/待補/TBD」不算',
      isGloss({ definition: '释义' }) && !isGloss({ definition: '待补' })
      && !isGloss({ definition: '待補' }) && !isGloss({ definition: 'TBD' })
      && !isGloss({ definition: '   ' }) && !isGloss({}));
    check('gloss 模式标注带 definition 的词（仁義）',
      ws(md.plan('仁義之師', { mode: 'gloss' })).join(',') === '仁義',
      ws(md.plan('仁義之師', { mode: 'gloss' })).join(','));
    check('definition=待补 的行不被打标（獃獃 仍作「词表词」）',
      ws(md.plan('獃獃', { mode: 'gloss' })).join(',') === '' && !isGloss(md.lookup('獃獃')),
      [ws(md.plan('獃獃', { mode: 'gloss' })).join(','), md.lookup('獃獃')]);
    check('合并：行 definition 与 annotations 释义共存（互不覆盖）', (function () {
      var mm = build([{ word: '仁義', zh_cn: '仁爱与正义' },
                      ['仁義', '仁義', 40, 3, '词表释义', true]]);
      var e = mm.lookup('仁義');
      return !!e && e.zh_cn === '仁爱与正义' && e.definition === '词表释义' && e.need_ai === true;
    })());
    check('对象形式也吃 definition / need_ai', (function () {
      var e = build([{ word: '仁', zh_cn: '仁爱', definition: 'D', need_ai: true }]).lookup('仁');
      return !!e && e.definition === 'D' && e.need_ai === true;
    })());

    return { pass: pass, fail: failed.length, failed: failed };
  }

  /* ---------- DOM 自检（浏览器；Node 下需自备 document shim） ---------- */

  function domSelftest(doc) {
    doc = doc || (typeof document !== 'undefined' ? document : null);
    var failed = [], pass = 0;
    function check(name, cond, detail) { if (cond) pass++; else failed.push({ name: name, detail: detail }); }
    if (!doc || !doc.body) {
      return Promise.resolve({ pass: 0, fail: 1, failed: [{ name: 'domSelftest：无 document', detail: null }] });
    }
    var text = "He said mornin' and 君子不器, old-fashioned.";
    var host = doc.createElement('div');
    host.textContent = text;
    doc.body.appendChild(host);
    var m = build([
      { word: 'morning', zh_cn: '早晨' }, { word: 'mornin', zh_cn: '早晨（口語）' },
      { word: 'old', zh_cn: '舊的' }, { word: 'fashioned', zh_cn: '…樣式的' },
      { word: '君', zh_cn: '君主' }, { word: '子', zh_cn: '子女' }, { word: '不', zh_cn: '否定' },
      ['君子', '君子', 900, 20]
    ], { mode: 'gloss' });

    function wiseEls() {
      var all = host.getElementsByTagName('wise'), out = [];
      for (var i = 0; i < all.length; i++) out.push(all[i]);
      return out;
    }
    function words() {
      var els = wiseEls(), out = [];
      for (var i = 0; i < els.length; i++) out.push(els[i].getAttribute('data-word'));
      return out;
    }
    function attr(word, name) {
      var els = wiseEls();
      for (var i = 0; i < els.length; i++) {
        if (els[i].getAttribute('data-word') === word) return els[i].getAttribute(name);
      }
      return null;
    }

    return m.annotate(host, { mode: 'gloss', budgetMs: 4 }).done.then(function () {
      var w = words();
      check('打标发生（≥3 个 <wise>）', w.length >= 3, w);
      check("data-word 是完整词形 mornin'", w.indexOf("mornin'") >= 0, w);
      check('data-key = mornin（释义键）', attr("mornin'", 'data-key') === 'mornin', attr("mornin'", 'data-key'));
      check('中文整词成段（君子，非 君 + 子）',
        w.indexOf('君子') >= 0 && w.indexOf('君') < 0 && w.indexOf('子') < 0, w);
      check('old-fashioned 拆成两个整词', w.indexOf('old') >= 0 && w.indexOf('fashioned') >= 0, w);
      check('textContent 逐字一致（复制/划选/下载不受影响）', host.textContent === text, host.textContent);
      var before = w.length;
      return m.annotate(host, { mode: 'gloss', budgetMs: 4 }).done.then(function () {
        check('幂等：重跑不重复包裹', words().length === before, before + ' → ' + words().length);
      });
    }).then(function () {
      if (host.parentNode) host.parentNode.removeChild(host);
      return { pass: pass, fail: failed.length, failed: failed };
    });
  }

  /* ---------- 对外接口 ---------- */

  function build(entries, opts) {
    var v = new Vocabulary(opts || {});
    if (typeof entries === 'string') entries = [entries];
    v.addList(entries || []);
    return v;
  }

  return {
    version: '1.2.0',
    build: build,
    Vocabulary: Vocabulary,
    Trie: Trie,
    normalizeEn: normalizeEn,
    isGloss: isGloss,
    hasDef: hasDef,
    isCjk: isCjk,
    isLatin: isLatin,
    collectTextNodes: collectTextNodes,
    selftest: selftest,
    domSelftest: domSelftest,
    EN_UNIT_SRC: EN_UNIT_SRC
  };
});


