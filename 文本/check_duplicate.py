#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 by_piece/ 里的重复文件（_2 / _3 后缀）
对比原文件和副本的内容：完全相同 → 真重复；不同 → 可能是误切/合并
"""

import os

BASE = os.path.dirname(os.path.abspath(__file__))

# 三本书的 by_piece 目录
DIRS = {
    "史記":   os.path.join(BASE, "史記", "by_piece"),
    "漢書":   os.path.join(BASE, "漢書", "by_piece"),
    "三國志": os.path.join(BASE, "三國志", "by_piece"),
}


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    for book, piece_dir in DIRS.items():
        if not os.path.isdir(piece_dir):
            print(f"\n📖 《{book}》⚠️ 目录不存在: {piece_dir}")
            continue

        files = sorted([f for f in os.listdir(piece_dir) if f.endswith(".txt")])
        # 找出带 _2 _3 后缀的文件
        dups = [f for f in files if re_search(r'_(\d+)\.txt$', f)]

        print(f"\n📖 《{book}》共 {len(files)} 文件")
        if not dups:
            print("   ✅ 无重复后缀文件")
            continue

        print(f"   发现 {len(dups)} 个带序号后缀的文件:\n")

        import hashlib
        for dup in dups:
            # 推导"原始名"：去掉末尾的 _数字
            stem = strip_suffix(dup)
            original_path = os.path.join(piece_dir, stem)
            dup_path = os.path.join(piece_dir, dup)

            if not os.path.exists(original_path):
                print(f"   · {dup}")
                print(f"     对应原文件 {stem} 不存在 → 可能命名异常，请手动检查")
                continue

            orig_text = read(original_path)
            dup_text = read(dup_path)

            if orig_text == dup_text:
                print(f"   · {dup}")
                print(f"     ↔ {stem}")
                print(f"     ✅ 内容完全相同 → 真重复，可安全删除 {dup}\n")
            else:
                # 看是"子集"还是"完全不同"
                if orig_text in dup_text or dup_text in orig_text:
                    print(f"   · {dup}")
                    print(f"     ↔ {stem}")
                    print(f"     ⚠️ 内容是包含关系（一个是另一个的前缀/后缀）→ 切分边界问题\n")
                else:
                    print(f"   · {dup}")
                    print(f"     ↔ {stem}")
                    print(f"     ❓ 内容不同 → 可能是误切，需手动确认\n")


def re_search(pattern, text):
    import re
    return re.search(pattern, text)


def strip_suffix(filename):
    """'呂不韋列傳_2.txt' → '呂不韋列傳.txt'"""
    import re
    return re.sub(r'_(\d+)\.txt$', '.txt', filename)


if __name__ == "__main__":
    main()