# -*- coding: utf-8 -*-
"""
gloss_lib.py — 释义数据核心库
=============================
供 fill_glosses.py 使用。为每个待补单字提供：
  en    : CC-CEDICT 英文释义（按读音匹配，取前若干词义）
  zh_cn : 简体释义（优先级：人工精编 override > 新华字典现代义项自动提取）
数据来源（仓库内）：
  data/cedict_single.json   CC-CEDICT 单字词条子集
  data/xinhua_word.json     新华字典 word.json 子集
  data/gloss_override.json  人工精编常用字简体释义
  data/pinyin_readings.json pinyin-pro 多音候选（仅用于 multi 标记，不由本库提供）
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

TONE_LETTERS = ('A-Za-z\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8\u012b\u00ed'
                '\u01d0\u00ec\u014d\u00f3\u01d2\u00f2\u016b\u00fa\u01d4\u00f9'
                '\u01d6\u01d8\u01da\u01dc\u00fc\u0251\u0261\u0144\u0148\u01f9\u00ea')
_TONE_MAP = dict(zip('\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8\u012b\u00ed'
                     '\u01d0\u00ec\u014d\u00f3\u01d2\u00f2\u016b\u00fa\u01d4\u00f9'
                     '\u01d6\u01d8\u01da\u01dc\u00fc',
                     ['a', 'a', 'a', 'a', 'e', 'e', 'e', 'e', 'i', 'i', 'i', 'i',
                      'o', 'o', 'o', 'o', 'u', 'u', 'u', 'u', 'u', 'u', 'u', 'u']))


def toneless(s):
    """去掉声调，用于读音比较（兼容符号声调 lè 与数字声调 le4）。"""
    if not s:
        return ''
    s = re.sub(r'[\u0300-\u036f]', '', s)
    s = ''.join(_TONE_MAP.get(c, c) for c in s)
    # 去数字声调标记（CC-CEDICT：gei3 / xiang2）
    s = re.sub(r'[0-5]', '', s)
    return s.strip().lower()



def _load(name, fallback):
    for base in (os.path.join(BASE, 'data'), BASE):
        p = os.path.join(base, name)
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    return fallback



# ---------- CC-CEDICT ----------
_CEDICT = None


def cedict():
    global _CEDICT
    if _CEDICT is None:
        _CEDICT = _load('cedict_single.json', {})
    return _CEDICT


def cedict_en(word, py=''):
    """按读音匹配 CC-CEDICT 英文释义；未命中读音则取全部词义；无词条则 ''。"""
    info = cedict().get(word)
    if not info:
        return ''
    readings = info.get('readings') or []
    t = toneless(py)
    if t:
        matched = [r for r in readings if toneless(r.get('py')) == t]
        if matched:
            readings = matched

    def pick(rs):
        gl = []
        for r in rs:
            for g in r.get('glosses') or []:
                g = g.strip()
                low = g.lower()
                if not g:
                    continue
                if low.startswith('old variant') or low.startswith('variant of'):
                    continue
                if 'used in ' + word.lower() == low or low.startswith('used in '):
                    continue
                gl.append(g)
                if len(gl) >= 3:
                    return gl
        return gl

    glosses = pick(readings)
    if not glosses and t:
        glosses = pick(info.get('readings') or [])
    return '\uff1b'.join(glosses) if glosses else ''



def cedict_readings(word):
    """返回去重去声调读音列表。"""
    info = cedict().get(word)
    out = []
    if info:
        for r in info.get('readings') or []:
            t = toneless(r.get('py'))
            if t and t not in out:
                out.append(t)
    return out


# ---------- makemeahanzi（CC-CEDICT 派生单字释义）英文兜底 ----------
_MMA = None
_TS = None


def _ts_map():
    global _TS
    if _TS is None:
        _TS = _load('trad_simp_map.json', {}) or {}
    return _TS


def _mma():
    global _MMA
    if _MMA is None:
        _MMA = _load('makemeahanzi_sub.json', {})
    return _MMA


def en_fallback(word):
    """CC-CEDICT 查不到时，用 makemeahanzi 的英文定义兜底。"""
    d = _mma()
    v = d.get(word)
    if v:
        return v
    s = _ts_map().get(word)
    if s:
        v = d.get(s)
    return v or ''


def en_gloss(word, py=''):
    """英文释义综合入口：CC-CEDICT → makemeahanzi。"""
    g = cedict_en(word, py)
    if not g:
        g = en_fallback(word)
    return g or ''


# ---------- 新华字典自动提取 ----------
_XHB = None
_SENSE_MARK_RE = re.compile(r'^[\u2488-\u249b\u2460-\u2473]')
_VERBOSE_HINTS = ('\u300a', '--', '\u53c8\u5982', '\u540c\u672c\u4e49', '(\u8c61\u5f62',
                  '(\u4f1a\u610f', '\u300b', '\u540c\u4e49', '\u53e6\u89c1', '\u5b57\u6e90')



def _xhb():
    global _XHB
    if _XHB is None:
        _XHB = _load('xinhua_word.json', {})
    return _XHB


def _block_score(text):
    sc = 0
    if re.search(r'[\u2488-\u249b\u2460-\u2473]', text):
        sc += 4
    if re.search(r'(?<!\d)\d{1,2}[.、](?!\d)', text):
        sc += 2
    if '\uff5e' in text:
        sc += 1
    if len(text) < 60:
        sc += 1
    for h in _VERBOSE_HINTS:
        if h in text:
            sc -= 3
    return sc


def _reading_blocks(word, simp):
    """word=注释用字（繁/简），simp=查表用简体。返回 [(toneless_py, block_text)]。"""
    e = _xhb().get(simp)
    if not e:
        return []
    exp = e.get('explanation') or ''
    variants = {simp}
    ow = e.get('oldword') or simp
    if ow:
        variants.add(ow)
    if word != simp:
        variants.add(word)
    alt = '|'.join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    pat = re.compile(r'(?m)^[ \t\u3000]*(?:' + alt +
                     r')(?:[（(][^）)]{1,4}[）)])?[ \t\u3000]*([' + TONE_LETTERS + r']{1,8})')
    blocks = []
    for m in pat.finditer(exp):
        start = m.end()
        nxt = pat.search(exp, start)
        end = nxt.start() if nxt else len(exp)
        block = exp[start:end].strip()
        if block:
            blocks.append((toneless(m.group(1)), block))
    return blocks


def _clean_gloss(block, max_senses=5):
    parts = []
    buf = ''
    for ch in block:
        if _SENSE_MARK_RE.match(ch):
            if buf.strip():
                parts.append(buf)
            buf = ''
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    out = []
    for p in parts:
        p = p.strip()
        idx = p.find('\uff5e')
        if idx >= 0:
            p = p[:idx]
        p = re.sub(r'\s+', '', p)
        p = p.rstrip('\u3002\uff1b;,\uff0c.\uff0e\uff1a:')
        p = re.split(r'\u300a|--', p)[0].strip()
        if not p:
            continue
        out.append(p)
        if len(out) >= max_senses:
            break
    return out


def xinhua_zh(word, simp, py=''):
    """新华字典自动简体释义。无则 ''。"""
    blocks = _reading_blocks(word, simp)
    if not blocks:
        return ''
    tt = toneless(py)
    scored = [(b[0], _block_score(b[1]), b[1]) for b in blocks]
    scored.sort(key=lambda x: (x[0] == tt, x[1]), reverse=True)
    best = scored[0][2]
    senses = _clean_gloss(best)
    return '\uff1b'.join(senses) if senses else ''


# ---------- 人工精编覆盖 ----------
_OVR = None


def overrides():
    global _OVR
    if _OVR is None:
        _OVR = _load('gloss_override.json', {})
    return _OVR
