#!/usr/bin/env python3
"""
license_detector.py —— 维基文库页面许可自动检测模块

核心原理：调用 MediaWiki API 的 prop=templates，读取页面 transclude 的模板列表，
匹配维基文库版权模板命名（{{PD-old}} / {{CC-by-sa}} / {{GFDL}} 等），
输出结构化许可判定结果。

维基文库版权模板参考：
- 公有领域：PD-old, PD-old-70, PD-old-50, PD-old-100, PD-old-assumed,
            PD-release, PD-self, PD-anon, PD-US, PD/1996, PD/1923 ...
- 自由许可：CC-by, CC-by-sa, CC-by-2.0/2.5/3.0/4.0, CC-sa,
            GFDL, GFDL_1.2, GPL, LGPL ...
- 其他：CopyrightedFreeUse, PD-self ...
"""

import requests

WS_API = "https://zh.wikisource.org/w/api.php"
UA = {"User-Agent": "MyReader/1.0 (contact: dev@example.com) Python/3.x"}

# ============ 模板 → 许可规则映射 ============
# 键为模板名（小写、去命名空间、去花括号后匹配），值为判定结果

# 公有领域类模板
PD_TEMPLATES = {
    "pd-old", "pd-old-70", "pd-old-60", "pd-old-50", "pd-old-100",
    "pd-old-99", "pd-old-80", "pd-old-75", "pd-old-assumed",
    "pd-release", "pd-self", "pd-anon", "pd-anon-1923", "pd-anon-1996",
    "pd-us", "pd-1923", "pd/1923", "pd/1996", "pd-old-70-1923",
    "pd-old-60-1923", "pd-old-50-1923", "pd-old-100-1996",
    "pd-old-99-1996", "pd-old-80-1996", "pd-old-75-1996",
    "pd-old-70-1996", "pd-old-60-1996", "pd-usgov", "pd-prc-exempt",
}

# CC BY-SA 类（含各版本）
CC_BY_SA_TEMPLATES = {
    "cc-by-sa", "cc-by-sa-2.0", "cc-by-sa-2.5", "cc-by-sa-3.0",
    "cc-by-sa-4.0", "cc-sa",
}

# CC BY 类（只需署名，不要求 SA）
CC_BY_TEMPLATES = {
    "cc-by", "cc-by-2.0", "cc-by-2.5", "cc-by-3.0", "cc-by-4.0",
}

# GFDL 类
GFDL_TEMPLATES = {
    "gfdl", "gfdl-small", "gfdl_1.2", "gfdl-1.2",
}

# GPL / LGPL
GPL_TEMPLATES = {
    "gpl", "lgpl",
}

# 需额外注意 / 未确认
SPECIAL_TEMPLATES = {
    "copyrightedfreeuse",        # 有版权但可自由使用，可能有附加条件
    "copyrightedfreeuseprovidedthat",
    "fairuse",                   # 合理使用，限制较多
    "版权标志",                   # 未确认版权的占位标记
}


def normalize_template(name):
    """把模板名归一化：去命名空间、去空格、小写"""
    name = name.strip()
    # 去掉 {{ }} 包裹
    name = name.strip("{}").strip()
    # 去命名空间前缀，如 Template: / 模板:
    if ":" in name:
        ns, _, tname = name.rpartition(":")
        ns_lower = ns.strip().lower()
        # 只去掉 Template/模板 这类命名空间前缀
        if ns_lower in ("template", "模板", "模板 talk", "template talk"):
            name = tname
    return name.strip().lower()


def fetch_page_templates(title, session=None):
    """
    拉取某页面使用的所有模板列表。
    返回原始模板名列表（未归一化）。
    """
    s = session or requests.Session()
    params = {
        "action": "query",
        "titles": title,
        "prop": "templates",
        "tlnamespace": "10",   # Template 命名空间
        "tllimit": "500",
        "format": "json",
    }
    try:
        r = s.get(WS_API, params=params, headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
        tpls = []
        for page in data.get("query", {}).get("pages", {}).values():
            for t in page.get("templates", []):
                tpls.append(t.get("title", ""))
        return tpls
    except Exception as e:
        print(f"  ⚠️ 模板拉取失败 [{title}]: {e}")
        return []


def detect_license(title, session=None, raw_templates=None):
    """
    对单个页面做许可判定。

    参数：
        title           页面标题
        session         复用 requests.Session
        raw_templates   可选，已拉取的模板列表；不传则自动拉

    返回 dict：
        {
            "status": "pd" | "free" | "restricted" | "unknown",
            "license": "公有领域" | "CC BY-SA 4.0" | ...,
            "redistributable": True/False/None,
            "attribution_required": True/False,
            "share_alike": True/False,
            "templates_matched": [...],
            "warnings": [...],
            "safe_to_use": True/False,
            "note": "给阅读器/用户的说明"
        }
    """
    if raw_templates is None:
        raw_templates = fetch_page_templates(title, session)

    normalized = [normalize_template(t) for t in raw_templates]
    matched = []          # 命中的版权模板
    warnings = []         # 风险提示

    # 分类统计
    pd_hit = []
    cc_by_sa_hit = []
    cc_by_hit = []
    gfdl_hit = []
    gpl_hit = []
    special_hit = []

    for t in normalized:
        if t in PD_TEMPLATES:
            pd_hit.append(t)
        elif t in CC_BY_SA_TEMPLATES:
            cc_by_sa_hit.append(t)
        elif t in CC_BY_TEMPLATES:
            cc_by_hit.append(t)
        elif t in GFDL_TEMPLATES:
            gfdl_hit.append(t)
        elif t in GPL_TEMPLATES:
            gpl_hit.append(t)
        elif t in SPECIAL_TEMPLATES:
            special_hit.append(t)

    matched = pd_hit + cc_by_sa_hit + cc_by_hit + gfdl_hit + gpl_hit + special_hit

    # ===== 判定逻辑 =====
    result = {
        "status": "unknown",
        "license": "未知",
        "redistributable": None,
        "attribution_required": None,
        "share_alike": None,
        "templates_matched": matched,
        "warnings": warnings,
        "safe_to_use": False,
        "note": "",
    }

    # 情况 1：明确公有领域
    if pd_hit and not (cc_by_sa_hit or cc_by_hit or gfdl_hit or gpl_hit):
        result.update({
            "status": "pd",
            "license": "公有领域（Public Domain）",
            "redistributable": True,
            "attribution_required": False,
            "share_alike": False,
            "safe_to_use": True,
            "note": "原文及批注属公有领域，可自由使用与再分发；"
                    "仍请保留作者署名与底本出处，并尊重署名权与保护作品完整权。",
        })
        # 若同时含 PD-old-70 等，提示注意美国版权差异
        if "pd-old-70" in pd_hit or "pd-old" in pd_hit:
            warnings.append(
                "页面使用 PD-old/PD-old-70 模板，依作者逝世年份判定为公有领域；"
                "若作品曾于 1923-1977 年间在美国出版，须另行确认美国版权状态。"
            )

    # 情况 2：CC BY-SA（含双许可叠加）
    elif cc_by_sa_hit:
        # 取最高版本号
        version = _highest_cc_version(cc_by_sa_hit)
        result.update({
            "status": "free",
            "license": f"CC BY-SA {version}",
            "redistributable": True,
            "attribution_required": True,
            "share_alike": True,
            "safe_to_use": True,
            "note": f"本页含 CC BY-SA {version} 授权的编辑性贡献。"
                   f"再分发须署名来源、标注许可，且衍生文本须以相同许可发布。",
        })
        if gfdl_hit:
            warnings.append("本页同时标记 GFDL，属双许可叠加，两者择一合规即可。")

    # 情况 3：仅 CC BY（不要求 SA）
    elif cc_by_hit:
        version = _highest_cc_version(cc_by_hit)
        result.update({
            "status": "free",
            "license": f"CC BY {version}",
            "redistributable": True,
            "attribution_required": True,
            "share_alike": False,
            "safe_to_use": True,
            "note": f"本页含 CC BY {version} 授权的编辑性贡献，再分发须署名来源与许可。",
        })
        if gfdl_hit:
            warnings.append("本页同时标记 GFDL，属双许可叠加。")

    # 情况 4：GFDL
    elif gfdl_hit:
        result.update({
            "status": "free",
            "license": "GFDL",
            "redistributable": True,
            "attribution_required": True,
            "share_alike": True,
            "safe_to_use": True,
            "note": "本页以 GNU 自由文档许可证发布，须保留许可声明与署名。",
        })

    # 情况 5：GPL / LGPL
    elif gpl_hit:
        result.update({
            "status": "free",
            "license": "GPL/LGPL",
            "redistributable": True,
            "attribution_required": True,
            "share_alike": True,
            "safe_to_use": True,
            "note": "本页以 GPL/LGPL 发布，条款较严格，请仔细阅读许可证全文。",
        })
        warnings.append("GPL/LGPL 对衍生作品要求完整开源，用于电子书再分发前请法务确认。")

    # 情况 6：CopyrightedFreeUse / FairUse / 未确认
    elif special_hit:
        if "copyrightedfreeuse" in special_hit or "copyrightedfreeuseprovidedthat" in special_hit:
            result.update({
                "status": "restricted",
                "license": "CopyrightedFreeUse（有条件自由使用）",
                "redistributable": None,
                "attribution_required": True,
                "share_alike": False,
                "safe_to_use": False,
                "note": "页面标记 CopyrightedFreeUse，可能有附加条件（如非商业用途），"
                        "须人工核实具体条款后方可使用。",
            })
        elif "fairuse" in special_hit:
            result.update({
                "status": "restricted",
                "license": "合理使用（Fair Use）",
                "redistributable": False,
                "attribution_required": True,
                "share_alike": False,
                "safe_to_use": False,
                "note": "合理使用仅限特定场景，不适合作为阅读器内置书源批量再分发。",
            })
        elif "版权标志" in special_hit:
            result.update({
                "status": "unknown",
                "license": "未确认",
                "redistributable": None,
                "attribution_required": None,
                "share_alike": None,
                "safe_to_use": False,
                "note": "页面版权尚未确认，维基文库可能予以删除；请勿作为内置书源使用。",
            })

    # 情况 7：啥模板都没匹配上
    else:
        if not matched:
            warnings.append("未检测到已知版权模板，可能为现代整理本或未标记页面。")
        result.update({
            "status": "unknown",
            "license": "未识别",
            "redistributable": None,
            "attribution_required": None,
            "share_alike": None,
            "safe_to_use": False,
            "note": "无法自动判定许可，建议人工核实页面底部版权标记，"
                    "或改用明确标记公有领域/自由许可的版本。",
        })

    result["warnings"] = warnings
    return result


def _highest_cc_version(hits):
    """从 CC 模板命中列表里取最高版本号，默认 4.0"""
    best = 0.0
    for h in hits:
        for ver in ("4.0", "3.0", "2.5", "2.0"):
            if ver in h:
                f = float(ver)
                if f > best:
                    best = f
                break
    return f"{best:.1f}" if best else "4.0"


def batch_detect(titles, session=None):
    """批量判定一组页面的许可，返回 {title: result}"""
    s = session or requests.Session()
    out = {}
    for t in titles:
        out[t] = detect_license(t, session=s)
    return out


# ============ 命令行自检 ============
if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] or [
        "水滸傳 (70回本)/楔子",
        "三國演義/第001回",
    ]
    s = requests.Session()
    for t in targets:
        print(f"\n🔍 {t}")
        r = detect_license(t, session=s)
        print(f"   许可: {r['license']}")
        print(f"   可再分发: {r['redistributable']}  | 需署名: {r['attribution_required']}  | SA: {r['share_alike']}")
        print(f"   可安全使用: {r['safe_to_use']}")
        print(f"   说明: {r['note']}")
        if r["warnings"]:
            for w in r["warnings"]:
                print(f"   ⚠️ {w}")
        print(f"   命中模板: {r['templates_matched']}")
