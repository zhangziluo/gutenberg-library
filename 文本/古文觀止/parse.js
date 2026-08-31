// parse.js —— 解析 古登堡《古文觀止》(eBook #25225)
// 1) 截取 START/END 之间正文，删除许可证/制作人员等元数据
// 2) 按「卷X‧篇名 出处」正则切分为 222 篇，段落内软换行合并
// 3) 输出全量 JSON + 8 篇「AI 领读范本」JSON
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', '古文觀止.txt');
const FULL_OUT = path.join(__dirname, 'gwz_full.json');
const SAMPLE_OUT = path.join(__dirname, '..', '..', '网站', 'assets', 'data', 'gwz-samples.json');

const raw = fs.readFileSync(SRC, 'utf8');

// ---- 1. 截取 START / END 之间 ----
const startMark = raw.indexOf('*** START OF THE PROJECT GUTENBERG EBOOK 古文觀止 ***');
const endMark = raw.indexOf('*** END OF THE PROJECT GUTENBERG EBOOK 古文觀止 ***');
let body = raw.slice(startMark >= 0 ? startMark : 0, endMark > startMark ? endMark : raw.length);

// ---- 2. 按篇切分 ----
// 篇目头格式：卷X‧篇名　出处（篇名与出处间为全角空格）
const HEADER_RE = /^([卷][一二三四五六七八九十]+)‧(.+?)[\s　]+(.+)$/;
const chapters = [];
let cur = null;
for (const rawLine of body.split(/\r?\n/)) {
  const line = rawLine.trim();
  if (/^附錄/.test(line)) break;            // 附录起视为正文章节结束
  const m = line.match(HEADER_RE);
  if (m) {
    // 收尾上一章
    if (cur) {
      cur.content = (cur._paras || []).filter(p => p.length).map(p => p.join('')).join('\n');
      delete cur._paras;
      if (cur.content) chapters.push(cur);
    }
    cur = { volume: m[1], title: m[2].trim(), source: m[3].trim(), _paras: [] };
    continue;
  }
  if (!cur) continue;                        // 篇目头之前的元数据丢弃
  if (!line) { cur._paras.push([]); continue; }
  if (!cur._paras.length) cur._paras.push([]);
  cur._paras[cur._paras.length - 1].push(line); // 段落内软换行直接拼接
}
if (cur) {
  cur.content = (cur._paras || []).filter(p => p.length).map(p => p.join('')).join('\n');
  delete cur._paras;
  if (cur.content) chapters.push(cur);
}

console.log('切分篇数：', chapters.length);

// ---- 3. 输出全量 JSON ----
const clean = chapters.map(c => ({ volume: c.volume, title: c.title, source: c.source, content: c.content }));
fs.mkdirSync(path.dirname(FULL_OUT), { recursive: true });
fs.writeFileSync(FULL_OUT, JSON.stringify(clean, null, 2), 'utf8');
console.log('已输出全量：', FULL_OUT);

// ---- 4. 8 篇范本（6 篇来自文件 + 2 篇本版缺失、以标准文本补入） ----
const byTitle = {};
clean.forEach(c => { byTitle[c.title] = c; });
const curated = [
  { volume: '卷十一', title: '愛蓮說', source: '周敦頤', content: '水陸草木之花，可愛者甚蕃。晉陶淵明獨愛菊。自李唐來，世人甚愛牡丹。予獨愛蓮之出淤泥而不染，濯清漣而不妖，中通外直，不蔓不枝，香遠益清，亭亭淨植，可遠觀而不可褻玩焉。\n予謂菊，花之隱逸者也；牡丹，花之富貴者也；蓮，花之君子者也。噫！菊之愛，陶後鮮有聞。蓮之愛，同予者何人？牡丹之愛，宜乎眾矣。' },
  { volume: '卷十一', title: '記承天寺夜遊', source: '蘇軾', content: '元豐六年十月十二日夜，解衣欲睡，月色入戶，欣然起行。念無與為樂者，遂至承天寺尋張懷民。懷民亦未寢，相與步於中庭。\n庭下如積水空明，水中藻荇交橫，蓋竹柏影也。何夜無月？何處無竹柏？但少閒人如吾兩人者耳。' }
];
curated.forEach(c => { if (!byTitle[c.title]) byTitle[c.title] = c; });

// 按由易到难的推荐顺序（鄭伯克段于鄢 需取 左傳 版，避免误取 穀梁傳 版）
const want = [
  { title: '曹劌論戰' },
  { title: '鄭伯克段于鄢', sourcePrefix: '左傳' },
  { title: '愛蓮說' },
  { title: '岳陽樓記' },
  { title: '前出師表' },
  { title: '記承天寺夜遊' },
  { title: '師說' },
  { title: '滕王閣序' }
];
const samples = [];
for (const w of want) {
  const hit = clean.find(c => c.title === w.title && (!w.sourcePrefix || c.source.indexOf(w.sourcePrefix) === 0))
    || byTitle[w.title];
  if (hit) samples.push(hit);
  else console.warn('未找到：', w.title);
}
console.log('范本篇数：', samples.length);
fs.mkdirSync(path.dirname(SAMPLE_OUT), { recursive: true });
fs.writeFileSync(SAMPLE_OUT, JSON.stringify(samples, null, 2), 'utf8');
console.log('已输出范本：', SAMPLE_OUT);
