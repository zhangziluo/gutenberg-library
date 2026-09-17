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
import collections
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


# ---------- ECDICT 英汉词典（英文词释义：中/英/音标）----------
# 数据按首字母分片存放于 data/ecdict_en/ecdict_{a..z}.json（parse_ecdict.py 生成），
# 查询时按首字母惰性加载 + LRU 缓存，避免把 70+ MiB 全量词典一次性读进内存。
ECDICT_DIRNAME = 'ecdict_en'
ECDICT_MAX_SHARDS = 3          # 同时驻留内存的分片数上限（约 ≤20 MiB）
_AZ = 'abcdefghijklmnopqrstuvwxyz'
_ECDICT_CACHE = None


def _ecdict_shard_path(letter):
    return os.path.join(BASE, 'data', ECDICT_DIRNAME, 'ecdict_%s.json' % letter)


def ecdict_shard(letter):
    """按首字母惰性加载 ECDICT 分片（LRU 缓存）。缺失返回 {}。"""
    global _ECDICT_CACHE
    if _ECDICT_CACHE is None:
        _ECDICT_CACHE = collections.OrderedDict()
    d = _ECDICT_CACHE.get(letter)
    if d is not None:
        _ECDICT_CACHE.move_to_end(letter)
        return d
    p = _ecdict_shard_path(letter)
    d = {}
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
    _ECDICT_CACHE[letter] = d
    while len(_ECDICT_CACHE) > ECDICT_MAX_SHARDS:
        _ECDICT_CACHE.popitem(last=False)
    return d


def ecdict():
    """兼容旧接口：合并全部分片。注意会占用大量内存，一般无需调用。"""
    out = {}
    for letter in _AZ + 'other':
        out.update(ecdict_shard(letter))
    return out


def ecdict_available():
    """ECDICT 分片目录是否已就绪（供上层给出友好提示）。"""
    d = os.path.join(BASE, 'data', ECDICT_DIRNAME)
    return os.path.isdir(d) and any(
        os.path.exists(_ecdict_shard_path(c)) for c in _AZ)


def _en_base_forms(word):
    """英词简单屈折还原：返回候选原形（含自身，保序去重）。
    统一弯引号 ’ → '（正文用弯引号，词库多用直引号）。"""
    w = (word or '').strip().lower().replace('\u2019', "'")
    if not w:
        return []
    c = [w]
    if w.endswith("'s") and len(w) > 2:
        c.append(w[:-2])
    if w.endswith("'") and len(w) > 1:
        c.append(w[:-1])
    if w.endswith('ies') and len(w) > 3:
        c.append(w[:-3] + 'y')
    if w.endswith('es') and len(w) > 2:
        c.append(w[:-2])
    if w.endswith('s') and not w.endswith('ss') and len(w) > 1:
        c.append(w[:-1])
    if w.endswith('ed') and len(w) > 2:
        c += [w[:-2], w[:-1]]              # walked→walk, loved→love
    if w.endswith('ing') and len(w) > 3:
        c += [w[:-3], w[:-3] + 'e']        # walking→walk, making→make
    if w.endswith('er') and len(w) > 2:
        c.append(w[:-2])
    if w.endswith('est') and len(w) > 3:
        c.append(w[:-3])
    if w.endswith('ly') and len(w) > 3:
        c.append(w[:-2])
    out = []
    for x in c:
        if x and x not in out:
            out.append(x)
    return out


def ecdict_entry(word):
    """按词形（原形/小写/首字母大写）查 ECDICT 首字母分片；无则 None。"""
    for cand in _en_base_forms(word):
        ch = cand[0]
        letter = ch if (ch.isascii() and ch.isalpha()) else 'other'
        d = ecdict_shard(letter)
        if not d:
            continue
        for key in (cand, cand[:1].upper() + cand[1:]):
            v = d.get(key)
            if v:
                return v
    return None


def ecdict_zh(word):
    """中文释义（无则 ''）。"""
    v = ecdict_entry(word)
    return (v.get('zh') or '') if v else ''


def ecdict_en(word):
    """英文释义（无则 ''）。"""
    v = ecdict_entry(word)
    return (v.get('en') or '') if v else ''


def ecdict_phonetic(word):
    """音标（无则 ''）。"""
    v = ecdict_entry(word)
    return (v.get('ph') or '') if v else ''


# ---------- 网络词典 API（英文释义兜底） ----------
# 主源 freedictionaryapi.com（Wiktionary 派生，免费、无需 Key，含 IPA 音标）；
# 备源 dictionaryapi.dev。带本地缓存 + 并发 + 限速 + 失败静默降级。
API_PROVIDERS = [
    ('freedict', 'https://freedictionaryapi.com/api/v1/entries/en/%s'),
    ('dictionaryapi', 'https://api.dictionaryapi.dev/api/v2/entries/en/%s'),
]
API_TIMEOUT = 10
API_FALLBACK_TIMEOUT = 4      # 备用源超时（失败时快速熔断）
API_WORKERS = 6                # 并发请求数（对免费服务保持克制）
API_MIN_INTERVAL = 0.15        # 全局最小请求间隔（秒）
_API_CACHE = None
_API_DIRTY = False
_API_LOCK = None
_API_LAST = [0.0]
_API_DEAD = set()              # 连续失败后熔断的来源名
_API_FAILS = {}


def _api_cache_path():
    return os.path.join(BASE, 'data', 'ecdict_api_cache.json')


def _api_cache():
    global _API_CACHE
    if _API_CACHE is None:
        _API_CACHE = _load('ecdict_api_cache.json', {}) or {}
    return _API_CACHE


def _api_cache_save():
    if not _API_DIRTY:
        return
    p = _api_cache_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(_API_CACHE, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def _parse_freedict(data):
    """freedictionaryapi.com → (英文释义串, 音标)。"""
    glosses, ph = [], ''
    for ent in (data.get('entries') or []):
        lang = ((ent.get('language') or {}).get('code') or 'en')
        if lang != 'en':
            continue
        if not ph:
            for p in (ent.get('pronunciations') or []):
                if p.get('type') == 'ipa' and p.get('text'):
                    ph = p['text']
                    break
        pos = ent.get('partOfSpeech') or ''
        for s in (ent.get('senses') or []):
            t = (s.get('definition') or '').strip()
            if not t:
                continue
            glosses.append((pos + '. ' + t) if pos else t)
            if len(glosses) >= 2:
                break
        if len(glosses) >= 2:
            break
    return '；'.join(glosses), ph


def _parse_dictionaryapi(data):
    """dictionaryapi.dev → (英文释义串, 音标)。"""
    glosses, ph = [], ''
    if not isinstance(data, list):
        return '', ''
    for item in data:
        if not ph and item.get('phonetic'):
            ph = item['phonetic']
        for m in (item.get('meanings') or []):
            pos = m.get('partOfSpeech') or ''
            for d in (m.get('definitions') or []):
                t = (d.get('definition') or '').strip()
                if not t:
                    continue
                glosses.append((pos + '. ' + t) if pos else t)
                if len(glosses) >= 2:
                    break
            if len(glosses) >= 2:
                break
        if glosses:
            break
    return '；'.join(glosses), ph


def _api_request(url, timeout=None):
    """HTTP GET 一个词典 API（带全局最小间隔限速）。返回解析后的 JSON。"""
    import time
    import urllib.request
    lock = _API_LOCK
    if lock is not None:
        with lock:                                  # 限速：串行节流后再发请求
            wait = API_MIN_INTERVAL - (time.time() - _API_LAST[0])
            if wait > 0:
                time.sleep(wait)
            _API_LAST[0] = time.time()
    req = urllib.request.Request(url, headers={'User-Agent': 'gutenberg-reader/1.0'})
    with urllib.request.urlopen(req, timeout=timeout or API_TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def _api_fetch(word):
    """多源依次尝试，返回 {'en':…, 'ph':…}（全部失败则 {'en':'','ph':''}）。

    某来源连续失败 3 次即熔断（本次运行内不再访问），
    避免备用源不可达时每次白等超时。
    """
    key = (word or '').strip().lower()
    if not key:
        return {'en': '', 'ph': ''}
    en = ph = ''
    for idx, (name, tpl) in enumerate(API_PROVIDERS):
        if name in _API_DEAD:
            continue
        try:
            data = _api_request(tpl % key,
                                timeout=API_TIMEOUT if idx == 0 else API_FALLBACK_TIMEOUT)
        except Exception:
            _API_FAILS[name] = _API_FAILS.get(name, 0) + 1
            if _API_FAILS[name] >= 3:
                _API_DEAD.add(name)
            continue
        _API_FAILS[name] = 0
        en, ph = (_parse_freedict(data) if name == 'freedict'
                  else _parse_dictionaryapi(data))
        if en or ph:
            break
    return {'en': en, 'ph': ph}


def api_en(word, use_network=True):
    """网络英文释义（含缓存）；use_network=False 时只读缓存，不发请求。"""
    key = (word or '').strip().lower()
    if not key:
        return ''
    cache = _api_cache()
    if key in cache:
        return cache[key].get('en', '')
    if not use_network:
        return ''
    rec = _api_fetch(word)
    global _API_DIRTY
    cache[key] = rec
    _API_DIRTY = True
    return rec.get('en', '')


def api_phonetic(word):
    """网络词典音标（仅读缓存，不发请求；音标以 ECDICT 为主）。"""
    key = (word or '').strip().lower()
    if not key:
        return ''
    return (_api_cache().get(key) or {}).get('ph', '')


def api_prefetch(words, budget=0, progress=True):
    """并发预取一批英文词的网络释义（写入缓存）。budget=0 表示不限条数。

    返回 (新增条数, 跳过条数)。缓存持久化，多次运行可逐步覆盖。
    """
    global _API_DIRTY, _API_LOCK
    import threading
    from concurrent.futures import ThreadPoolExecutor
    cache = _api_cache()
    todo, seen = [], set()
    for w in words:
        k = (w or '').strip().lower()
        if not k or k in cache or k in seen:
            continue
        seen.add(k)
        todo.append(k)
    skipped = 0
    if budget and len(todo) > budget:
        skipped = len(todo) - budget
        todo = todo[:budget]
    if not todo:
        return 0, skipped
    _API_LOCK = threading.Lock()
    done = [0]

    def work(k):
        rec = _api_fetch(k)
        cache[k] = rec
        done[0] += 1
        if progress and done[0] % 200 == 0:
            _api_cache_save()                        # 增量存盘，中断可续
            print(f'      … 网络词典 {done[0]}/{len(todo)}', flush=True)
        return rec

    with ThreadPoolExecutor(max_workers=API_WORKERS) as ex:
        list(ex.map(work, todo))
    _API_DIRTY = True
    return len(todo), skipped


def api_flush():
    """把网络词典缓存写盘（批量流程末尾调用）。"""
    _api_cache_save()


# ---------- 英文词释义综合入口 ----------
def en_word_zh(word):
    """英文词中文释义：ECDICT（离线打底）。"""
    return ecdict_zh(word)


def en_word_en(word, use_network=True):
    """英文词英文释义：ECDICT 优先 → Free Dictionary API 兜底。"""
    g = ecdict_en(word)
    if g:
        return g
    return api_en(word, use_network=use_network)


def en_word_phonetic(word):
    """英文词音标：ECDICT（打底）→ 网络词典缓存；无则 ''。"""
    ph = ecdict_phonetic(word)
    if ph:
        return ph
    return api_phonetic(word)


def en_word_needs_api(word):
    """该英文词是否需要网络词典补充：缺英文释义或音标，且缓存中尚无记录。"""
    key = (word or '').strip().lower()
    if not key:
        return False
    if key in _api_cache():
        return False
    v = ecdict_entry(word)
    if not v:
        return True
    return not (v.get('en') and v.get('ph'))


def en_word_rare(word, hard_rank=20000):
    """英文词是否「很生僻」：ECDICT 未收录，或两语料库排名都超出 hard_rank。"""
    v = ecdict_entry(word)
    if not v:
        return True
    ranks = [r for r in (v.get('frq', 0), v.get('bnc', 0)) if r and r > 0]
    if not ranks:
        return True
    return min(ranks) > hard_rank


def is_english_word(word):
    """是否英文词（含 ASCII 字母且无 CJK）。"""
    if not word:
        return False
    if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', word):
        return False
    return bool(re.search(r'[A-Za-z]', word))


# ---------- 人工精编覆盖 ----------
_OVR = None


def overrides():
    global _OVR
    if _OVR is None:
        _OVR = _load('gloss_override.json', {})
    return _OVR
