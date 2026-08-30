# 部署到 Vercel（后端代理 + API Key 安全）

本目录含 `api/` 两个 Serverless 函数，部署到 Vercel 后：

- **AI API Key 不再出现在前端**：DeepSeek Key 只存在 Vercel 环境变量，用户打开网页即可用 AI，无需注册/填 Key。
- **CTEXT 古籍接口走代理**：解决浏览器直接 fetch 被 CORS 拦截的问题。
- **可公开分享**：部署后会得到 `https://你的项目.vercel.app` 的链接，发给别人就能直接用。

## 一、准备

1. 安装 Vercel CLI：`npm i -g vercel`
2. 注册/登录 Vercel（可用 GitHub 账号）：`vercel login`
3. 准备好你的 DeepSeek API Key（platform.deepseek.com 创建，sk- 开头）

## 二、部署

在**项目根目录**（含 `api/`、`vercel.json`、各 html 的目录）执行：

```bash
vercel          # 首次部署，按提示确认，项目名随意
vercel env add DEEPSEEK_API_KEY   # 粘贴你的 DeepSeek API Key
vercel --prod   # 重新部署使环境变量生效
```

部署完成后，Vercel 会输出一个 `https://xxx.vercel.app` 的地址。

## 三、验证

打开 `https://xxx.vercel.app/shiji_reader.html`：

- 侧边栏 **API Key 输入框可留空**（走代理）。
- 点"📚 在线文库"选一篇古籍 → 回到阅读器，AI 自动逐句翻译应正常工作。
- 若代理不可用（如本地直接双击打开 HTML），则仍需在 Key 输入框填入 DeepSeek Key 走直连。

## 四、本地开发

```bash
vercel dev      # 启动本地开发服务器，自动映射 api/ 为 /api/chat、/api/ctext
```

之后访问 `http://localhost:3000/shiji_reader.html` 即可本地联调代理。

## 五、环境变量说明

| 变量名 | 必填 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API Key（sk- 开头），仅服务端可见 |

CTEXT 走匿名访问（apikey=test），无需配置 Key。

## 六、安全说明

- `api/chat.js` 仅把前端传入的 `system/user` 转发给 DeepSeek，不记录/不存储任何用户文本。
- 前端代码中 `USE_PROXY = true`（`prompt_templates.js`），部署后自动优先走代理；若代理不可达，会自动 fallback 到直连（此时需要前端填 Key）。
- 如需限制调用频率/防滥用，可在 Vercel 后台开启"Rate Limiting"或加一层简单的 IP 限额中间件。
