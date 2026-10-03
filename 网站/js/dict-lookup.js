/* ============================================================
   离线查词模块（DictLookup）—— 搜索页/阅读页共用
   ------------------------------------------------------------
   数据源（全部离线、按需取分片）：
     _site_data/vocab_final.json        本站词表（中文多字词 → 释义；含 need_ai）
     _site_data/dict/kangxi/<n>.json    康熙字典（单字）
     _site_data/dict/shuowen/<n>.json   说文解字（单字）
     _site_data/dict/cedict/<n>.json    CC-CEDICT 英汉（单字/词）
     _site_data/dict/dict_meta.json     分片数与词典清单
   分片规则：ord(首字) % shards（与 文本/新书/build_dict_shards.py 一致）

   用法：
     DictLookup.lookup('仁').then(function (r) {
       // r = { word, single, items:[{label,text,needAI,freq,books}], parts:[{char,text}] }
     });
   ============================================================ */
'use strict';

window.DictLookup = (function () {
  var SHARDS_FALLBACK = 128;
  var CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
  var ASCII = /[A-Za-z]/;

  var metaPromise = null;
  var vocabPromise = null;
  var shardCache = {};

  function base() { return (typeof DATA_BASE === 'string') ? DATA_BASE : '_site_data/'; }

  function loadJSON(url) {
    if (typeof window.loadJSON === 'function') return window.loadJSON(url);
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function meta() {
    if (!metaPromise) {
      metaPromise = loadJSON(base() + 'dict/dict_meta.json')
        .catch(function () { return { shards: SHARDS_FALLBACK, dicts: [] }; });
    }
    return metaPromise;
  }

  /** 取某词典中「首字 = ch」所在分片（缓存；失败回 {}） */
  function shard(dict, ch) {
    return meta().then(function (m) {
      var n = ch.codePointAt(0) % (m.shards || SHARDS_FALLBACK);
      var key = dict + '/' + n;
      if (!shardCache[key]) {
        shardCache[key] = loadJSON(base() + 'dict/' + dict + '/' + n + '.json')
          .catch(function () { return {}; });
      }
      return shardCache[key];
    });
  }

  function vocabRows() {
    if (!vocabPromise) {
      vocabPromise = loadJSON(base() + 'vocab_final.json').then(function (d) {
        if (!d) return [];
        if (Array.isArray(d)) return d;
        return [].concat(d.zh || [], d.en || []);
      }).catch(function () { return []; });
    }
    return vocabPromise;
  }

  function isCJK(s) { return CJK.test(s); }

  function lookup(word) {
    word = String(word || '').trim();
    if (!word) return Promise.resolve(null);
    var single = Array.from(word).length === 1 && isCJK(word);
    var jobs = [];

    // ① 本站词表（词形 / 简体形 命中）
    jobs.push(vocabRows().then(function (rows) {
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        if (!r) continue;
        if (r[0] === word || (r[1] && r[1] === word)) {
          return { label: '本站词表', text: r[4] || '', needAI: !!r[5],
                   freq: r[2], books: r[3] };
        }
      }
      return null;
    }));

    // ② 康熙 / 说文（仅单字）
    if (single) {
      jobs.push(shard('kangxi', word).then(function (d) {
        return d[word] ? { label: '康熙字典', text: d[word] } : null;
      }));
      jobs.push(shard('shuowen', word).then(function (d) {
        return d[word] ? { label: '说文解字', text: d[word] } : null;
      }));
    }

    // ③ CC-CEDICT（单字或词；键大小写敏感，另试小写）
    jobs.push(shard('cedict', word).then(function (d) {
      var v = d[word];
      if (v == null && ASCII.test(word)) v = d[word.toLowerCase()];
      return (v != null) ? { label: 'CC-CEDICT', text: v } : null;
    }));

    return Promise.all(jobs).then(function (res) {
      var items = res.filter(Boolean);
      var out = { word: word, single: single, items: items, parts: [] };
      if (single || !isCJK(word) || Array.from(word).length > 6) return out;
      // 多字词：附成分字释义（康熙优先，其次说文/CC-CEDICT）
      var chars = Array.from(word).slice(0, 6);
      return Promise.all(chars.map(function (c) {
        return Promise.all([
          shard('kangxi', c).then(function (d) { return d[c] || null; }),
          shard('shuowen', c).then(function (d) { return d[c] || null; }),
          shard('cedict', c).then(function (d) { return d[c] || null; }),
        ]).then(function (r) {
          var t = r[0] || r[1] || r[2] || '';
          return { char: c, text: t };
        });
      })).then(function (parts) {
        out.parts = parts;
        return out;
      });
    });
  }

  return { lookup: lookup, shard: shard, meta: meta };
})();
