// api/ctext.js
// Vercel Serverless Function
// 代理 CTEXT（中国哲学书电子化计划）API，避免浏览器直接 fetch 被 CORS 拦截。
// 前端调用：/api/ctext?method=gettext&texts=shiji/xiangyu-benji

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(204).end();

  const { method: ctextMethod, texts, query } = req.query || {};
  const params = new URLSearchParams();
  if (ctextMethod) params.set("method", ctextMethod);
  if (texts) params.set("texts", texts);
  if (query) params.set("query", query);
  params.set("apikey", "test"); // 匿名访问

  const url = "https://ctext.org/api.php?" + params.toString();

  try {
    const upstream = await fetch(url);
    const text = await upstream.text();
    res.setHeader("Content-Type", "application/xml; charset=utf-8");
    return res.status(200).send(text);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
