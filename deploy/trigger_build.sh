#!/usr/bin/env bash
# ============================================================
# trigger_build.sh — 触发一次 Cloudflare Pages 构建
# ------------------------------------------------------------
# 凭据按优先级自动选择（有哪个用哪个，都没有就友好退出）：
#   1) CF_DEPLOY_HOOK           —— Pages 控制台「部署钩子」URL（**推荐**，无需 token）
#   2) CF_API_TOKEN + CF_ACCOUNT_ID + CF_PAGES_PROJECT（token 需 Pages:Edit）
#   3) 回退：本机 wrangler 已登录的 OAuth 凭据（~/.wrangler/config/default.toml）
#            + 自动发现账号 / 项目
# 说明：本仓库已与 GitHub 连接，**push 本身就会自动触发构建**；
#       本脚本用于「想再显式触发一次」或 push 没触发时的补救。
#
# 用法（任意目录）：
#   bash deploy/trigger_build.sh              # 触发构建
#   bash deploy/trigger_build.sh --list       # 只列最近 5 次部署（不触发）
#   bash deploy/trigger_build.sh --dry-run    # 只显示将要做什么
#
# 凭据可写在项目根 .env（已在 .gitignore）：
#   CF_DEPLOY_HOOK=https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/xxxx
#   或 CF_API_TOKEN=… CF_ACCOUNT_ID=… CF_PAGES_PROJECT=myfami
# ============================================================
set -uo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"

[ -f "$ROOT/.env" ] && { set -a; . "$ROOT/.env"; set +a; }

DRY=0; LIST=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --list)    LIST=1 ;;
    -h|--help) sed -n '2,25p' "$SELF"; exit 0 ;;
    *) echo "未知参数：${a}（支持 --list / --dry-run）"; exit 2 ;;
  esac
done

PY="$(command -v python3)"
CF_API="https://api.cloudflare.com/client/v4"

# ---------- 1) 部署钩子（最简单） ----------
if [ -n "${CF_DEPLOY_HOOK:-}" ]; then
  if [ "$DRY" = "1" ]; then echo "[dry-run] 将 POST $CF_DEPLOY_HOOK"; exit 0; fi
  echo "==> 触发部署钩子"
  code="$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST "$CF_DEPLOY_HOOK" || echo 000)"
  case "$code" in 2*|3*) echo "  ✅ 已触发（HTTP ${code}）"; exit 0 ;;
                 *) echo "  ❌ 触发失败（HTTP ${code}）；请确认钩子 URL 有效"; exit 1 ;; esac
fi

# ---------- 2/3) API：显式 token 或 wrangler OAuth ----------
TOKEN="${CF_API_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$HOME/.wrangler/config/default.toml" ]; then
  TOKEN="$(grep -m1 '^oauth_token' "$HOME/.wrangler/config/default.toml" \
           | sed -E 's/^[^=]*=[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/')"
  SRC="wrangler OAuth"
else
  SRC="CF_API_TOKEN"
fi
if [ -z "$TOKEN" ]; then
  echo "未找到 Cloudflare 凭据。三种办法任选其一："
  echo "  ① 项目根 .env 写 CF_DEPLOY_HOOK=<Pages 部署钩子 URL>"
  echo "  ② .env 写 CF_API_TOKEN + CF_ACCOUNT_ID + CF_PAGES_PROJECT"
  echo "  ③ 本机执行一次 npx wrangler login"
  exit 0        # 非致命：流水线里只当作提示
fi
AUTH="Authorization: Bearer $TOKEN"

api_get () { curl -s -m 25 -H "$AUTH" "$CF_API/$1"; }

ACC="${CF_ACCOUNT_ID:-}"
if [ -z "$ACC" ]; then
  ACC="$(api_get 'accounts' | "$PY" -c 'import json,sys;d=json.load(sys.stdin);r=d.get("result") or [];print(r[0]["id"] if d.get("success") and r else "")')"
fi
PROJ="${CF_PAGES_PROJECT:-}"
if [ -z "$PROJ" ]; then
  PROJ="$(api_get "accounts/$ACC/pages/projects" | "$PY" -c 'import json,sys;d=json.load(sys.stdin);r=d.get("result") or [];print(r[0]["name"] if d.get("success") and r else "")')"
fi
if [ -z "$ACC" ] || [ -z "$PROJ" ]; then
  echo "❌ 无法确定 account / project（凭据来源：${SRC}）；可用 .env 指定 CF_ACCOUNT_ID / CF_PAGES_PROJECT"
  exit 1
fi
BRANCH="${CF_PAGES_BRANCH:-main}"
echo "凭据：$SRC ｜ 账号：$ACC ｜ 项目：$PROJ ｜ 分支：$BRANCH"

show_deployments () {
  api_get "accounts/$ACC/pages/projects/$PROJ/deployments?per_page=5" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("success"):
    print("  ❌", json.dumps(d.get("errors"), ensure_ascii=False)[:200]); raise SystemExit(1)
print("  最近 5 次部署（提交 / 分支 / 阶段 / 状态 / 时间）")
for x in d["result"]:
    m = (x.get("deployment_trigger") or {}).get("metadata") or {}
    st = x.get("latest_stage") or {}
    print("   %-9s %-6s %-8s %-8s %s" % ((m.get("commit_hash") or "-")[:8],
          (m.get("branch") or "-")[:6], st.get("name") or "-",
          st.get("status") or "-", x.get("created_on")))'
}

if [ "$LIST" = "1" ]; then show_deployments; exit 0; fi

if [ "$DRY" = "1" ]; then
  echo "[dry-run] 将 POST accounts/$ACC/pages/projects/$PROJ/deployments {\"branch\":\"$BRANCH\"}"
  show_deployments
  exit 0
fi

echo "==> 触发构建"
curl -s -m 40 -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  --data "{\"branch\":\"$BRANCH\"}" \
  "$CF_API/accounts/$ACC/pages/projects/$PROJ/deployments" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("success"):
    print("  ❌ 触发失败：", json.dumps(d.get("errors"), ensure_ascii=False)[:300]); raise SystemExit(1)
r = d["result"]
m = (r.get("deployment_trigger") or {}).get("metadata") or {}
print("  ✅ 已触发：id=%s 提交=%s 时间=%s" % (r.get("id"), (m.get("commit_hash") or "-")[:8], r.get("created_on")))
print("     预览：%s" % (r.get("url") or ""))'
