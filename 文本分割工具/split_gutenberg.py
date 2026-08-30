# -*- coding: utf-8 -*-
"""
古登堡繁体中文古籍 通用分割脚本
============================================================
支持：《史記》《漢書》《三國志》（可扩展至其他古登堡中文 txt）

用法：
    1) 把本脚本与 史記.txt / 漢書.txt / 三國志.txt 放在同一文件夹
    2) cd 到该文件夹，运行：  python3 split_gutenberg.py
    脚本会自动发现同目录下的 *.txt（跳过自身），逐个分割。

每本书在脚本下方的 BOOKS 配置中定义：
    - heading_re : 标题行正则（匹配"篇/卷"起始行）
    - cats       : 类别词列表（决定五体分组 & 篇名归类）
    - cat_dir    : 类别 -> 输出子目录名映射

标题行判定规则（繁体）：
    《史記》  "史記 五帝本紀"        -> 本紀/表/書/世家/列傳
    《漢書》  "漢書 高帝紀第一"      -> 紀/表/志/傳
    《三國志》"三國志 魏書 武帝紀第一" -> 魏志/蜀志/吳志（按"某書/某志+紀/傳"切分）

输出：
    <书名>_分割/by_piece/  逐篇 txt
    <书名>_分割/by_category/  按类别分组 txt
"""
import os
import re
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(__file__)

# 文件名(简体) -> 配置键(繁体) 的兼容映射
NAME_NORMALIZE = {
    "史记": "史記", "汉书": "漢書", "三国志": "三國志",
    "史記": "史記", "漢書": "漢書", "三國志": "三國志",
}


# ==================== 每本书的配置 ====================
# cat_dir 的 key 必须覆盖 cats 中所有类别词
# 空白字符组：兼容半角空格、全角空格（　）、制表符
# （古登堡繁体 txt 标题中常见全角空格，\s 不总能匹配）
_WS = r'[ \u3000\t]+'

BOOKS = {
    # -------- 《史記》 --------
    "史記": {
        "cats": ["本紀", "表", "書", "世家", "列傳"],
        "cat_dir": {
            "本紀": "01_benji", "表": "02_biao", "書": "03_shu",
            "世家": "04_shijia", "列傳": "05_liezhuan",
        },
        # 标题行：行首 "史記" + 空白 + 任意 + 类别词 + 行尾
        "heading_pattern": r'^史記' + _WS + r'.*(?:本紀|表|書|世家|列傳)\s*$',
    },
    # -------- 《漢書》 --------
    "漢書": {
        "cats": ["紀", "表", "志", "傳"],
        "cat_dir": {
            "紀": "01_ji", "表": "02_biao", "志": "03_zhi", "傳": "04_zhuan",
        },
        # 标题行：行首 "漢書" + 空白 + 含 紀/表/志/傳 任一类别词
        # 注：类别词后常跟序号（如 "高帝紀第一"），故不加行尾约束
        "heading_pattern": r'^漢書' + _WS + r'.*(?:紀|表|志|傳)',
    },
    # -------- 《三國志》 --------
    "三國志": {
        "cats": ["魏書", "蜀書", "吳書"],
        "cat_dir": {
            "魏書": "01_wei", "蜀書": "02_shu", "吳書": "03_wu",
        },
        # 标题行：行首 "三國志" + 空白 + ... + 魏書/蜀書/吳書（类别词，可在行中任意位置）
        # 例："三國志 魏書 武帝紀第一" —— 魏書 在行中，故不加行尾约束
        "heading_pattern": r'^三國志' + _WS + r'.*(?:魏書|蜀書|吳書)',
    },
}


# ==================== 通用处理流程 ====================

def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', name)
    return name.strip()


def is_gutenberg_line(s):
    """剔除古登堡残留：含 *** 标记，或纯英文行"""
    if '***' in s:
        return True
    return bool(re.search(r'[A-Za-z]', s)) and not bool(re.search(r'[\u4e00-\u9fff]', s))


def split_book(src_path, config):
    text = open(src_path, "r", encoding="utf-8-sig").read()

    # 截取正文（从 *** START OF ... 之后）
    m = re.search(r'\*\*\*\s*START OF THE PROJECT GUTENBERG EBOOK', text)
    if m:
        text = text[m.end():]

    cats = config["cats"]
    cat_dir_map = config["cat_dir"]
    heading_re = re.compile(config["heading_pattern"])
    lines = text.split("\n")

    # 定位所有篇标题行
    headings = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not heading_re.match(s):
            continue
        # 取类别：优先"以类别词结尾"，否则取行中最后出现的类别词
        cat = None
        for c in cats:
            if s.endswith(c):
                cat = c
                break
        if cat is None:
            last_pos = -1
            for c in cats:
                pos = s.rfind(c)
                if pos > last_pos:
                    last_pos = pos
                    cat = c
        if cat:
            headings.append((i, cat, s))

    if not headings:
        print("  ⚠️  未识别到任何标题行，请检查 heading_pattern 与文件编码")
        return

    print(f"  识别到 {len(headings)} 个篇标题")

    # 输出目录：以文件名(去扩展名)命名
    book_name = os.path.splitext(os.path.basename(src_path))[0]
    out_dir = os.path.join(BASE, book_name + "_分割")
    os.makedirs(out_dir, exist_ok=True)

    seen = {}

    def write_piece(start, end, name, subdir):
        kept = [ln for ln in lines[start:end] if not is_gutenberg_line(ln.strip())]
        body = "\n".join(kept).strip()
        if not body:
            return
        d = os.path.join(out_dir, subdir)
        os.makedirs(d, exist_ok=True)
        base = safe_name(name)
        path = os.path.join(d, base + ".txt")
        # 重名处理（如 高祖本紀 出现两次 -> 高祖本紀_2）
        if os.path.exists(path) or base in seen:
            stem, ext = os.path.splitext(base)
            idx = seen.get(base, 1) + 1
            seen[base] = idx
            path = os.path.join(d, f"{stem}_{idx}{ext}")
        else:
            seen[base] = 1
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(body + "\n")

    # 模式A：逐篇
    for k, (i, cat, name) in enumerate(headings):
        end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        write_piece(i, end, name, "by_piece")

    # 模式B：按类别分组
    for k, (i, cat, name) in enumerate(headings):
        end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        kept = [ln for ln in lines[i:end] if not is_gutenberg_line(ln.strip())]
        body = "\n".join(kept).strip()
        if not body:
            continue
        d = os.path.join(out_dir, "by_category")
        os.makedirs(d, exist_ok=True)
        cat_folder = cat_dir_map.get(cat, cat)
        path = os.path.join(d, cat_folder + ".txt")
        with open(path, "a", encoding="utf-8-sig") as f:
            f.write(f"【{name}】\n{body}\n\n")

    # 报告
    print(f"  ✅ 逐篇：{len(glob.glob(os.path.join(out_dir,'by_piece','*.txt')))} 个文件")
    print("  === 按类别 ===")
    for c in cats:
        folder = cat_dir_map.get(c, c)
        p = os.path.join(out_dir, "by_category", folder + ".txt")
        if os.path.exists(p):
            n = len(glob.glob(os.path.join(out_dir, "by_piece", "*.txt")))  # placeholder
            print(f"    {folder}.txt  {os.path.getsize(p)//1024} KB")
    print(f"  输出：{out_dir}\n")


def main():
    # 自动发现同目录下所有 .txt（跳过本脚本）
    txts = [t for t in glob.glob(os.path.join(BASE, "*.txt"))
            if os.path.basename(t) != SELF]
    if not txts:
        print(f"❌ 在 {BASE} 下未找到任何 .txt 文件（除 {SELF} 外）")
        return
    for src in sorted(txts):
        name = os.path.splitext(os.path.basename(src))[0]
        # 识别是哪本书（兼容简繁文件名）
        matched = NAME_NORMALIZE.get(name)
        if not matched:
            for book in BOOKS:
                if book in name:
                    matched = book
                    break
        if not matched:
            print(f"⏭  跳过「{name}」：未在 BOOKS 中配置，如需支持请添加配置")
            continue
        print(f"📖 处理《{matched}》 <- {os.path.basename(src)}")
        split_book(src, BOOKS[matched])


if __name__ == "__main__":
    main()
