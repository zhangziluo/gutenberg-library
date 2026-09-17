#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_ecdict.py — ECDICT 英汉词典解析（英文词释义数据源）
========================================================
把 ECDICT（skywind3000/ECDICT，MIT 协议、无版权）的 ecdict.csv 转成本项目用的
紧凑数据：

  data/ecdict_en/ecdict_{a..z}.json  英词 → {ph, en, zh, pos, frq, bnc}
                                     **按首字母分片**（每片 ≈ ≤8 MiB，避免 70+ MiB 单文件）
                                     fill_glosses.py 按首字母惰性加载 + LRU
  data/common_words_en.json          常用词表 {rank, words:[…]}
                                     （gutenberg_import.py 挑「英文难词」用）

用法：
  python3 parse_ecdict.py                      # 本地无 csv 时自动下载（约 63 MiB）
  python3 parse_ecdict.py --csv /path/ecdict.csv
  python3 parse_ecdict.py --rank 5000          # 常用词表规模（默认 5000）
  python3 parse_ecdict.py --only-annotations   # 仅保留已入库注释里的英文词（分片更小）

说明：
  · ECDICT csv 列为 word,phonetic,definition,translation,pos,collins,oxford,
    tag,bnc,frq,exchange,detail,audio；
    translation=中文释义、definition=英文释义、frq/bnc=语料库词频排名（0=未收录）。
  · 原始 csv 与生成的 json 均为本地构建数据，不进部署包（见 .gitignore）。
"""
import argparse
import csv
import glob
import json
import os
import re
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
DATA_DIR = os.path.join(BASE, 'data')

ECDICT_URL = 'https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv'
ECDICT_GIT = 'https://github.com/skywind3000/ECDICT.git'
DEFAULT_CSV = os.path.join(DATA_DIR, 'ecdict.csv')   # 本地缓存（已 gitignore）
ECDICT_DIR = os.path.join(DATA_DIR, 'ecdict_en')     # 释义分片目录（按首字母）
AZ = 'abcdefghijklmnopqrstuvwxyz'


def shard_of(key):
    """词 → 分片名：按首字母 a-z，其余归 other。"""
    ch = key[0] if key else ''
    return ch if ch in AZ else 'other'


def shard_path(letter):
    return os.path.join(ECDICT_DIR, 'ecdict_%s.json' % letter)

FIELDS = ['word', 'phonetic', 'definition', 'translation', 'pos', 'collins',
          'oxford', 'tag', 'bnc', 'frq', 'exchange', 'detail', 'audio']

# 词形规整：仅字母/撇号/连字符/点/空格，长度受限
WORD_OK_RE = re.compile(r"^[A-Za-z][A-Za-z'\-\. ]{0,39}$")
NET_SECTION_RE = re.compile(r'\n?\[网络\]')
HAN_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


def _clean(text, max_len=180):
    """ECDICT 释义清洗：去 [网络] 段、换行归一为「；」、限长。"""
    if not text:
        return ''
    t = text.replace('\r', '').replace('\\n', '\n')
    t = NET_SECTION_RE.split(t)[0]
    parts = [p.strip() for p in t.split('\n') if p.strip()]
    t = '；'.join(parts)
    t = re.sub(r'[ \t\u3000]+', ' ', t).strip()
    t = t.strip('；; ')
    if len(t) > max_len:
        t = t[:max_len].rstrip('；; ,，。.')
    return t


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _remote_size():
    """远端文件总字节数（Range 探测）。失败返回 0。"""
    try:
        import urllib.request
        req = urllib.request.Request(ECDICT_URL, headers={'Range': 'bytes=0-0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            cr = r.headers.get('Content-Range') or ''
            if '/' in cr:
                return int(cr.rsplit('/', 1)[1])
    except Exception:
        pass
    return 0


def _download_range(off, n):
    import urllib.request
    req = urllib.request.Request(
        ECDICT_URL, headers={'Range': 'bytes=%d-%d' % (off, off + n - 1)})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def download_csv(dest):
    """下载 ECDICT csv（断点续传 + 分块重试）。

    该文件约 63 MiB，raw.githubusercontent 在弱网下易超时/截断；
    若本函数反复失败，可改用 git 稀疏克隆（更快更稳）：
        git clone --depth 1 --filter=blob:none https://github.com/skywind3000/ECDICT.git /tmp/ecdict_git
        cp /tmp/ecdict_git/ecdict.csv <dest>
    """
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    total = _remote_size()
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if total and have >= total:
        print(f'✅ 已存在完整文件 {dest}（{have} 字节）')
        return
    if have:
        print(f'== 续传 {dest}：已有 {have}/{total or "?"} 字节')
    else:
        print(f'== 下载 ECDICT（约 63 MiB）→ {dest}')
        print(f'   {ECDICT_URL}')
    CHUNK = 4 << 20
    off = have
    fails = 0
    with open(dest, 'ab') as f:
        while True:
            n = CHUNK
            if total:
                if off >= total:
                    break
                n = min(CHUNK, total - off)
            try:
                data = _download_range(off, n)
            except Exception as e:
                fails += 1
                if fails >= 8:
                    raise SystemExit('❌ 下载失败（可改用 git 克隆，见 docstring）：%s' % e)
                time.sleep(3)
                continue
            if not data:
                break
            f.write(data)
            f.flush()
            off += len(data)
            if off % (16 << 20) < CHUNK:
                print(f'   … {off / 1048576:.1f} MiB', flush=True)
    print(f'✅ 下载完成 {os.path.getsize(dest) / 1048576:.1f} MiB')


def collect_annotation_words():
    """已入库注释里的英文词（data/books/*.json 与 网站/_site_data/*.json）。"""
    words = set()
    files = list(glob.glob(os.path.join(ROOT, 'data', 'books', '*.json')))
    files += list(glob.glob(os.path.join(ROOT, '网站', '_site_data', '*.json')))
    for f in sorted(set(files)):
        if os.path.basename(f) == 'books.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        anns = []
        if isinstance(d, dict):
            if d.get('annotations'):
                anns = d['annotations']
            else:                          # _site_data 聚合文件：书名 → 书对象
                for v in d.values():
                    if isinstance(v, dict) and v.get('annotations'):
                        anns += v['annotations']
        for a in anns:
            w = (a or {}).get('word') or ''
            if w and not HAN_RE.search(w) and re.match(r"^[A-Za-z][A-Za-z'\-]*$", w):
                words.add(w.lower())
    return words



def parse(csv_path, rank_limit, only_ann):
    only = collect_annotation_words() if only_ann else None
    if only_ann:
        print(f'== 仅保留已入库注释英文词：{len(only)} 个')

    buckets = {c: {} for c in AZ}
    buckets['other'] = {}
    common = []            # (best_rank, word)
    n_rows = n_kept = 0
    with open(csv_path, encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            n_rows += 1
            word = (row.get('word') or '').strip()
            if not word or not WORD_OK_RE.match(word) or HAN_RE.search(word):
                continue
            key = word.lower()
            if only is not None and key not in only:
                continue
            zh = _clean(row.get('translation'))
            en = _clean(row.get('definition'))
            if not zh and not en:
                continue
            frq = _to_int(row.get('frq'))
            bnc = _to_int(row.get('bnc'))
            rec = {'zh': zh, 'en': en,
                   'ph': (row.get('phonetic') or '').strip(),
                   'pos': (row.get('pos') or '').strip()}
            if frq:
                rec['frq'] = frq
            if bnc:
                rec['bnc'] = bnc
            buckets[shard_of(key)][key] = rec
            n_kept += 1
            ranks = [r for r in (frq, bnc) if r > 0]
            if ranks:
                common.append((min(ranks), key))

    common.sort()
    words, seen = [], set()
    for _, w in common:
        if w in seen:
            continue
        seen.add(w)
        words.append(w)
        if len(words) >= rank_limit:
            break

    print(f'   原始行 {n_rows:,} → 保留词条 {n_kept:,}（含中文或英文释义）')
    print(f'   常用词表（排名前 {rank_limit}）：{len(words)}')

    os.makedirs(ECDICT_DIR, exist_ok=True)
    # 改结构后清理：旧的单体文件 + 上一次残留的分片
    legacy = os.path.join(DATA_DIR, 'ecdict_en.json')
    if os.path.exists(legacy):
        os.remove(legacy)
        print(f'   （已移除旧单体文件 {os.path.relpath(legacy, ROOT)}）')
    for p in glob.glob(os.path.join(ECDICT_DIR, 'ecdict_*.json')):
        os.remove(p)

    total = biggest = kept = 0
    big_letter = '-'
    n_shards = 0
    for c in list(AZ) + ['other']:
        b = buckets[c]
        if not b:
            continue
        p = shard_path(c)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(b, f, ensure_ascii=False, separators=(',', ':'))
        sz = os.path.getsize(p)
        total += sz
        kept += len(b)
        n_shards += 1
        if sz > biggest:
            biggest, big_letter = sz, c
    print(f'✅ {os.path.relpath(ECDICT_DIR, ROOT)}：{kept:,} 词条 / {n_shards} 片 / '
          f'合计 {total / 1048576:.1f} MiB / 最大 {big_letter} 片 {biggest / 1048576:.1f} MiB')

    p2 = os.path.join(DATA_DIR, 'common_words_en.json')
    out = {
        '_source': 'ECDICT (skywind3000/ECDICT, MIT)；frq=当代语料库排名，bnc=BNC 语料库排名',
        '_note': '排名靠前的常见词不标注；排名超出本表的英文词判为难词。',
        'rank': rank_limit,
        'words': words,
    }
    with open(p2, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f'✅ {os.path.relpath(p2, ROOT)}  {len(words)} 词')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=DEFAULT_CSV, help='ECDICT csv 路径（缺失则下载）')
    ap.add_argument('--rank', type=int, default=5000, help='常用词表规模（默认 5000）')
    ap.add_argument('--only-annotations', action='store_true',
                    help='仅保留已入库注释中的英文词（各分片体积更小）')
    args = ap.parse_args()

    csv_path = args.csv
    if not (os.path.exists(csv_path) and os.path.getsize(csv_path) > (1 << 20)):
        csv_path = DEFAULT_CSV
        download_csv(csv_path)
    print(f'== 解析 {csv_path}（{os.path.getsize(csv_path) / 1048576:.1f} MiB）')
    parse(csv_path, args.rank, args.only_annotations)


if __name__ == '__main__':
    main()
