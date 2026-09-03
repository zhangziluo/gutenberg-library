#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slim_books_index.py — 把 books.json 重建为「轻量书库目录」。
--------------------------------------------------------
输入目录（默认为 网站/_site_data）：内含 {書名}.json（含 sections + annotations）。
输出 books.json = { 書名: { title, section_count, categories } }，
只作为首页书架的目录源；正文与注释一律从单书文件按需加载。

用法：
  python3 slim_books_index.py [目录]
  例：python3 文本/新书/slim_books_index.py 网站/_site_data
      python3 文本/新书/slim_books_index.py dist/_site_data   # 构建产物
"""
import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
DEFAULT = os.path.join(ROOT, '网站', '_site_data')


def slim_into(target):
    books = {}
    count = 0
    for f in sorted(glob.glob(os.path.join(target, '*.json'))):
        name = os.path.basename(f)
        if name == 'books.json':
            continue
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        title = d.get('title') or name[:-5]
        books[title] = {
            'title': title,
            'section_count': d.get('section_count', 0) or 0,
            'categories': d.get('categories', []) or [],
        }
        count += 1
    out = os.path.join(target, 'books.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(books, fh, ensure_ascii=False, indent=1)
    size = os.path.getsize(out)
    print('✅ %s → %d 本（%.2f MiB）' % (out, count, size / 1048576.0))
    return size


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    slim_into(target)
