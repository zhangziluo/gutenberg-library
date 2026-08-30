// 通用国学文库目录（经/史/子/集 + 史记全本），供 library.html 使用。
// ctextId 为中国哲学书电子化计划（CTEXT，ctext.org）的篇目 URL slug。
// 部分 slug 为估算值；加载时若 CTEXT 返回为空，文库会自动回退到"古诗文网检索"。
// 用法：<script src="guoxue_catalog.js"></script> 后使用全局 GUOXUE_CATALOG。

(function (global) {
  // 每本书：{ book: 书名, items: [{title, ctextId}] }
  var books = {};

  // ===== 史部 · 史记（复用原 130 篇数据）=====
  var SHIJI = [];
  var B = [["五帝本纪第一","shiji/wu-di-benji"],["夏本纪第二","shiji/xia-benji"],["殷本纪第三","shiji/yin-benji"],["周本纪第四","shiji/zhou-benji"],["秦本纪第五","shiji/qin-benji"],["秦始皇本纪第六","shiji/qin-shihuang-benji"],["项羽本纪第七","shiji/xiangyu-benji"],["高祖本纪第八","shiji/gaozu-benji"],["吕太后本纪第九","shiji/lv-taihou-benji"],["孝文本纪第十","shiji/xiao-wen-benji"],["孝景本纪第十一","shiji/xiao-jing-benji"],["孝武本纪第十二","shiji/xiao-wu-benji"]];
  var T = [["三代世表第一","shiji/san-dai-shi-biao"],["十二诸侯年表第二","shiji/shi-er-zhu-hou-nian-biao"],["六国年表第三","shiji/liu-guo-nian-biao"],["秦楚之际月表第四","shiji/qin-chu-zhi-ji-yue-biao"],["汉兴以来诸侯王年表第五","shiji/han-xing-yi-lai-zhu-hou-wang-nian-biao"],["高祖功臣侯者年表第六","shiji/gaozu-gong-chen-hou-zhe-nian-biao"],["惠景间侯者年表第七","shiji/hui-jing-jian-hou-zhe-nian-biao"],["建元以来侯者年表第八","shiji/jian-yuan-yi-lai-hou-zhe-nian-biao"],["建元已来王子侯者年表第九","shiji/jian-yuan-yi-lai-wang-zi-hou-zhe-nian-biao"],["汉兴以来将相名臣年表第十","shiji/han-xing-yi-lai-jiang-xiang-ming-chen-nian-biao"]];
  var S = [["礼书第一","shiji/li-shu"],["乐书第二","shiji/yue-shu"],["律书第三","shiji/lv-shu"],["历书第四","shiji/li-shu2"],["天官书第五","shiji/tian-guan-shu"],["封禅书第六","shiji/feng-shan-shu"],["河渠书第七","shiji/he-qu-shu"],["平准书第八","shiji/ping-zhun-shu"]];
  var J = [["吴太伯世家第一","shiji/wu-taibo-shi-jia"],["齐太公世家第二","shiji/qi-taigong-shi-jia"],["鲁周公世家第三","shiji/lu-zhougong-shi-jia"],["燕召公世家第四","shiji/yan-zhaogong-shi-jia"],["管蔡世家第五","shiji/guan-cai-shi-jia"],["陈杞世家第六","shiji/chen-qi-shi-jia"],["卫康叔世家第七","shiji/wei-kangshu-shi-jia"],["宋微子世家第八","shiji/song-weizi-shi-jia"],["晋世家第九","shiji/jin-shi-jia"],["楚世家第十","shiji/chu-shi-jia"],["越王勾践世家第十一","shiji/yue-wang-goujian-shi-jia"],["郑世家第十二","shiji/zheng-shi-jia"],["赵世家第十三","shiji/zhao-shi-jia"],["魏世家第十四","shiji/wei-shi-jia"],["韩世家第十五","shiji/han-shi-jia"],["田敬仲完世家第十六","shiji/tian-jingzhong-wan-shi-jia"],["孔子世家第十七","shiji/kongzi-shi-jia"],["陈涉世家第十八","shiji/chen-she-shi-jia"],["外戚世家第十九","shiji/wai-qi-shi-jia"],["楚元王世家第二十","shiji/chu-yuanwang-shi-jia"],["荆燕世家第二十一","shiji/jing-yan-shi-jia"],["齐悼惠王世家第二十二","shiji/qi-daohui-wang-shi-jia"],["萧相国世家第二十三","shiji/xiao-xiangguo-shi-jia"],["曹相国世家第二十四","shiji/cao-xiangguo-shi-jia"],["留侯世家第二十五","shiji/liu-hou-shi-jia"],["陈丞相世家第二十六","shiji/chen-chengxiang-shi-jia"],["绛侯周勃世家第二十七","shiji/jiang-hou-zhou-bo-shi-jia"],["梁孝王世家第二十八","shiji/liang-xiaowang-shi-jia"],["五宗世家第二十九","shiji/wu-zong-shi-jia"],["三王世家第三十","shiji/san-wang-shi-jia"]];
  var L = [["伯夷列传第一","shiji/bo-yi-liezhuan"],["管晏列传第二","shiji/guan-yan-liezhuan"],["老子韩非列传第三","shiji/laozi-hanfei-liezhuan"],["司马穰苴列传第四","shiji/sima-rangju-liezhuan"],["孙子吴起列传第五","shiji/sunzi-wuqi-liezhuan"],["伍子胥列传第六","shiji/wu-zixu-liezhuan"],["仲尼弟子列传第七","shiji/zhongni-dizi-liezhuan"],["商君列传第八","shiji/shang-jun-liezhuan"],["苏秦列传第九","shiji/su-qin-liezhuan"],["张仪列传第十","shiji/zhang-yi-liezhuan"],["樗里子甘茂列传第十一","shiji/chu-lizi-gan-mao-liezhuan"],["穰侯列传第十二","shiji/rang-hou-liezhuan"],["白起王翦列传第十三","shiji/bai-qi-wang-jian-liezhuan"],["孟子荀卿列传第十四","shiji/mengzi-xunqing-liezhuan"],["孟尝君列传第十五","shiji/mengchang-jun-liezhuan"],["平原君虞卿列传第十六","shiji/pingyuan-jun-yu-qing-liezhuan"],["魏公子列传第十七","shiji/wei-gongzi-liezhuan"],["春申君列传第十八","shiji/chun-shen-jun-liezhuan"],["范雎蔡泽列传第十九","shiji/fan-ju-cai-ze-liezhuan"],["乐毅列传第二十","shiji/yue-yi-liezhuan"],["廉颇蔺相如列传第二十一","shiji/lianpo-linxiangru-liezhuan"],["田单列传第二十二","shiji/tian-dan-liezhuan"],["鲁仲连邹阳列传第二十三","shiji/lu-zhonglian-zou-yang-liezhuan"],["屈原贾生列传第二十四","shiji/qu-yuan-jia-sheng-liezhuan"],["吕不韦列传第二十五","shiji/lv-buwei-liezhuan"],["刺客列传第二十六","shiji/cike-liezhuan"],["李斯列传第二十七","shiji/li-si-liezhuan"],["蒙恬列传第二十八","shiji/meng-tian-liezhuan"],["张耳陈馀列传第二十九","shiji/zhang-er-chen-yu-liezhuan"],["魏豹彭越列传第三十","shiji/wei-bao-peng-yue-liezhuan"],["黥布列传第三十一","shiji/qing-bu-liezhuan"],["淮阴侯列传第三十二","shiji/huaiyin-hou-liezhuan"],["韩信卢绾列传第三十三","shiji/han-xin-lu-wan-liezhuan"],["田儋列传第三十四","shiji/tian-dan-liezhuan2"],["樊郦滕灌列传第三十五","shiji/fan-li-teng-guan-liezhuan"],["张丞相列传第三十六","shiji/zhang-chengxiang-liezhuan"],["郦生陆贾列传第三十七","shiji/li-sheng-lu-jia-liezhuan"],["傅靳蒯成列传第三十八","shiji/fu-jin-kuai-cheng-liezhuan"],["刘敬叔孙通列传第三十九","shiji/liu-jing-shu-sun-tong-liezhuan"],["季布栾布列传第四十","shiji/ji-bu-luan-bu-liezhuan"],["袁盎晁错列传第四十一","shiji/yuan-ang-chao-cuo-liezhuan"],["张释之冯唐列传第四十二","shiji/zhang-shi-zhi-feng-tang-liezhuan"],["万石张叔列传第四十三","shiji/wan-shi-zhang-shu-liezhuan"],["田叔列传第四十四","shiji/tian-shu-liezhuan"],["扁鹊仓公列传第四十五","shiji/bian-que-cang-gong-liezhuan"],["吴王濞列传第四十六","shiji/wu-wang-bi-liezhuan"],["魏其武安侯列传第四十七","shiji/wei-qi-wu-an-hou-liezhuan"],["韩长孺列传第四十八","shiji/han-chang-ru-liezhuan"],["李将军列传第四十九","shiji/li-jiangjun-liezhuan"],["匈奴列传第五十","shiji/xiongnu-liezhuan"],["卫将军骠骑列传第五十一","shiji/wei-jiangjun-piaoqi-liezhuan"],["平津侯主父列传第五十二","shiji/ping-jin-hou-zhu-fu-liezhuan"],["南越列传第五十三","shiji/nan-yue-liezhuan"],["东越列传第五十四","shiji/dong-yue-liezhuan"],["朝鲜列传第五十五","shiji/chao-xian-liezhuan"],["西南夷列传第五十六","shiji/xi-nan-yi-liezhuan"],["司马相如列传第五十七","shiji/sima-xiangru-liezhuan"],["淮南衡山列传第五十八","shiji/huai-nan-heng-shan-liezhuan"],["循吏列传第五十九","shiji/xun-li-liezhuan"],["汲郑列传第六十","shiji/ji-zheng-liezhuan"],["儒林列传第六十一","shiji/ru-lin-liezhuan"],["酷吏列传第六十二","shiji/ku-li-liezhuan"],["大宛列传第六十三","shiji/da-yuan-liezhuan"],["游侠列传第六十四","shiji/you-xia-liezhuan"],["佞幸列传第六十五","shiji/ning-xing-liezhuan"],["滑稽列传第六十六","shiji/hua-ji-liezhuan"],["日者列传第六十七","shiji/ri-zhe-liezhuan"],["龟策列传第六十八","shiji/gui-ce-liezhuan"],["货殖列传第六十九","shiji/huo-zhi-liezhuan"],["太史公自序第七十","shiji/taishigong-zixu"]];
  function wrap(list){return list.map(function(i){return {title:i[0], ctextId:i[1]};});}
  books["史记"] = { book:"史记", group:"史", sections:[
    {name:"本纪（12）", items:wrap(B)},{name:"表（10）", items:wrap(T)},{name:"书（8）", items:wrap(S)},
    {name:"世家（30）", items:wrap(J)},{name:"列传（70）", items:wrap(L)}
  ]};

  // ===== 经部：论语 / 孟子 / 老子 / 庄子 =====
  books["论语"] = { book:"论语", group:"经", sections:[
    {name:"各篇", items:[
      ["学而第一","lunyu/xue-er"],["为政第二","lunyu/wei-zheng"],["八佾第三","lunyu/ba-yi"],["里仁第四","lunyu/li-ren"],
      ["公冶长第五","lunyu/gong-ye-chang"],["雍也第六","lunyu/yong-ye"],["述而第七","lunyu/shu-er"],["泰伯第八","lunyu/tai-bo"],
      ["子罕第九","lunyu/zi-han"],["乡党第十","lunyu/xiang-dang"],["先进第十一","lunyu/xian-jin"],["颜渊第十二","lunyu/yan-yuan"],
      ["子路第十三","lunyu/zi-lu"],["宪问第十四","lunyu/xian-wen"],["卫灵公第十五","lunyu/wei-ling-gong"],["季氏第十六","lunyu/ji-shi"],
      ["阳货第十七","lunyu/yang-huo"],["微子第十八","lunyu/wei-zi"],["子张第十九","lunyu/zi-zhang"],["尧曰第二十","lunyu/yao-yue"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};
  books["孟子"] = { book:"孟子", group:"经", sections:[
    {name:"各篇", items:[
      ["梁惠王上","mengzi/liang-hui-wang-shang"],["梁惠王下","mengzi/liang-hui-wang-xia"],["公孙丑上","mengzi/gong-sun-chou-shang"],["公孙丑下","mengzi/gong-sun-chou-xia"],
      ["滕文公上","mengzi/teng-wen-gong-shang"],["滕文公下","mengzi/teng-wen-gong-xia"],["离娄上","mengzi/li-lou-shang"],["离娄下","mengzi/li-lou-xia"],
      ["万章上","mengzi/wan-zhang-shang"],["万章下","mengzi/wan-zhang-xia"],["告子上","mengzi/gao-zi-shang"],["告子下","mengzi/gao-zi-xia"],
      ["尽心上","mengzi/jin-xin-shang"],["尽心下","mengzi/jin-xin-xia"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};
  books["老子"] = { book:"老子（道德经）", group:"子", sections:[
    {name:"上下篇", items:[
      ["道经（上篇）","laozi/dao-jing"],["德经（下篇）","laozi/de-jing"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};
  books["庄子"] = { book:"庄子", group:"子", sections:[
    {name:"内篇（7）·外杂篇选", items:[
      ["逍遥游","zhuangzi/xiao-yao-you"],["齐物论","zhuangzi/qi-wu-lun"],["养生主","zhuangzi/yang-sheng-zhu"],["人间世","zhuangzi/ren-jian-shi"],
      ["德充符","zhuangzi/de-chong-fu"],["大宗师","zhuangzi/da-zong-shi"],["应帝王","zhuangzi/ying-di-wang"],["秋水","zhuangzi/qiu-shui"],
      ["达生","zhuangzi/da-sheng"],["天下","zhuangzi/tian-xia"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};

  // ===== 史部：汉书（选篇）/ 资治通鉴（选篇）=====
  books["汉书"] = { book:"汉书（选篇）", group:"史", sections:[
    {name:"代表篇目", items:[
      ["高帝纪上","hanshu/gao-di-ji-shang"],["高帝纪下","hanshu/gao-di-ji-xia"],["项羽传","hanshu/xiang-yu-zhuan"],["韩信传","hanshu/han-xin-zhuan"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};

  // ===== 集部：楚辞 / 陶渊明集 / 李白诗选 =====
  books["楚辞"] = { book:"楚辞（选篇）", group:"集", sections:[
    {name:"代表篇目", items:[
      ["离骚","chuci/li-sao"],["九歌·东皇太一","chuci/jiu-ge"],["天问","chuci/tian-wen"],["九章·涉江","chuci/jiu-zhang"]
    ].map(function(i){return {title:i[0],ctextId:i[1]};})}
  ]};

  // 快速入口顺序
  var QUICK = ["史记","论语","孟子","老子","庄子","楚辞","汉书"];
  var GROUPS = [
    {name:"经", desc:"儒家经典"},{name:"史", desc:"历代史书"},{name:"子", desc:"诸子百家"},{name:"集", desc:"诗文集"}
  ];

  global.GUOXUE_CATALOG = {
    books: books,           // {书名: {book,group,sections:[{name,items}]}}
    quick: QUICK,           // 快速入口书名顺序
    groups: GROUPS,         // 经史子集
    recentKey: "guoxue_recent", // localStorage 最近阅读 key
    listByGroup: function (gName) {
      return Object.keys(books).filter(function (k){return books[k].group===gName;}).map(function(k){return books[k];});
    }
  };
})(window);
