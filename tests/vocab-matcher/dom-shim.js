/* 最小 DOM shim：只为在 Node 里验证 vocab-matcher 的 annotate()（TreeWalker + 空闲分批 + 落节点）
   实现范围严格对应模块用到的 API，不做通用兼容。 */
'use strict';

function mkText(s, doc) {
  var t = { nodeType: 3, nodeName: '#text', nodeValue: String(s), childNodes: [], parentNode: null, ownerDocument: doc };
  Object.defineProperty(t, 'textContent', {
    get: function () { return t.nodeValue; },
    set: function (v) { t.nodeValue = String(v); }
  });
  Object.defineProperty(t, 'isConnected', {
    get: function () {
      var n = t;
      while (n.parentNode) n = n.parentNode;
      return !!n._connected;
    }
  });
  return t;
}

function mkEl(tag, doc, isFrag) {
  var el = {
    nodeType: 1, nodeName: String(tag).toUpperCase(), nodeValue: null, ownerDocument: doc,
    childNodes: [], parentNode: null, _attrs: {}, _frag: !!isFrag, _connected: false
  };
  Object.defineProperty(el, 'textContent', {
    get: function () {
      var out = '';
      for (var i = 0; i < el.childNodes.length; i++) out += el.childNodes[i].textContent;
      return out;
    },
    set: function (v) {
      el.childNodes.length = 0;
      if (v !== '' && v != null) el.appendChild(mkText(v, doc));
    }
  });
  Object.defineProperty(el, 'isConnected', {
    get: function () {
      var n = el;
      while (n.parentNode) n = n.parentNode;
      return !!n._connected;
    }
  });
  el.appendChild = function (child) {
    if (child._frag) {
      var kids = child.childNodes.slice();
      child.childNodes.length = 0;
      for (var i = 0; i < kids.length; i++) el.appendChild(kids[i]);
      return child;
    }
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = el;
    el.childNodes.push(child);
    return child;
  };
  el.removeChild = function (child) {
    var i = el.childNodes.indexOf(child);
    if (i >= 0) { el.childNodes.splice(i, 1); child.parentNode = null; }
    return child;
  };
  el.replaceChild = function (next, old) {
    var i = el.childNodes.indexOf(old);
    if (i < 0) throw new Error('replaceChild: 目标不在父节点下');
    if (next._frag) {
      var kids = next.childNodes.slice();
      next.childNodes.length = 0;
      el.childNodes.splice.apply(el.childNodes, [i, 1].concat(kids));
      for (var k = 0; k < kids.length; k++) kids[k].parentNode = el;
      old.parentNode = null;
      return old;
    }
    el.childNodes[i] = next;
    next.parentNode = el;
    old.parentNode = null;
    return old;
  };
  el.setAttribute = function (k, v) { el._attrs[k] = String(v); };
  el.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(el._attrs, k) ? el._attrs[k] : null; };
  Object.defineProperty(el, 'className', {
    get: function () { return el._attrs['class'] || ''; },
    set: function (v) { el._attrs['class'] = String(v); }
  });
  el.closest = function (sel) {
    var parts = String(sel).split(',');
    function hasClass(n, cls) { return (' ' + (n._attrs['class'] || '') + ' ').indexOf(' ' + cls + ' ') >= 0; }
    var n = el;
    while (n && n.nodeType === 1) {
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i].trim();
        if (!p) continue;
        if (p.charAt(0) === '.') {
          if (hasClass(n, p.slice(1))) return n;
        } else if (p.charAt(0) === '[') {
          if (n.getAttribute(p.slice(1, -1)) != null) return n;
        } else if (n.nodeName === p.toUpperCase()) {
          return n;
        }
      }
      n = n.parentNode;
    }
    return null;
  };
  el.getElementsByTagName = function (tag) {
    var want = String(tag).toUpperCase(), out = [];
    (function walk(node) {
      for (var i = 0; i < node.childNodes.length; i++) {
        var c = node.childNodes[i];
        if (c.nodeType !== 1) continue;
        if (c.nodeName === want) out.push(c);
        walk(c);
      }
    })(el);
    return out;
  };
  return el;
}

function mkWalker(root, filter) {
  var stack = [root];
  return {
    nextNode: function () {
      while (stack.length) {
        var n = stack.pop();
        if (n.nodeType !== 3) {
          var kids = n.childNodes || [];
          for (var i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
        } else if (!filter || filter.acceptNode(n) === 1) {
          return n;
        }
      }
      return null;
    }
  };
}

function mkDoc() {
  var doc = {
    nodeType: 9, nodeName: '#document', parentNode: null, childNodes: [], _connected: true,
    createElement: function (t) { return mkEl(t, doc, false); },
    createTextNode: function (t) { return mkText(t, doc); },
    createDocumentFragment: function () { return mkEl('#fragment', doc, true); },
    createTreeWalker: function (root, what, filter) { return mkWalker(root, filter); }
  };
  var body = mkEl('body', doc, false);
  body._connected = true;
  body.parentNode = doc;
  doc.childNodes.push(body);
  if (Object.defineProperty) {
    Object.defineProperty(doc, 'body', { get: function () { return body; } });
  } else doc.body = body;
  return doc;
}

module.exports = { mkDoc: mkDoc };
