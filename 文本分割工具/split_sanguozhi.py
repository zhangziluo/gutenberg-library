import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "三國志.txt")

OUT_PIECE = os.path.join(BASE, "三国志_by_piece")
OUT_CAT = os.path.join(BASE, "三国志_by_category")
os.makedirs(OUT_PIECE, exist_ok=True)
os.makedirs(OUT_CAT, exist_ok=True)

# 标题行：如 "魏書一␣␣武帝紀第一"  或  "蜀書一␣劉二牧傳第一"
# 组1 = 书别（魏書/蜀書/吳書），组2 = 篇名（含纪/传）
title_pattern = re.compile(r'^(魏書|蜀書|吳書)\s*([一二三四五六七八九十]+)\s+(.+)$')

seen = {}
cat_files = {}

with open(SRC, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

current_file = None
current_cat = None

for line in lines:
    stripped = line.strip()

    # 跳过古登堡英文头尾与纯英文行
    if '***' in stripped or 'Project Gutenberg' in stripped:
        continue
    if stripped.isascii() and len(stripped) > 0:
        continue

    m = title_pattern.match(stripped)
    if m:
        book, num, name = m.group(1), m.group(2), m.group(3)
        cat = {'魏書': '01_wei', '蜀書': '02_shu', '吳書': '03_wu'}[book]

        if current_file:
            current_file.close()

        # 文件名：魏書_01_武帝紀第一.txt
        base_name = f"{book}_{num}_{name}"
        safe = re.sub(r'[\\/:*?"<>|]', '_', base_name)
        if safe in seen:
            seen[safe] += 1
            safe = f"{safe}_{seen[safe]}"
        else:
            seen[safe] = 1

        current_file = open(os.path.join(OUT_PIECE, f"{safe}.txt"), 'w', encoding='utf-8')

        if cat not in cat_files:
            cat_files[cat] = open(os.path.join(OUT_CAT, f"{cat}.txt"), 'w', encoding='utf-8')
        current_cat = cat

    if current_file:
        current_file.write(line)
    if current_cat and current_cat in cat_files:
        cat_files[current_cat].write(line)

if current_file:
    current_file.close()
for f in cat_files.values():
    f.close()

print("✅ 《三国志》分割完成")
print(f"   逐篇：{OUT_PIECE}/")
print(f"   分类：{OUT_CAT}/")
print("\n各书篇数：")
for cat in ['01_wei', '02_shu', '03_wu']:
    path = os.path.join(OUT_CAT, f"{cat}.txt")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            cnt = len(title_pattern.findall(f.read()))
        label = {'01_wei':'魏書','02_shu':'蜀書','03_wu':'吳書'}[cat]
        print(f"   {label}：{cnt} 篇")