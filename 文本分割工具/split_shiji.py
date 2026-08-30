import re
import os

# 脚本所在目录
BASE = os.path.dirname(os.path.abspath(__file__))

# 源文件（和脚本同目录下的 史记.txt）
SRC = os.path.join(BASE, "汉书.txt")

# 输出目录（在脚本同目录下创建）
OUT_PIECE = os.path.join(BASE, "by_piece")
OUT_CAT = os.path.join(BASE, "by_category")

os.makedirs(OUT_PIECE, exist_ok=True)
os.makedirs(OUT_CAT, exist_ok=True)

# 繁体《史记》标题正则（raw string，避免转义警告）
pattern = re.compile(r'^史記\s+.*(本紀|表|書|世家|列傳)\s*$')

# 五体分类映射
CAT_DIR = {
    '本紀': '01_benji',
    '表':   '02_biao',
    '書':   '03_shu',
    '世家': '04_shijia',
    '列傳': '05_liezhuan',
}

# 分类文件句柄
cat_files = {}

with open(SRC, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

current_file = None
current_cat = None
seen = {}  # 处理重名

for line in lines:
    stripped = line.strip()

    # 跳过古登堡标记行和英文
    if '***' in stripped or 'Project Gutenberg' in stripped:
        continue
    if stripped.isascii() and len(stripped) > 0:
        continue

    # 匹配标题行
    m = pattern.match(stripped)
    if m:
        cat = m.group(1)

        # 关闭上一个文件
        if current_file:
            current_file.close()

        # 文件名：用标题，去非法字符
        safe = re.sub(r'[\\/:*?"<>|]', '_', stripped)
        if safe in seen:
            seen[safe] += 1
            safe = f"{safe}_{seen[safe]}"
        else:
            seen[safe] = 1

        # 逐篇输出
        path = os.path.join(OUT_PIECE, f"{safe}.txt")
        current_file = open(path, 'w', encoding='utf-8')

        # 分类输出
        current_cat = CAT_DIR.get(cat)
        if current_cat and current_cat not in cat_files:
            cat_path = os.path.join(OUT_CAT, f"{current_cat}.txt")
            cat_files[current_cat] = open(cat_path, 'w', encoding='utf-8')

    # 写入内容
    if current_file:
        current_file.write(line)
    if current_cat and current_cat in cat_files:
        cat_files[current_cat].write(line)

# 关闭所有文件
if current_file:
    current_file.close()
for f in cat_files.values():
    f.close()

print("✅ 分割完成！")
print(f"   逐篇输出：{OUT_PIECE}/")
print(f"   分类输出：{OUT_CAT}/")