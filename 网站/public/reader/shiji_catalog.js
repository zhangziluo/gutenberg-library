// 《史记》全 130 篇目录（按司马迁原书体例：本纪12 + 表10 + 书8 + 世家30 + 列传70 = 130）
// ctextId 为中国哲学书电子化计划（CTEXT，ctext.org）的篇目 URL slug，用于在线文库检索/加载。
// 若某篇 CTEXT slug 不稳定，文库会回退到"关键词检索"模式，不影响使用。
// 用法：<script src="shiji_catalog.js"></script> 后使用全局 SHIJI_CATALOG。

(function (global) {
  var B = [ // 本纪 12
    ["五帝本纪第一","shiji/wu-di-benji"],["夏本纪第二","shiji/xia-benji"],["殷本纪第三","shiji/yin-benji"],
    ["周本纪第四","shiji/zhou-benji"],["秦本纪第五","shiji/qin-benji"],["秦始皇本纪第六","shiji/qin-shihuang-benji"],
    ["项羽本纪第七","shiji/xiangyu-benji"],["高祖本纪第八","shiji/gaozu-benji"],["吕太后本纪第九","shiji/lv-taihou-benji"],
    ["孝文本纪第十","shiji/xiao-wen-benji"],["孝景本纪第十一","shiji/xiao-jing-benji"],["孝武本纪第十二","shiji/xiao-wu-benji"]
  ];
  var T = [ // 表 10
    ["三代世表第一","shiji/san-dai-shi-biao"],["十二诸侯年表第二","shiji/shi-er-zhu-hou-nian-biao"],["六国年表第三","shiji/liu-guo-nian-biao"],
    ["秦楚之际月表第四","shiji/qin-chu-zhi-ji-yue-biao"],["汉兴以来诸侯王年表第五","shiji/han-xing-yi-lai-zhu-hou-wang-nian-biao"],["高祖功臣侯者年表第六","shiji/gaozu-gong-chen-hou-zhe-nian-biao"],
    ["惠景间侯者年表第七","shiji/hui-jing-jian-hou-zhe-nian-biao"],["建元以来侯者年表第八","shiji/jian-yuan-yi-lai-hou-zhe-nian-biao"],["建元已来王子侯者年表第九","shiji/jian-yuan-yi-lai-wang-zi-hou-zhe-nian-biao"],["汉兴以来将相名臣年表第十","shiji/han-xing-yi-lai-jiang-xiang-ming-chen-nian-biao"]
  ];
  var S = [ // 书 8
    ["礼书第一","shiji/li-shu"],["乐书第二","shiji/yue-shu"],["律书第三","shiji/lv-shu"],["历书第四","shiji/li-shu2"],
    ["天官书第五","shiji/tian-guan-shu"],["封禅书第六","shiji/feng-shan-shu"],["河渠书第七","shiji/he-qu-shu"],["平准书第八","shiji/ping-zhun-shu"]
  ];
  var J = [ // 世家 30
    ["吴太伯世家第一","shiji/wu-taibo-shi-jia"],["齐太公世家第二","shiji/qi-taigong-shi-jia"],["鲁周公世家第三","shiji/lu-zhougong-shi-jia"],["燕召公世家第四","shiji/yan-zhaogong-shi-jia"],["管蔡世家第五","shiji/guan-cai-shi-jia"],
    ["陈杞世家第六","shiji/chen-qi-shi-jia"],["卫康叔世家第七","shiji/wei-kangshu-shi-jia"],["宋微子世家第八","shiji/song-weizi-shi-jia"],["晋世家第九","shiji/jin-shi-jia"],["楚世家第十","shiji/chu-shi-jia"],
    ["越王勾践世家第十一","shiji/yue-wang-goujian-shi-jia"],["郑世家第十二","shiji/zheng-shi-jia"],["赵世家第十三","shiji/zhao-shi-jia"],["魏世家第十四","shiji/wei-shi-jia"],["韩世家第十五","shiji/han-shi-jia"],
    ["田敬仲完世家第十六","shiji/tian-jingzhong-wan-shi-jia"],["孔子世家第十七","shiji/kongzi-shi-jia"],["陈涉世家第十八","shiji/chen-she-shi-jia"],["外戚世家第十九","shiji/wai-qi-shi-jia"],["楚元王世家第二十","shiji/chu-yuanwang-shi-jia"],
    ["荆燕世家第二十一","shiji/jing-yan-shi-jia"],["齐悼惠王世家第二十二","shiji/qi-daohui-wang-shi-jia"],["萧相国世家第二十三","shiji/xiao-xiangguo-shi-jia"],["曹相国世家第二十四","shiji/cao-xiangguo-shi-jia"],["留侯世家第二十五","shiji/liu-hou-shi-jia"],
    ["陈丞相世家第二十六","shiji/chen-chengxiang-shi-jia"],["绛侯周勃世家第二十七","shiji/jiang-hou-zhou-bo-shi-jia"],["梁孝王世家第二十八","shiji/liang-xiaowang-shi-jia"],["五宗世家第二十九","shiji/wu-zong-shi-jia"],["三王世家第三十","shiji/san-wang-shi-jia"]
  ];
  var L = [ // 列传 70
    ["伯夷列传第一","shiji/bo-yi-liezhuan"],["管晏列传第二","shiji/guan-yan-liezhuan"],["老子韩非列传第三","shiji/laozi-hanfei-liezhuan"],["司马穰苴列传第四","shiji/sima-rangju-liezhuan"],["孙子吴起列传第五","shiji/sunzi-wuqi-liezhuan"],
    ["伍子胥列传第六","shiji/wu-zixu-liezhuan"],["仲尼弟子列传第七","shiji/zhongni-dizi-liezhuan"],["商君列传第八","shiji/shang-jun-liezhuan"],["苏秦列传第九","shiji/su-qin-liezhuan"],["张仪列传第十","shiji/zhang-yi-liezhuan"],
    ["樗里子甘茂列传第十一","shiji/chu-lizi-gan-mao-liezhuan"],["穰侯列传第十二","shiji/rang-hou-liezhuan"],["白起王翦列传第十三","shiji/bai-qi-wang-jian-liezhuan"],["孟子荀卿列传第十四","shiji/mengzi-xunqing-liezhuan"],["孟尝君列传第十五","shiji/mengchang-jun-liezhuan"],
    ["平原君虞卿列传第十六","shiji/pingyuan-jun-yu-qing-liezhuan"],["魏公子列传第十七","shiji/wei-gongzi-liezhuan"],["春申君列传第十八","shiji/chun-shen-jun-liezhuan"],["范雎蔡泽列传第十九","shiji/fan-ju-cai-ze-liezhuan"],["乐毅列传第二十","shiji/yue-yi-liezhuan"],
    ["廉颇蔺相如列传第二十一","shiji/lianpo-linxiangru-liezhuan"],["田单列传第二十二","shiji/tian-dan-liezhuan"],["鲁仲连邹阳列传第二十三","shiji/lu-zhonglian-zou-yang-liezhuan"],["屈原贾生列传第二十四","shiji/qu-yuan-jia-sheng-liezhuan"],["吕不韦列传第二十五","shiji/lv-buwei-liezhuan"],
    ["刺客列传第二十六","shiji/cike-liezhuan"],["李斯列传第二十七","shiji/li-si-liezhuan"],["蒙恬列传第二十八","shiji/meng-tian-liezhuan"],["张耳陈馀列传第二十九","shiji/zhang-er-chen-yu-liezhuan"],["魏豹彭越列传第三十","shiji/wei-bao-peng-yue-liezhuan"],
    ["黥布列传第三十一","shiji/qing-bu-liezhuan"],["淮阴侯列传第三十二","shiji/huaiyin-hou-liezhuan"],["韩信卢绾列传第三十三","shiji/han-xin-lu-wan-liezhuan"],["田儋列传第三十四","shiji/tian-dan-liezhuan2"],["樊郦滕灌列传第三十五","shiji/fan-li-teng-guan-liezhuan"],
    ["张丞相列传第三十六","shiji/zhang-chengxiang-liezhuan"],["郦生陆贾列传第三十七","shiji/li-sheng-lu-jia-liezhuan"],["傅靳蒯成列传第三十八","shiji/fu-jin-kuai-cheng-liezhuan"],["刘敬叔孙通列传第三十九","shiji/liu-jing-shu-sun-tong-liezhuan"],["季布栾布列传第四十","shiji/ji-bu-luan-bu-liezhuan"],
    ["袁盎晁错列传第四十一","shiji/yuan-ang-chao-cuo-liezhuan"],["张释之冯唐列传第四十二","shiji/zhang-shi-zhi-feng-tang-liezhuan"],["万石张叔列传第四十三","shiji/wan-shi-zhang-shu-liezhuan"],["田叔列传第四十四","shiji/tian-shu-liezhuan"],["扁鹊仓公列传第四十五","shiji/bian-que-cang-gong-liezhuan"],
    ["吴王濞列传第四十六","shiji/wu-wang-bi-liezhuan"],["魏其武安侯列传第四十七","shiji/wei-qi-wu-an-hou-liezhuan"],["韩长孺列传第四十八","shiji/han-chang-ru-liezhuan"],["李将军列传第四十九","shiji/li-jiangjun-liezhuan"],["匈奴列传第五十","shiji/xiongnu-liezhuan"],
    ["卫将军骠骑列传第五十一","shiji/wei-jiangjun-piaoqi-liezhuan"],["平津侯主父列传第五十二","shiji/ping-jin-hou-zhu-fu-liezhuan"],["南越列传第五十三","shiji/nan-yue-liezhuan"],["东越列传第五十四","shiji/dong-yue-liezhuan"],["朝鲜列传第五十五","shiji/chao-xian-liezhuan"],
    ["西南夷列传第五十六","shiji/xi-nan-yi-liezhuan"],["司马相如列传第五十七","shiji/sima-xiangru-liezhuan"],["淮南衡山列传第五十八","shiji/huai-nan-heng-shan-liezhuan"],["循吏列传第五十九","shiji/xun-li-liezhuan"],["汲郑列传第六十","shiji/ji-zheng-liezhuan"],
    ["儒林列传第六十一","shiji/ru-lin-liezhuan"],["酷吏列传第六十二","shiji/ku-li-liezhuan"],["大宛列传第六十三","shiji/da-yuan-liezhuan"],["游侠列传第六十四","shiji/you-xia-liezhuan"],["佞幸列传第六十五","shiji/ning-xing-liezhuan"],
    ["滑稽列传第六十六","shiji/hua-ji-liezhuan"],["日者列传第六十七","shiji/ri-zhe-liezhuan"],["龟策列传第六十八","shiji/gui-ce-liezhuan"],["货殖列传第六十九","shiji/huo-zhi-liezhuan"],["太史公自序第七十","shiji/taishigong-zixu"]
  ];
  function wrap(name, list) { return list.map(function (item) { return { title: item[0], ctextId: item[1], category: name }; }); }
  global.SHIJI_CATALOG = {
    categories: [
      { name: "本纪", items: wrap("本纪", B) },
      { name: "表", items: wrap("表", T) },
      { name: "书", items: wrap("书", S) },
      { name: "世家", items: wrap("世家", J) },
      { name: "列传", items: wrap("列传", L) }
    ],
    all: function () { var a = []; this.categories.forEach(function (c) { a = a.concat(c.items); }); return a; }
  };
})(window);
