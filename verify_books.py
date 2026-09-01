import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data', 'books')

def load(k):
    return json.load(open(os.path.join(DATA, k + '.json'), encoding='utf-8'))

keys = ['shanshui-qing', 'shanhaijing', 'yijing', 'mulan-qi-nv-zhuan', 'yecao']

# 1) 易經 64卦后的傳
yj = load('yijing')
print('易經 卦后传章节:', [c['title'] for c in yj['chapters'][64:]])
print('易經 卦数:', len([c for c in yj['chapters'] if c['title'].startswith('第')]))

# 2) 山海經 卷标题合法性
vols = ['南山經','西山經','北山經','東山經','中山經','海外南經','海外西經','海外北經','海外東經','海內南經','大荒南經','海內西經','海內北經','海內東經','大荒東經','大荒西經','大荒北經','海內經']
sh = load('shanhaijing')
print('山海經 卷数:', len(sh['chapters']), '| 标题全部合法:', all(c['title'] in vols for c in sh['chapters']))

# 3) 木蘭 无附錄/編修記錄
ml = load('mulan-qi-nv-zhuan')
blob = json.dumps(ml, ensure_ascii=False)
print('木蘭 含附錄:', '附錄' in blob or '編修記錄' in blob)
print('木蘭 章数:', len(ml['chapters']), '| 序内容头:', ml['chapters'][0]['content'][:24])

# 4) 野草 篇数与题辞
yc = load('yecao')
print('野草 篇数:', len(yc['chapters']), '| 題辭头:', yc['chapters'][0]['content'][:36])

# 5) 山水情 首末
sq = load('shanshui-qing')
print('山水情 章数:', len(sq['chapters']), '| 首:', sq['chapters'][0]['title'], '| 末:', sq['chapters'][-1]['title'])

# 6) Gutenberg 残留检查
for k in keys:
    b = load(k)
    blob = json.dumps(b, ensure_ascii=False)
    resid = [w for w in ['START OF', 'END OF', 'Produced by', 'Gutenberg License', 'www.gutenberg'] if w in blob]
    print(f'{k}: 残留={resid or "无"}')

# 7) 每章非空
for k in keys:
    b = load(k)
    empties = [c['title'] for c in b['chapters'] if not c['content'].strip()]
    print(f'{k}: 空章节={empties or "无"}')
