import os

BASE = os.path.dirname(os.path.abspath(__file__))

files = []
for f in os.listdir(BASE):
    if f.endswith('.txt'):
        files.append(f)

for fname in sorted(files):
    path = os.path.join(BASE, fname)
    size = os.path.getsize(path)
    print(f"\n{'='*60}")
    print(f"文件: {fname}  ({size:,} 字节)")
    print('='*60)

    with open(path, 'r', encoding='utf-8-sig') as fh:
        lines = fh.readlines()

    print(f"总行数: {len(lines)}\n")

    # 打印前 40 行原始内容（用 repr 显示真实空白字符）
    print(">>> 前 40 行（repr 形式，\\n=换行 \\t=制表符 　=全角空格）:")
    for i, line in enumerate(lines[:40], 1):
        # 把全角空格换成可见标记方便看
        visible = line.rstrip('\n').replace('　', '␣').replace('\t', '→')
        print(f"  L{i:>3}: {visible}")

    # 再找含"卷"字的行
    print("\n>>> 含「卷」字的行（最多 30 个）:")
    count = 0
    for i, line in enumerate(lines, 1):
        if '卷' in line or '卷' in line:
            visible = line.strip().replace('　', '␣')
            print(f"  L{i:>3}: {visible}")
            count += 1
            if count >= 30:
                break
    if count == 0:
        print("  (没有找到「卷」字)")

    # 找含"书/紀/傳"的行
    print("\n>>> 含「書/纪/传」关键字的行（最多 20 个）:")
    count = 0
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if any(k in s for k in ['書', '书', '紀', '纪', '傳', '传']):
            visible = s.replace('　', '␣')
            print(f"  L{i:>3}: {visible}")
            count += 1
            if count >= 20:
                break