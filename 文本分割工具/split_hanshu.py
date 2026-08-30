import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "汉书.txt")

OUT_PIECE = os.path.join(BASE, "汉书_by_piece")
OUT_CAT = os.path.join(BASE, "汉书_by_category")
os.makedirs(OUT_PIECE, exist_ok=True)
os.makedirs(OUT_CAT, exist_ok=True)

# 《汉书》篇名行：形如 【高帝紀第一】 【天文志第六】 【司馬遷傳第三十二】
title_pattern = re.compile(r'^【(.+?)】\s*$')

# 五体分类：从篇名提取（纪/表/志/传）
def get_category(name):
    if '紀' in name:   return '01_ji'
    if '表' in name:   return '02_biao'
    if '志' in name:   return '03_zhi'
    if '傳' in name:   return '04_zhuan'
    return None

cat_files = {}
seen = {}

with open(SRC, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

current_file = None
current_cat = None

for line in lines:
    stripped = line.strip()

    # 跳过古登堡英文头尾
    if '***' in stripped or 'Project Gutenberg' in stripped:
        continue
    if stripped.isascii() and len(stripped) > 0:
        continue

    m = title_pattern.match(stripped)
    if m:
        name = m.group(1)  # 如 "高帝紀第一"
        cat = get_category(name)

        if current_file:
            current_file.close()

        # 文件名
        safe = re.sub(r'[\\/:*?"<>|]', '_', name)
        if safe in seen:
            seen[safe] += 1
            safe = f"{safe}_{seen[safe]}"
        else:
            seen[safe] = 1

        current_file = open(os.path.join(OUT_PIECE, f"{safe}.txt"), 'w', encoding='utf-8')

        if cat:
            if cat not in cat_files:
                cat_files[cat] = open(os.path.join(OUT_CAT, f"{cat}.txt"), 'w', encoding='utf-8')
            current_cat = cat
        else:
            current_cat = None

    if current_file:
        current_file.write(line)
    if current_cat and current_cat in cat_files:
        cat_files[current_cat].write(line)

if current_file:
    current_file.close()
for f in cat_files.values():
    f.close()

# 统计
print("✅ 《汉书》分割完成")
print(f"   逐篇：{OUT_PIECE}/")
print(f"   分类：{OUT_CAT}/")
print("\n各类篇数：")
for cat in ['01_ji', '02_biao', '03_zhi', '04_zhuan']:
    path = os.path.join(OUT_CAT, f"{cat}.txt")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            titles = title_pattern.findall(f.read())
        label = {'01_ji':'紀','02_biao':'表','03_zhi':'志','04_zhuan':'傳'}[cat]
        print(f"   {label}：{len(titles)} 篇")