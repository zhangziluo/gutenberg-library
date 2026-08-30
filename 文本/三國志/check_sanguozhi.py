#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
《三国志》古登堡版切分结果核验
用途：确认 三国志_by_piece 里的篇目编号是否连续、有无重复、何处断档。
用法：把本脚本放在 三国志_by_piece 的【父目录】下运行
"""

import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
PIECE_DIR = os.path.join(BASE, "by_piece")

# 扩展中文数字映射（支持到二十及以上）
CN_NUM = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
    '二十一': 21, '二十二': 22, '二十三': 23, '二十四': 24, '二十五': 25,
    '二十六': 26, '二十七': 27, '二十八': 28, '二十九': 29, '三十': 30
}

def num_to_int(num_cn):
    """将中文数字转换为整数"""
    if num_cn in CN_NUM:
        return CN_NUM[num_cn]
    # 容错：如果已经是阿拉伯数字
    if num_cn.isdigit():
        return int(num_cn)
    # 容错：处理类似“二十”被拆开的情况（如“二”“十”）
    if '十' in num_cn and len(num_cn) == 2:
        return CN_NUM.get(num_cn[0], 0) * 10 + CN_NUM.get(num_cn[1], 0)
    raise KeyError(f"未支持的中文数字: '{num_cn}'")

def check_book(book_name, max_num):
    book_dir = PIECE_DIR
    # 匹配文件名：魏書_一_武帝紀第一.txt 或 魏書_1_武帝紀第一.txt
    pattern = re.compile(rf'^{book_name}_([一二三四五六七八九十\d]+)_')
    
    found_nums = []
    files = [f for f in os.listdir(book_dir) if f.endswith('.txt')]
    
    for f in files:
        m = pattern.match(f)
        if m:
            try:
                num = num_to_int(m.group(1))
                found_nums.append(num)
            except KeyError as e:
                print(f"  ⚠️ 跳过文件 {f}: {e}")
                
    found_nums = sorted(found_nums)
    expected = list(range(1, max_num + 1))
    missing = [n for n in expected if n not in found_nums]
    
    print(f"\n=== {book_name} ===")
    print(f"  找到: {len(found_nums)} 篇 (编号: {found_nums})")
    print(f"  缺失: {len(missing)} 篇 (编号: {missing})")
    
    # 检查重复
    seen = set()
    duplicates = []
    for n in found_nums:
        if n in seen:
            duplicates.append(n)
        seen.add(n)
    if duplicates:
        print(f"  ⚠️ 重复编号: {duplicates}")

def main():
    if not os.path.exists(PIECE_DIR):
        print(f"❌ 找不到目录: {PIECE_DIR}")
        print("请把本脚本放在 三国志_by_piece 的父目录下运行。")
        return
        
    print("开始核验《三国志》切分结果...")
    check_book("魏書", 30)
    check_book("蜀書", 15)
    check_book("吳書", 20)
    print("\n核验完成。")

if __name__ == "__main__":
    main()