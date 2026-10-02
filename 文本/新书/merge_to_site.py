#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_to_site.py — 由 data/books + library-index 重建站点数据（CLI 薄封装）
================================================================================
实际逻辑在 `gutenberg_import.merge_to_site()`（唯一实现，随新功能持续维护）。
本脚本只是给「手动改了 data/books 或 library-index.json 后，想重建站点数据」
提供一个好记的命令：

  1) 网站/_site_data/{书名}.json        阅读器单书（正文 + 注释）
  2) 网站/_site_data/books.json         轻量目录索引
  3) 网站/assets/data/books-data.json   书库页统一数据源

用法：
  python3 文本/新书/merge_to_site.py              # 重建
  python3 文本/新书/merge_to_site.py --dry-run    # 只检查输入，不写文件

注：本文件早期带一份独立实现（CAT_KEY 缺「叢部」，遇 叢部 书会 KeyError），
    已删除，统一走 gutenberg_import.merge_to_site()，避免两份实现漂移。
"""
import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
sys.path.insert(0, BASE)


def main():
    ap = argparse.ArgumentParser(
        description='重建站点数据（网站/_site_data + assets/data/books-data.json）')
    ap.add_argument('--dry-run', action='store_true', help='只检查输入，不写文件')
    args = ap.parse_args()

    lib = os.path.join(ROOT, 'library-index.json')
    books = os.path.join(ROOT, 'data', 'books')
    if not os.path.exists(lib):
        sys.exit('缺少 %s' % lib)
    if not os.path.isdir(books):
        sys.exit('缺少 %s（单书正本目录）' % books)

    if args.dry_run:
        d = json.load(open(lib, encoding='utf-8'))
        n = sum(len(c['books']) for c in d['categories'])
        print('library-index：%d 条；data/books：%d 个文件（--dry-run，未写文件）'
              % (n, len(os.listdir(books))))
        return

    import gutenberg_import
    import slim_books_index
    print('↻ merge_to_site …')
    gutenberg_import.merge_to_site()
    slim_books_index.slim_into(os.path.join(ROOT, '网站', '_site_data'))
    print('✅ 已重建 网站/_site_data/ 与 网站/assets/data/books-data.json')


if __name__ == '__main__':
    main()
