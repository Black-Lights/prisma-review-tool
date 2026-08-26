// graph-canvas — editor de nós, sem framework: SVG + DOM puro.
// Objetivo: dar pra ler o arquivo inteiro numa sentada e entender tudo.

const SVG_NS = 'http://www.w3.org/2000/svg';
const NODE_W = 220;
const NODE_H = 90;

const svg = document.getElementById('canvas');
const wrap = document.getElementById('canvas-wrap');
const detail = document.getElementById('detail');
const statusPill = document.getElementById('status-pill');

let graph = { nodes: [], edges: [] };
let selectedId = null;
let view = { x: 0, y: 0, scale: 1 };
let dragging = null; // { type: 'node'|'pan'|'connect', ... }
let runStatus = { running: false, order: [], currentIndex: -1, nodes: [] };

const viewport = document.createElementNS(SVG_NS, 'g');
viewport.setAttribute('id', 'viewport');
svg.appendChild(viewport);

function applyViewTransform() {
  viewport.setAttribute('transform', `translate(${view.x}, ${view.y}) scale(${view.scale})`);
}

function toGraphCoords(clientX, clientY) {
  const rect = svg.getBoundingClientRect();
  return {
    x: (clientX - rect.left - view.x) / view.scale,
    y: (clientY - rect.top - view.y) / view.scale,
  };
}

function genId() {
  return 'n_' + Math.random().toString(36).slice(2, 10);
}

// ---------- carregar / salvar ----------

async function loadGraph() {
  const res = await fetch('/api/graph');
  graph = await res.json();
  render();
}

let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    await fetch('/api/graph', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(graph),
    });
  }, 300);
}

// ---------- criação de nós ----------

document.getElementById('btn-add-node').addEventListener('click', () => {
  const center = toGraphCoords(wrap.clientWidth / 2, wrap.clientHeight / 2);
  const node = {
    id: genId(),
    type: 'generic',
    title: 'Novo nó',
    x: center.x - NODE_W / 2,
    y: center.y - NODE_H / 2,
    config: { apiKey: '', notes: '' },
    status: 'idle',
    lastOutput: null,
  };
  graph.nodes.push(node);
  selectedId = node.id;
  render();
  scheduleSave();
});

document.getElementById('btn-run').addEventListener('click', async () => {
  await fetch('/api/graph/run', { method: 'POST' });
  pollRunStatus();
});

document.getElementById('btn-reset').addEventListener('click', async () => {
  if (!confirm('Apagar todos os nós e conexões?')) return;
  await fetch('/api/reset', { method: 'POST' });
  graph = { nodes: [], edges: [] };
  selectedId = null;
  render();
  renderDetailEmpty();
});

// ---------- pan & zoom ----------

wrap.addEventListener('mousedown', (e) => {
  if (e.target === svg || e.target === wrap) {
    dragging = { type: 'pan', startX: e.clientX, startY: e.clientY, origX: view.x, origY: view.y };
    wrap.classList.add('panning');
  }
});

wrap.addEventListener('wheel', (e) => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const newScale = Math.min(2.5, Math.max(0.3, view.scale * factor));
  const rect = svg.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  // mantém o ponto sob o mouse fixo ao aplicar zoom
  view.x = mx - ((mx - view.x) / view.scale) * newScale;
  view.y = my - ((my - view.y) / view.scale) * newScale;
  view.scale = newScale;
  applyViewTransform();
}, { passive: false });

window.addEventListener('mousemove', (e) => {
  if (!dragging) return;

  if (dragging.type === 'pan') {
    view.x = dragging.origX + (e.clientX - dragging.startX);
    view.y = dragging.origY + (e.clientY - dragging.startY);
    applyViewTransform();
  }

  if (dragging.type === 'node') {
    const pos = toGraphCoords(e.clientX, e.clientY);
    const node = graph.nodes.find((n) => n.id === dragging.id);
    if (node) {
      node.x = pos.x - dragging.offsetX;
      node.y = pos.y - dragging.offsetY;
      renderNodesAndEdges();
    }
  }

  if (dragging.type === 'connect') {
    const pos = toGraphCoords(e.clientX, e.clientY);
    dragging.previewTo = pos;
    renderNodesAndEdges();
  }
});

window.addEventListener('mouseup', (e) => {
  if (dragging && dragging.type === 'pan') wrap.classList.remove('panning');

  if (dragging && dragging.type === 'connect') {
    const target = document.elementFromPoint(e.clientX, e.clientY);
    const portEl = target && target.closest('.port.port-in');
    if (portEl) {
      const toId = portEl.getAttribute('data-node-id');
      if (toId && toId !== dragging.fromId) {
        const exists = graph.edges.some((ed) => ed.from === dragging.fromId && ed.to === toId);
        if (!exists) {
          graph.edges.push({ id: genId(), from: dragging.fromId, to: toId });
          scheduleSave();
        }
      }
    }
    dragging = null;
    renderNodesAndEdges();
    return;
  }

  if (dragging && dragging.type === 'node') scheduleSave();
  dragging = null;
});

// ---------- render ----------

function render() {
  renderNodesAndEdges();
  if (selectedId) {
    const n = graph.nodes.find((x) => x.id === selectedId);
    if (n) renderDetail(n); else renderDetailEmpty();
  }
}

function renderNodesAndEdges() {
  viewport.innerHTML = '';

  // edges primeiro (atrás dos nós)
  for (const edge of graph.edges) {
    const from = graph.nodes.find((n) => n.id === edge.from);
    const to = graph.nodes.find((n) => n.id === edge.to);
    if (!from || !to) continue;
    drawEdge(portPos(from, 'out'), portPos(to, 'in'), 'edge');
  }

  if (dragging && dragging.type === 'connect') {
    const from = graph.nodes.find((n) => n.id === dragging.fromId);
    if (from) drawEdge(portPos(from, 'out'), dragging.previewTo, 'edge-preview');
  }

  for (const node of graph.nodes) drawNode(node);
}

function portPos(node, side) {
  return { x: node.x + (side === 'out' ? NODE_W : 0), y: node.y + NODE_H / 2 };
}

function drawEdge(from, to, cls) {
  const path = document.createElementNS(SVG_NS, 'path');
  const midX = (from.x + to.x) / 2;
  path.setAttribute('d', `M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${to.y}, ${to.x} ${to.y}`);
  path.setAttribute('class', cls);
  viewport.appendChild(path);
}

function drawNode(node) {
  const g = document.createElementNS(SVG_NS, 'g');
  g.setAttribute('class', `node-box status-${node.status}${node.id === selectedId ? ' selected' : ''}`);
  g.setAttribute('transform', `translate(${node.x}, ${node.y})`);

  const body = document.createElementNS(SVG_NS, 'rect');
  body.setAttribute('class', 'body');
  body.setAttribute('width', NODE_W);
  body.setAttribute('height', NODE_H);
  g.appendChild(body);

  const titleBar = document.createElementNS(SVG_NS, 'rect');
  titleBar.setAttribute('class', 'title-bar');
  titleBar.setAttribute('width', NODE_W);
  titleBar.setAttribute('height', 26);
  g.appendChild(titleBar);

  const title = document.createElementNS(SVG_NS, 'text');
  title.setAttribute('x', 12);
  title.setAttribute('y', 17);
  title.textContent = node.title;
  g.appendChild(title);

  const typeLabel = document.createElementNS(SVG_NS, 'text');
  typeLabel.setAttribute('class', 'node-type');
  typeLabel.setAttribute('x', 12);
  typeLabel.setAttribute('y', 42);
  typeLabel.textContent = node.type;
  g.appendChild(typeLabel);

  const statusLabel = document.createElementNS(SVG_NS, 'text');
  statusLabel.setAttribute('x', 12);
  statusLabel.setAttribute('y', 62);
  statusLabel.setAttribute('fill', 'var(--muted)');
  statusLabel.textContent = statusText(node.status);
  g.appendChild(statusLabel);

  // porta de entrada
  const portIn = document.createElementNS(SVG_NS, 'g');
  portIn.setAttribute('class', 'port port-in');
  portIn.setAttribute('data-node-id', node.id);
  portIn.setAttribute('transform', `translate(0, ${NODE_H / 2})`);
  const cIn = document.createElementNS(SVG_NS, 'circle');
  cIn.setAttribute('r', 6);
  portIn.appendChild(cIn);
  g.appendChild(portIn);

  // porta de saída
  const portOut = document.createElementNS(SVG_NS, 'g');
  portOut.setAttribute('class', 'port port-out');
  portOut.setAttribute('data-node-id', node.id);
  portOut.setAttribute('transform', `translate(${NODE_W}, ${NODE_H / 2})`);
  const cOut = document.createElementNS(SVG_NS, 'circle');
  cOut.setAttribute('r', 6);
  portOut.appendChild(cOut);
  portOut.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    const pos = toGraphCoords(e.clientX, e.clientY);
    dragging = { type: 'connect', fromId: node.id, previewTo: pos };
  });
  g.appendChild(portOut);

  // arrastar o corpo move o nó; clique seleciona
  body.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    const pos = toGraphCoords(e.clientX, e.clientY);
    dragging = { type: 'node', id: node.id, offsetX: pos.x - node.x, offsetY: pos.y - node.y };
    selectedId = node.id;
    render();
  });
  titleBar.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    const pos = toGraphCoords(e.clientX, e.clientY);
    dragging = { type: 'node', id: node.id, offsetX: pos.x - node.x, offsetY: pos.y - node.y };
    selectedId = node.id;
    render();
  });
  titleBar.addEventListener('dblclick', (e) => {
    e.stopPropagation();
    const novo = prompt('Novo nome do nó:', node.title);
    if (novo) {
      node.title = novo;
      render();
      scheduleSave();
    }
  });

  viewport.appendChild(g);
}

function statusText(status) {
  return { idle: 'ocioso', running: '⏳ executando…', done: '✔ concluído', error: '✖ erro' }[status] || status;
}

// ---------- painel de propriedades ----------

function renderDetailEmpty() {
  detail.innerHTML = `<h2>Propriedades</h2><p class="muted">Clique num nó pra configurar, ou arraste da bolinha da direita de um nó até outro pra conectar.</p>`;
}

function renderDetail(node) {
  detail.innerHTML = `
    <h2>Propriedades</h2>
    <div class="field">
      <label>Nome</label>
      <input id="f-title" type="text" value="${escapeAttr(node.title)}" />
    </div>
    <div class="field">
      <label>Tipo</label>
      <select id="f-type">
        ${['generic', 'http', 'script', 'ai'].map((t) => `<option value="${t}" ${t === node.type ? 'selected' : ''}>${t}</option>`).join('')}
      </select>
    </div>
    <div class="field">
      <label>API Key</label>
      <input id="f-apikey" type="password" value="${escapeAttr(node.config.apiKey || '')}" placeholder="cole a chave aqui" />
    </div>
    <div class="field">
      <label>Notas / configuração</label>
      <textarea id="f-notes" placeholder="qualquer anotação livre sobre esse nó">${escapeHtml(node.config.notes || '')}</textarea>
    </div>
    ${node.lastOutput ? `<div class="field"><label>Última saída</label><textarea readonly>${escapeHtml(node.lastOutput)}</textarea></div>` : ''}
    <div class="field-actions">
      <button class="btn-run-node">▶ Rodar este nó</button>
      <button class="btn-delete-node">Excluir</button>
    </div>
  `;

  document.getElementById('f-title').addEventListener('input', (e) => {
    node.title = e.target.value;
    renderNodesAndEdges();
    scheduleSave();
  });
  document.getElementById('f-type').addEventListener('change', (e) => {
    node.type = e.target.value;
    renderNodesAndEdges();
    scheduleSave();
  });
  document.getElementById('f-apikey').addEventListener('input', (e) => {
    node.config.apiKey = e.target.value;
    scheduleSave();
  });
  document.getElementById('f-notes').addEventListener('input', (e) => {
    node.config.notes = e.target.value;
    scheduleSave();
  });
  detail.querySelector('.btn-run-node').addEventListener('click', async () => {
    await fetch(`/api/nodes/${node.id}/run`, { method: 'POST' });
    pollRunStatus();
  });
  detail.querySelector('.btn-delete-node').addEventListener('click', () => {
    graph.nodes = graph.nodes.filter((n) => n.id !== node.id);
    graph.edges = graph.edges.filter((e) => e.from !== node.id && e.to !== node.id);
    selectedId = null;
    render();
    renderDetailEmpty();
    scheduleSave();
  });
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, '&quot;');
}

// ---------- execução: polling de status ----------

let pollTimer = null;
function pollRunStatus() {
  clearTimeout(pollTimer);
  const tick = async () => {
    const res = await fetch('/api/run/status');
    runStatus = await res.json();
    // reflete o status de cada nó no grafo local
    for (const n of runStatus.nodes || []) {
      const local = graph.nodes.find((x) => x.id === n.id);
      if (local) {
        local.status = n.status;
        local.lastOutput = n.lastOutput;
      }
    }
    render();
    if (runStatus.running) {
      pollTimer = setTimeout(tick, 500);
    }
  };
  tick();
}

// ---------- healthcheck geral ----------

async function pollHealth() {
  try {
    const res = await fetch('/api/health');
    const h = await res.json();
    statusPill.textContent = `conectado — ${h.nodes} nó(s), ${h.edges} conexão(ões)`;
    statusPill.style.color = 'var(--done)';
  } catch (e) {
    statusPill.textContent = 'servidor desconectado';
    statusPill.style.color = 'var(--error)';
  } finally {
    setTimeout(pollHealth, 3000);
  }
}

applyViewTransform();
loadGraph();
pollHealth();
