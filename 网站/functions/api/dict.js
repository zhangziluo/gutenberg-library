/**
 * /api/dict —— 在线词典同域代理（Cloudflare Pages Function）
 * ============================================================
 * 前端查词**绝不直连第三方**，一律走本同域接口：
 *   /api/dict?source=wiktionary&lang=zh&q=之   → {lang}.wiktionary.org Action API
 *   /api/dict?source=wikipedia&lang=zh&q=仁    → {lang}.wikipedia.org Action API
 *   /api/dict?source=freedict&lang=en&q=hello  → api.dictionaryapi.dev
 *   /api/dict?source=moedict&q=之              → www.moedict.tw（萌典）
 *   /api/dict?source=unihan&q=国               → **本站静态分片**（拼音/部首/笔画，不联网）
 * 配套接口：/api/dict-links（新窗口链接模板）、/api/translate（MyMemory 翻译）。
 *
 * 契约：
 *   · 任何情况下都返回 JSON，绝不空响应；
 *   · 统一带 source / query，解析结果在 result；wiki 源另保留顶层 extract（旧调用方兼容）；
 *   · 上游失败 → 502 {"error":"fetch failed"}；查不到 → 200 {"error":"not found"}；
 *     unihan 本地无此字 → 200 {"error":"no local data"}（前端据此继续降级）；
 *   · 上游超时 **2.5s**（前端 3s 放弃，留返程余量），保证前端能及时降级；
 *   · 响应 cache-control: public, max-age=86400（同一条查询当天不再回源）。
 */

const TIMEOUT_MS = 2500;                 // 上游超时（< 前端 3s）
const MAX_Q = 64;
const WIKI_CHARS = 500;                  // Wiktionary extracts 截取长度（需求：前 500 字）
const UNIHAN_SHARDS = 128;               // 与 文本/新书/build_unihan_slim.py 同口径

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
const CACHE = { 'Cache-Control': 'public, max-age=86400' };
const UA = 'yidui-gushu-dict-proxy/1.0 (+https://myfami.cn)';

const SOURCES = {
  wikipedia: { kind: 'wiki', host: 'wikipedia.org' },
  wiktionary: { kind: 'wiki', host: 'wiktionary.org' },
  freedict: { kind: 'freedict' },
  moedict: { kind: 'moedict' },
  unihan: { kind: 'unihan' },
  // translate：翻译也走本路由（与 /api/translate 同样的实现）
  // 原因：线上实测 /api/translate 那条路由的 isolate 访问上游会 502，而本路由能稳定访问
  // （见 memory-bank ⑰ 的排障记录）。前端优先用 /api/dict?source=translate。
  translate: { kind: 'translate' },
};

/* ---- 翻译上游（与 网站/functions/api/translate.js 保持同款；测试会校验两边 URL 一致） ---- */
function mMlang(code) {
  const c = String(code || '').trim().toLowerCase();
  if (!c) return '';
  if (c.indexOf('zh') === 0) return /hant|tw|hk|mo/.test(c) ? 'zh-TW' : 'zh-CN';
  return c;
}

function myMemoryUrl(q, from, to) {
  return 'https://api.mymemory.translated.net/get?' +
    new URLSearchParams({ q: q, langpair: from + '|' + to }).toString();
}

function googleGtxUrl(q, from, to) {
  return 'https://translate.googleapis.com/translate_a/single?' +
    new URLSearchParams({ client: 'gtx', sl: from, tl: to, dt: 't', q: q }).toString();
}

async function translateVia(q, from, to) {
  const tried = [];
  const attempts = [
    { provider: 'mymemory', url: myMemoryUrl(q, from, to),
      pick: (d) => (d && d.responseData && d.responseData.translatedText) || '',
      match: (d) => (d.responseData && d.responseData.match) || 0 },
    { provider: 'google', url: googleGtxUrl(q, from, to),
      pick: (d) => ((Array.isArray(d) && Array.isArray(d[0])) ? d[0] : [])
        .map(s => (s && s[0]) || '').join('').trim(),
      match: () => 0 },
  ];
  for (const a of attempts) {
    try {
      const r = await fetchWithTimeout(a.url, TIMEOUT_MS);
      // ⚠️ 必须先消费 body！否则（尤其非 2xx 时）CF Pages Functions 会因为
      //    「unconsumed response body」把整个请求判成 502（本项目的翻译接口就栽在这）
      const raw = await r.text();
      if (!r.ok) {
        tried.push({ provider: a.provider, ok: false, upstream: r.status,
                     sample: raw.slice(0, 90) });
        continue;
      }
      let d;
      try { d = JSON.parse(raw); }
      catch (e) { tried.push({ provider: a.provider, ok: false, error: 'bad upstream json' }); continue; }
      const text = String(a.pick(d) || '').trim();
      if (!text || (a.provider === 'mymemory' && d.responseStatus !== 200)) {
        tried.push({ provider: a.provider, ok: false, error: 'no translation', upstream: d && d.responseStatus });
        continue;
      }
      tried.push({ provider: a.provider, ok: true });
      return { ok: true, text: text.slice(0, 2000), match: a.match(d), provider: a.provider, tried };
    } catch (e) {
      tried.push({ provider: a.provider, ok: false, error: 'fetch failed',
                   detail: (e && e.name === 'AbortError') ? 'timeout' : String((e && e.message) || e) });
    }
  }
  return { ok: false, error: 'no translation', tried };
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: Object.assign({ 'content-type': 'application/json; charset=utf-8' }, CORS, extra),
  });
}

/** 带超时的上游请求（Worker / Node 通用） */
async function fetchWithTimeout(url, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await fetch(url, {
      signal: ctl.signal,
      headers: {
        accept: 'application/json',
        'user-agent': UA,
        'Api-User-Agent': 'myfami-reader/1.0 (+https://myfami.cn)',   // 萌典要求带这个
      },
    });
  } finally {
    clearTimeout(timer);
  }
}

/* ---------------- 上游 URL 构造 ---------------- */
function upstreamUrl(source, lang, q) {
  const cfg = SOURCES[source];
  const enc = encodeURIComponent(q);
  if (cfg.kind === 'wiki') {
    return 'https://' + lang + '.' + cfg.host + '/w/api.php?' + new URLSearchParams({
      action: 'query', prop: 'extracts', exintro: '1', explaintext: '1',
      exchars: String(WIKI_CHARS), redirects: '1', format: 'json', origin: '*', titles: q,
    }).toString();
  }
  if (source === 'freedict') {
    return 'https://api.dictionaryapi.dev/api/v2/entries/' + lang + '/' + enc;
  }
  if (source === 'moedict') {
    return 'https://www.moedict.tw/a/' + enc + '.json';
  }
  return '';
}

/* ---------------- 解析：按 source 提取核心字段 ---------------- */
function parseBySource(source, lang, data) {
  const cfg = SOURCES[source] || {};

  if (cfg.kind === 'wiki') {
    const pages = (data && data.query && data.query.pages) || {};
    const first = Object.keys(pages).map(k => pages[k])[0];
    if (!first || 'missing' in first) return { error: 'not found' };
    const extract = String(first.extract || '').trim();
    if (!extract) return { error: 'empty extract' };
    const title = String(first.title || '');
    return {
      title,
      url: 'https://' + lang + '.' + cfg.host + '/wiki/' +
           encodeURIComponent(title.replace(/ /g, '_')),
      result: { extract: extract.slice(0, WIKI_CHARS) },
    };
  }

  if (source === 'freedict') {
    const entry = Array.isArray(data) ? data[0] : data;
    if (!entry || !entry.word) return { error: 'not found' };
    return {
      title: entry.word,
      result: {
        word: entry.word,
        phonetics: (entry.phonetics || []).map(p => p.text).filter(Boolean),
        meanings: (entry.meanings || []).slice(0, 3).map(m => ({
          partOfSpeech: m.partOfSpeech || '',
          definitions: (m.definitions || []).slice(0, 3).map(d => d.definition).filter(Boolean),
        })),
      },
    };
  }

  if (source === 'moedict') {
    // 萌典 /a/{字}.json 的**真实**结构是紧凑键：t=标题, h=heteronyms, b=注音, p=拼音, d=释义数组, f=释义文本
    // （需求伪代码写的是 heteronyms/bopomofo/pinyin/meanings/def —— 两种都兼容，避免上游改版翻车）
    const hs = data && (data.h || data.heteronyms);
    if (!data || !hs || !hs.length) return { error: 'not found' };
    const clean = s => String(s == null ? '' : s).replace(/[`~]/g, '').trim();   // 去萌典的行内标记
    const defs = h => {
      const arr = h.d || h.meanings || [];
      return arr.slice(0, 3).map(m => clean((m && (m.f || m.def)) != null ? (m.f || m.def) : m))
        .filter(Boolean);
    };
    const en = clean((data.translation && data.translation.English) || data.English || '');
    return {
      title: String(data.t || data.title || ''),
      result: {
        word: String(data.t || data.title || ''),
        heteronyms: hs.slice(0, 3).map(h => ({
          bopomofo: h.b || h.bopomofo || '',
          pinyin: h.p || h.pinyin || '',
          meanings: defs(h),
        })),
        en: en,
      },
    };
  }

  return { result: data };
}

/* ---------------- unihan：读本站静态分片（不联网） ---------------- */
async function loadUnihan(q, url, env) {
  const ch = Array.from(q)[0];
  if (!ch) return { error: 'not found' };
  const n = ch.codePointAt(0) % UNIHAN_SHARDS;
  const target = new URL('/_site_data/dict/unihan/' + n + '.json', url.origin).toString();
  let resp;
  try {
    if (env && env.ASSETS && typeof env.ASSETS.fetch === 'function') {
      resp = await env.ASSETS.fetch(new Request(target));      // Pages 资产绑定：零网络
    } else {
      resp = await fetchWithTimeout(target, TIMEOUT_MS);       // 本地/回退：自取本站静态文件
    }
  } catch (e) {
    return { error: 'no local data', detail: String((e && e.message) || e) };
  }
  if (!resp || !resp.ok) return { error: 'no local data', upstream: resp && resp.status };
  let shard;
  try { shard = await resp.json(); } catch (e) { return { error: 'no local data' }; }
  const rec = shard && shard[ch];
  if (!rec) return { error: 'not found' };
  return {
    title: ch,
    result: {
      char: ch,
      pinyin: rec.p || '',
      radical: rec.r || '',
      strokes: rec.s == null ? null : rec.s,
    },
  };
}

/* ---------------- 主入口（带顶层兜底：任何意外都返回 JSON，不让 Pages 吐 502 错误页） ---------------- */
export async function onRequest(ctx) {
  try {
    return await handleRequest(ctx);
  } catch (e) {
    let source = '';
    try { source = new URL(ctx.request.url).searchParams.get('source') || ''; } catch (e2) {}
    return json({ source, error: 'internal', detail: String((e && e.message) || e) }, 500);
  }
}

async function handleRequest(ctx) {
  const request = ctx && ctx.request;
  const env = ctx && ctx.env;

  if (!request) return json({ error: 'bad request' }, 400);
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405);

  const url = new URL(request.url);
  const source = (url.searchParams.get('source') || 'wikipedia').toLowerCase();
  const lang = (url.searchParams.get('lang') || 'zh').toLowerCase();
  const q = (url.searchParams.get('q') || '').trim();

  // 诊断探针（只允许白名单主机，避免变成开放代理；线上排障用；放最前面，不需要 q）
  //   /api/dict?probe=https://api.mymemory.translated.net/get?q=hi&langpair=en%7Czh
  const probe = url.searchParams.get('probe');
  if (probe) {
    const allowed = ['api.mymemory.translated.net', 'translate.googleapis.com', 'www.moedict.tw'];
    let host = '';
    try { host = new URL(probe).hostname; } catch (e) { return json({ error: 'bad probe url' }, 400); }
    if (allowed.indexOf(host) < 0) return json({ error: 'host not allowed', host }, 403);
    const t0 = Date.now();
    try {
      const r = await fetchWithTimeout(probe, TIMEOUT_MS);
      const text = await r.text();
      return json({ probe: probe, host: host, status: r.status, size: text.length,
                    ms: Date.now() - t0, sample: text.slice(0, 200) }, 200);
    } catch (e) {
      return json({ probe: probe, host: host, error: String((e && e.message) || e),
                    name: (e && e.name) || '', ms: Date.now() - t0 }, 200);
    }
  }

  if (!q) return json({ error: 'missing q' }, 400);
  if (q.length > MAX_Q) return json({ error: 'q too long' }, 400);
  if (!SOURCES[source]) return json({ error: 'bad source' }, 400);
  if (!/^[a-z][a-z-]{1,11}$/.test(lang)) return json({ error: 'bad lang' }, 400);

  // ① unihan：本站静态数据，不走网络
  if (source === 'unihan') {
    const r = await loadUnihan(q, url, env);
    if (r.error) return json({ source, query: q, error: r.error, detail: r.detail }, 200, CACHE);
    return json({ source, query: q, title: r.title, result: r.result }, 200, CACHE);
  }

  // ② translate：翻译（MyMemory 主 → Google gtx 备）；参数 langpair=zh-TW|en
  if (source === 'translate') {
    const pair = (url.searchParams.get('langpair') || 'zh-TW|en').split('|');
    const from = mMlang(pair[0]);
    const to = mMlang(pair[1]);
    if (!from || !to) return json({ source, query: q, error: 'bad langpair' }, 400);
    const tr = await translateVia(q, from, to);
    if (!tr.ok) {
      return json({ source, query: q, source_lang: from, target_lang: to,
                    error: tr.error, tried: tr.tried }, 502, CACHE);
    }
    return json({ source, query: q, source_lang: from, target_lang: to,
                  translatedText: tr.text, match: tr.match, provider: tr.provider,
                  result: { translatedText: tr.text, match: tr.match, provider: tr.provider } },
                200, CACHE);
  }

  // ③ 其余：转发第三方（前端只见同域）
  const upstream = upstreamUrl(source, lang, q);
  try {
    const r = await fetchWithTimeout(upstream, TIMEOUT_MS);
    const raw = await r.text();      // ⚠️ 统一先消费 body（未消费时 CF 可能把请求判成 502）
    if (!r.ok) {
      // Free Dictionary 未命中返回 **404 JSON**（不是空数组）→ 归一成 not found 便于前端降级
      if (source === 'freedict' && r.status === 404) {
        return json({ source, query: q, error: 'not found' }, 200, CACHE);
      }
      return json({ source, query: q, error: 'fetch failed', upstream: r.status,
                    sample: raw.slice(0, 90) }, 502);
    }
    let data;
    try { data = JSON.parse(raw); }
    catch (e) { return json({ source, query: q, error: 'bad upstream json' }, 502); }

    const parsed = parseBySource(source, lang, data);
    if (parsed.error) return json({ source, query: q, error: parsed.error }, 200, CACHE);

    const body = { source, query: q, title: parsed.title || q,
                   url: parsed.url, result: parsed.result };
    if (SOURCES[source].kind === 'wiki') body.extract = parsed.result.extract;   // 旧调用方兼容
    return json(body, 200, CACHE);
  } catch (e) {
    const msg = (e && e.name === 'AbortError') ? 'timeout' : String((e && e.message) || e);
    return json({ source, query: q, error: 'fetch failed', detail: msg }, 502);
  }
}
