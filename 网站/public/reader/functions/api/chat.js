// functions/api/chat.js
// Cloudflare Pages Functions —— AI 聊天代理
// 部署到 Cloudflare Pages 后，本函数自动挂在 /api/chat。
// 前端无需任何 API Key；本站主 Key 只存在 Cloudflare Pages 后台环境变量 DEEPSEEK_API_KEY 中。
//
// 环境变量：DEEPSEEK_API_KEY（必填）
// 安全限制：
//   1) 单次输入最大 3000 token（约 5000 字）
//   2) 简单单 IP 频率限制：同一 IP 60 秒内最多 10 次请求
//   3) 所有错误返回明确的 error 字段，前端可据此提示用户

const MAX_INPUT_TOKENS = 3000;        // 单次最大输入 token
const RATE_LIMIT_WINDOW_MS = 60_000;  // 限流窗口：60 秒
const RATE_LIMIT_MAX = 10;            // 每窗口最多请求次数

// 简易内存限流（尽力而为）：
// Cloudflare Pages Functions 免费档每次请求可能由不同 isolate 处理，
// 该 Map 在单实例内生效。如需跨请求精确限流，请改用 KV / Durable Objects。
const rateMap = new Map(); // ip -> number[]（时间戳数组）

function json(headers, obj, status) {
  return new Response(JSON.stringify(obj), { status, headers });
}

function corsHeaders(extra) {
  return Object.assign({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8"
  }, extra || {});
}

// 简易 token 估算：中文 1 字 ≈ 0.6 token，其他字符 ≈ 4 字符 1 token
// （3000 token ≈ 约 5000 个中文字符）
function estimateTokens(text) {
  if (!text) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const other = text.length - cjk;
  return Math.ceil(cjk * 0.6 + other / 4);
}

function isRateLimited(ip) {
  const now = Date.now();
  const arr = (rateMap.get(ip) || []).filter(t => now - t < RATE_LIMIT_WINDOW_MS);
  if (arr.length >= RATE_LIMIT_MAX) {
    rateMap.set(ip, arr);
    return true;
  }
  arr.push(now);
  rateMap.set(ip, arr);
  return false;
}

export async function onRequest(context) {
  const { request, env } = context;
  const headers = corsHeaders();

  // ---- CORS 预检 ----
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }
  if (request.method !== "POST") {
    return json(headers, { error: "方法不允许，仅支持 POST" }, 405);
  }

  // ---- 1) 单 IP 频率限制 ----
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("x-forwarded-for") || "unknown";
  if (isRateLimited(ip)) {
    return json(headers, { error: "请求过于频繁，请在 60 秒后重试。" }, 429);
  }

  // ---- 2) 解析请求体 ----
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return json(headers, { error: "请求体不是合法 JSON" }, 400);
  }
  const { system, user, model, json: wantJson } = body || {};
  if (!user || typeof user !== "string" || !user.trim()) {
    return json(headers, { error: "缺少 user 字段" }, 400);
  }

  // ---- 3) 输入长度限制（3000 token ≈ 约 5000 字） ----
  const inputText = ((system || "") + " " + user);
  if (estimateTokens(inputText) > MAX_INPUT_TOKENS) {
    return json(headers, {
      error: "输入内容过长：单次最多 3000 token（约 5000 字），请精简后再试。"
    }, 400);
  }

  // ---- 4) 读取服务端 Key（绝不进入前端） ----
  const apiKey = env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    // 本地开发 / 未配置环境变量：前端据此提示“本地模式请填入 API Key”
    return json(headers, {
      error: "LOCAL_MODE:服务端未配置 DEEPSEEK_API_KEY，请在 Cloudflare Pages 后台添加该环境变量。"
    }, 500);
  }

  // ---- 5) 转发给 DeepSeek ----
  const upstreamBody = {
    model: model || "deepseek-chat",
    messages: [
      { role: "system", content: system || "你是古文助教。" },
      { role: "user", content: user }
    ],
    temperature: 0.7,
    stream: false
  };
  if (wantJson) upstreamBody.response_format = { type: "json_object" };

  try {
    const upstream = await fetch("https://api.deepseek.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + apiKey
      },
      body: JSON.stringify(upstreamBody)
    });

    const data = await upstream.json();
    if (!upstream.ok) {
      const msg = (data.error && data.error.message) || ("上游 AI 服务错误：" + upstream.status);
      return json(headers, { error: msg }, 502);
    }
    return json(headers, data, 200);
  } catch (err) {
    return json(headers, { error: "AI 服务暂时不可用：" + err.message }, 502);
  }
}
