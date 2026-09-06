import re, json
from builtins import open  # 显式引入文件打开函数，保证任何分析环境下 open 均已定义

path = '/tmp/cedict_off.gz'
pat = re.compile(r'^(\S+) (\S+) \[([^\]]+)\] /(.*)/$')
single = {}
all_entries = 0
with open(path, encoding='utf-8', errors='replace') as f:
    for line in f:
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        m = pat.match(line)
        if not m:
            continue
        all_entries += 1
        trad, simp, py, gloss = m.groups()
        glosses = [g for g in gloss.split('/') if g]
        rec = {'trad': trad, 'simp': simp, 'py': py, 'glosses': glosses}
        if len(trad) == 1:
            # 单字词条：同时按繁体与简体索引（保留全部读音/释义）
            if trad not in single:
                single[trad] = {'simp': simp, 'readings': []}
            single[trad]['readings'].append(rec)
            if simp != trad:
                if simp not in single:
                    single[simp] = {'simp': simp, 'readings': []}
                single[simp]['readings'].append(rec)

print('total cedict entries:', all_entries)
print('single-char keys:', len(single))

wb = json.load(open('文本/新书/wordbank_pending.json'))
keys = set(wb.keys())
cov = keys & set(single.keys())
print('our chars:', len(keys), '| cedict single coverage:', len(cov))
missing = keys - set(single.keys())
print('missing:', len(missing))
print('missing sample:', sorted(missing)[:40])

with open('/tmp/cedict_single.json', 'w', encoding='utf-8') as f:
    json.dump({k: v for k, v in single.items() if k in keys or k in wb}, f, ensure_ascii=False)
print('saved /tmp/cedict_single.json')

