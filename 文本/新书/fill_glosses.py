#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_glosses.py — 释义回填（中文：CC-CEDICT / 新华字典 / 人工精编 / pinyin-pro；
                              英文：ECDICT 英汉词典打底 + Free Dictionary API 网络释义）
=======================================================================
为全部注释单字/单词补齐 zh_cn/zh_tw/en/note，并写入四处：
  1) 文本/新书/wordbank.json                     规范词库（中文，后续入库可复用）
     文本/新书/wordbank_en.json                  规范词库（英文，后续入库可复用）
  2) data/books/*.json                           原始新书数据 annotations
  3) 网站/_site_data/{書名}.json                  阅读器单书 annotations
  4) 网站/_site_data/books.json                   聚合索引中的 annotations
附加标记：
  multi  : 是否多音字（pinyin-pro）
  rare   : 是否字频外生僻字（common_hanzi 之外）；英文词则按 ECDICT 词频判定
只改动每个 annotation 的 zh_cn/zh_tw/en/note/multi/rare（英文词另写音标到 pinyin），
其余字段原样保留。

用法：
  python3 fill_glosses.py                    # 中文 + 英文（英文缺英文释义时调网络词典 API）
  python3 fill_glosses.py --api-budget=8000  # 放大网络词典请求预算（缓存持久，可多次运行累积）
  python3 fill_glosses.py --no-network       # 离线：英文只用 ECDICT 打底
"""
import glob
import json
import os
import subprocess
import sys

import gloss_lib as G

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))          # 项目根
DATA_BOOKS = os.path.join(ROOT, 'data', 'books')
SITE_DATA = os.path.join(ROOT, '网站', '_site_data')
TS = json.load(open(os.path.join(BASE, 'trad_simp_map.json'), encoding='utf-8'))
COMMON = set(json.load(open(os.path.join(BASE, 'common_hanzi.json'), encoding='utf-8'))['chars'])
READINGS = json.load(open(os.path.join(BASE, 'data', 'pinyin_readings.json'), encoding='utf-8'))

def gloss_order(word_pys):
    """遍历顺序：先中文词、再英文词（英文按字典序 = 首字母聚簇）。

    ECDICT 释义按首字母分片存放，聚簇遍历可让每片只加载一次，
    避免 LRU 反复换入换出（分片最大约 7 MiB）。
    """
    zh = [w for w in word_pys if not G.is_english_word(w)]
    en = sorted(w for w in word_pys if G.is_english_word(w))
    return zh + en


def build_glosses(word_pys, overrides, use_network=True):
    """word -> {pinyin, zh_cn, en, multi, readings, rare, simp}

    中文词（CJK）：CC-CEDICT / 新华字典 / 人工精编（原逻辑不变）；
    英文词：ECDICT 英汉词典打底（zh_cn/en/音标），Free Dictionary API 兜底英文释义。
    """
    glosses = {}
    for w in gloss_order(word_pys):
        pys = word_pys[w]
        py = pys[0] if pys else ''
        if G.is_english_word(w):
            zh = overrides.get(w) or G.en_word_zh(w)
            en = G.en_word_en(w, use_network=use_network)
            glosses[w] = {
                'pinyin': py or G.en_word_phonetic(w),
                'zh_cn': zh or '',
                'en': en or '',
                'multi': False,
                'readings': '',
                'rare': G.en_word_rare(w),
                'simp': w,
            }
            continue
        simp = TS.get(w, w)
        zh = overrides.get(w) or G.xinhua_zh(w, simp, py)
        en = G.en_gloss(w, py)
        info = READINGS.get(w) or {}
        multi = bool(info.get('multiple'))
        readings = info.get('readings', '')
        rare = not (w in COMMON or simp in COMMON)
        glosses[w] = {
            'pinyin': py,
            'zh_cn': zh or '',
            'en': en or '',
            'multi': multi,
            'readings': readings or '',
            'rare': rare,
            'simp': simp,
        }
    return glosses


def make_traditional(items):
    """items: [{id, text}] -> {id: trad} 使用 tradify.js。"""
    items = [it for it in items if it.get('text')]
    if not items:
        return {}
    proc = subprocess.run(
        ['node', os.path.join(BASE, 'tradify.js')],
        input=json.dumps(items, ensure_ascii=False),
        capture_output=True, text=True, encoding='utf-8', timeout=600, cwd=BASE)
    if proc.returncode != 0:
        print('  ⚠️ tradify 异常:', proc.stderr.strip()[:200])
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def note_text(g):
    if g['multi'] and g['readings']:
        return '多音字，可讀「%s」，須依文意斷音。' % g['readings']
    return None


def collect_annotations():
    """返回 word -> [pinyin...] 全集。"""
    word_pys = {}
    files = list(glob.glob(os.path.join(DATA_BOOKS, '*.json')))
    files += list(glob.glob(os.path.join(SITE_DATA, '*.json')))
    for f in sorted(set(files)):
        if os.path.basename(f) == 'books.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for a in d.get('annotations', []):
            w = a.get('word', '')
            if not w:
                continue
            py = a.get('pinyin') or ''
            if py not in word_pys.setdefault(w, []):
                word_pys[w].append(py)
    return word_pys

def write_wordbank(glosses, trad_map):
    """中文词 → wordbank.json；英文词 → wordbank_en.json（避免污染中文分词词库）。"""
    out = {
        '_说明': '重难字词注释词库（fill_glosses.py 生成）：简体/繁体/英文释义 + 读音标记。',
        '_updated': 'auto',
        '_source': 'CC-CEDICT / 新华字典(chinese-xinhua) / 人工精编 gloss_override.json / pinyin-pro',
    }
    en_out = {
        '_说明': '英文重难词词库（fill_glosses.py 生成）：英文词 → 中文/英文释义 + 音标。',
        '_updated': 'auto',
        '_source': 'ECDICT(skywind3000/ECDICT, MIT) / Free Dictionary API(freedictionaryapi.com)',
    }
    for w in sorted(glosses):
        g = glosses[w]
        entry = {
            'pinyin': g['pinyin'],
            'zh_cn': g['zh_cn'] or None,
            'zh_tw': trad_map.get(g['zh_cn'], '') or None,
            'en': g['en'] or None,
            'rare': g['rare'],
            'is_difficult': True,
        }
        if G.is_english_word(w):
            en_out[w] = entry
            continue
        entry.update({'pinyin_notes': None, 'note': note_text(g),
                      'multi': g['multi'], 'readings': g['readings'] or None})
        out[w] = entry
    with open(os.path.join(BASE, 'wordbank.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('✅ wordbank.json:', len(out) - 3, '中文词条')
    if len(en_out) > 3:
        with open(os.path.join(BASE, 'wordbank_en.json'), 'w', encoding='utf-8') as f:
            json.dump(en_out, f, ensure_ascii=False, indent=1)
        print('✅ wordbank_en.json:', len(en_out) - 3, '英文词条')


def apply_glosses_to(anns, glosses, zh2tw, stats):
    """把释义写进一组 annotation。返回是否发生改动。"""
    touched = False
    for a in anns:
        w = a.get('word', '')
        g = glosses.get(w)
        if not g:
            continue
        stats['entries'] += 1
        zh_cn = g['zh_cn']
        zh_tw = zh2tw.get(zh_cn, '') if zh_cn else ''
        note = note_text(g)
        newvals = {
            'zh_cn': zh_cn or None,
            'zh_tw': zh_tw or None,
            'en': g['en'] or None,
            'note': note,
            'multi': g['multi'],
            'rare': g['rare'],
        }
        if G.is_english_word(w) and g['pinyin']:
            newvals['pinyin'] = g['pinyin']      # 英文词：音标写入 pinyin 字段
            stats['en_words'] += 1
        for k, v in newvals.items():
            if a.get(k) != v:
                touched = True
                a[k] = v
        if zh_cn:
            stats['zh'] += 1
        if zh_tw:
            stats['zh_tw'] += 1
        if g['en']:
            stats['en'] += 1
        if note:
            stats['note'] += 1
    return touched


def backfill_files(glosses, trad_map):
    """回填 annotations（zh_cn/zh_tw/en/note/multi/rare）。
    books.json 为「书名→书对象」字典，需逐书处理；其余为顶层 annotations。"""
    files = [os.path.join(SITE_DATA, 'books.json')]
    files += sorted(glob.glob(os.path.join(DATA_BOOKS, '*.json')))
    files += sorted(f for f in glob.glob(os.path.join(SITE_DATA, '*.json'))
                    if os.path.basename(f) != 'books.json')

    stats = {'entries': 0, 'zh': 0, 'zh_tw': 0, 'en': 0, 'note': 0, 'en_words': 0}
    changed_files = 0
    for f in files:
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        touched = False
        if os.path.basename(f) == 'books.json' and isinstance(d, dict):
            for v in d.values():
                anns = v.get('annotations') if isinstance(v, dict) else None
                if anns:
                    if apply_glosses_to(anns, glosses, trad_map, stats):
                        touched = True
        else:
            anns = d.get('annotations')
            if anns and apply_glosses_to(anns, glosses, trad_map, stats):
                touched = True
        if touched:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, indent=2)
            changed_files += 1
    print('✅ 回填文件数:', changed_files)
    print('   条目/简体/繁体/英文/note:', stats)



def main():
    no_network = '--no-network' in sys.argv        # 离线模式：只用 ECDICT 打底
    api_budget = 3000                              # 网络词典每次运行最多请求词数
    for a in sys.argv:
        if a.startswith('--api-budget='):
            try:
                api_budget = int(a.split('=', 1)[1])
            except ValueError:
                pass
    print('== 1) 汇总全注释词')
    word_pys = collect_annotations()
    n_en = sum(1 for w in word_pys if G.is_english_word(w))
    print('   唯一词:', len(word_pys), '（其中英文词:', n_en, '）')

    print('== 2) 英文网络释义预取（ECDICT 缺英文释义的词；预算 %d）' % api_budget)
    if not G.ecdict_available():
        print('   ⚠️ 缺 ECDICT 分片（data/ecdict_en/）：英文释义将只剩网络来源，'
              '请先运行 parse_ecdict.py')
    if no_network:
        print('   跳过（离线模式）')
    else:
        need = sorted(w for w in word_pys if G.is_english_word(w)
                      and G.en_word_needs_api(w))
        fetched, skipped = G.api_prefetch(need, budget=api_budget)
        print(f'   待取 {len(need)}，本次请求 {fetched}'
              + (f'，超预算跳过 {skipped}（可重跑或调大 --api-budget）' if skipped else ''))

    print('== 3) 计算释义')
    overrides = G.overrides()
    glosses = build_glosses(word_pys, overrides, use_network=False)
    zh_have = sum(1 for g in glosses.values() if g['zh_cn'])
    en_have = sum(1 for g in glosses.values() if g['en'])
    print('   词数:', len(glosses), '| 简体释义:', zh_have, '| 英文:', en_have)
    enw = [w for w in glosses if G.is_english_word(w)]
    if enw:
        en_zh = sum(1 for w in enw if glosses[w]['zh_cn'])
        en_ok = sum(1 for w in enw if glosses[w]['en'])
        en_ph = sum(1 for w in enw if glosses[w]['pinyin'])
        print(f'   英文词 {len(enw)}：中文释义 {en_zh} / 英文释义 {en_ok} / 音标 {en_ph}')

    print('== 4) 简体→繁体（opencc）')
    order = list(glosses.values())
    items = [{'id': i, 'text': g['zh_cn']} for i, g in enumerate(order)]
    trad_by_id = make_traditional(items)
    zh2tw = {}
    for i, g in enumerate(order):
        t = trad_by_id.get(str(i), '')
        if t:
            zh2tw[g['zh_cn']] = t
    print('   转换条数:', len(zh2tw))

    print('== 5) 写 wordbank.json / wordbank_en.json')
    write_wordbank(glosses, zh2tw)

    print('== 6) 回填 annotations')
    backfill_files(glosses, zh2tw)
    if not no_network:
        G.api_flush()                              # 网络词典缓存写盘
    print('完成。')



if __name__ == '__main__':
    main()

