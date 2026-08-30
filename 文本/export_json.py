#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古登堡中文古籍 → 结构化 JSON 导出（v2 修正版）
修正点：
  1. 分类匹配失败的篇一律打印，不再吞掉
  2. 自动校验每书应有序号连续性（如传 1-70）
  3. 文件名去重逻辑统一，避免 _2 后缀干扰计数
用法：放在 文本/ 目录下运行  python3 export_json.py
"""

import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_site_data")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------
# 工具：中文数字 → int
# ---------------------------------------------------------------
CN_NUM = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
    '二十一': 21, '二十二': 22, '二十三': 23, '二十四': 24, '二十五': 25,
    '二十六': 26, '二十七': 27, '二十八': 28, '二十九': 29, '三十': 30,
    '三十一': 31, '三十二': 32, '三十三': 33, '三十四': 34, '三十五': 35,
    '三十六': 36, '三十七': 37, '三十八': 38, '三十九': 39, '四十': 40,
    '四十一': 41, '四十二': 42, '四十三': 43, '四十四': 44, '四十五': 45,
    '四十六': 46, '四十七': 47, '四十八': 48, '四十九': 49, '五十': 50,
    '五十一': 51, '五十二': 52, '五十三': 53, '五十四': 54, '五十五': 55,
    '五十六': 56, '五十七': 57, '五十八': 58, '五十九': 59, '六十': 60,
    '六十一': 61, '六十二': 62, '六十三': 63, '六十四': 64, '六十五': 65,
    '六十六': 66, '六十七': 67, '六十八': 68, '六十九': 69, '七十': 70,
}


def cn_to_int(s):
    """把 '第十一' / '七十' 之类转成 int；纯阿拉伯数字也能处理"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    # 形如 "一十X" 的兜底（一般不会有）
    raise ValueError(f"无法解析中文数字: {s}")


# ---------------------------------------------------------------
# 每本书配置
# ---------------------------------------------------------------
BOOKS = {
    "史記": {
        # 👇 路径按你重命名后的实际目录填写
        "dir": os.path.join(BASE, "史記", "by_piece"),
        "cat_order": ["本紀", "表", "書", "世家", "列傳"],
        "cat_ids": {"本紀": "benji", "表": "biao", "書": "shu",
                    "世家": "shijia", "列傳": "liezhuan"},
        "cat_expected": {"本紀": 12, "表": 10, "書": 8, "世家": 30, "列傳": 70},
        # 从文件名（已去掉扩展名）里抽分类词
        "cat_from_title": lambda t: _extract_cat(t, ["本紀", "表", "書", "世家", "列傳"]),
        # 抽序号（用于校验连续性），返回 int 或 None
        "num_from_title": lambda t: _extract_num(t, ["本紀", "表", "書", "世家", "列傳"]),
    },
    "漢書": {
        "dir": os.path.join(BASE, "漢書", "by_piece"),
        "cat_order": ["紀", "表", "志", "傳"],
        "cat_ids": {"紀": "ji", "表": "biao", "志": "zhi", "傳": "zhuan"},
        "cat_expected": {"紀": 12, "表": 8, "志": 10, "傳": 70},
        "cat_from_title": lambda t: _extract_cat(t, ["紀", "表", "志", "傳"]),
        "num_from_title": lambda t: _extract_num(t, ["紀", "表", "志", "傳"]),
    },
    "三國志": {
        "dir": os.path.join(BASE, "三國志", "by_piece"),
        "cat_order": ["魏書", "蜀書", "吳書"],
        "cat_ids": {"魏書": "wei", "蜀書": "shu", "吳書": "wu"},
        "cat_expected": {"魏書": 30, "蜀書": 15, "吳書": 20},
        "cat_from_title": lambda t: _extract_cat(t, ["魏書", "蜀書", "吳書"]),
        "num_from_title": lambda t: _extract_num(t, ["魏書", "蜀書", "吳書"]),
    },
}


def _extract_cat(title, cat_list):
    """从篇名中找第一个出现的分类词。cat_list 顺序决定优先级。"""
    for c in cat_list:
        if c in title:
            return c
    return None


def _extract_num(title, cat_list):
    """抽 '第X' 里的 X，转成 int。找不到返回 None。"""
    m = re.search(r'第([一二三四五六七八九十百]+\d*)', title)
    if m:
        try:
            return cn_to_int(m.group(1))
        except ValueError:
            return None
    return None


def split_paragraphs(text):
    """按空行分段；连续非空行合并为一个段落。"""
    paragraphs = []
    current = []
    for line in text.split("\n"):
        s = line.strip()
        if s == "":
            if current:
                paragraphs.append("".join(current))
                current = []
        else:
            current.append(s)
    if current:
        paragraphs.append("".join(current))
    return [p for p in paragraphs if len(p) > 1]


def process_book(book_name, config):
    piece_dir = config["dir"]
    if not os.path.isdir(piece_dir):
        print(f"  ⚠️ 目录不存在: {piece_dir}")
        return []

    sections = []
    # 排序时去掉 _2 之类后缀干扰，直接用原始文件名
    files = sorted([f for f in os.listdir(piece_dir) if f.endswith(".txt")])

    for fname in files:
        fpath = os.path.join(piece_dir, fname)
        with open(fpath, "r", encoding="utf-8") as fh:
            content = fh.read()

        title = os.path.splitext(fname)[0]
        cat_label = config["cat_from_title"](title)
        cat_id = config["cat_ids"].get(cat_label) if cat_label else None
        num = config["num_from_title"](title)

        paragraphs = split_paragraphs(content)
        sections.append({
            "book": book_name,
            "title": title,
            "category": cat_id,
            "category_label": cat_label,
            "number": num,
            "paragraphs": paragraphs,
            "char_count": sum(len(p) for p in paragraphs),
            "para_count": len(paragraphs),
        })

    # ---- 统计 ----
    cat_count = {}
    for s in sections:
        c = s["category_label"] or "【未分类】"
        cat_count[c] = cat_count.get(c, 0) + 1

    print(f"   共 {len(sections)} 篇")
    for cat in config["cat_order"] + ["【未分类】"]:
        if cat in cat_count:
            mark = " ⚠️" if cat == "【未分类】" else ""
            print(f"     · {cat}: {cat_count[cat]} 篇{mark}")

    # ---- 打印未分类 ----
    unclassified = [s["title"] for s in sections if not s["category_label"]]
    if unclassified:
        print(f"\n   ⚠️ 未分类篇目（{len(unclassified)} 篇，请检查标题格式）:")
        for t in unclassified:
            print(f"      · {t}")

    # ---- 序号连续性校验（每分类）----
    print("   序号校验:")
    by_cat = {}
    for s in sections:
        by_cat.setdefault(s["category_label"] or "【未分类】", []).append(s["number"])

    for cat in config["cat_order"]:
        nums = sorted([n for n in by_cat.get(cat, []) if n is not None])
        expected = config["cat_expected"].get(cat)
        if not nums:
            print(f"     · {cat}: (无)")
            continue
        max_n = max(nums)
        # 期望 1..expected，找出缺失
        if expected:
            full = set(range(1, expected + 1))
            missing = sorted(full - set(nums))
            status = f"缺失 {missing}" if missing else "连续 ✅"
            print(f"     · {cat}: 1-{max_n}, 期望 {expected} → {status}")
        else:
            print(f"     · {cat}: 1-{max_n}")

    return sections


def main():
    all_books = {}
    for book_name, config in BOOKS.items():
        print(f"\n📖 处理《{book_name}》...")

        # 路径自检
        if not os.path.isdir(config["dir"]):
            print(f"  ⚠️ 跳过：{config['dir']} 不存在，请检查 BOOKS 配置里的 dir")
            continue

        sections = process_book(book_name, config)
        all_books[book_name] = {
            "title": book_name,
            "section_count": len(sections),
            "categories": config["cat_order"],
            "sections": sections,
        }

    # ---- 输出 ----
    out_path = os.path.join(OUT_DIR, "books.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已导出: {out_path}")

    for book_name, data in all_books.items():
        book_path = os.path.join(OUT_DIR, f"{book_name}.json")
        with open(book_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"   · {book_path}")

    print("\n🎉 全部完成！")


if __name__ == "__main__":
    main()