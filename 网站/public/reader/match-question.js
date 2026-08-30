/* ============================================================
 * 连线题完整实现
 * 复制到 shiji_reader.html 的 <script> 里，替换掉现有的 match 渲染逻辑
 *
 * 数据结构：{ type:'match', question:'...', pairs:[{left, right}, ...] }
 * ============================================================ */


/* ---------- 1. 渲染 ---------- */
function renderMatch(container, item, qIdx) {
  container.dataset.type = 'match';
  container.dataset.idx = qIdx;
  container._connections = [];   // 存储配对：[{leftKey, rightKey}]

  const stem = document.createElement('div');
  stem.className = 'q-stem';
  stem.textContent = `${qIdx + 1}. ${item.question || '连线题：点击左侧词条，再点击右侧释义完成配对'}`;
  container.appendChild(stem);

  const board = document.createElement('div');
  board.className = 'match-board';

  const leftCol = document.createElement('div');
  leftCol.className = 'match-col match-left';
  item.pairs.forEach(p => {
    const node = document.createElement('div');
    node.className = 'match-node';
    node.dataset.side = 'left';
    node.dataset.key = p.left;
    node.textContent = p.left;
    leftCol.appendChild(node);
  });

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.className = 'match-lines';

  const rightCol = document.createElement('div');
  rightCol.className = 'match-col match-right';
  const rights = item.pairs.map(p => p.right).sort(() => Math.random() - 0.5);
  rights.forEach(r => {
    const node = document.createElement('div');
    node.className = 'match-node';
    node.dataset.side = 'right';
    node.dataset.key = r;
    node.textContent = r;
    rightCol.appendChild(node);
  });

  board.appendChild(leftCol);
  board.appendChild(svg);
  board.appendChild(rightCol);
  container.appendChild(board);

  const result = document.createElement('div');
  result.className = 'result';
  container.appendChild(result);

  initMatch(board, item, result);
}


/* ---------- 2. 交互 ---------- */
function initMatch(board, item, resultEl) {
  const svg = board.querySelector('.match-lines');
  let selLeft = null, selRight = null;

  function syncSvgSize() {
    const rect = board.getBoundingClientRect();
    svg.setAttribute('width', rect.width);
    svg.setAttribute('height', rect.height);
  }
  syncSvgSize();
  window.addEventListener('resize', () => { syncSvgSize(); redraw(); });

  function getLinePoints(leftEl, rightEl) {
    const b = board.getBoundingClientRect();
    const l = leftEl.getBoundingClientRect();
    const r = rightEl.getBoundingClientRect();
    return {
      x1: l.right - b.left,  y1: l.top + l.height / 2 - b.top,
      x2: r.left - b.left,   y2: r.top + r.height / 2 - b.top,
    };
  }

  function redraw() {
    svg.innerHTML = '';
    board._connections.forEach(c => {
      const lEl = board.querySelector(`.match-left .match-node[data-key="${cssEscape(c.leftKey)}"]`);
      const rEl = board.querySelector(`.match-right .match-node[data-key="${cssEscape(c.rightKey)}"]`);
      if (!lEl || !rEl) return;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      const pts = getLinePoints(lEl, rEl);
      line.setAttribute('x1', pts.x1); line.setAttribute('y1', pts.y1);
      line.setAttribute('x2', pts.x2); line.setAttribute('y2', pts.y2);
      line.classList.add('match-line');
      line._conn = c;   // 绑定数据，用于点击删除
      svg.appendChild(line);
    });
  }

  board.querySelectorAll('.match-node').forEach(node => {
    node.addEventListener('click', () => {
      const side = node.dataset.side;

      if (side === 'left') {
        if (selLeft === node) { node.classList.remove('sel'); selLeft = null; return; }
        if (selLeft) selLeft.classList.remove('sel');
        selLeft = node; node.classList.add('sel');
        if (selRight) selRight.classList.remove('sel');
        selRight = null;
      } else {
        if (selRight === node) { node.classList.remove('sel'); selRight = null; return; }
        if (selRight) selRight.classList.remove('sel');
        selRight = node; node.classList.add('sel');
        if (selLeft) selLeft.classList.remove('sel');
        selLeft = null;
      }

      if (selLeft && selRight) {
        board._connections.push({ leftKey: selLeft.dataset.key, rightKey: selRight.dataset.key });
        selLeft.classList.add('matched');
        selRight.classList.add('matched');
        selLeft.classList.remove('sel');
        selRight.classList.remove('sel');
        selLeft = null; selRight = null;
        redraw();
        checkComplete();
      }
    });
  });

  // 点击连线 → 删除
  svg.addEventListener('click', e => {
    const line = e.target;
    if (!line.classList || !line.classList.contains('match-line')) return;
    const c = line._conn;
    if (!c) return;
    const lEl = board.querySelector(`.match-left .match-node[data-key="${cssEscape(c.leftKey)}"]`);
    const rEl = board.querySelector(`.match-right .match-node[data-key="${cssEscape(c.rightKey)}"]`);
    lEl && lEl.classList.remove('matched');
    rEl && rEl.classList.remove('matched');
    board._connections = board._connections.filter(x => x !== c);
    redraw();
    resultEl.textContent = '';
  });

  function checkComplete() {
    if (board._connections.length === item.pairs.length) {
      const { correct, total } = gradeMatch(board, item);
      resultEl.innerHTML = `✅ 配对结果：${correct}/${total} 正确`;
      resultEl.style.color = correct === total ? 'green' : 'red';
    }
  }
}


/* ---------- 3. 判分 ---------- */
function gradeMatch(board, item) {
  let correct = 0;
  board._connections.forEach(c => {
    if (item.pairs.some(p => p.left === c.leftKey && p.right === c.rightKey)) correct++;
  });
  return { correct, total: item.pairs.length };
}


/* ---------- 4. 工具 ---------- */
function cssEscape(str) {
  if (window.CSS && CSS.escape) return CSS.escape(str);
  return String(str).replace(/[^a-zA-Z0-9_-]/g, s => '\\' + s);
}


/* ============================================================
 * 集成指引
 * ============================================================
 *
 * 【A】renderExam() 里加分支：
 *
 *   else if (item.type === 'match') {
 *     const qEl = document.createElement('div');
 *     qEl.className = 'exam-q';
 *     container.appendChild(qEl);
 *     renderMatch(qEl, item, qIdx);
 *     return qEl;
 *   }
 *
 * 【B】提交判分时（遍历 .exam-q）：
 *
 *   const all = [];
 *   document.querySelectorAll('.exam-q').forEach(qEl => {
 *     if (qEl.dataset.type === 'match') {
 *       all.push({ index: +qEl.dataset.idx, type:'match',
 *                  pairs: examData 里对应题.pairs,
 *                  answer: qEl._connections });   // [{leftKey,rightKey}]
 *     }
 *   });
 *   // match 的 correct 数 = gradeMatch(qEl, 对应题).correct
 *
 * 【C】CSS（加到 <style>）：
 *
 *   .match-board { display:flex; position:relative; gap:4em;
 *                  margin:1em 0; align-items:flex-start; }
 *   .match-col   { display:flex; flex-direction:column; gap:0.8em; z-index:2; }
 *   .match-node  { padding:0.5em 1em; border:1px solid #ccc; border-radius:6px;
 *                  cursor:pointer; user-select:none; background:#fff; }
 *   .match-node.sel     { outline:2px solid #ff9800; }
 *   .match-node.matched { background:#e8f5e9; border-color:#4caf50; }
 *   .match-lines { position:absolute; top:0; left:0; width:100%; height:100%;
 *                  pointer-events:none; z-index:1; overflow:visible; }
 *   .match-lines .match-line { pointer-events:auto; cursor:pointer;
 *                              stroke:#888; stroke-width:2; }
 *   .match-lines .match-line:hover { stroke:#f44336; stroke-width:3; }
 *
 * ============================================================ */
