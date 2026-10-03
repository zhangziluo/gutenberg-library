/**
 * /api/dict —— 在线词典同域代理（Cloudflare Pages Function）
 * ============================================================
 * 前端查词**绝不直连第三方**，统一走本同域接口：
 *   /api/dict?source=wikipedia&lang=zh&q=仁
 *   /api/dict?source=wiktionary&lang=zh&q=仁
 *
 * 转发到对应 wiki 的 **Action API**（带 origin=*），取页面首段（exintro/explaintext）。
 * 约定：
 *   · 任何情况下都返回 JSON（绝不空响应）；
 *   · 上游失败 → 502 {"error":"fetch failed"}；页面不存在 → 200 {"error":"not found"}；
 *   · 响应头始终带 Access-Control-Allow-Origin: *（同域也一并给上，便于跨域调试）。
 */

const HOSTS = { wikipedia: 'wikipedia.org', wiktionary: 'wiktionary.org' };
const TIMEOUT_MS = 8000;
const MAX_Q = 64;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: Object.assign(
      { 'content-type': 'application/json; charset=utf-8' },
      CORS, extra),
  });
}

export async function onRequest({ request }) {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (request.method !== 'GET') {
    return json({ error: 'method not allowed' }, 405);
  }

  const url = new URL(request.url);
  const source = (url.searchParams.get('source') || 'wikipedia').toLowerCase();
  const lang = (url.searchParams.get('lang') || 'zh').toLowerCase();
  const q = (url.searchParams.get('q') || '').trim();

  if (!q) return json({ error: 'missing q' }, 400);
  if (q.length > MAX_Q) return json({ error: 'q too long' }, 400);
  if (!HOSTS[source]) return json({ error: 'bad source' }, 400);
  if (!/^[a-z][a-z-]{1,11}$/.test(lang)) return json({ error: 'bad lang' }, 400);

  const api = 'https://' + lang + '.' + HOSTS[source] + '/w/api.php?' +
    new URLSearchParams({
      action: 'query',
      prop: 'extracts',
      exintro: '1',
      explaintext: '1',
      exchars: '400',
      redirects: '1',
      format: 'json',
      origin: '*',
      titles: q,
    }).toString();

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(api, {
      signal: ctl.signal,
      headers: {
        accept: 'application/json',
        // Wikimedia 要求带 UA（否则可能 403）
        'user-agent': 'yidui-gushu-dict-proxy/1.0 (+https://myfami.cn)',
      },
    });
    if (!r.ok) {
      return json({ error: 'fetch failed', upstream: r.status }, 502);
    }
    const data = await r.json();
    const pages = (data && data.query && data.query.pages) || {};
    const first = Object.keys(pages).map(k => pages[k])[0];
    if (!first || 'missing' in first) {
      return json({ error: 'not found', q, source, lang }, 200);
    }
    const extract = String(first.extract || '').trim();
    if (!extract) {
      return json({ error: 'empty extract', q, source, lang }, 200);
    }
    return json({
      source, lang, q,
      title: first.title || q,
      extract,
      url: 'https://' + lang + '.' + HOSTS[source] + '/wiki/' +
           encodeURIComponent(String(first.title || q).replace(/ /g, '_')),
    }, 200, { 'Cache-Control': 'public, max-age=600' });
  } catch (e) {
    return json({ error: 'fetch failed', detail: String((e && e.message) || e) }, 502);
  } finally {
    clearTimeout(timer);
  }
}
