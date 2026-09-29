#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""definition_fill.py —— 给 vocab_final.json 的词表行**回填释义**（definition / need_ai）

背景
  前端 `网站/js/vocab-matcher.js` 拿 vocab_final.json 建 Trie 做词边界匹配，
  但词表行原先只有 `[词形, 简体形, 词次, 书数]`——**没有释义**，词卡只能显示「待补」。
  本脚本把释义直接写进行内（行扩成 6 元），前端读行即得释义，无需另抓接口。

产出（默认**原地回写** `网站/_site_data/vocab_final.json`）
    {"_meta": {…}, "zh": [["君子","君子",8478,43,"君：…；子：…",true], …], "en": [[…]]}
    行 = [词形, 简体形(可空), 全库词次, 出现书数, definition, need_ai]
      definition : 释义字符串；查不到时写「待补」
      need_ai    : true 表示释义缺失（「待补」）或只是**逐字合成**的弱释义 → 待 AI 精修

匹配规则（整词优先，查不到再退化到单字）
  · 英文词头：**整词精确匹配**（先过「最大词形」校验，绝不做前缀/子串匹配）
      gloss_override → ECDICT 中文释义 → ECDICT 英文释义 → 网络词典缓存（--network 才发请求）
  · 中文词头：**双字及以上整词优先** → 单字兜底 → 逐字合成 → 待补
      词级（整词）   gloss_override → 词级中文源（--zh-word-src，或 data/ 自动发现：
                     cedict_words.json / shuowen.json(说文) / kangxi.json(康熙) / hanyu_words.json）
      单字（长度 1） gloss_override → 新华字典 → CC-CEDICT(英) → makemeahanzi(英)
      逐字合成       整词源查不到时逐字取单字释义拼成「君：…；子：…」（need_ai=true）
      去自我引用     单字释义以「同'X'：」开头且 X 是本字／繁简对应字时去掉该前缀；繁↔简单字对应表
                     由词表自身推出（｜無學→无学｜⇒ 無↔无），故简体词 无不 的「无：同'無'：①没有」
                     也会被整理成「无：①没有」
      全无           definition="待补"、need_ai=true

  注：仓库内现有单字源（cedict_single / xinhua_word / gloss_override / makemeahanzi_sub）
  只覆盖本词表用字的 **30.5%**，故多字词多数落到「逐字合成」或「待补」。想要整词级释义，
  把**说文解字／康熙字典／CC-CEDICT 多字词**转成 `{词: 释义}` JSON 放进 `data/`（自动发现）
  或用 `--zh-word-src` 传入即可，无需改代码。

自检（每次运行都做，失败即报错且**不落盘**）
  行数不变、每行长度 = 6、**前四元逐项未被改动**、need_ai 为布尔、词形仍合法。

用法
    python3 文本/新书/definition_fill.py                       # 原地回填（离线，只读缓存）
    python3 文本/新书/definition_fill.py --dry-run              # 只看命中统计
    python3 文本/新书/definition_fill.py --zh-word-src data/shuowen.json
    python3 文本/新书/definition_fill.py --limit 500 --out /tmp/vf.json   # 抽样验证
    python3 文本/新书/definition_fill.py --selftest             # 规则回归（对抗性样例）

前置：先跑 `python3 文本/新书/build_vocab_final.py` 生成 4 元行词表。
"""
import argparse
import collections
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
IN_DEFAULT = os.path.join(ROOT, '网站', '_site_data', 'vocab_final.json')

try:                                            # 复用词形定义，避免两处规则走偏
    import build_vocab_final as BV
    is_pure_cjk, is_max_en = BV.is_pure_cjk, BV.is_max_en
except Exception:                               # 单独拷贝本脚本时也能跑
    def is_pure_cjk(word):
        return bool(word) and re.fullmatch(
            r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+', word) is not None

    def is_max_en(word):
        _L = (r"A-Za-z\u00c0-\u024f\u0250-\u02af\u1e00-\u1eff\u2c60-\u2c7f"
              r"\ua720-\ua7ff\ufb00-\ufb06")
        return bool(word) and re.fullmatch(
            '[%s]+(?:[-\u0027\u2019\u02bc][%s]+)*' % (_L, _L), word) is not None

try:                                            # 释义来源（缺失时全部判「待补」）
    import gloss_lib as G
except Exception:
    G = None

PENDING = '待补'                                 # 缺失占位（前端 reader.js 认识这个值）
ROW_FIELDS = '[词形, 简体形(可空), 全库词次, 出现书数, definition, need_ai]'
# data/ 里叫这些名字的词级中文源会被自动发现（说文解字／康熙字典／CC-CEDICT 多字词…）
AUTO_ZH_SRC = ('cedict_words.json', 'shuowen.json', 'kangxi.json', 'hanyu_words.json')

def clip(s, n):
    """压空白 + 去首尾标点 + 限长（超长截断并补省略号）。"""
    t = re.sub(r'\s+', ' ', str(s or '')).strip().strip('；;，,、。 ')
    if n and n > 0 and len(t) > n:
        t = t[:n].rstrip('；;，,、。 ') + '…'
    return t


def clip_senses(t, n):
    """按义项边界截断（优先在「；／，／。」处收尾，避免半句被截）。"""
    t = re.sub(r'\s+', ' ', str(t or '')).strip().strip('；;，,、。 ')
    if not n or n <= 0 or len(t) <= n:
        return t
    head = t[:n]
    cut = max(head.rfind('；'), head.rfind(';'), head.rfind('，'), head.rfind('。'))
    if cut >= n * 0.6:
        head = head[:cut]
    return head.rstrip('；;，,、。 ') + '…'


def strip_self_ref(t, *chars):
    """去掉「同'X'：」「同’X’：」这类**自我引用**前缀（X 与检索字或简繁对应字相同时才去）。"""
    if not t:
        return t
    for ch in chars:
        if not ch:
            continue
        m = re.match(r"^同\s*['\u2018\u201c\"]?\s*%s\s*['\u2019\u201d\"]?\s*[：:]\s*" % re.escape(ch), t)
        if m:
            t = t[m.end():].strip()
            break
    return t


def char_variants(rows):
    """从词表自身推「繁↔简」单字对应：只取**长度一致且繁简不同**的行（無學→无学 ⇒ 無↔无、學↔学）。

    仅供 strip_self_ref 判定「同'X'：」是不是自我引用（如简体词 无不 的单字释义以 同'無'： 开头）。
    """
    pairs = {}
    for r in rows:
        w = str(r[0] or '')
        s = str(r[1]) if len(r) > 1 and r[1] else ''
        if not s or s == w or len(s) != len(w):
            continue
        for a, b in zip(w, s):
            if a != b:
                pairs.setdefault(a, set()).add(b)
                pairs.setdefault(b, set()).add(a)
    return pairs


def as_text(v):
    """把来源值归一为释义字符串：兼容 str / list / {'definition'|'zh_cn'|'zh'|'en'}。"""
    if not v:
        return ''
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (list, tuple)):
        return '；'.join(x for x in (as_text(i) for i in v) if x)
    if isinstance(v, dict):
        for k in ('definition', 'zh_cn', 'zh', 'gloss', 'zh_tw', 'en'):
            t = as_text(v.get(k))
            if t:
                return t
    return ''


def load_zh_word_srcs(paths=(), auto=True):
    """载入词级中文源 `{词: 释义}`（只取 len(词) ≥ 2，先到先得，不覆盖已有键）。

    返回 (merged_dict, used_list)；used_list = [(abspath, 条数), …]，供 _meta 记录。
    """
    cands = []
    if auto:                                    # data/ 自动发现（说文／康熙／多字词表…）
        for name in AUTO_ZH_SRC:
            for base in (os.path.join(BASE, 'data'), BASE):
                p = os.path.join(base, name)
                if os.path.exists(p) and p not in cands:
                    cands.append(p)
    for p in (paths or []):
        if p not in cands:
            cands.append(p)
    out, used = {}, []
    for p in cands:
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
        except Exception as e:
            print('  ⚠️ 词级源载入失败（跳过）：%s ← %s' % (p, e), file=sys.stderr)
            continue
        if not isinstance(d, dict):
            print('  ⚠️ 词级源不是 {词: 释义} 对象（跳过）：%s' % p, file=sys.stderr)
            continue
        n = 0
        for k, v in d.items():
            k, t = str(k), as_text(v)
            if len(k) < 2 or not t or k in out:
                continue
            out[k] = t
            n += 1
        used.append((os.path.abspath(p), n))
    return out, used


class Sources(object):
    """释义来源容器：默认从 gloss_lib 惰性取数；**全部访问都走本类方法**，
    自测时可注入纯字典（不碰磁盘/网络）。传 None = 用 gloss_lib；传 {} = 空源。"""

    def __init__(self, zh_word=None, overrides=None, xinhua=None, cedict=None,
                 mma=None, ecdict=None, api=None, use_network=False):
        self.zh_word = dict(zh_word or {})      # 词级中文源（已合并）
        self._ovr, self._xh = overrides, xinhua
        self._cd, self._mma = cedict, mma
        self._ec, self._api = ecdict, api       # ecdict: {词: 释义}；api: 网络词典缓存
        self.use_network = use_network

    # ---- 惰性磁盘源（首次访问才读） ----
    def ovr(self):
        if self._ovr is None:
            self._ovr = dict((str(k), as_text(v))
                             for k, v in (G.overrides() if G else {}).items())
        return self._ovr or {}

    def word_zh(self, key):
        """词级中文释义 → (释义, 来源)：词级源 → 人工覆盖。"""
        t = as_text(self.zh_word.get(key))
        if t:
            return t, 'zh-word'
        return as_text(self.ovr().get(key)), 'override'

    def char_zh(self, ch, simp=''):
        """单字中文释义 → (释义, 来源)：人工覆盖 → 新华字典 → CC-CEDICT → makemeahanzi。"""
        for k in ((ch, simp) if simp and simp != ch else (ch,)):
            t = as_text(self.ovr().get(k))
            if t:
                return t, 'override'
        if self._xh is not None:
            t = as_text(self._xh.get(ch) or (simp and self._xh.get(simp)))
        else:
            t = as_text(G.xinhua_zh(ch, simp or ch)) if G else ''
        if t:
            return t, 'xinhua'
        if self._cd is not None:
            t = as_text(self._cd.get(ch) or (simp and self._cd.get(simp)))
        else:
            t = as_text(G.cedict_en(ch)) if G else ''
        if t:
            return t, 'cedict'
        if self._mma is not None:
            t = as_text(self._mma.get(ch) or (simp and self._mma.get(simp)))
        else:
            t = as_text(G.en_fallback(ch)) if G else ''
        if t:
            return t, 'makemeahanzi'
        return '', ''

    def en_word(self, word):
        """英文词释义 → (释义, 来源)：覆盖 → ECDICT → 网络词典缓存（--network 才请求）。"""
        low = (word or '').lower()
        t = as_text(self.ovr().get(word)) or as_text(self.ovr().get(low))
        if t:
            return t, 'override'
        if self._ec is not None:
            t = as_text(self._ec.get(low))
            if t:
                return t, 'ecdict'
        elif G:
            for fn, src in ((G.ecdict_zh, 'ecdict-zh'), (G.ecdict_en, 'ecdict-en')):
                t = as_text(fn(word))
                if t:
                    return t, src
        if self._api is not None:
            t = as_text(self._api.get(low))
            if t:
                return t, 'api-cache'
        elif G:
            t = as_text(G.api_en(word, use_network=False))      # 只读缓存
            if t:
                return t, 'api-cache'
            if self.use_network:
                t = as_text(G.api_en(word, use_network=True))
                if t:
                    return t, 'api'
        return '', ''


def resolve_zh(word, simp, S, max_len=160, char_len=48, var_pairs=None):
    """中文词释义 → (definition, need_ai, source)。

    整词（词级源／覆盖）→ 单字链 → 逐字合成 → 待补。逐字合成不是真词义 → need_ai=True。
    var_pairs:「繁↔简」单字对应表（char_variants 产出），只用于去「同'X'：」自我引用。
    """
    vp = var_pairs or {}
    # 单字释义常以「同'X'：…」交叉引用同义形（X 为本字或繁简对应字）→ 视为自我引用，去掉前缀
    keys = [word] + ([simp] if simp and simp != word else [])
    for k in keys:
        t, src = S.word_zh(k)
        if t:
            return clip(t, max_len), False, src
    if len(word) == 1:
        t, src = S.char_zh(word, simp)
        if t:
            return clip(strip_self_ref(t, word, simp, *sorted(vp.get(word, ()))), max_len), False, src
        return PENDING, True, 'pending'
    parts = []
    # 繁体词的简体形按字对应（长度一致时）：单字链据此再查一次简体键（如 無 ← 无）
    s_chars = list(simp) if simp and len(simp) == len(word) else []
    for i, ch in enumerate(word):
        t, _src = S.char_zh(ch, s_chars[i] if s_chars else '')
        if t:
            alt = [s_chars[i] if s_chars else ''] + sorted(vp.get(ch, ()))
            parts.append(ch + '：' + clip_senses(strip_self_ref(t, ch, *alt), char_len))
    if parts:
        return clip_senses('；'.join(parts), max_len), True, 'zh-composite'
    return PENDING, True, 'pending'


def resolve_en(word, S, max_len=160):
    """英文词释义 → (definition, need_ai, source)。

    **整词精确匹配**：词形先过「最大词形」校验，绝不前缀/子串命中（mor 永不命中 morning）。
    """
    if not word or not is_max_en(word):
        return PENDING, True, 'illegal-form'
    t, src = S.en_word(word)
    if t:
        return clip(t, max_len), False, src
    return PENDING, True, 'pending'


def fill_rows(rows, lang, S, max_len=160):
    """行 → 6 元行。返回 (新行列表, 统计 Counter)。

    行 = [词形, 简体形(可空), 全库词次, 出现书数, definition, need_ai]
    **前四元逐项原样保留**（写后 verify 会比对），只在尾部追加两个字段。
    """
    out, stats = [], collections.Counter()
    var_pairs = char_variants(rows) if lang == 'zh' else {}   # 繁↔简单字对应（去自我引用用）
    for r in rows:
        base = [r[i] if i < len(r) else ('', '', 0, 0)[i] for i in range(4)]
        word = str(base[0] or '')
        simp = str(base[1]) if base[1] else ''
        if lang == 'zh':
            d, ai, src = resolve_zh(word, simp, S, max_len, var_pairs=var_pairs)
        else:
            d, ai, src = resolve_en(word, S, max_len)
        stats[src] += 1
        if src in ('pending', 'illegal-form'):
            stats['_pending'] += 1
        if ai:
            stats['_need_ai'] += 1
        out.append(base + [d, ai])
    return out, stats


def verify(path, zh_before, en_before):
    """回读校验：行数不变 / 行长度 = 6 / **前四元未被改动** / 词形合法。失败即抛错（不静默）。"""
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    zh, en = d.get('zh') or [], d.get('en') or []
    assert len(zh) == len(zh_before), 'zh 行数不一致：%d != %d' % (len(zh), len(zh_before))
    assert len(en) == len(en_before), 'en 行数不一致：%d != %d' % (len(en), len(en_before))
    for i, row in enumerate(zh):
        assert isinstance(row, list) and len(row) == 6, 'zh 行长度应为 6：%r' % (row,)
        assert list(row[:4]) == list(zh_before[i][:4]), 'zh 前四元被改动：%r' % (row,)
        assert is_pure_cjk(row[0]) and len(row[0]) >= 2, 'zh 词形非法：%r' % (row[0],)
        assert isinstance(row[4], str) and row[4], 'zh 释义非法：%r' % (row,)
        assert isinstance(row[5], bool), 'zh need_ai 应为布尔：%r' % (row,)
    for i, row in enumerate(en):
        assert isinstance(row, list) and len(row) == 6, 'en 行长度应为 6：%r' % (row,)
        assert list(row[:4]) == list(en_before[i][:4]), 'en 前四元被改动：%r' % (row,)
        assert is_max_en(row[0]), 'en 词形非法：%r' % (row[0],)
        assert isinstance(row[4], str) and row[4], 'en 释义非法：%r' % (row,)
        assert isinstance(row[5], bool), 'en need_ai 应为布尔：%r' % (row,)
    return len(zh), len(en)


def stat_line(name, rows, stats):
    """一行统计：行数 / 有释义 / 待补 / need_ai + 各来源计数。"""
    hit = sum(n for k, n in stats.items() if not k.startswith('_'))
    filled = hit - stats['_pending']
    srcs = '、'.join('%s %d' % (k, n) for k, n in sorted(stats.items())
                     if not k.startswith('_') and k not in ('pending', 'illegal-form'))
    return ('%s %d 行 ｜ 有释义 %d（%.1f%%）｜ 待补 %d ｜ need_ai %d%s'
            % (name, len(rows), filled, 100.0 * filled / max(1, len(rows)),
               stats['_pending'], stats['_need_ai'], ('  ← ' + srcs) if srcs else ''))


def selftest():
    """对抗性样例：整词优先 / 单字兜底 / 逐字合成 / 待补 + need_ai / 英文禁子串。"""
    import tempfile
    cases = []

    def check(name, cond, detail=None):
        cases.append((name, bool(cond), detail))

    S = Sources(zh_word={'君子': '有德之人；品格高尚者', '说服': '用言语使人信服'},
                overrides={'說': '①用话表达、讲话；②解释说明'},
                xinhua={'學': '学习；学问', '者': '助词，用在形容词后表人或事物', '无': "同'無'：没有；不"},
                cedict={}, mma={},
                ecdict={'morning': 'n. 早晨'},
                api={'walk': '走；步行'})

    d, ai, src = resolve_zh('君子', '', S)
    check('中文整词优先：词级源命中（君子）',
          d == '有德之人；品格高尚者' and ai is False and src == 'zh-word', (d, ai, src))

    d, ai, src = resolve_zh('說', '', S)
    check('中文单字链：人工覆盖优先（說）',
          d == '①用话表达、讲话；②解释说明' and ai is False and src == 'override', (d, ai, src))

    d, ai, src = resolve_zh('學', '', S)
    check('中文单字链：新华字典兜底（學）',
          d == '学习；学问' and ai is False and src == 'xinhua', (d, ai, src))

    d, ai, src = resolve_zh('學者', '', S)
    check('整词查不到 → 逐字合成（學者）+ need_ai',
          d == '學：学习；学问；者：助词，用在形容词后表人或事物'
          and ai is True and src == 'zh-composite', (d, ai, src))

    d, ai, src = resolve_zh('無學', '无学', S)
    check('繁体词逐字合成时按字回退简体形（無學 → 无 + 學）',
          d == '無：没有；不；學：学习；学问' and ai is True and src == 'zh-composite', (d, ai, src))

    d, ai, src = resolve_zh('說服', '说服', S)
    check('繁体词查不到时用简体形兜底（說服 → 说服）',
          d == '用言语使人信服' and ai is False and src == 'zh-word', (d, ai, src))

    d, ai, src = resolve_zh('獃獃', '', S)
    check('全无来源 → 待补 + need_ai（獃獃）',
          d == PENDING and ai is True and src == 'pending', (d, ai, src))

    d, ai, src = resolve_en('morning', S)
    check('英文整词命中（morning → ECDICT）',
          d == 'n. 早晨' and ai is False and src == 'ecdict', (d, ai, src))

    d, ai, src = resolve_en('walk', S)
    check('英文网络缓存兜底（walk → api-cache）',
          d == '走；步行' and ai is False and src == 'api-cache', (d, ai, src))

    d, ai, src = resolve_en('morn', S)
    check('英文禁前缀/子串：morn 不得命中 morning',
          d == PENDING and ai is True and src == 'pending', (d, ai, src))

    d, ai, src = resolve_en('mornin-', S)
    check('英文非法词形 → 待补（illegal-form）',
          d == PENDING and ai is True and src == 'illegal-form', (d, ai, src))

    rows = [['君子', '君子', 900, 20], ['學者', '学者', 120, 5], ['獃獃', '', 3, 1]]
    new, st = fill_rows(rows, 'zh', S)
    check('行扩成 6 元且前四元原样保留',
          all(len(r) == 6 and list(r[:4]) == list(rows[i][:4]) for i, r in enumerate(new)), new)
    check('need_ai 是布尔（不是 0/1）',
          all(r[5] is True or r[5] is False for r in new), [r[5] for r in new])
    check('统计：词级 1 / 合成 1 / 待补 1 / need_ai 2',
          st['zh-word'] == 1 and st['zh-composite'] == 1
          and st['_pending'] == 1 and st['_need_ai'] == 2, dict(st))
    new2, _ = fill_rows(rows, 'zh', S)
    check('幂等：重复回填结果一致', new == new2, new2)
    check('stat_line 可渲染', '中文 3 行' in stat_line('中文', rows, st), stat_line('中文', rows, st))

    tf = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump({'仁義': {'definition': '仁爱与正义'}, '天下': '普天之下',
               '仁': '单字不入词级源', '空': ''}, tf, ensure_ascii=False)
    tf.close()
    try:
        m, used = load_zh_word_srcs([tf.name], auto=False)
        check('词级源兼容 {词: 释义} / {词: {definition}}（忽略单字与空值）',
              m.get('仁義') == '仁爱与正义' and m.get('天下') == '普天之下'
              and '仁' not in m and '空' not in m, m)
        check('词级源被记录（used）', len(used) == 1 and used[0][1] == 2, used)
        S2 = Sources(zh_word=m, overrides={}, xinhua={}, cedict={}, mma={}, ecdict={}, api={})
        check('外部词级源参与解析（仁義 → zh-word）',
              resolve_zh('仁義', '', S2)[:2] == ('仁爱与正义', False), resolve_zh('仁義', '', S2))
    finally:
        os.unlink(tf.name)

    check('strip_self_ref：只去「同本字/简繁对应字」的自我引用前缀',
          strip_self_ref("同'無'：①没有", '無') == '①没有'
          and strip_self_ref("同'無'：①没有", '无', '無') == '①没有'
          and strip_self_ref("同'某'：①别的", '無', '无') == "同'某'：①别的"
          and strip_self_ref('①没有', '無') == '①没有', None)
    Sw = Sources(zh_word={}, overrides={}, xinhua={'无': "同'無'：①没有；②不"},
                 cedict={}, mma={}, ecdict={}, api={})
    check('繁↔简对应表：简体词的单字释义也去掉「同\'無\'：」自我引用',
          resolve_zh('无不', '', Sw)[0] == "无：同'無'：①没有；②不"
          and resolve_zh('无不', '', Sw, var_pairs={'无': {'無'}})[0] == '无：①没有；②不'
          and char_variants([['無學', '无学', 9, 2]]) == {'無': {'无'}, '无': {'無'},
                                                          '學': {'学'}, '学': {'學'}},
          [resolve_zh('无不', '', Sw)[0], resolve_zh('无不', '', Sw, var_pairs={'无': {'無'}})[0],
           char_variants([['無學', '无学', 9, 2]])])
    check('fill_rows 自动从词表推繁简对应（繁体行给出对应关系 → 简体行跟着去自我引用）',
          fill_rows([['無學', '无学', 9, 2], ['无不', '', 7, 3]], 'zh', Sw)[0][1][4]
          == '无：①没有；②不',
          fill_rows([['無學', '无学', 9, 2], ['无不', '', 7, 3]], 'zh', Sw)[0][1][4])
    check('clip_senses：义项边界收尾 / 无标点时硬截',
          clip_senses('①甲（甲甲）；②乙（乙乙）；③丙（丙丙）', 14) == '①甲（甲甲）；②乙（乙乙）…'
          and clip_senses('没有标点的长句子', 3) == '没有标…',
          [clip_senses('①甲（甲甲）；②乙（乙乙）；③丙（丙丙）', 14), clip_senses('没有标点的长句子', 3)])
    check('clip：压空白 / 去首尾标点 / 超长截断',
          clip('  a  b； ', 10) == 'a b' and clip('一二三四五', 3) == '一二三…',
          [clip('  a  b； ', 10), clip('一二三四五', 3)])
    check('as_text 兼容 str / list / 对象 / 空',
          as_text('x') == 'x' and as_text(['a', 'b']) == 'a；b'
          and as_text({'definition': 'd'}) == 'd' and as_text(None) == '', None)
    check('词形规则复用 build_vocab_final（君子 合法 / mornin- 非法）',
          is_pure_cjk('君子') and is_pure_cjk('獃獃') and not is_max_en('mornin-'), None)

    bad = [c for c in cases if not c[1]]
    for name, ok, detail in cases:
        print('  %s %s%s' % ('✅' if ok else '❌', name, '' if ok else '  ← %r' % (detail,)))
    print('自检：%d 通过 / %d 失败' % (len(cases) - len(bad), len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--in', dest='inp', default=IN_DEFAULT,
                    help='输入 vocab_final.json（4 或 6 元行）')
    ap.add_argument('--out', dest='out', default=None, help='输出路径（默认原地回写 --in）')
    ap.add_argument('--limit', type=int, default=0, help='只处理前 N 行（必须配 --out，抽样验证用）')
    ap.add_argument('--zh-word-src', dest='zh_src', action='append', default=[], metavar='PATH',
                    help='词级中文源 {词: 释义}，可重复（说文／康熙／CC-CEDICT 多字词…）')
    ap.add_argument('--no-auto-zh-src', dest='auto_zh', action='store_false', default=True,
                    help='不从 data/ 自动发现词级源')
    ap.add_argument('--network', action='store_true', help='允许网络词典补英文（默认只读缓存）')
    ap.add_argument('--max-len', type=int, default=160, help='单条释义长度上限（默认 160）')
    ap.add_argument('--dry-run', action='store_true', help='只打印统计，不写文件')
    ap.add_argument('--selftest', action='store_true', help='规则回归自检')
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    out_path = args.out or args.inp
    if args.limit and not args.dry_run and os.path.abspath(out_path) == os.path.abspath(args.inp):
        print('--limit 会截断词表，请配合 --out 另存（避免原地覆盖）', file=sys.stderr)
        return 2
    if not os.path.exists(args.inp):
        print('找不到输入：%s\n先跑：python3 文本/新书/build_vocab_final.py' % args.inp, file=sys.stderr)
        return 2

    t0 = time.time()
    with open(args.inp, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        print('输入不是对象（应为 {_meta, zh, en}）：%s' % args.inp, file=sys.stderr)
        return 2
    zh_before, en_before = data.get('zh') or [], data.get('en') or []
    if args.limit:
        zh_before, en_before = zh_before[:args.limit], en_before[:args.limit]

    zh_word, used = load_zh_word_srcs(args.zh_src, args.auto_zh)
    if used:
        print('词级中文源 %d 条（%s）' % (len(zh_word),
              '、'.join('%s %d' % (os.path.relpath(p, ROOT), n) for p, n in used)))
    else:
        print('词级中文源 0 条 → 多字词只能逐字合成／待补'
              '（放 data/shuowen.json 或用 --zh-word-src 可提供整词释义）')
    if not G:
        print('⚠️ gloss_lib 不可用 → 所有词判「待补」', file=sys.stderr)

    S = Sources(zh_word=zh_word, use_network=args.network)
    zh_new, st_zh = fill_rows(zh_before, 'zh', S, args.max_len)
    en_new, st_en = fill_rows(en_before, 'en', S, args.max_len)
    print(stat_line('中文', zh_before, st_zh))
    print(stat_line('英文', en_before, st_en))
    if args.dry_run:
        print('（--dry-run：未写文件）')
        for r in zh_new[:12]:
            print('   %s → %s%s' % (r[0], r[4], '  [need_ai]' if r[5] else ''))
        return 0

    meta = dict(data.get('_meta') or {})
    meta['generator'] = 'build_vocab_final.py + definition_fill.py'
    meta['fields'] = {'zh': ROW_FIELDS, 'en': ROW_FIELDS}
    meta['definition'] = {
        'generator': 'definition_fill.py',
        'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'fields': 'definition=释义（缺失为「待补」）｜need_ai=true = 释义缺失或仅逐字合成，待 AI 精修',
        'zh': dict(st_zh), 'en': dict(st_en),
        'zh_word_sources': [{'path': os.path.relpath(p, ROOT), 'entries': n} for p, n in used],
        'sources': ('中文：词级源(说文/康熙/多字词表) → 单字(人工覆盖→新华字典→CC-CEDICT'
                    '→makemeahanzi) → 逐字合成；英文：整词 ECDICT → 网络词典缓存'),
    }
    meta['usage'] = ('网站/js/vocab-matcher.js 建 Trie 做中文最长前缀匹配（词边界）；'
                     '释义内嵌行内 definition/need_ai，reader.js 词卡展示')
    out = dict(data)
    out['_meta'], out['zh'], out['en'] = meta, zh_new, en_new
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + '.part'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    os.replace(tmp, out_path)
    n_zh, n_en = verify(out_path, zh_before, en_before)
    size = os.path.getsize(out_path) / 1048576.0
    print('写出 %s ｜ 中文 %d + 英文 %d 行 ｜ %.2f MiB ｜ %.1f s'
          % (os.path.relpath(out_path, ROOT), n_zh, n_en, size, time.time() - t0))
    print('回读校验通过（行数不变 / 6 元行 / 前四元未改动 / 词形合法）')
    if size > 24:
        print('⚠️ 超过 Cloudflare 单文件 25 MiB 上限，请收紧词表或降低 --max-len', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
