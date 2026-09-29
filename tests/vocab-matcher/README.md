# vocab-matcher 测试（Node 直跑，不需要浏览器/构建）

验证 `网站/js/vocab-matcher.js`（前端词级标注）与 `reader.js` 的接线。**不在部署产物里**
（`deploy/build.sh` 只复制 `网站/`），纯本地开发用。

## 跑法

```bash
cd <项目根>

# 1. 模块自检（纯函数，66 项断言；浏览器里也能跑：reader.html?vmselftest=1）
node -e "const V=require('./网站/js/vocab-matcher.js');const r=V.selftest();
console.log('通过 '+r.pass+' 失败 '+r.fail, r.failed);"

# 2. DOM 层（Node + 极简 DOM shim：TreeWalker / 空闲分批 / <wise> 落节点 / 幂等 / 取消 / 跳过区）
node tests/vocab-matcher/dom-test.js

# 3. 集成（真实书 JSON + 真实 vocab_final.json + opencc 简繁转换）
node tests/vocab-matcher/integration-test.js

# 4. 浏览器冒烟（jsdom 加载真实 reader.html；需先装 jsdom，本仓库无根 package.json）
npm i --prefix /tmp/vmtest jsdom
export JSDOM_PATH=/tmp/vmtest/node_modules/jsdom
node tests/vocab-matcher/reader-smoke-test.js                      # 默认 論語
BOOK=Walden node tests/vocab-matcher/reader-smoke-test.js          # 换书（英文）
NO_VOCAB=1 node tests/vocab-matcher/reader-smoke-test.js           # 健壮性：词表缺失 → 降级为只用 annotations
VOCAB_WRAP=all node tests/vocab-matcher/reader-smoke-test.js       # 密度开关：词级全标（默认 gloss，另有 rare）

# 5. 词表内嵌释义展示（词表词被标 + 词卡显示 definition；need_ai → 「AI 待補」标签）
node tests/vocab-matcher/definition-show-test.js
```

## 覆盖的硬保证

- 分段拼回 **逐字等于**原文本（`textContent` 不变 → 复制/下载/划选/AI 全不受影响）
- 英文命中必须是**最大词形**：`mornin'` 整词（不得截成 `mornin`）、`untouched` 不命中 `touch`
- 中文命中必须落在**同一 CJK 连续段**内，且**词内不散单字**（`君子`/`人不知` 整体成段）
- 重叠永远取**最长**（`不知 > 不 + 知`）；命中不重叠
- 词表行内嵌释义：`definition`（占位「待补」不算释义）计入「有释义」→ 词表词因此可标；
  行首四元（词形/简体/词次/书数）**不被解析改写**（`raw[4]` 只读作 definition，不再误读成 pinyin）
- 幂等：同一段重跑不重复包裹；跳过区（`<script>/<pre>/[data-no-annotate]/<wise>`）不打标
- reader 接线：`<wise data-word>` 是完整词形（词卡标题即取它）、旧 `.ann-word` 类名保留、
  换档/切简繁后重渲染仍逐字一致

## 文件

| 文件 | 作用 |
| --- | --- |
| `dom-shim.js` | 极简 DOM（element/text/fragment/TreeWalker/closest/isConnected），只为跑 `annotate()` |
| `dom-test.js` | DOM 层测试（21 项） |
| `integration-test.js` | 真实语料集成（26 项，含 繁→简、英文缩写/所有格、词表内嵌释义 definition/need_ai） |
| `definition-show-test.js` | 词表释义展示（jsdom 真实页面，6 项：内嵌释义命中 22、待补词被误标 0、点 `無邪` 词卡出释义 + 「AI 待補」标签） |
| `reader-smoke-test.js` | jsdom 加载真实页面（14 项，可用 `BOOK=` 换书） |
