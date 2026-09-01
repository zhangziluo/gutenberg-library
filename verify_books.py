import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data', 'books')

def load(k):
    return json.load(open(os.path.join(DATA, k + '.json'), encoding='utf-8'))

keys = ['shanshui-qing', 'shanhaijing', 'yijing', 'mulan-qi-nv-zhuan', 'yecao',
        'zhongguo-xiaoshuo-shilue', 'zhaohua-xishi', 'nanqiang-beidiao-ji',
        'aq-zhengzhuan', 'panghuang', 'kuangren-riji']

EXPECT = {
    'shanshui-qing': 22, 'shanhaijing': 18, 'yijing': 69, 'mulan-qi-nv-zhuan': 33,
    'yecao': 24, 'zhongguo-xiaoshuo-shilue': 29, 'zhaohua-xishi': 10,
    'nanqiang-beidiao-ji': 46, 'aq-zhengzhuan': 9, 'panghuang': 8, 'kuangren-riji': 1,
}

all_ok = True
for k in keys:
    d = load(k)
    n = len(d['chapters'])
    exp = EXPECT[k]
    fields = all(x in d for x in ['book', 'author', 'category', 'subcategory', 'chapters'])
    empty = sum(1 for c in d['chapters'] if not c['content'].strip())
    blob = json.dumps(d, ensure_ascii=False)
    resid = [w for w in ['START OF', 'END OF', 'Produced by', 'Gutenberg License', 'www.gutenberg'] if w in blob]
    ok = (n == exp) and fields and (empty == 0) and not resid
    all_ok = all_ok and ok
    print(f"{k}: {'✓' if ok else '✗'} 章数={n}(预期{exp}) 字段={fields} 空章={empty} 残留={resid or '无'} | {d['book']}/{d['author']}/{d['category']}/{d['subcategory']}")

# 专项检查
yj = load('yijing')
print('易經 传:', [c['title'] for c in yj['chapters'][64:]])
sh = load('shanhaijing')
vols = ['南山經','西山經','北山經','東山經','中山經','海外南經','海外西經','海外北經','海外東經','海內南經','大荒南經','海內西經','海內北經','海內東經','大荒東經','大荒西經','大荒北經','海內經']
print('山海經 卷标题合法:', all(c['title'] in vols for c in sh['chapters']))
ml = load('mulan-qi-nv-zhuan')
print('木蘭 含附錄:', '附錄' in json.dumps(ml, ensure_ascii=False))

# 鲁迅专题专项
sl = load('zhongguo-xiaoshuo-shilue')
print('中國小說史略 首末:', sl['chapters'][0]['title'], '|', sl['chapters'][-1]['title'])
dup9 = sum(1 for c in sl['chapters'] if c['title'] == '第九篇 唐之傳奇文（下）')
print('中國小說史略 第九篇去重:', dup9 == 1)
nq = load('nanqiang-beidiao-ji')
bb = sum(1 for c in nq['chapters'] for para in c['content'].split('\n') if para.strip() in ('BB', 'B　B'))
print('南腔北調集 BB残留:', bb)
aq = load('aq-zhengzhuan')
print('阿Q正傳 标题:', [c['title'] for c in aq['chapters']])
ph = load('panghuang')
print('彷徨 篇目:', [c['title'] for c in ph['chapters']])
kr = load('kuangren-riji')
print('狂人日記 首段:', kr['chapters'][0]['content'][:60])
zh = load('zhaohua-xishi')
print('朝花夕拾 篇目:', [c['title'] for c in zh['chapters']])

# 内容抽样
print('--- 南腔北調集 首篇开头 ---')
print(nq['chapters'][0]['content'][:90])
print('--- 朝花夕拾 小引开头 ---')
print(zh['chapters'][0]['content'][:90])

print('\n总体:', '全部通过 ✅' if all_ok else '存在失败 ❌')

