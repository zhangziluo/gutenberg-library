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
const TIMEOUT_MS = 3000;
const UA = 'yidui-gushu-translate-proxy/1.0 (+https://myfami.cn)';

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

export async function onRequest(ctx) {
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

  const api = 'https://api.mymemory.translated.net/get?' +
    new URLSearchParams({ q: q, langpair: from + '|' + to }).toString();

  try {
    const r = await fetchWithTimeout(api, TIMEOUT_MS);
    if (!r.ok) return json({ error: 'fetch failed', upstream: r.status }, 502);
    let data;
    try { data = await r.json(); }
    catch (e) { return json({ error: 'bad upstream json' }, 502); }

    const text = data && data.responseData && data.responseData.translatedText;
    if (!text || data.responseStatus !== 200) {
      // 403 = 免费额度用尽（MyMemory 会把提示塞在 responseDetails）
      const detail = String((data && data.responseDetails) || '').slice(0, 120);
      return json({ error: 'no translation', upstream: data && data.responseStatus,
                    detail: detail, query: q, source: from, target: to }, 502, CACHE);
    }
    return json({
      query: q, source: from, target: to,
      translatedText: String(text).slice(0, 2000),
      match: (data.responseData && data.responseData.match) || 0,
      url: 'https://mymemory.translated.net/',
    }, 200, CACHE);
  } catch (e) {
    const msg = (e && e.name === 'AbortError') ? 'timeout' : String((e && e.message) || e);
    return json({ error: 'fetch failed', detail: msg }, 502);
  }
}
