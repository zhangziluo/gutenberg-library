/**
 * /api/translate —— MyMemory 翻译代理（**根目录转发层**）
 * ============================================================
 * 见 `functions/api/dict.js` 顶部说明：Pages 只从仓库根目录的 functions/ 读 Functions。
 * 实现只有一份：`网站/functions/api/translate.js`。
 */
export { onRequest, mmLang } from '../../网站/functions/api/translate.js';
