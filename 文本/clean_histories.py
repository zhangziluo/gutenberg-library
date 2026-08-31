#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三史 by_piece 文本清洗（2026-08-31）
处理项：
  1. 首段冗余篇名/卷题行（史記 126 篇、漢書 99 篇【篇名】、三國志 29 篇）
  2. 末段「漢書 卷XX」卷题残留（漢書 98 篇）
  3. 末段独立分类词残字（史記 三王世家『列傳』、平準書『世家』、孝武本紀『表』）
  4. Gutenberg 英文授权样板（史記貨殖列傳、漢書敘傳第七十、三國志吳書第二十）
  5. 史記貨殖列傳 拆分出「太史公自序」为独立篇目
用法：python3 文本/clean_histories.py
"""
import os
import re
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
BOOKS = ["史記", "漢書", "三國志"]

def norm(s):
    """归一化：去掉空白、下划线、书名号括号，用于标题比对。"""
    s = s.replace("_", "").replace("　", "").replace(" ", "")
    s = re.sub(r"[【】《》\[\]()（）]", "", s)
    return s


def first_nonempty_idx(lines):
    for i, l in enumerate(lines):
        if l.strip():
            return i
    return None


def last_nonempty_idx(lines):
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            return i
    return None


def strip_first_title_line(lines, title):
    """若首个非空行与篇名归一化后相同，则删除该行。"""
    i = first_nonempty_idx(lines)
    if i is None:
        return lines
    if norm(lines[i]) == norm(title):
        del lines[i]
    return lines


def strip_trailing_volume_line(lines):
    """删除末尾独立行「漢書 卷XX」。"""
    i = last_nonempty_idx(lines)
    if i is not None and re.match(r"^漢書[ 　]*卷[一二三四五六七八九十百]+$", lines[i].strip()):
        del lines[i]
    return lines


def strip_trailing_category_word(lines):
    """删除末尾独立的分类词残字行（本紀/表/書/世家/列傳）。"""
    i = last_nonempty_idx(lines)
    if i is not None and re.match(r"^(本紀|表|書|世家|列傳)$", lines[i].strip()):
        del lines[i]
    return lines


def cut_gutenberg_boilerplate(lines):
    """从『Updated editions』行起删除到文件尾（Gutenberg 授权样板）。"""
    for i, l in enumerate(lines):
        if l.strip().startswith("Updated editions"):
            return lines[:i]
    return lines


def write_lines(path, lines):
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    summary = []

    # ---------- 史記 ----------
    d = os.path.join(BASE, "史記", "by_piece")
    files = sorted(glob.glob(os.path.join(d, "*.txt")))
    recovered = None
    for f in files:
        title = os.path.splitext(os.path.basename(f))[0]
        lines = open(f, encoding="utf-8").read().split("\n")
        orig = list(lines)

        # 5) 貨殖列傳 → 拆出 太史公自序
        if title == "史記 貨殖列傳":
            cut = None
            for i, l in enumerate(lines):
                if norm(l.strip()) == "史記太史公自序":
                    cut = i
                    break
            if cut is not None:
                zixu = lines[cut:]
                lines = lines[:cut]
                zixu = cut_gutenberg_boilerplate(zixu)
                zixu = strip_first_title_line(zixu, "史記 太史公自序")
                zixu = strip_trailing_category_word(zixu)
                zixu_path = os.path.join(d, "史記 太史公自序.txt")
                write_lines(zixu_path, zixu)
                recovered = ("史記 太史公自序", len([l for l in zixu if l.strip()]))
                print(f"  拆分: 史記 貨殖列傳 ←→ 新增「史記 太史公自序.txt」")

        # 4) 样板
        lines = cut_gutenberg_boilerplate(lines)
        # 1) 首段篇名
        lines = strip_first_title_line(lines, title)
        # 3) 尾段分类词残字
        lines = strip_trailing_category_word(lines)

        if lines != orig:
            write_lines(f, lines)
            removed = len(orig) - len(lines)
            summary.append((title, removed, "首行/尾部/样板清洗"))

    # ---------- 漢書 ----------
    d = os.path.join(BASE, "漢書", "by_piece")
    for f in sorted(glob.glob(os.path.join(d, "*.txt"))):
        title = os.path.splitext(os.path.basename(f))[0]
        lines = open(f, encoding="utf-8").read().split("\n")
        orig = list(lines)
        lines = cut_gutenberg_boilerplate(lines)          # 4) 敘傳第七十 样板
        lines = strip_first_title_line(lines, title)      # 1) 【篇名】首行（漢書全部 99 篇）
        lines = strip_trailing_volume_line(lines)         # 2) 漢書 卷XX
        if lines != orig:
            write_lines(f, lines)
            summary.append((title, len(orig) - len(lines), "首行篇名/尾部卷题/样板"))

    # ---------- 三國志 ----------
    d = os.path.join(BASE, "三國志", "by_piece")
    for f in sorted(glob.glob(os.path.join(d, "*.txt"))):
        title = os.path.splitext(os.path.basename(f))[0]
        lines = open(f, encoding="utf-8").read().split("\n")
        orig = list(lines)
        lines = cut_gutenberg_boilerplate(lines)          # 4) 吳書_二十 样板
        lines = strip_first_title_line(lines, title)      # 1) 卷题首行
        if lines != orig:
            write_lines(f, lines)
            summary.append((title, len(orig) - len(lines), "首行卷题/样板"))

    print(f"\n共修改 {len(summary)} 个文件：")
    for t, n, why in summary:
        print(f"  · {t}  （-{n} 行，{why}）")
    if recovered:
        print(f"\n新增独立篇目：{recovered[0]}（{recovered[1]} 行）")

    # ---------- 复核：应无残留 ----------
    print("\n===== 复核 =====")
    leftover = []
    for book in BOOKS:
        d = os.path.join(BASE, book, "by_piece")
        for f in sorted(glob.glob(os.path.join(d, "*.txt"))):
            title = os.path.splitext(os.path.basename(f))[0]
            ls = [l.strip() for l in open(f, encoding="utf-8").read().splitlines() if l.strip()]
            head, tail = (ls[0] if ls else ""), (ls[-1] if ls else "")
            if norm(head) == norm(title):
                leftover.append((book, os.path.basename(f), "首行仍=篇名", head[:30]))
            if re.match(r"^漢書[ 　]*卷[一二三四五六七八九十百]+$", tail):
                leftover.append((book, os.path.basename(f), "尾行仍=漢書卷", tail))
            if re.match(r"^(本紀|表|書|世家|列傳)$", tail):
                leftover.append((book, os.path.basename(f), "尾行仍=分类词", tail))
            if any("Updated editions" in l or "Project Gutenberg" in l for l in ls):
                leftover.append((book, os.path.basename(f), "仍有Gutenberg样板", ""))
    if leftover:
        for x in leftover:
            print("  ⚠️", x)
    else:
        print("  ✅ 无残留")


if __name__ == "__main__":
    main()
