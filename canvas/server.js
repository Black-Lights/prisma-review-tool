/**
 * graph-canvas — servidor local do editor de nós (estilo n8n/LangGraph).
 *
 * Zero dependências externas — só módulos nativos do Node.
 *
 * O que ele faz:
 *  - Serve o editor visual (pasta public/).
 *  - Guarda o grafo (nós + conexões + configs de cada nó, incluindo API keys)
 *    em data/graph.json — persiste entre sessões.
 *  - Executa o grafo quando você pede: percorre os nós em ordem topológica
 *    (respeitando as conexões) e vai marcando cada um como "rodando" ->
 *    "concluído", pra você acompanhar visualmente no canvas.
 *
 * API:
 *   GET  /api/graph          -> retorna o grafo salvo (nodes, edges)
 *   PUT  /api/graph          -> salva o grafo inteiro (o editor manda o estado completo)
 *   POST /api/graph/run      -> inicia uma execução (assíncrona) do grafo inteiro
 *   POST /api/nodes/:id/run  -> executa só um nó específico
 *   GET  /api/run/status     -> estado da execução em andamento (pro editor fazer polling)
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = process.env.GRAPH_CANVAS_PORT ? Number(process.env.GRAPH_CANVAS_PORT) : 4600;
const DATA_FILE = path.join(__dirname, 'data', 'graph.json');
const PUBLIC_DIR = path.join(__dirname, 'public');

let graph = { nodes: [], edges: [] };
let runState = { running: false, order: [], currentIndex: -1, startedAt: null, finishedAt: null };

function loadGraph() {
  try {
    graph = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch (e) {
    graph = { nodes: [], edges: [] };
  }
}

function saveGraph() {
  try {
    fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true });
    fs.writeFileSync(DATA_FILE, JSON.stringify(graph, null, 2));
  } catch (e) {
    console.error('[graph-canvas] falha ao salvar:', e.message);
  }
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (c) => (data += c));
    req.on('end', () => {
      if (!data) return resolve({});
      try {
        resolve(JSON.parse(data));
      } catch (e) {
        reject(e);
      }
    });
    req.on('error', reject);
  });
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
};

function serveStatic(req, res, pathname) {
  const rel = pathname === '/' ? '/index.html' : pathname;
  const filePath = path.join(PUBLIC_DIR, rel);
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    return res.end('Forbidden');
  }
  fs.readFile(filePath, (err, content) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('Not found');
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(filePath)] || 'application/octet-stream' });
    res.end(content);
  });
}

/** Ordena os nós topologicamente a partir das conexões (edges). Nós sem
 *  dependência de entrada vêm primeiro. Ciclos simplesmente entram na ordem
 *  em que aparecem (não travamos nisso — é um protótipo). */
function topologicalOrder() {
  const incoming = new Map(graph.nodes.map((n) => [n.id, 0]));
  for (const e of graph.edges) {
    incoming.set(e.to, (incoming.get(e.to) || 0) + 1);
  }
  const queue = graph.nodes.filter((n) => (incoming.get(n.id) || 0) === 0).map((n) => n.id);
  const visited = new Set();
  const order = [];
  while (queue.length) {
    const id = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    order.push(id);
    for (const e of graph.edges.filter((e) => e.from === id)) {
      incoming.set(e.to, (incoming.get(e.to) || 0) - 1);
      if (incoming.get(e.to) <= 0 && !visited.has(e.to)) queue.push(e.to);
    }
  }
  // Qualquer nó que sobrou (ciclo ou desconexo) entra no final, na ordem original
  for (const n of graph.nodes) if (!visited.has(n.id)) order.push(n.id);
  return order;
}

/** Execução "mock": marca cada nó como running -> done, com um pequeno delay,
 *  na ordem topológica. Ponto de extensão futuro: aqui é onde entraria a
 *  chamada real (HTTP com a API key do nó, rodar um script, etc). */
async function runGraph(singleNodeId) {
  const order = singleNodeId ? [singleNodeId] : topologicalOrder();
  runState = { running: true, order, currentIndex: -1, startedAt: new Date().toISOString(), finishedAt: null };

  for (let i = 0; i < order.length; i++) {
    runState.currentIndex = i;
    const node = graph.nodes.find((n) => n.id === order[i]);
    if (!node) continue;
    node.status = 'running';
    node.lastRunAt = new Date().toISOString();
    saveGraph();

    await new Promise((r) => setTimeout(r, 700 + Math.random() * 500));

    node.status = 'done';
    node.lastOutput = `Nó "${node.title}" (${node.type}) executado às ${new Date().toLocaleTimeString('pt-BR')}.`;
    saveGraph();
  }

  runState.running = false;
  runState.finishedAt = new Date().toISOString();
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = url.pathname;

  try {
    if (pathname === '/api/health' && req.method === 'GET') {
      return sendJson(res, 200, { ok: true, nodes: graph.nodes.length, edges: graph.edges.length });
    }

    if (pathname === '/api/graph' && req.method === 'GET') {
      return sendJson(res, 200, graph);
    }

    if (pathname === '/api/graph' && req.method === 'PUT') {
      const body = await readBody(req);
      graph = {
        nodes: Array.isArray(body.nodes) ? body.nodes : [],
        edges: Array.isArray(body.edges) ? body.edges : [],
      };
      saveGraph();
      return sendJson(res, 200, { ok: true });
    }

    if (pathname === '/api/graph/run' && req.method === 'POST') {
      if (runState.running) return sendJson(res, 409, { error: 'já tem uma execução em andamento' });
      runGraph(null); // não espera terminar — o cliente acompanha via /api/run/status
      return sendJson(res, 202, { ok: true });
    }

    const runOneMatch = pathname.match(/^\/api\/nodes\/([^/]+)\/run$/);
    if (runOneMatch && req.method === 'POST') {
      if (runState.running) return sendJson(res, 409, { error: 'já tem uma execução em andamento' });
      runGraph(runOneMatch[1]);
      return sendJson(res, 202, { ok: true });
    }

    if (pathname === '/api/run/status' && req.method === 'GET') {
      return sendJson(res, 200, { ...runState, nodes: graph.nodes });
    }

    if (pathname === '/api/reset' && req.method === 'POST') {
      graph = { nodes: [], edges: [] };
      saveGraph();
      return sendJson(res, 200, { ok: true });
    }

    if (req.method === 'GET') {
      return serveStatic(req, res, pathname);
    }

    sendJson(res, 405, { error: 'method not allowed' });
  } catch (err) {
    console.error('[graph-canvas] erro:', err);
    sendJson(res, 500, { error: String(err.message || err) });
  }
});

loadGraph();
server.listen(PORT, '127.0.0.1', () => {
  console.log(`[graph-canvas] editor em http://127.0.0.1:${PORT}`);
});
