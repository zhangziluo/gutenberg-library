# -*- coding: utf-8 -*-
"""
正则单元测试：验证三本书的 heading_pattern 能正确识别标题、归类类别
（因《漢書》《三國志》源文件需用户从古登堡下载，此处用模拟标题行做正则验证）
"""
import re
import sys
sys.path.insert(0, "/data/workspace")
from split_gutenberg import BOOKS


def run(book_name, sample_headings):
    cfg = BOOKS[book_name]
    cats = cfg["cats"]
    heading_re = re.compile(cfg["heading_pattern"])
    print(f"\n📖 《{book_name}》 pattern: {cfg['heading_pattern']}")
    ok = 0
    for line, expect_cat in sample_headings:
        m = heading_re.match(line.strip())
        if not m:
            print(f"  ❌ 未匹配：{line}")
            continue
        # 取类别
        cat = None
        for c in cats:
            if line.strip().endswith(c):
                cat = c
                break
        if cat is None:
            cat = next((c for c in cats if c in line), None)
        status = "✅" if cat == expect_cat else "❌"
        if cat == expect_cat:
            ok += 1
        print(f"  {status} {line}  -> 归类为 [{cat}] (期望 {expect_cat})")
    print(f"  通过 {ok}/{len(sample_headings)}")


if __name__ == "__main__":
    # 《史記》模拟标题 —— 已知能跑通，作为基线
    run("史記", [
        ("史記 五帝本紀", "本紀"),
        ("史記 夏本紀", "本紀"),
        ("史記 三代世表", "表"),
        ("史記 天官書", "書"),
        ("史記 三王世家", "世家"),
        ("史記 仲尼弟子列傳", "列傳"),
        ("史記 貨殖列傳", "列傳"),
    ])

    # 《漢書》模拟标题 —— 古登堡繁体版常见格式
    run("漢書", [
        ("漢書 高帝紀第一", "紀"),
        ("漢書 武帝紀第六", "紀"),
        ("漢書 古今人表", "表"),
        ("漢書 律曆志第一", "志"),
        ("漢書 藝文志第十", "志"),
        ("漢書 項羽傳", "傳"),
        ("漢書 司馬遷傳第三十二", "傳"),
    ])

    # 《三國志》模拟标题 —— 按 魏書/蜀書/吳書 分组
    run("三國志", [
        ("三國志 魏書 武帝紀第一", "魏書"),
        ("三國志 魏書 文帝紀第二", "魏書"),
        ("三國志 蜀書 先主傳第二", "蜀書"),
        ("三國志 吳書 吳主傳第二", "吳書"),
    ])
