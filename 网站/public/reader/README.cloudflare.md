# 部署到 Cloudflare Pages（多 Provider AI 代理 + API Key 安全）

本目录（`public/reader/`）既可作为静态站部署到 Cloudflare Pages，`functions/` 目录会被自动识别为 **Pages Functions**（服务端函数）。

**核心安全点：**
- 前端代码中**没有任何站长 Key 明文**
- 站长提供 Provider 的 Key 只存在 Cloudflare Pages 后台环境变量中
- 用户填自己的 Key 时，前端直连对应厂商（Key 只在浏览器，不经服务端）

## 一、环境变量（必配）

在 Cloudflare Pages **项目设置 → 环境变量**中添加：

| 变量 | 用途 | 对应代理 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek V4-Flash（站长提供，低成本） | `/api/proxy/deepseek` |

保存后**重新部署一次**让变量生效。未配置时前端会提示填自己的 Key 或切自填模式。

## 二、部署步骤

1. **推送代码**：把本项目（或本目录）推到 GitHub/GitLab 仓库。
2. **Cloudflare 控制台** → Workers 与 Pages → 创建 → 连接 Git 仓库。
3. **构建配置**：
   - 构建命令：`留空`（纯静态，无需构建）
   - 输出目录：`public/reader`（即本目录；若整个项目根部署则为 `网站/public/reader`）
   - 注意：Functions 自动从 `functions/` 目录收集，**必须保证输出目录内含 `functions/`**。
4. 设置第二节的**一个环境变量**。
5. 部署完成后，打开 `https://你的项目.pages.dev/shiji_reader.html`。

## 三、多 Provider 架构

### 前端（prompt_templates.js 的 `PROVIDERS`）

| 分组 | Provider | 方式 | 说明 |
|---|---|---|---|
| 站长提供 | 💰 DeepSeek V4-Flash | `/api/proxy/deepseek` | 默认选中，**强制 v4-flash** |
| 用户自填 Key | DeepSeek / OpenAI / 阿里百炼 Qwen / 月之暗面 Kimi / 智谱 GLM / 火山方舟豆包 / 自定义端点 | **直连** | Key 只在前端 |

### 失败行为

- 选中站长 Provider → 直接走代理；代理失败 → 提示「服务暂不可用，请填入自己的 DeepSeek Key 后重试」。
- 本地未配置环境变量（代理返回 `LOCAL_MODE`）→ 提示填写自己的 Key 或切换到自填模式。

### UI（侧栏）

- 主下拉共 **2 个选项**（默认 DeepSeek）：💰 DeepSeek V4-Flash（站长提供）→ `/api/proxy/deepseek`；🔑 使用自己的 API Key
- 选「🔑 使用自己的 API Key」展开：服务商下拉 + API Key + 模型名（带默认值）+ 自定义端点（仅 custom 服务商显示）
- 选择持久化到 `localStorage`（`gjs:provider`），Key 持久化到 `guoxue_api_key`

## 四、服务端安全限制（functions/api/proxy/*.js）

| 限制 | 实现 |
|---|---|
| 单次输入最大 token | 3000（约 5000 字），超出返回 400（前端也有同样限制） |
| 单 IP 频率限制 | 60 秒内最多 10 次，超出返回 429 |
| 错误信息 | 全部返回明确的 `{ error: "..." }`；未配置环境变量返回 `LOCAL_MODE:` |
| Key 明文 | 前端绝不出现；仅服务端 `env.*` 读取 |

> ⚠️ 频率限制为**内存 Map 实现**（尽力而为）。Cloudflare Pages 免费档请求可能落在不同 isolate，如需跨请求精确限流，请改用 **Workers KV / Durable Objects** 或 Cloudflare 的 Rate Limiting 规则。

## 五、本地开发

```bash
# 方式一：直接打开 HTML（无服务端）
# 站长 DeepSeek 代理会失败（LOCAL_MODE）→ 提示填 Key 或切自填模式 → 选"使用自己的 API Key"填入即可直连

# 方式二：本地模拟 Pages Functions（推荐）
npm i -g wrangler
cd public/reader
DEEPSEEK_API_KEY=sk-你的Key wrangler pages dev .
# 打开 http://localhost:8788/shiji_reader.html
```

本地**不配**环境变量时，对应函数返回 `LOCAL_MODE` 错误，前端提示填自己的 Key 或切自填模式——符合预期。

## 六、与 Vercel 版本的兼容

- 原有 `api/chat.js`（Vercel Serverless）**保留未动**，Vercel 部署仍可用（`api/` 目录 Vercel 识别、Cloudflare 忽略）。
- Cloudflare 用 `functions/`（含旧的 `/api/chat` 与新 `/api/proxy/*`）。
- 若只用 Vercel 且想要多 Provider 代理，需将 `functions/api/proxy/*.js` 的 handler 转成 Vercel 格式（`export default async function handler(req, res)`）后放入 `api/proxy/`。

