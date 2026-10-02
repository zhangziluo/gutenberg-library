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


# ============================================================
# 智能分章：单页长文按「卷/回/篇/章/品/則/節/折」等标题行切分
#   —— 维基文库很多典籍是「一个页面放全文」，wiki 无 ==小标题== 也无子页，
#      toolkit 只能整页当 1 章；此处按中文古籍常见篇目行再切一次。
# ============================================================
# (标签, 正则)：按「命中行数最多」的那个模式切，避免误切
_SPLIT_PATTERNS = [
    ('卷', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}卷(?:[\s　].{0,24})?$')),
    ('回', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}回(?:[\s　].{0,24})?$')),
    ('篇', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}篇(?:[\s　].{0,24})?$')),
    ('章', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}章(?:[\s　].{0,24})?$')),
    ('品', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}品(?:[\s　].{0,24})?$')),
    ('則', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}則(?:[\s　].{0,24})?$')),
    ('節', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}節(?:[\s　].{0,24})?$')),
    ('折', re.compile(r'^第[〇零一二三四五六七八九十百千0-9]{1,6}折(?:[\s　].{0,24})?$')),
    ('卷', re.compile(r'^[卷篇部][上下中]$')),
    ('卷', re.compile(r'^[上下中][卷篇部]$')),
    ('卷', re.compile(r'^卷[〇零一二三四五六七八九十百千0-9]{1,6}(?:[\s　].{0,24})?$')),
    ('卷', re.compile(r'^[〇零一二三四五六七八九十百千]{1,6}卷(?:[\s　].{0,24})?$')),
    ('篇', re.compile(r'^(自序|原序|序言|序|前言|後序|跋|後記|凡例|緣起|楔子|'
                     r'引言|導言|緒論|緒言|附錄|外篇|附記|卷首)$')),
    ('篇', re.compile(r'^[〔【《][^〕】》]{1,24}[〕】》]$')),
    ('篇', re.compile(r'^其[〇零一二三四五六七八九十]+$')),
]
# 明显是目录/导航碎片的行（不作为切分点）
_TOC_NOISE = re.compile(r'(目錄|目次|全覽|全览|上一[章卷篇]|下一[章卷篇]|^[◄►←→\s]+$)')


def detect_split(lines):
    """返回 (标签, 切分行号列表)；不足以切分则 (None, [])。"""
    best = (None, [])
    for label, rx in _SPLIT_PATTERNS:
        idx = [i for i, ln in enumerate(lines)
               if rx.match(ln.strip()) and not _TOC_NOISE.search(ln)]
        if len(idx) >= 2 and len(idx) > len(best[1]):
            best = (label, idx)
    return best


def smart_split(text, title):
    """把单篇长文按篇目标题行切成 [{title, content}]；切不动返回 None。

    护栏：至少 2 个切分点；每段正文须 ≥ 40 字（过短的并入下一段）；切分点前若
    有前言（序/小引）则单独成一段。
    """
    lines = (text or "").split('\n')
    if len(lines) < 8:
        return None
    label, cuts = detect_split(lines)
    if label is None:
        return None
    bounds = list(cuts) + [len(lines)]
    # 切分点之前若有内容 → 前言段
    head = '\n'.join(lines[:cuts[0]]).strip()
    sections = []
    if len(head) >= 40:
        sections.append({'title': '序', 'content': head})
    for i, start in enumerate(cuts):
        end = bounds[i + 1]
        body = '\n'.join(lines[start + 1:end]).strip()
        chap_title = lines[start].strip()
        if len(body) < 40:
            # 太短：并入上一段（多为目录碎片/空章）
            if sections:
                sections[-1]['content'] = (sections[-1]['content'] + '\n' +
                                           chap_title + '\n' + body).strip()
            continue
        sections.append({'title': chap_title, 'content': chap_title + '\n' + body})
    if len(sections) < 2:
        return None
    return label, sections


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
    ap.add_argument("--title", default=None,
                    help="覆盖书名（默认用抓取结果的 book 字段；用于去掉「(四部叢刊本)」等版本后缀）")
    ap.add_argument("--author", default="佚名", help="作者（默认 佚名）")
    ap.add_argument("--category", default="子部", help="五部分类（默认 子部）")
    ap.add_argument("--subcategory", default="", help="子分类（如 蒙學 / 四書 / 小說家）")
    ap.add_argument("--label", default=None,
                    help="篇目标签（篇/回/卷/章；默认按智能分章结果自动判定，判不出用 篇）")
    ap.add_argument("--split", default="auto", choices=["auto", "none"],
                    help="智能分章：auto（默认识别单页长文的卷/回/篇/章…标题行并切分）/ none")
    ap.add_argument("--no-annotate", action="store_true",
                    help="不生成注释（默认会用词库给难字/词生成 annotations，供释义回填）")
    ap.add_argument("--no-merge", action="store_true", help="不重生成目录/阅读器数据")
    ap.add_argument("--force", action="store_true", help="存在受限/未知章节时仍导入（跳过它们）")
    args = ap.parse_args()

    src_path = resolve_json(args.json)
    if not os.path.isfile(src_path):
        print(f"❌ 找不到 novels_json 文件：{args.json}（已尝试 {src_path}）")
        sys.exit(1)

    novel = json.load(open(src_path, encoding="utf-8"))
    title = (args.title or novel.get("book") or "").strip()
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

    # ── 智能分章：单页长文 / 章数过少时，按卷/回/篇/章…标题行再切 ──
    detected_label = None
    if args.split != "none":
        expanded = []
        for ch in chapters:
            body = ch.get("content", "")
            if len(chapters) <= 2 and len(body) >= 2000:
                res = smart_split(body, ch.get("title", ""))
                if res:
                    lbl, secs = res
                    detected_label = detected_label or lbl
                    for s in secs:
                        s["source_url"] = ch.get("source_url", "")
                        s["license"] = ch.get("license", "")
                        s["revid"] = ch.get("revid")
                    print("  ✂️ 智能分章：《%s》%d 字 → %d %s"
                          % (ch.get("title", ""), len(body), len(secs), lbl))
                    expanded.extend(secs)
                    continue
            expanded.append(ch)
        if len(expanded) != len(chapters):
            chapters = expanded

    label = args.label or detected_label or "篇"

    out = {
        "book": title,
        "author": args.author,
        "category": args.category,
        "subcategory": args.subcategory,
        "section_label": label,
        "lang": "zh",
        "chapters": chapters,
    }

    # ── 生成注释（難字/詞）→ 写进正本顶层 annotations，供 fill_glosses 释义回填 ──
    if not args.no_annotate:
        sys.path.insert(0, BASE)
        import gutenberg_import
        reports = {}
        try:
            anns, pending = gutenberg_import.annotate_book(
                {"book": title}, chapters, reports)
            out["annotations"] = anns
            gutenberg_import.merge_pending(key, pending)
            r = reports.get(title, {})
            print("  📝 注释 %d 条（词库命中 %d，待补 %d）"
                  % (len(anns), r.get("wordbank_hits", 0), r.get("pending", 0)))
            if not anns:
                print("     ⚠️ 未产出注释（词库为空或正文过短）")
        except Exception as e:
            print("  ⚠️ 注释生成失败（跳过）：%s" % e)

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

