// api/chat.js
// Vercel Serverless Function
// 接收前端 POST { system, user, model? }，转发给 DeepSeek，返回模型输出。
// 前端永远不需要 API Key；Key 只存在 Vercel 环境变量 DEEPSEEK_API_KEY 中。

export default async function handler(req, res) {
  // 允许简单的前后端同域调用
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  const { system, user, model, json } = req.body || {};
  if (!user) return res.status(400).json({ error: "缺少 user 字段" });

  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return res.status(500).json({
      error: "服务端未配置 DEEPSEEK_API_KEY，请在 Vercel 后台添加该环境变量。"
    });
  }

  try {
    const upstreamBody = {
      model: model || "deepseek-chat",
      messages: [
        { role: "system", content: system || "你是古文助教。" },
        { role: "user", content: user }
      ],
      temperature: 0.7,
      stream: false
    };
    if (json) upstreamBody.response_format = { type: "json_object" }; // 强制 JSON 输出
    const upstream = await fetch("https://api.deepseek.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify(upstreamBody)
    });

    const data = await upstream.json();
    if (!upstream.ok) return res.status(upstream.status).json(data);
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
