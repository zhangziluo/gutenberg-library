#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_search_index.py — 生成前端「目录层 + 快照层」搜索索引
================================================================
产物（网站/_site_data/search/）：
  meta.json      {built, books, sections, snap_shards, snap_head, snap_tail, max_kb}
  titles.json    {"books":[{t,a,c,s,n,k}], "sections":[[bookIdx, secIdx, title, label], ...]}
                 —— 书名 / 作者 / 分类 + **全部篇目标题**（一次加载，秒查）
  snap/<n>.json  快照层分片（n = 0..SNAP_SHARDS-1）：
                 [[gIdx, bookIdx, secIdx, snapText], ...]
                 snapText = 该篇正文「前 H 字 + 尾 T 字」（已去零宽/折叠空白）
                 —— 按关键词定位到「书 → 篇」；前端并行取全部分片后扫一遍

要点：
  · 篇目顺序与前端 common.js orderedSections() 一致（复用 build_sentences.ordered_sections）
  · 分片书（超大字书）自动从 {书名}/{k}.json 拼回 sections
  · 快照按 gIdx % SNAP_SHARDS 分片 → 前端可并行 fetch、按 gIdx 还原绝对顺序

用法：
  python3 文本/build_search_index.py                 # 生成
  python3 文本/build_search_index.py --dry-run       # 只统计体积，不写文件
  python3 文本/build_search_index.py --snap-head 160 --snap-tail 60 --shards 64
"""
import argparse
import datetime
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))            # 文本/
ROOT = os.path.dirname(BASE)
SD = os.path.join(ROOT, '网站', '_site_data')
OUT = os.path.join(SD, 'search')
BOOKS_DATA = os.path.join(ROOT, '网站', 'assets', 'data', 'books-data.json')

sys.path.insert(0, BASE)
from build_sentences import load_sections  # noqa: E402  （已按前端同序排好）

SKIP = {'books.json', 'vocab_final.json', 'dict_meta.json'}
INVISIBLE = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)
WS = re.compile(r'[ \t\u3000\xa0]+')
CAT_NAME = {'jing': '經部', 'shi': '史部', 'zi': '子部', 'ji': '集部', 'cong': '叢部'}


def clean(t):
    """去零宽字符、折叠空白、去首尾。"""
    return WS.sub(' ', (t or '').translate(INVISIBLE)).strip()


def snap_of(text, head, tail):
    """前 head 字 + 尾 tail 字（不足则整篇）。"""
    if len(text) <= head + tail:
        return text
    return text[:head] + ' … ' + text[-tail:]


def book_meta():
    """title → {author, cat 中文, sub, sections, key}（来自书库页数据源）。"""
    meta = {}
    try:
        d = json.load(open(BOOKS_DATA, encoding='utf-8'))
    except Exception:
        return meta
    for b in d.get('books') or []:
        meta[b.get('title')] = {
            'author': b.get('author') or '',
            'cat': CAT_NAME.get(b.get('category') or '', ''),
            'sub': b.get('subcategory') or '',
            'n': b.get('sections') or 0,
            'k': b.get('book_id') or b.get('id') or '',
        }
    return meta


def collect():
    """遍历单书文件（含分片书）→ 书目 + 篇目列表。"""
    meta = book_meta()
    books = []
    sections = []
    for fn in sorted(os.listdir(SD)):
        if not fn.endswith('.json') or fn in SKIP:
            continue
        title = fn[:-5]
        secs = load_sections(title)
        if not secs:
            continue
        m = meta.get(title) or {}
        bidx = len(books)
        books.append({'t': title, 'a': m.get('author', ''),
                      'c': m.get('cat', ''), 's': m.get('sub', ''),
                      'n': len(secs), 'k': m.get('k', '')})
        for si, s in enumerate(secs):
            sections.append({
                'g': len(sections), 'b': bidx, 'i': si,
                'title': clean(s.get('title') or ''),
                'label': s.get('category_label') or '',
                'text': clean(''.join(s.get('paragraphs') or [])),
            })
    return books, sections


def main():
    ap = argparse.ArgumentParser(description='生成搜索索引（目录层 + 快照层）')
    ap.add_argument('--snap-head', type=int, default=180, help='快照取正文前 N 字（默认 180）')
    ap.add_argument('--snap-tail', type=int, default=60, help='快照取正文尾 N 字（默认 60）')
    ap.add_argument('--shards', type=int, default=64, help='快照分片数（默认 64）')
    ap.add_argument('--dry-run', action='store_true', help='只统计，不写文件')
    args = ap.parse_args()

    books, sections = collect()
    if not sections:
        sys.exit('没有读到任何篇目，先确认 网站/_site_data 是否就绪')

    titles = {'books': books,
              'sections': [[s['b'], s['i'], s['title'], s['label']] for s in sections]}

    snap_bytes = 0
    for s in sections:
        s['snap'] = snap_of(s['text'], args.snap_head, args.snap_tail)
        snap_bytes += len(s['snap'].encode('utf-8'))

    titles_bytes = len(json.dumps(titles, ensure_ascii=False,
                                  separators=(',', ':')).encode('utf-8'))
    print('书目 %d 本 ｜ 篇目 %d 篇' % (len(books), len(sections)))
    print('  titles.json ≈ %.2f MB（%.0f KB）' % (titles_bytes / 1048576, titles_bytes / 1024))
    print('  snap/ 共 %d 片 ≈ %.2f MB（每片平均 %.0f KB）'
          % (args.shards, snap_bytes / 1048576, snap_bytes / 1024.0 / args.shards))
    print('  快照口径：正文前 %d 字 + 尾 %d 字' % (args.snap_head, args.snap_tail))

    if args.dry_run:
        print('（--dry-run：未写文件）')
        return

    os.makedirs(os.path.join(OUT, 'snap'), exist_ok=True)
    with open(os.path.join(OUT, 'titles.json'), 'w', encoding='utf-8') as f:
        json.dump(titles, f, ensure_ascii=False, separators=(',', ':'))

    max_kb = 0
    for n in range(args.shards):
        rows = [[s['g'], s['b'], s['i'], s['snap']]
                for s in sections if s['g'] % args.shards == n]
        p = os.path.join(OUT, 'snap', '%d.json' % n)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
        max_kb = max(max_kb, os.path.getsize(p) / 1024.0)

    meta = {'built': datetime.date.today().isoformat(),
            'books': len(books), 'sections': len(sections),
            'snap_shards': args.shards, 'snap_head': args.snap_head,
            'snap_tail': args.snap_tail, 'max_kb': round(max_kb, 1),
            'note': '目录层 titles.json（书名/作者/分类 + 全部篇目标题）；'
                    '快照层 snap/{n}.json（每篇正文前 H 字 + 尾 T 字）'}
    with open(os.path.join(OUT, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(OUT, 'snap', '%d.json' % n))
                for n in range(args.shards))
    print('✅ 已写 %s（snap 合计 %.1f MB，单片最大 %.0f KB）'
          % (os.path.relpath(OUT, ROOT), total / 1048576, max_kb))


if __name__ == '__main__':
    main()

