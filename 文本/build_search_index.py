#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_search_index.py — 生成前端「目录层 + 快照层」搜索索引
================================================================
产物（网站/_site_data/search/）：
  meta.json      {built, books, sections, meta_books, snap_shards, snap_head, snap_tail, max_kb}
  titles.json    {"books":[{t,a,c,s,n,k}], "sections":[[bookIdx, secIdx, title, label], ...]}
                 —— 书名 / 作者 / 分类 + **全部篇目标题**（一次加载，秒查）
  snap/<n>.json  快照层分片（n = 0..SNAP_SHARDS-1）：
                 [[gIdx, bookIdx, secIdx, snapText], ...]
                 snapText = 该篇正文「前 H 字 + 尾 T 字」（已去零宽/折叠空白）
                 —— 按关键词定位到「书 → 篇」；前端并行取全部分片后扫一遍

元数据（书名 → 作者/分类）来源，按优先级合并（字段级补齐，谁有值用谁）：
  ① 网站/assets/data/books-data.json （书库页数据源，权威）
  ② library-index.json               （分类书目索引）
  ③ --meta <文件>（可多次）           （临时补充，如 `git show <rev>:…` 导出的旧书目）
  ④ 文本/新书/book_meta_full.json     （**累积档**：每次生成后把合并结果写回，只增不减）
  ⇒ 分批推送（push_batch.sh）会把 ①② 收窄成「累计到第 K 批」，靠 ④ 兜住历史元数据，
    否则已入库的书会**丢掉作者/分类**（实测：第 2 批把 115 本维基文库书的元数据挤掉过）。

要点：
  · 篇目顺序与前端 common.js orderedSections() 一致（复用 build_sentences.ordered_sections）
  · 分片书（超大字书）自动从 {书名}/{k}.json 拼回 sections
  · 快照按 gIdx % SNAP_SHARDS 分片 → 前端可并行 fetch、按 gIdx 还原绝对顺序

用法：
  python3 文本/build_search_index.py                 # 生成（并刷新累积档）
  python3 文本/build_search_index.py --dry-run       # 只统计体积，不写文件
  python3 文本/build_search_index.py --snap-head 160 --snap-tail 60 --shards 64
  python3 文本/build_search_index.py --meta /tmp/old-books-data.json
  python3 文本/build_search_index.py --no-meta-update # 不写累积档
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
LIB_INDEX = os.path.join(ROOT, 'library-index.json')
META_ARCHIVE = os.path.join(BASE, '新书', 'book_meta_full.json')   # 元数据累积档
META_FIELDS = ('author', 'cat', 'sub', 'n', 'k')
ARCHIVE_NOTE = ('书目元数据累积档（build_search_index.py 自动维护，勿手改）：'
                '把「书库数据源 / library-index / 历史全量」合并后的作者·分类按书名累积，'
                '分批推送（push_batch.sh）收窄聚合文件后仍能补齐元数据。')

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


def _load(path):
    """读 JSON；读不到/坏了都返回 None（元数据缺了也不该让索引生成失败）。"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _blank():
    return dict.fromkeys(META_FIELDS, '')


def _norm_books_data(d):
    """books-data.json → {title: {author, cat, sub, n, k}}。"""
    out = {}
    for b in (d or {}).get('books') or []:
        t = b.get('title')
        if not t:
            continue
        out[t] = {
            'author': b.get('author') or '',
            'cat': CAT_NAME.get(b.get('category') or '', ''),
            'sub': b.get('subcategory') or '',
            'n': b.get('sections') or 0,
            'k': b.get('book_id') or b.get('id') or '',
        }
    return out


def _norm_library_index(d):
    """library-index.json → {title: {author, cat, sub, n, k}}（分类取所在部名）。"""
    out = {}
    for c in (d or {}).get('categories') or []:
        for b in c.get('books') or []:
            t = b.get('book')
            if not t:
                continue
            out[t] = {
                'author': b.get('author') or '',
                'cat': c.get('name') or '',
                'sub': b.get('subcategory') or '',
                'n': b.get('chapters') or 0,
                'k': b.get('key') or '',
            }
    return out


def _norm_archive(d):
    """累积档（{_note, meta:{title:{author,cat,sub,n,k}}}）→ 同 schema 的 dict。"""
    out = {}
    for t, m in ((d or {}).get('meta') or {}).items():
        if isinstance(m, dict):
            out[t] = {k: m.get(k) or (0 if k == 'n' else '') for k in META_FIELDS}
    return out


def _norm_meta(d):
    """按结构自动识别：累积档 / books-data / library-index。"""
    if not isinstance(d, dict):
        return {}
    if 'meta' in d:
        return _norm_archive(d)
    if 'books' in d:
        return _norm_books_data(d)
    return _norm_library_index(d)


def _merge_meta(*sources):
    """多来源合并：字段级「先到先得」，后面的来源只补空值（不覆盖已有值）。"""
    out = {}
    for src in sources:
        for t, m in (src or {}).items():
            cur = out.setdefault(t, _blank())
            for k in META_FIELDS:
                v = m.get(k)
                if v and not cur[k]:
                    cur[k] = v
    return out


def load_meta(extra_paths=None):
    """书名 → {author, cat, sub, n, k}（见文件头「元数据来源」）。

    返回 (meta, archive)：archive 是「仅累积档」里的条目数，供打印统计用。
    """
    archive = _norm_archive(_load(META_ARCHIVE))
    sources = [_norm_books_data(_load(BOOKS_DATA)),
               _norm_library_index(_load(LIB_INDEX))]
    for p in extra_paths or []:
        d = _load(p)
        if d is None:
            print('⚠ 读不到 --meta 文件：%s（已跳过）' % p)
            continue
        sources.append(_norm_meta(d))
    sources.append(archive)
    return _merge_meta(*sources), archive


def write_meta_archive(meta):
    """把合并后的元数据写回累积档（只增不减；排序后落盘，便于 diff）。"""
    d = {'_note': ARCHIVE_NOTE,
         'books': len(meta),
         'meta': {t: meta[t] for t in sorted(meta)}}
    os.makedirs(os.path.dirname(META_ARCHIVE), exist_ok=True)
    with open(META_ARCHIVE, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    return META_ARCHIVE


def collect(meta):
    """遍历单书文件（含分片书）→ 书目 + 篇目列表。"""
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
    ap.add_argument('--meta', action='append', default=[], metavar='文件',
                    help='额外元数据来源（books-data / library-index / 累积档，可多次；补空不覆盖）')
    ap.add_argument('--no-meta-update', action='store_true',
                    help='不把合并结果写回累积档 文本/新书/book_meta_full.json')
    ap.add_argument('--dry-run', action='store_true', help='只统计，不写文件')
    args = ap.parse_args()

    meta, archive = load_meta(args.meta)
    books, sections = collect(meta)
    if not sections:
        sys.exit('没有读到任何篇目，先确认 网站/_site_data 是否就绪')

    with_meta = sum(1 for b in books if b['a'] or b['c'])
    print('元数据：累积档 %d 条 ｜ 本库挂上作者/分类 %d/%d 本'
          % (len(archive), with_meta, len(books)))

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

    meta_out = {'built': datetime.date.today().isoformat(),
                'books': len(books), 'sections': len(sections),
                'meta_books': with_meta,
                'snap_shards': args.shards, 'snap_head': args.snap_head,
                'snap_tail': args.snap_tail, 'max_kb': round(max_kb, 1),
                'note': '目录层 titles.json（书名/作者/分类 + 全部篇目标题）；'
                        '快照层 snap/{n}.json（每篇正文前 H 字 + 尾 T 字）'}
    with open(os.path.join(OUT, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(OUT, 'snap', '%d.json' % n))
                for n in range(args.shards))
    print('✅ 已写 %s（snap 合计 %.1f MB，单片最大 %.0f KB）'
          % (os.path.relpath(OUT, ROOT), total / 1048576, max_kb))

    if args.no_meta_update:
        print('（--no-meta-update：未刷新累积档）')
    else:
        p = write_meta_archive(meta)
        print('✅ 元数据累积档 %s（%d 条）' % (os.path.relpath(p, ROOT), len(meta)))


if __name__ == '__main__':
    main()

