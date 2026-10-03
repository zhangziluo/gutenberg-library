/**
 * /api/dict-links —— 「更多词典」新窗口链接模板（Cloudflare Pages Function）
 * ============================================================
 *   GET /api/dict-links?lang=zh&q=之
 *   → { lang, query, links: [{ name, host, url, note, group }] }
 *
 * 只**拼 URL 模板、不 fetch 第三方**（前端点一下才 window.open）。
 * 语言表：zh / en / fr / de / es 为需求指定；其余语种自动给
 * 「{lang}.wiktionary.org + 英文兜底」，比单纯退回 en 更好用。
 *
 * ⚠️ 白名单闸门仍在**前端**（js/dict-links.js）：本接口可能返回被墙/被拦的源
 *   （如 zh.wiktionary.org），前端会按 hidden 规则过滤掉，绝不渲染、绝不预取。
 */

const MAX_Q = 64;
const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const K = (name, host, note, path) => ({ name, host, note, path });

/** 各语言的「新窗口查词」模板：path 里 %s 会被 URL 编码后的查询词替换 */
const LINKS = {
  zh: [
    K('漢典', 'www.zdic.net', '字 · 词 · 成语', 'https://www.zdic.net/hans/%s'),
    K('萌典', 'www.moedict.tw', '国语辞典 · 台语 · 客语', 'https://www.moedict.tw/%s'),
    K('教育部重編國語辭典', 'dict.revised.moe.edu.tw', '台湾教育部',
      'https://dict.revised.moe.edu.tw/search.jsp?word=%s'),
    K('中文 Wiktionary', 'zh.wiktionary.org', '被墙源 · 需开「容错外链」',
      'https://zh.wiktionary.org/wiki/%s'),
  ],
  en: [
    K('Merriam-Webster', 'www.merriam-webster.com', '美式英语权威', 'https://www.merriam-webster.com/dictionary/%s'),
    K('Cambridge', 'dictionary.cambridge.org', '英式 / 美式', 'https://dictionary.cambridge.org/dictionary/english/%s'),
    K('Collins', 'www.collinsdictionary.com', '英式英语', 'https://www.collinsdictionary.com/dictionary/english/%s'),
    K('Oxford Learner\'s', 'www.oxfordlearnersdictionaries.com', '学习者词典',
      'https://www.oxfordlearnersdictionaries.com/definition/english/%s'),
  ],
  fr: [
    K('Larousse', 'www.larousse.fr', '法语词典', 'https://www.larousse.fr/dictionnaires/francais/%s'),
    K('CNRTL', 'www.cnrtl.fr', '法语词源 / 历史', 'https://www.cnrtl.fr/definition/%s'),
  ],
  de: [
    K('Duden', 'www.duden.de', '德语正字法', 'https://www.duden.de/rechtschreibung/%s'),
    K('DWDS', 'www.dwds.de', '德语语料库词典', 'https://www.dwds.de/wb/%s'),
  ],
  es: [
    K('RAE', 'dle.rae.es', '西班牙皇家学院', 'https://dle.rae.es/%s'),
  ],
  it: [
    K('Treccani', 'www.treccani.it', '意大利语', 'https://www.treccani.it/vocabolario/%s'),
  ],
  ru: [
    K('Викисловарь (ru)', 'ru.wiktionary.org', '俄语维基词典', 'https://ru.wiktionary.org/wiki/%s'),
  ],
};

const LANG_NAMES = { it: '意大利语', ru: '俄语' };

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: Object.assign({ 'content-type': 'application/json; charset=utf-8' }, CORS, extra),
  });
}

/** 语言 → 链接表（未知语种：{lang}.wiktionary.org + 英文兜底） */
export function buildDictLinks(lang, q) {
  const enc = encodeURIComponent(q);
  const list = LINKS[lang] ? LINKS[lang].slice() : [];
  if (!LINKS[lang]) {
    if (/^[a-z][a-z-]{1,11}$/.test(lang)) {
      list.push(K(lang + ' Wiktionary', lang + '.wiktionary.org',
                 (LANG_NAMES[lang] || lang) + '维基词典',
                 'https://' + lang + '.wiktionary.org/wiki/%s'));
    }
    LINKS.en.forEach(function (it) { list.push(it); });   // 英文源兜底
  }
  return list.map(function (it) {
    return { name: it.name, host: it.host, note: it.note, group: LINKS[lang] ? lang : 'en',
             url: it.path.replace('%s', enc) };
  });
}

export async function onRequest(ctx) {
  const request = ctx && ctx.request;
  if (!request) return json({ error: 'bad request' }, 400);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405);

  const url = new URL(request.url);
  const lang = (url.searchParams.get('lang') || 'zh').toLowerCase();
  const q = (url.searchParams.get('q') || '').trim();
  if (!q) return json({ error: 'missing q' }, 400);
  if (q.length > MAX_Q) return json({ error: 'q too long' }, 400);
  if (!/^[a-z][a-z-]{1,11}$/.test(lang)) return json({ error: 'bad lang' }, 400);

  return json({ lang, query: q, links: buildDictLinks(lang, q) }, 200,
              { 'Cache-Control': 'public, max-age=86400' });
}
