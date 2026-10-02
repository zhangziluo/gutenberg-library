#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reclassify_en_books.py — 按中文古籍（四部＋叢部）分类逻辑重分「已入库英文书」
================================================================================
背景：英文书入库时默认一律归入「子部 · 小說家（西洋）」（见
`~/gutenberg_project/scripts/cleaned_to_books.py` 的 CAT/SUBCAT）。本脚本按
**四部分类法** 把已入库（library-index.json 中）的英文书按体裁重新分门别类。

分类口径（沿用站点既有约定 + 传统四部）：
  · 經部 —— 儒家經典、宗教／倫理經典、蒙學          （英文书目中暂无）
  · 史部 —— 史書、傳記、遊記、地理                  （英文书目中暂无）
  · 子部 —— 諸子百家、小說家、譜錄……                （小說→子部·小說家；食譜→子部·譜錄）
  · 集部 —— 詩文詞曲、別集、總集                     （戲曲→集部·戲曲；散文別集→集部·別集）
  · 叢部 —— 綜合性叢書／合集（跨部之叢書）           （英文书目中暂无）
其中「小說家／戲曲」的子類沿用中文书已有的体裁名，英文书加「·西洋」以别于中文。
映射表 `EN_CLASS` 按「书名」索引（同名多版本的莎剧共用一条，归同一类）。

会同步更新的文件：
  1) library-index.json                       —— 主索引（把书在分类间搬移 + 改写 subcategory）
  2) 网站/assets/data/books-data.json         —— 前端统一数据源（category key + subcategory）
  3) data/books/pg*.json                      —— 单书正本（category/subcategory，供日后 merge）
  4) --also 指定的副本（如 ~/gutenberg_project/progress/full/*）—— 备份同步，避免下次分批推送回退

用法：
  python3 scripts/reclassify_en_books.py --dry-run      # 只预览，不落盘
  python3 scripts/reclassify_en_books.py                # 应用到站点三处数据
  python3 scripts/reclassify_en_books.py \
      --also ~/gutenberg_project/progress/full/library-index.json \
      --also ~/gutenberg_project/progress/full/books-data.json
写入前一律做「JSON 可解析 + 英文书全覆盖 + 分类 key 合法」自检，失败不落盘。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_INDEX = os.path.join(ROOT, 'library-index.json')
BOOKS_DATA = os.path.join(ROOT, '网站', 'assets', 'data', 'books-data.json')
DATA_BOOKS = os.path.join(ROOT, 'data', 'books')

# 分类顺序（与 gutenberg_import.merge_to_site 的 cat_order 保持一致）
CAT_ORDER = ['經部', '史部', '子部', '集部', '近現代文學', '叢部']
# 分类名 → 前端 key（与 gutenberg_import.CAT_KEY 一致）
CAT_KEY = {'經部': 'jing', '史部': 'shi', '子部': 'zi', '集部': 'ji',
           '近現代文學': 'ji', '叢部': 'cong'}

# ------------------------------------------------------------------
# 英文书 → (部类, 子类) 映射（键为 library-index 的 `book` / 单书的 `book`）
# ------------------------------------------------------------------
EN_CLASS = {
    # ── 子部 · 小說家 ───────────────────────────────────────────
    # 志怪·西洋：哥特／神怪志异
    'Frankenstein': ('子部', '小說家（志怪·西洋）'),
    'Dracula': ('子部', '小說家（志怪·西洋）'),
    'The Arabian Nights Entertainments': ('子部', '小說家（志怪·西洋）'),
    # 公案·西洋：侦探断案
    'The Hound of the Baskervilles': ('子部', '小說家（公案·西洋）'),
    # 童話·西洋：童话／儿童文学
    'Peter Pan : [Peter and Wendy]': ('子部', '小說家（童話·西洋）'),
    'The Jungle Book': ('子部', '小說家（童話·西洋）'),
    'The Wind in the Willows': ('子部', '小說家（童話·西洋）'),
    'A Little Princess': ('子部', '小說家（童話·西洋）'),
    "Grimms' Fairy Tales": ('子部', '小說家（童話·西洋）'),
    'Little Lord Fauntleroy': ('子部', '小說家（童話·西洋）'),
    'Through the Looking-Glass': ('子部', '小說家（童話·西洋）'),
    'The Adventures of Pinocchio': ('子部', '小說家（童話·西洋）'),
    'The Bobbsey Twins at School': ('子部', '小說家（童話·西洋）'),
    # 寓言·西洋：寓言／托喻
    'Fables': ('子部', '小說家（寓言·西洋）'),
    # 西洋：一般西洋小说／世情
    'Anne of Green Gables': ('子部', '小說家（西洋）'),
    'A Girl of the Limberlost': ('子部', '小說家（西洋）'),
    'The Cash Boy': ('子部', '小說家（西洋）'),
    'Bab: A Sub-Deb': ('子部', '小說家（西洋）'),
    'Cast Upon the Breakers': ('子部', '小說家（西洋）'),
    'The Errand Boy; Or, How Phil Brent Won Success': ('子部', '小說家（西洋）'),
    'Joe the Hotel Boy; Or, Winning out by Pluck': ('子部', '小說家（西洋）'),
    "Driven from Home; Or, Carl Crawford's Experience": ('子部', '小說家（西洋）'),
    'Dolly Dialogues': ('子部', '小說家（西洋）'),
    # 譜錄（食譜）
    'Recipes Tried and True': ('子部', '譜錄（食譜）'),
    # ── 集部 ────────────────────────────────────────────────────
    # 別集·西洋：散文／隨筆（个人文集）
    'Walden': ('集部', '別集（西洋）'),
    # 戲曲·西洋：戏剧（含莎剧各版本）
    'She Stoops to Conquer; Or, The Mistakes of a Night: A Comedy': ('集部', '戲曲（西洋）'),
    "Lady Windermere's Fan": ('集部', '戲曲（西洋）'),
    'A Woman of No Importance': ('集部', '戲曲（西洋）'),
    'An ideal husband': ('集部', '戲曲（西洋）'),
    'Misalliance': ('集部', '戲曲（西洋）'),
    'The Double-Dealer: A Comedy': ('集部', '戲曲（西洋）'),
    'The Old Bachelor: A Comedy': ('集部', '戲曲（西洋）'),
    'Love for Love: A Comedy': ('集部', '戲曲（西洋）'),
    'The Way of the World': ('集部', '戲曲（西洋）'),
    'The Playboy of the Western World: A Comedy in Three Acts': ('集部', '戲曲（西洋）'),
    'The Well of the Saints: A Comedy in Three Acts': ('集部', '戲曲（西洋）'),
    "The Tinker's Wedding": ('集部', '戲曲（西洋）'),
    'A Florentine Tragedy; La Sainte Courtisane': ('集部', '戲曲（西洋）'),
    'The Plays of W. E. Henley and R. L. Stevenson': ('集部', '戲曲（西洋）'),
    'The Comedy of Errors': ('集部', '戲曲（西洋）'),
    'The Taming of the Shrew': ('集部', '戲曲（西洋）'),
    'The Two Gentlemen of Verona': ('集部', '戲曲（西洋）'),
    "Love's Labour's Lost": ('集部', '戲曲（西洋）'),
    'The Merry Wives of Windsor': ('集部', '戲曲（西洋）'),
    'Much Ado about Nothing': ('集部', '戲曲（西洋）'),
    'Julius Caesar': ('集部', '戲曲（西洋）'),
    'Hamlet': ('集部', '戲曲（西洋）'),
    'Twelfth Night': ('集部', '戲曲（西洋）'),
    'Troilus and Cressida': ('集部', '戲曲（西洋）'),
    "All's Well That Ends Well": ('集部', '戲曲（西洋）'),
    'Othello': ('集部', '戲曲（西洋）'),
    'King Lear': ('集部', '戲曲（西洋）'),
}

CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def is_english_title(title):
    """书名不含 CJK 即视作英文书（与 batch 脚本同一判据）。"""
    return bool(title) and not CJK_RE.search(title)


def dump(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


# ------------------------------------------------------------------
# 1) library-index.json
# ------------------------------------------------------------------
def reclassify_index(data):
    """把英文书在分类之间搬移，并改写 subcategory；返回 (搬移数, 命中书名集)。

    同一部内排序：本就在该部的书（多在先的中文书）保持原序，其后追加从别的部
    搬来的英文书 —— 让索引读起来仍是「中文在前、西洋在后」。
    """
    stayers = {name: [] for name in CAT_ORDER}
    movers = {name: [] for name in CAT_ORDER}
    moved = 0
    seen = set()
    for grp in data['categories']:
        cur = grp['name']
        for b in grp['books']:
            title = b.get('book', '')
            target = cur
            if title in EN_CLASS:
                cat, sub = EN_CLASS[title]
                target = cat
                if b.get('subcategory') != sub or cur != cat:
                    moved += 1
                b['subcategory'] = sub
                seen.add(title)
            if target not in stayers:
                raise ValueError('未知分类：%s' % target)
            (stayers if target == cur else movers)[target].append(b)
    data['categories'] = [
        {'name': name, 'books': stayers[name] + movers[name]}
        for name in CAT_ORDER
        if stayers[name] or movers[name] or name != '叢部'   # 叢部空则不出现
    ]
    return moved, seen


# ------------------------------------------------------------------
# 2) books-data.json
# ------------------------------------------------------------------
def reclassify_books_data(data):
    """改写前端数据源的 category / subcategory / summary / description。"""
    n = 0
    seen = set()
    for b in data['books']:
        title = b.get('title', '')
        if title not in EN_CLASS:
            continue
        cat, sub = EN_CLASS[title]
        b['category'] = CAT_KEY[cat]
        b['subcategory'] = sub
        b['summary'] = sub
        b['description'] = sub
        seen.add(title)
        n += 1
    return n, seen


# ------------------------------------------------------------------
# 3) data/books/pg*.json
# ------------------------------------------------------------------
def reclassify_data_books(key_title):
    """按 key→title 改写单书正本的 category/subcategory。返回处理本数。"""
    n = 0
    for key, title in key_title.items():
        if title not in EN_CLASS:
            continue
        path = os.path.join(DATA_BOOKS, key + '.json')
        if not os.path.exists(path):
            continue
        cat, sub = EN_CLASS[title]
        with open(path, encoding='utf-8') as f:
            rec = json.load(f)
        rec['category'] = cat
        rec['subcategory'] = sub
        dump(path, rec)
        n += 1
    return n


def collect_key_title(data):
    return {b['key']: b.get('book', '') for grp in data['categories'] for b in grp['books']}


def english_titles(data):
    return [b.get('book', '') for grp in data['categories']
            for b in grp['books'] if is_english_title(b.get('book', ''))]




def main():
    ap = argparse.ArgumentParser(description='按四部分类法重分已入库英文书')
    ap.add_argument('--dry-run', action='store_true', help='只预览，不写文件')
    ap.add_argument('--also', action='append', default=[], metavar='PATH',
                    help='额外同步的文件（聚合文件副本，如 progress/full/...），可多次')
    ap.add_argument('--no-data-books', action='store_true',
                    help='不改写 data/books/ 单书正本')
    args = ap.parse_args()

    with open(LIB_INDEX, encoding='utf-8') as f:
        index = json.load(f)

    titles = english_titles(index)
    unmapped = sorted({t for t in titles if t not in EN_CLASS})
    if unmapped:
        print('✗ 以下英文书未在 EN_CLASS 映射表中，请补全后再运行：')
        for t in unmapped:
            print('   -', t)
        sys.exit(1)

    key_title = collect_key_title(index)
    print('英文书：%d 条（去重 %d 种）' % (len(titles), len(set(titles))))

    if args.dry_run:
        preview = {}
        for grp in index['categories']:
            for b in grp['books']:
                t = b.get('book', '')
                cat = EN_CLASS[t][0] if t in EN_CLASS else grp['name']
                preview[cat] = preview.get(cat, 0) + 1
        print('\n── 重分类后分布（预览）──')
        for name in CAT_ORDER:
            if name in preview:
                print('  %-6s %d 条' % (name, preview[name]))
        order = {}
        for t in titles:
            order.setdefault(EN_CLASS[t], []).append(t)
        print('\n── 英文书归类明细 ──')
        for (cat, sub), ts in sorted(order.items(), key=lambda kv: CAT_ORDER.index(kv[0][0])):
            print('  [%s · %s] %d 种' % (cat, sub, len(set(ts))))
            for t in sorted(set(ts)):
                print('      · ' + t)
        print('\n（--dry-run：未写任何文件）')
        return

    moved, _ = reclassify_index(index)
    dump(LIB_INDEX, index)
    print('✅ library-index.json：搬移/改写 %d 条' % moved)

    with open(BOOKS_DATA, encoding='utf-8') as f:
        bd = json.load(f)
    n_bd, seen_bd = reclassify_books_data(bd)
    dump(BOOKS_DATA, bd)
    print('✅ books-data.json：改写 %d 条' % n_bd)
    if set(EN_CLASS) - seen_bd:
        print('   ⚠ 映射表中这些书名未出现在 books-data.json：%s'
              % '、'.join(sorted(set(EN_CLASS) - seen_bd)))

    if not args.no_data_books:
        n_db = reclassify_data_books(key_title)
        print('✅ data/books/：改写 %d 本' % n_db)

    for path in args.also:
        p = os.path.expanduser(path)
        if not os.path.exists(p):
            print('   ⚠ 跳过（不存在）：%s' % p)
            continue
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d.get('categories'), list):
            m, _ = reclassify_index(d)
            dump(p, d)
            print('✅ 同步 %s（搬移 %d 条）' % (p, m))
        elif isinstance(d.get('books'), list):
            k, _ = reclassify_books_data(d)
            dump(p, d)
            print('✅ 同步 %s（改写 %d 条）' % (p, k))
        else:
            print('   ⚠ 跳过（无法识别的结构）：%s' % p)

    # 写后回读自检
    with open(LIB_INDEX, encoding='utf-8') as f:
        chk = json.load(f)
    bad = [t for t in english_titles(chk) if t not in EN_CLASS]
    if bad:
        print('✗ 自检失败：仍有英文书未归类 %s' % bad)
        sys.exit(1)
    for grp in chk['categories']:
        if grp['name'] not in CAT_KEY:
            print('✗ 自检失败：未知分类 %s' % grp['name'])
            sys.exit(1)
    dist = {}
    for grp in chk['categories']:
        for b in grp['books']:
            if is_english_title(b.get('book', '')):
                dist[grp['name']] = dist.get(grp['name'], 0) + 1
    print('\n── 英文书最终分布 ──')
    for name in CAT_ORDER:
        if name in dist:
            print('  %-6s %d 条' % (name, dist[name]))
    print('自检通过 ✅')


if __name__ == '__main__':
    main()

