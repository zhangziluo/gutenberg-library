import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))

def find_txt(keyword):
    """找文件名包含 keyword 的 txt"""
    for f in os.listdir(BASE):
        if f.endswith('.txt') and keyword in f:
            return os.path.join(BASE, f)
    return None

def scan_titles(path, label):
    """扫描并打印所有可能的标题行，供人工核对"""
    print(f"\n{'='*60}\n扫描 {label}：{os.path.basename(path)}\n{'='*60}")
    with open(path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    # 通用标题候选：以"卷"开头，或包含 纪/表/志/传/书
    candidates = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # 汉书格式：卷一上·高帝紀第一上
        # 三国志格式：卷一 魏書一 武帝紀第一
        # 史记格式：史記 卷一 五帝本紀第一
        if re.match(r'^卷[一二三四五六七八九十百]+\s*[上下]?\s*[·・]?', s) or \
           re.match(r'^史記\s+卷', s) or \
           ('書一' in s and '卷' in s) or \
           ('本紀' in s and '卷' in s):
            candidates.append((i+1, s))

    print(f"找到 {len(candidates)} 个候选标题行：\n")
    for ln, text in candidates[:80]:  # 先打印前80个
        print(f"  L{ln:>4}: {text}")
    if len(candidates) > 80:
        print(f"  ... 还有 {len(candidates)-80} 个")
    return lines, candidates

# ===== 主流程 =====
books = [
    ("漢書", "han"),
    ("汉书", "han"),
    ("三國志", "sanguo"),
    ("三国志", "sanguo"),
]

for keyword, book_id in books:
    path = find_txt(keyword)
    if not path:
        continue
    lines, candidates = scan_titles(path, keyword)
    
    # 让用户确认
    print(f"\n上面是 {keyword} 识别到的标题行。")
    print("如果格式不对，请把前 10 行贴给我，我调整正则。")
    print("确认无误后，脚本才会真正切分。\n")