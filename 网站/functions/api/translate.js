/**
 * /api/translate —— MyMemory 翻译同域代理（Cloudflare Pages Function）
 * ============================================================
 *   GET /api/translate?q=<文本>&from=zh-Hant&to=en
 *   GET /api/translate?q=<文本>&langpair=zh-TW|en        ← 兼容直接给 langpair
 *   → { query, source, target, translatedText, match, url }
 *
 * · 前端绝不直连 api.mymemory.translated.net（同域代理，规避 CORS 与「网络连接已中断」）；
 * · 语言码归一：繁中 → zh-TW、简中 → zh-CN，其余原样；
 * · q 截断到 500 字符（免费版单次上限）；上游超时 3s；
 * · 配额用尽时 MyMemory 返回 responseStatus 403 → 这里 502 + JSON（前端提示「翻译暂不可用」）；
 * · 响应 cache-control: public, max-age=86400。
 */

const MAX_Q = 500;
const TIMEOUT_MS = 2500;
const UA = 'Mozilla/5.0 (compatible; yidui-gushu-translate-proxy/1.0; +https://myfami.cn)';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
const CACHE = { 'Cache-Control': 'public, max-age=86400' };

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: Object.assign({ 'content-type': 'application/json; charset=utf-8' }, CORS, extra),
  });
}

/** 语言码归一（MyMemory 要 zh-TW / zh-CN 这种带地区的形式） */
export function mmLang(code) {
  const c = String(code || '').trim().toLowerCase();
  if (!c) return '';
  if (c.indexOf('zh') === 0) return /hant|tw|hk|mo/.test(c) ? 'zh-TW' : 'zh-CN';
  return c;
}

async function fetchWithTimeout(url, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await fetch(url, { signal: ctl.signal,
                              headers: { accept: 'application/json', 'user-agent': UA } });
  } finally {
    clearTimeout(timer);
  }
}

/** 主源：MyMemory（免费、无需 Key） */
async function viaMyMemory(q, from, to) {
  const api = 'https://api.mymemory.translated.net/get?' +
    new URLSearchParams({ q: q, langpair: from + '|' + to }).toString();
  const r = await fetchWithTimeout(api, TIMEOUT_MS);
  const raw = await r.text();          // ⚠️ 必须消费 body（否则 CF 可能把请求判成 502）
  if (!r.ok) return { ok: false, error: 'fetch failed', upstream: r.status, provider: 'mymemory',
                      sample: raw.slice(0, 90) };
  let d;
  try { d = JSON.parse(raw); } catch (e) { return { ok: false, error: 'bad upstream json', provider: 'mymemory' }; }
  const text = d && d.responseData && d.responseData.translatedText;
  if (!text || d.responseStatus !== 200) {
    return { ok: false, error: 'no translation', provider: 'mymemory',
             upstream: d && d.responseStatus,
             detail: String((d && d.responseDetails) || '').slice(0, 120) };
  }
  return { ok: true, text: String(text).slice(0, 2000), provider: 'mymemory',
           match: (d.responseData && d.responseData.match) || 0,
           url: 'https://mymemory.translated.net/' };
}

/** 备用源：Google 免密 gtx 接口（免费、无需 Key；主源被墙/限流时救急） */
async function viaGoogle(q, from, to) {
  const api = 'https://translate.googleapis.com/translate_a/single?' +
    new URLSearchParams({ client: 'gtx', sl: from, tl: to, dt: 't', q: q }).toString();
  const r = await fetchWithTimeout(api, TIMEOUT_MS);
  const raw = await r.text();          // ⚠️ 同上：body 必须消费
  if (!r.ok) return { ok: false, error: 'fetch failed', upstream: r.status, provider: 'google',
                      sample: raw.slice(0, 90) };
  let d;
  try { d = JSON.parse(raw); } catch (e) { return { ok: false, error: 'bad upstream json', provider: 'google' }; }
  const segs = (Array.isArray(d) && Array.isArray(d[0])) ? d[0] : [];
  const text = segs.map(s => (s && s[0]) || '').join('').trim();
  if (!text) return { ok: false, error: 'no translation', provider: 'google' };
  return { ok: true, text: text.slice(0, 2000), provider: 'google', match: 0,
           url: 'https://translate.google.com/' };
}

/** 备用源：Google 免密 gtx 接口（免费、无需 Key；主源被墙/限流时救急） */
async function viaGoogle(q, from, to) {
  const api = 'https://translate.googleapis.com/translate_a/single?' +
    new URLSearchParams({ client: 'gtx', sl: from, tl: to, dt: 't', q: q }).toString();
  const r = await fetchWithTimeout(api, TIMEOUT_MS);
  if (!r.ok) return { ok: false, error: 'fetch failed', upstream: r.status, provider: 'google' };
  const d = await r.json();
  const segs = (Array.isArray(d) && Array.isArray(d[0])) ? d[0] : [];
  const text = segs.map(s => (s && s[0]) || '').join('').trim();
  if (!text) return { ok: false, error: 'no translation', provider: 'google' };
  return { ok: true, text: text.slice(0, 2000), provider: 'google', match: 0,
           url: 'https://translate.google.com/' };
}

export async function onRequest(ctx) {
  try {
    const request = ctx && ctx.request;
    if (!request) return json({ error: 'bad request' }, 400);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (request.method !== 'GET') return json({ error: 'method not allowed' }, 405);

    const url = new URL(request.url);
    const q = (url.searchParams.get('q') || '').trim().slice(0, MAX_Q);
    if (!q) return json({ error: 'missing q' }, 400);

    const langpair = (url.searchParams.get('langpair') || '').trim();
    let from;
    let to;
    if (langpair) {
      const parts = langpair.split('|');
      from = mmLang(parts[0]);
      to = mmLang(parts[1]);
    } else {
      from = mmLang(url.searchParams.get('from') || 'zh-Hant');
      to = mmLang(url.searchParams.get('to') || 'en');
    }
    if (!from || !to) return json({ error: 'bad langpair' }, 400);

    // 主源 MyMemory → 备用源 Google gtx（任一成功即回；都失败给结构化错误）
    const tried = [];
    for (const fn of [viaMyMemory, viaGoogle]) {
      let r;
      try {
        r = await fn(q, from, to);
      } catch (e) {
        r = { ok: false, provider: fn === viaMyMemory ? 'mymemory' : 'google',
              error: 'fetch failed',
              detail: (e && e.name === 'AbortError') ? 'timeout' : String((e && e.message) || e) };
      }
      tried.push({ provider: r.provider, ok: !!r.ok, error: r.error || '',
                   upstream: r.upstream, detail: r.detail || '' });
      if (r.ok) {
        const body = { query: q, source: from, target: to, translatedText: r.text,
                       match: r.match || 0, provider: r.provider, url: r.url };
        if (url.searchParams.get('debug')) body.tried = tried;
        return json(body, 200, CACHE);
      }
    }
    return json({ error: 'no translation', query: q, source: from, target: to, tried }, 502, CACHE);
  } catch (e) {
    // 顶层兜底：任何意外都返回 JSON，绝不让 Pages 抛 502 错误页（前端才能优雅降级）
    return json({ error: 'internal', detail: String((e && e.message) || e) }, 500);
  }
}
