/**
 * /api/dict —— 同域词典代理（**根目录转发层**）
 * ============================================================
 * 为什么这里还有一份：
 *   Cloudflare Pages 的构建配置是「根目录 = 仓库根、输出目录 = 网站/」，
 *   而 Pages **只从「根目录」下的 `functions/` 读取 Functions**（不会去构建输出目录里找）。
 *   真正的实现只写一份，放在 `网站/functions/api/dict.js`；本文件把它原样再导出，
 *   这样「仓库根 functions/」与「网站/functions/」两种布局都能命中路由（不重复实现、不会走偏）。
 *   若哪天把 Pages 项目的根目录改成 `网站`，本文件就变成冗余（留着无害）。
 */
export { onRequest } from '../../网站/functions/api/dict.js';
