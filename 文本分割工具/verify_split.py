# -*- coding: utf-8 -*-
"""逐个确认分割内容：分类文件数、每篇首尾、重名、总字符数、残留英文抽样"""
import os
import re
import glob

BASE = os.path.dirname(os.path.abspath(__file__))


def check(book_dir):
    piece_dir = os.path.join(book_dir, "by_piece")
    cat_dir = os.path.join(book_dir, "by_category")
    if not os.path.isdir(piece_dir):
        print(f"  ❌ 未找到 {piece_dir}")
        return

    files = sorted(glob.glob(os.path.join(piece_dir, "*.txt")))
    print(f"\n{'='*50}")
    print(f"📁 {book_dir}")
    print(f"  逐篇总数：{len(files)}")

    # 1) 按类别统计
    cat_count = {}
    for f in files:
        name = os.path.basename(f)
        # 从内容首行判断类别（首行即标题）
        head = open(f, encoding="utf-8-sig").readline().strip()
        m = re.search(r'(本紀|表|書|世家|列傳|紀|表|志|傳|魏書|蜀書|吳書)', head)
        if m:
            cat_count[m.group(1)] = cat_count.get(m.group(1), 0) + 1
    print(f"  按类别：{cat_count}")

    # 2) 抽查：每类第一个 & 最后一个文件的首尾
    print("  --- 抽查（各类首尾篇）---")
    checked = set()
    for cat in cat_count:
        for f in files:
            head = open(f, encoding="utf-8-sig").readline().strip()
            if cat in head:
                if cat not in checked:
                    body = open(f, encoding="utf-8-sig").read()
                    print(f"    [首] {os.path.basename(f)}: {head} ... {body.strip()[-20:]}")
                    checked.add(cat)
                # 找该类最后一个
                last = None
            if cat in open(f, encoding="utf-8-sig").readline().strip():
                last = f
        if last and last not in [files[0]]:
            body = open(last, encoding="utf-8-sig").read()
            head = body.split("\n")[0].strip()
            print(f"    [末] {os.path.basename(last)}: {head} ... {body.strip()[-20:]}")

    # 3) 残留英文抽样（前5个含英文字母的行）
    print("  --- 古登堡残留检查（每篇扫描）---")
    residue = 0
    for f in files:
        for i, line in enumerate(open(f, encoding="utf-8-sig")):
            s = line.strip()
            if re.search(r'[A-Za-z]{4,}', s) and not re.search(r'[\u4e00-\u9fff]', s):
                residue += 1
                if residue <= 5:
                    print(f"    ⚠️  {os.path.basename(f)} 行{i+1}: {s[:60]}")
    print(f"    纯英文残留行总数：{residue}")

    # 4) 重名文件
    dups = [os.path.basename(f) for f in files if re.search(r'_\d+\.txt$', os.path.basename(f))]
    print(f"  重名拆分文件：{dups}")

    # 5) 总字符数
    total = sum(len(open(f, encoding="utf-8-sig").read()) for f in files)
    print(f"  总字符数（含标点）：{total:,}")


if __name__ == "__main__":
    for d in ["史记_分割", "漢書_分割", "三國志_分割"]:
        full = os.path.join(BASE, d)
        if os.path.isdir(full):
            check(full)
        else:
            print(f"⏭  跳过 {d}（源文件未提供）")
