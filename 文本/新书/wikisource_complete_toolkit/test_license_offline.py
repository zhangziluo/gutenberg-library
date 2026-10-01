#!/usr/bin/env python3
"""
离线测试：模拟维基文库页面返回的模板列表，验证 detect_license 判定逻辑。
这些模板名来自维基文库真实版权标记页面（Help:版权标记 / Wikisource:Copyright tags）。
"""

from license_detector import detect_license, normalize_template


# 模拟 API 返回的 templates 字段（title 带 "Template:" 命名空间前缀）
SAMPLES = {
    "公有领域 · 古籍正文（如水浒金本、三国、西游、红楼各回）": [
        "Template:PD-old",
    ],
    "公有领域 · 作者逝世70年以上": [
        "Template:PD-old-70",
    ],
    "CC BY-SA 4.0 · 含现代编辑贡献": [
        "Template:Header",
        "Template:PD-old",
        "Template:CC-by-sa-4.0",
    ],
    "CC BY-SA 3.0 · 多版本命中应取最高": [
        "Template:CC-by-sa-2.0",
        "Template:CC-by-sa-3.0",
        "Template:CC-by-sa-4.0",
    ],
    "CC BY（不要求SA）": [
        "Template:CC-by-4.0",
    ],
    "GFDL 双许可叠加": [
        "Template:GFDL",
        "Template:PD-old-70",
    ],
    "CopyrightedFreeUse · 需人工核实": [
        "Template:CopyrightedFreeUse",
    ],
    "合理使用 · 不可用": [
        "Template:Fairuse",
    ],
    "未确认版权 · 不可用": [
        "Template:版权标志",
    ],
    "啥都没有 · 无法判定": [],
}


def main():
    print("=" * 70)
    print("维基文库许可检测模块 · 离线逻辑验证")
    print("=" * 70)

    pass_count = 0
    fail_count = 0

    for label, tpls in SAMPLES.items():
        # 用 raw_templates 直接注入，跳过网络请求
        r = detect_license("测试页", raw_templates=tpls)
        ok = r["safe_to_use"]
        icon = "✅" if ok else "⚠️ "
        print(f"\n{icon} {label}")
        print(f"   模板: {tpls if tpls else '(空)'}")
        print(f"   判定许可: {r['license']}")
        print(f"   可再分发: {r['redistributable']}  "
              f"需署名: {r['attribution_required']}  "
              f"SA: {r['share_alike']}  "
              f"安全: {r['safe_to_use']}")
        print(f"   说明: {r['note']}")
        if r["warnings"]:
            for w in r["warnings"]:
                print(f"   ⚠️ {w}")
        if ok:
            pass_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 70)
    print(f"验证完成：安全可用 {pass_count} 类 / 受限或未知 {fail_count} 类")
    print("=" * 70)


if __name__ == "__main__":
    main()
