// prompt_templates.js
// AI 模式 Prompt 模板系统 + 统一调用入口
// 供 shiji_reader.html 使用（通过 <script src="prompt_templates.js"></script> 引入）

const PROMPT_TEMPLATES = {
  // 模式1：逐句翻译（阅读中默认）
  translate: {
    label: "逐句翻译",
    system: "你是古文助教。将用户给的一句文言文翻译成现代汉语，并标出1-2个关键采分点（通假字/词类活用/古今异义/重要虚词）。",
    build: (sentence) => `古文：${sentence}\n用JSON返回：{"bai":"白话翻译","notes":["采分点1","采分点2"]}`
  },
  // 模式2：学习卡片（检测理解）
  quiz: {
    label: "学习卡片",
    system: "你是古文助教。根据给定文言文生成一份学习卡片。",
    build: (text) => `文言文：\n${text}\n用JSON返回：{"translation":"全文翻译","quiz":[{"type":"choice|fill|short","question":"题面","options":["A","B","C","D"],"answer":"答案","explanation":"解析"},...]}。题目覆盖字词解释、句子翻译、文意理解，共4-5道。`
  },
  // 模式3：试卷生成（按题型分拆，精确控制数量）
  exam: {
    label: "出试卷",
    system: "你是资深语文教师，擅长根据文言文出标准化自测试卷。",
    byType: {
      choice: (text, n, difficulty) => `根据下面文言文出 ${n} 道单项选择题（4个选项，只有1个正确答案），难度${difficulty}。用JSON数组返回，每项：{"q":"题面","opts":["A","B","C","D"],"a":"正确答案字母","exp":"解析"}。覆盖字词解释、文意理解、细节辨析。\n文言文：\n${text}`,
      judge:  (text, n, difficulty) => `根据下面文言文出 ${n} 道判断题（正确填"对"，错误填"错"），难度${difficulty}。用JSON数组返回，每项：{"q":"判断句","a":"对/错","exp":"解析"}。考察对原文事实与细节的理解。\n文言文：\n${text}`,
      fill:   (text, n,olerance) => `根据下面文言文出 ${n} 道填空题（用"____"表示空，每题1个空，考查核心字词或采分点），难度${difficulty}。用JSON数组返回，每项：{"q":"题目（含____）","a":"答案","exp":"采分点解析"}。\n文言文：\n${text}`,
      short:  (text, n, difficulty) => `根据下面文言文出 ${n} 道简答题（考察翻译/归纳/人物分析），难度${difficulty}。用JSON数组返回，每项：{"q":"问题","a":"参考答案要点","exp":"评分提示"}。\n文言文：\n${text}`
    }
  },
  // 模式4：深度解析
  deepdive: {
    label: "深度解析",
    system: "你是古文研究学者。对用户给出的一句/一段文言文做逐字精讲。",
    build: (text) => `请对下面文言文做深度解析，包含：①逐字/逐词释义（标注词性、用法）②特殊语法（通假/活用/省略/倒装）③涉及的历史典故或文化背景④整段白话串讲。用Markdown格式返回。\n\n文言文：\n${text}`
  },
  // 模式5：跨篇关联
  relate: {
    label: "跨篇关联",
    system: "你是熟读《史记》及诸子百家的古文助教。",
    build: (text, title) => `篇目《${title || "未知"}》片段：\n${text}\n请找出：①本典籍内与该片段主题/人物/写法相关的其他篇目（篇名+简要关联理由）②其他古籍（如《左传》《国语》《论语》《孟子》等）中主题相近的篇目。用JSON返回：{"internal":[{"title":"篇名","reason":"关联理由"}],"external":[{"title":"典籍·篇名","reason":"关联理由"}]}。`
  }
};

// 题型元信息（用于组卷 UI 渲染顺序与标签）
const QUESTION_TYPES = [
  { key: "choice", label: "选择题", defaultN: 3 },
  { key: "judge",  label: "判断题", defaultN: 2 },
  { key: "fill",   label: "填空题", defaultN: 2 },
  { key: "short",  label: "问答题", defaultN: 1 }
];

// 统一调用入口（system + user 两段式）
// payload.lang: 'zh_cn' | 'zh_tw' | 'en' —— 指定 AI 输出语言（注释语言切换用）
const ANN_OUTPUT_LANG = {
  zh_cn: '简体中文',
  zh_tw: '繁體中文',
  en: 'English'
};
async function runMode(modeKey, payload, apiKey, provider, model) {
  const tpl = PROMPT_TEMPLATES[modeKey];
  if (!tpl) throw new Error("未知模式：" + modeKey);
  let userMsg = tpl.build(payload.text, payload.title || "");
  const outLang = ANN_OUTPUT_LANG[payload.lang];
  if (outLang) {
    userMsg += "\n\n重要：所有输出内容（翻译、字词释义、解析、题面、选项、说明等）一律使用"
      + outLang + " 书写，不要夹杂其他语言（专有名词如人名、地名可保留原文）。";
  }
  return callAIChat(tpl.system, userMsg, apiKey, provider, model);
}

// ========== 多 Provider 支持 ==========
// 每项：{ label, group:'free'|'user', endpoint?, proxy?, model, needUserKey }
const PROVIDERS = {
  // —— 站长提供（走服务端代理，无需用户 Key）——
  'deepseek-site': { label: '💰 DeepSeek V4-Flash（站长提供）', group: 'free', proxy: '/api/proxy/deepseek', model: 'deepseek-v4-flash', needUserKey: false },

  // —— 用户自填 Key（直连，needUserKey=true）——
  'deepseek': { label: 'DeepSeek',            group: 'user', endpoint: 'https://api.deepseek.com/v1/chat/completions',            model: 'deepseek-chat',           needUserKey: true },
  'openai':   { label: 'OpenAI',              group: 'user', endpoint: 'https://api.openai.com/v1/chat/completions',              model: 'gpt-4o-mini',             needUserKey: true },
  'qwen':     { label: '阿里百炼 Qwen',        group: 'user', endpoint: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions', model: 'qwen-plus', needUserKey: true },
  'kimi':     { label: '月之暗面 Kimi',        group: 'user', endpoint: 'https://api.moonshot.cn/v1/chat/completions',            model: 'moonshot-v1-8k',          needUserKey: true },
  'glm':      { label: '智谱 GLM',            group: 'user', endpoint: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',   model: 'glm-4-flash',             needUserKey: true },
  'doubao':   { label: '火山方舟豆包',         group: 'user', endpoint: 'https://ark.cn-beijing.volces.com/api/v3/chat/completions', model: 'doubao-seed-1-6-250615', needUserKey: true },
  'custom':   { label: '自定义 OpenAI 兼容端点', group: 'user', endpoint: '', model: '', needUserKey: true }
};

// 自定义端点（由前端 UI 设置，仅用于 custom provider）
let CUSTOM_ENDPOINT = '';

// 输入 token 上限（所有请求，含直连）
const MAX_INPUT_TOKENS = 3000;
function estimateTokens(text) {
  if (!text) return 0;
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const other = text.length - cjk;
  return Math.ceil(cjk * 0.6 + other / 4);
}

// 代理请求（站长提供 Provider）
async function callProxy(proxyPath, system, user, model) {
  let resp;
  try {
    resp = await fetch(proxyPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system, user, model })
    });
  } catch (e) {
    throw new Error("服务暂不可用，请填入自己的 DeepSeek Key 后重试。");
  }
  let data = {};
  try { data = await resp.json(); } catch (e) { /* 非 JSON 响应 */ }
  if (!resp.ok) {
    const msg = data.error || ("HTTP " + resp.status);
    // 本地未配置环境变量：提示填 Key 或切自填模式
    if (msg.indexOf("LOCAL_MODE") === 0) throw new Error("本地模式：服务端未配置 Key，请填写自己的 API Key 或切换到自填模式。");
    throw new Error("服务暂不可用，请填入自己的 DeepSeek Key 后重试。");
  }
  if (!data.choices || !data.choices[0] || !data.choices[0].message) throw new Error("代理返回异常");
  return data.choices[0].message.content;
}

// 用户自填 Key 直连（OpenAI 兼容格式）
async function callOpenAICompat(endpoint, model, system, user, apiKey) {
  if (!endpoint) throw new Error("自定义端点未配置，请在设置里填写。");
  if (!model) throw new Error("模型名不能为空，请在设置里填写。");
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + apiKey },
    body: JSON.stringify({
      model, temperature: 0.7,
      messages: [{ role: "system", content: system }, { role: "user", content: user }]
    })
  });
  let data = {};
  try { data = await resp.json(); } catch (e) { /* 非 JSON */ }
  if (!resp.ok) throw new Error((data.error && (data.error.message || data.error)) || ("AI 请求失败 " + resp.status));
  if (!data.choices || !data.choices[0] || !data.choices[0].message) throw new Error("AI 返回异常");
  return data.choices[0].message.content;
}

// 统一对外：多 Provider 路由
async function callAIChat(system, user, apiKey, provider, model) {
  const prov = PROVIDERS[provider];
  if (!prov) throw new Error("未知 Provider：" + provider);

  // 单次输入 token 上限（所有请求）
  if (estimateTokens((system || "") + " " + (user || "")) > MAX_INPUT_TOKENS) {
    throw new Error("输入内容过长：单次最多 3000 token（约 5000 字），请精简后再试。");
  }

  if (prov.needUserKey) {
    if (!apiKey || !String(apiKey).trim()) throw new Error("本地模式请填入 API Key。");
    const m = (model && String(model).trim()) || prov.model;
    const endpoint = prov.endpoint || CUSTOM_ENDPOINT;
    return callOpenAICompat(endpoint, m, system, user, apiKey);
  }
  // 站长提供 Provider：直接走代理
  return callProxy(prov.proxy, system, user, prov.model);
}

// ===== 兼容壳：setExamAlloc（历史 API，当前前端未调用，保留不报错） =====
function setExamAlloc() { /* 兼容保留 */ }
window.setExamAlloc = setExamAlloc;
