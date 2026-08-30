#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定位 by_piece/ 里缺失的篇目（v2 反向推断版）

算法：从【实际文件名】提取 (分类, 序号)，与期望值比对。
     不依赖手写参考目录的篇名字符串，彻底规避异体/错字误报。

用法：放在 文本/ 下运行  python3 find_missing.py
"""

import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------
# 每本书配置：只关心「分类词」和「期望的最大序号」
# ---------------------------------------------------------------
BOOKS = {
    "史記": {
        "dir": os.path.join(BASE, "史記", "by_piece"),
        "cat_order": ["本紀", "表", "書", "世家", "列傳"],
        "cat_expected": {"本紀": 12, "表": 10, "書": 8, "世家": 30, "列傳": 70},
    },
    "漢書": {
        "dir": os.path.join(BASE, "漢書", "by_piece"),
        "cat_order": ["紀", "表", "志", "傳"],
        "cat_expected": {"紀": 12, "表": 8, "志": 10, "傳": 70},
    },
    "三國志": {
        "dir": os.path.join(BASE, "三國志", "by_piece"),
        "cat_order": ["魏書", "蜀書", "吳書"],
        "cat_expected": {"魏書": 30, "蜀書": 15, "吳書": 20},
    },
}


def parse_filename(title, cat_list):
    """
    从文件名（已去扩展名）提取 (分类词, 序号int)。
    返回 (None, None) 表示无法解析。
    例：
      '五帝本紀第一'     -> ('本紀', 1)
      '酈食其傳第十'      -> ('傳', 10)
      '魏書一 武帝紀第一' -> ('魏書', 1)
    """
    # 优先匹配「书别 + 序号」格式（三国志）
    m = re.match(r'^(魏書|蜀書|吳書)\s*[一二三四五六七八九十]+\s', title)
    if m:
        return m.group(1), None  # 序号由后面的通用逻辑处理

    cat = None
    for c in cat_list:
        if c in title:
            cat = c
            break
    if not cat:
        return None, None

    # 抽 "第X" 的序号
    m = re.search(r'第([一二三四五六七八九十百]+)', title)
    if not m:
        return cat, None
    cn = m.group(1)
    # 中文数字 → int
    num = cn_to_int(cn)
    return cat, num


CN_NUM = {}
for i, ch in enumerate("一二三四五六七八九十"):
    CN_NUM[ch] = i + 1

def cn_to_int(s):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    # 十几、二十几
    if "十" in s:
        parts = s.split("十")
        tens = CN_NUM.get(parts[0], 1) if parts[0] else 1
        ones = CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    raise ValueError(f"无法解析序号: {s}")


def check_book(book_name, config):
    piece_dir = config["dir"]
    if not os.path.isdir(piece_dir):
        print(f"\n📖 《{book_name}》⚠️ 目录不存在: {piece_dir}")
        return

    # 收集所有文件的 (分类, 序号)
    by_cat = {}   # cat -> set of nums
    unparsed = []
    files = [f for f in os.listdir(piece_dir) if f.endswith(".txt")]

    for f in files:
        title = os.path.splitext(f)[0]
        # 去重后缀（如 _2）不影响序号
        base = re.sub(r'_\d+$', '', title)
        cat, num = parse_filename(base, config["cat_order"])
        if not cat:
            unparsed.append(title)
            continue
        by_cat.setdefault(cat, set()).add(num)

    print(f"\n📖 《{book_name}》共 {len(files)} 文件")

    all_ok = True
    for cat in config["cat_order"]:
        nums = sorted([n for n in by_cat.get(cat, set()) if n])
        expected = config["cat_expected"].get(cat)
        if not expected:
            # 无期望上限（如三国志，我们只列出现有）
            print(f"   · {cat}: {len(nums)} 篇 (序号 {nums[:3]}...{nums[-3:] if len(nums)>3 else ''})")
            continue

        full = set(range(1, expected + 1))
        missing = sorted(full - set(nums))
        found = len(nums)
        if missing:
            all_ok = False
            print(f"   · {cat}: 找到 {found}/{expected}，缺失第 {missing} 篇 ⚠️")
        else:
            print(f"   · {cat}: {found}/{expected} 连续 ✅")

    if unparsed:
        print(f"\n   ⚠️ 无法解析分类的文件 ({len(unparsed)} 个，请检查文件名）:")
        for t in unparsed[:10]:
            print(f"      · {t}")

    if all_ok and not unparsed:
        print("   ✅ 无缺失")


def main():
    for book_name, config in BOOKS.items():
        check_book(book_name, config)
    print()


if __name__ == "__main__":
    main()