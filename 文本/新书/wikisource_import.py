#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wikisource_import.py —— 维基文库抓取结果 → 书库入库

把 wikisource_complete_toolkit 抓取的 novels_json/{书名}.json 转成站内
data/books/{key}.json 正本 + library-index.json 条目（source=维基文库），
并调用 merge_to_site() 重生成目录页数据（books-data.json）与阅读器数据。

用法：
  python3 wikisource_import.py --json novels_json/論語.json \\
      --key lunyu-ws --author 孔子 --category 經部 --subcategory 四書 --label 篇

  # 只转正本与索引、不重生成目录/阅读器
  python3 wikisource_import.py --json novels_json/論語.json --no-merge

  # 存在受限/未知章节时仍导入（跳过它们，其余入库）
  python3 wikisource_import.py --json novels_json/論語.json --force

合规：
  - 只有 safe_to_use=True 的章节进入书库；受限/未知章节默认导致中止（--force 跳过）。
  - 书目来源统一记为「维基文库」；正本携带 license 与 source_url 供追溯。
"""

import os
import re
import sys
import json
import hashlib
import argparse

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
DATA_BOOKS = os.path.join(ROOT, 'data', 'books')
WS_NOVELS = os.path.join(BASE, 'wikisource_complete_toolkit', 'novels_json')
LIB_INDEX = os.path.join(ROOT, 'library-index.json')

CAT_ORDER = ['經部', '史部', '子部', '集部', '近現代文學', '叢部']


def derive_key(title):
    """书名 → key（保留字母数字与汉字，其余转连字符；纯汉字时用汉字作 key）。"""
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.strip()).strip("-")
    if not s:
        s = "ws-" + hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    return s


def clean_text(text):
    """去掉 Wikisource 页头导航残留（含 ◄ ► 的标题栏 + 下一标题行）。"""
    lines = (text or "").split("\n")
    start = 0
    for i, ln in enumerate(lines[:20]):
        if "►" in ln:
            start = i + 2          # 跳过 ► 行及其后「下一章标题」行
            break
    while start < len(lines) and not lines[start].strip():
        start += 1
    body = [ln.rstrip() for ln in lines[start:]]
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


def resolve_json(path):
    if os.path.isfile(path):
        return path
    for cand in (os.path.join(WS_NOVELS, path),
                 os.path.join(WS_NOVELS, path + ".json")):
        if os.path.isfile(cand):
            return cand
    return path


def load_index():
    return json.load(open(LIB_INDEX, encoding="utf-8"))


def existing_titles(index):
    return {b["book"] for grp in index["categories"] for b in grp["books"]}


def existing_keys(index):
    return {b["key"] for grp in index["categories"] for b in grp["books"]}


def upsert_index(index, entry, category):
    """把条目放进指定分类（不存在则创建），保持 CAT_ORDER 顺序。"""
    for grp in index["categories"]:
        if grp["name"] == category:
            grp["books"].append(entry)
            return
    new = {"name": category, "books": [entry]}
    idx = CAT_ORDER.index(category) if category in CAT_ORDER else len(CAT_ORDER)
    index["categories"].insert(idx, new)


def main():
    ap = argparse.ArgumentParser(description="维基文库抓取结果 → 书库入库")
    ap.add_argument("--json", required=True, help="novels_json/{书名}.json 路径或书名")
    ap.add_argument("--key", help="入库 key（data/books/{key}.json；省略则从书名推导）")
    ap.add_argument("--author", default="佚名", help="作者（默认 佚名）")
    ap.add_argument("--category", default="子部", help="五部分类（默认 子部）")
    ap.add_argument("--subcategory", default="", help="子分类（如 蒙學 / 四書 / 小說家）")
    ap.add_argument("--label", default="篇", help="篇目标签（篇/回/卷/章，默认 篇）")
    ap.add_argument("--no-merge", action="store_true", help="不重生成目录/阅读器数据")
    ap.add_argument("--force", action="store_true", help="存在受限/未知章节时仍导入（跳过它们）")
    args = ap.parse_args()

    src_path = resolve_json(args.json)
    if not os.path.isfile(src_path):
        print(f"❌ 找不到 novels_json 文件：{args.json}（已尝试 {src_path}）")
        sys.exit(1)

    novel = json.load(open(src_path, encoding="utf-8"))
    title = (novel.get("book") or "").strip()
    if not title:
        print("❌ 抓取结果缺少 book 字段，无法入库")
        sys.exit(1)

    index = load_index()
    if title in existing_titles(index):
        print(f"❌ 书库已有同名书《{title}》，站内按书名定位会冲突，请先处理重名问题")
        sys.exit(1)

    key = args.key or derive_key(title)
    if key in existing_keys(index) or os.path.exists(os.path.join(DATA_BOOKS, key + ".json")):
        print(f"❌ key「{key}」已存在，请用 --key 指定另一个 key")
        sys.exit(1)

    chapters_in = novel.get("chapters", [])
    unsafe = [c for c in chapters_in if not c.get("safe_to_use")]
    if unsafe and not args.force:
        print("⚠️  存在受限/未知许可的章节，默认中止（合规闸门）：")
        for c in unsafe:
            print(f"     {c.get('title')}  [{c.get('license', '未识别')}]")
        print("     如需跳过它们并导入其余章节，请加 --force")
        sys.exit(1)

    chapters = []
    for c in chapters_in:
        if not c.get("safe_to_use"):
            print(f"  ⚠️ 跳过受限章节：{c.get('title')}（{c.get('license', '未识别')}）")
            continue
        text = clean_text(c.get("content_text", ""))
        if not text.strip():
            print(f"  ⚠️ 跳过空章节：{c.get('title')}")
            continue
        chapters.append({
            "title": c.get("title", "").strip(),
            "content": text,
            "source_url": c.get("source_url", ""),
            "license": c.get("license", ""),
            "revid": c.get("revid"),
        })
    if not chapters:
        print("❌ 没有可入库的安全章节")
        sys.exit(1)

    out = {
        "book": title,
        "author": args.author,
        "category": args.category,
        "subcategory": args.subcategory,
        "section_label": args.label,
        "lang": "zh",
        "chapters": chapters,
    }
    out_path = os.path.join(DATA_BOOKS, key + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✅ 正本：{os.path.relpath(out_path, ROOT)}（{len(chapters)} 章）")

    entry = {
        "key": key, "book": title, "author": args.author,
        "subcategory": args.subcategory, "chapters": len(chapters),
        "source": "维基文库",
        "path": os.path.join("data", "books", key + ".json"),
    }
    upsert_index(index, entry, args.category)
    with open(LIB_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"✅ 索引：已加入《{title}》（{args.category} · 来源 维基文库）")

    if args.no_merge:
        print("（--no-merge：跳过目录/阅读器数据重建）")
        return

    sys.path.insert(0, BASE)
    import gutenberg_import
    import slim_books_index
    print("↻ 重建目录页 + 阅读器数据（merge_to_site）…")
    gutenberg_import.merge_to_site()
    # books.json 统一走 slim_books_index 的轻量格式（indent=1，与站内既有格式一致）
    slim_books_index.slim_into(os.path.join(ROOT, '网站', '_site_data'))
    print(f"✅ 完成：《{title}》已进书库（目录页将显示来源「维基文库」）")


if __name__ == "__main__":
    main()

