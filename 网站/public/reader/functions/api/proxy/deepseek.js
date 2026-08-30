// functions/api/proxy/deepseek.js
// Cloudflare Pages Functions —— DeepSeek 代理（低成本兜底）
// 环境变量：DEEPSEEK_API_KEY（服务端设置，前端绝不出现）
// 模型强制 deepseek-v4-flash（成本控制，不使用 Pro）
// 限制：单次输入 ≤3000 token；单 IP 60 秒 ≤10 次

const VENDOR_ENDPOINT = 'https://api.deepseek.com/chat/completions';
const ENV_KEY = 'DEEPSEEK_API_KEY';
const FORCED_MODEL = 'deepseek-v4-flash'; // 强制模型，忽略前端传入

const MAX_INPUT_TOKENS = 3000;
const RATE_LIMIT_WINDOW_MS = 60000;
const RATE_LIMIT_MAX = 10;
const UPSTREAM_TIMEOUT_MS = 30000; // 上游请求超时，避免函数长时间挂起
const rateMap = new Map();

function json(headers, obj, status) {
  return new Response(JSON.stringify(obj), { status, headers });
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json; charset=utf-8'
  };
}

function estimateTokens(text) {
  if (!text) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const other = text.length - cjk;
  return Math.ceil(cjk * 0.6 + other / 4);
}

function isRateLimited(ip) {
  const now = Date.now();
  const arr = (rateMap.get(ip) || []).filter(t => now - t < RATE_LIMIT_WINDOW_MS);
  if (arr.length >= RATE_LIMIT_MAX) { rateMap.set(ip, arr); return true; }
  arr.push(now);
  rateMap.set(ip, arr);
  return false;
}

// 取客户端 IP：CF-Connecting-IP 优先；x-forwarded-for 可能是逗号分隔的代理链，取第一个
function clientIp(request) {
  const cf = request.headers.get('CF-Connecting-IP');
  if (cf && cf.trim()) return cf.trim();
  const fwd = request.headers.get('x-forwarded-for');
  if (fwd) {
    const first = fwd.split(',')[0].trim();
    if (first) return first;
  }
  return 'unknown';
}

// 从上游错误响应中提取人类可读信息（保证返回字符串，避免对象泄漏给前端）
function upstreamErrorMessage(data, rawText, status) {
  if (data && data.error) {
    const e = data.error;
    if (typeof e === 'string' && e) return e;
    if (e && typeof e.message === 'string' && e.message) return e.message;
    if (e && typeof e === 'object') {
      try { return JSON.stringify(e); } catch (err) { /* 忽略 */ }
    }
  }
  const snippet = (rawText || '').trim().slice(0, 200);
  return '上游 AI 服务错误：' + status + (snippet ? '（' + snippet + '）' : '');
}

export async function onRequest(context) {
  const { request, env } = context;
  const headers = corsHeaders();

  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
  if (request.method !== 'POST') return json(headers, { error: '方法不允许，仅支持 POST' }, 405);

  const ip = clientIp(request);
  if (isRateLimited(ip)) {
    return json(Object.assign({}, headers, { 'Retry-After': String(RATE_LIMIT_WINDOW_MS / 1000) }),
      { error: '请求过于频繁，请在 60 秒后重试。' }, 429);
  }

  let body;
  try { body = await request.json(); } catch (e) { return json(headers, { error: '请求体不是合法 JSON' }, 400); }
  const { system, user } = body || {};
  if (!user || typeof user !== 'string' || !user.trim()) return json(headers, { error: '缺少 user 字段' }, 400);
  if (system !== undefined && system !== null && typeof system !== 'string') {
    return json(headers, { error: 'system 字段必须是字符串' }, 400);
  }

  if (estimateTokens((system || '') + ' ' + user) > MAX_INPUT_TOKENS) {
    return json(headers, { error: '输入内容过长：单次最多 3000 token（约 5000 字），请精简后再试。' }, 400);
  }

  const apiKey = env[ENV_KEY];
  if (!apiKey) {
    return json(headers, { error: 'LOCAL_MODE:服务端未配置 ' + ENV_KEY + '，请在 Cloudflare Pages 后台添加。' }, 500);
  }

  const upstreamBody = {
    model: FORCED_MODEL, // 强制 deepseek-v4-flash
    messages: [
      { role: 'system', content: system || '你是古文助教。' },
      { role: 'user', content: user }
    ],
    temperature: 0.7,
    stream: false,
    // deepseek-v4 默认开启思考模式（默认高努力）：此时 temperature 会被忽略，且更慢更贵。
    // 本代理定位“低成本兜底”，显式关闭思考模式，让 temperature 生效、响应更快。
    thinking: { type: 'disabled' },
    max_tokens: 2000 // 限制输出长度，控制成本
  };

  // 超时控制：避免上游挂起导致函数长时间占住
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const upstream = await fetch(VENDOR_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey },
      body: JSON.stringify(upstreamBody),
      signal: controller.signal
    });
    // 先按文本读取：上游错误响应可能不是 JSON（如网关 502 的 HTML 页面）
    const rawText = await upstream.text();
    let data = null;
    try { data = rawText ? JSON.parse(rawText) : null; } catch (e) { data = null; }

    if (!upstream.ok) {
      // 上游 429 透传为 429（与智谱一致，便于前端统一处理）
      const status = upstream.status === 429 ? 429 : 502;
      return json(headers, { error: upstreamErrorMessage(data, rawText, upstream.status) }, status);
    }
    if (!data || !data.choices) {
      return json(headers, { error: '上游 AI 服务返回异常（缺少 choices 字段）' }, 502);
    }
    return json(headers, data, 200);
  } catch (err) {
    const reason = (err && err.name === 'AbortError')
      ? '上游 AI 服务响应超时，请稍后重试。'
      : 'AI 服务暂时不可用：' + (err && err.message);
    return json(headers, { error: reason }, 502);
  } finally {
    clearTimeout(timer);
  }
}
