/**
 * Cliente mínimo pra falar com o servidor local do LangGraph (porta 2024).
 * Sem o SDK oficial de propósito: os payloads abaixo foram testados na mão
 * (curl) contra o servidor real antes de escrever este arquivo, então o
 * contrato aqui é garantidamente compatível com a versão instalada.
 */

const BASE_URL = process.env.NEXT_PUBLIC_LANGGRAPH_URL || "http://127.0.0.1:2024";

export type GraphStructure = {
  nodes: { id: string; type?: string; data?: { name?: string } }[];
  edges: { source: string; target: string }[];
};

export async function listAssistants(): Promise<{ assistant_id: string; graph_id: string; name: string }[]> {
  const res = await fetch(`${BASE_URL}/assistants/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Falha ao listar assistants: ${res.status}`);
  return res.json();
}

export async function getGraphStructure(assistantId: string): Promise<GraphStructure> {
  const res = await fetch(`${BASE_URL}/assistants/${assistantId}/graph`);
  if (!res.ok) throw new Error(`Falha ao buscar estrutura do grafo: ${res.status}`);
  return res.json();
}

export async function createThread(): Promise<{ thread_id: string }> {
  const res = await fetch(`${BASE_URL}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Falha ao criar thread: ${res.status}`);
  return res.json();
}

export async function getThreadState(threadId: string): Promise<{
  values: Record<string, unknown>;
  next: string[];
}> {
  const res = await fetch(`${BASE_URL}/threads/${threadId}/state`);
  if (!res.ok) throw new Error(`Falha ao buscar estado da thread: ${res.status}`);
  return res.json();
}

export type StreamEvent = { event: string; data: unknown };

/**
 * Roda (ou continua) uma thread, parando antes de CADA nó (step-by-step).
 * `input` só deve ser passado na primeira chamada de uma thread nova;
 * nas chamadas seguintes (continuar) passe `input: null`.
 * `onEvent` é chamado pra cada evento SSE conforme chega, em tempo real.
 */
export async function streamRun(
  threadId: string,
  assistantId: string,
  input: Record<string, unknown> | null,
  allNodeIds: string[],
  onEvent: (evt: StreamEvent) => void
): Promise<void> {
  const res = await fetch(`${BASE_URL}/threads/${threadId}/runs/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      assistant_id: assistantId,
      input,
      interrupt_before: allNodeIds,
      stream_mode: ["updates", "values"],
    }),
  });
  if (!res.ok || !res.body) throw new Error(`Falha ao rodar: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // eventos SSE são separados por linha em branco: "event: X\ndata: Y\n\n"
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      const eventLine = lines.find((l) => l.startsWith("event:"));
      const dataLine = lines.find((l) => l.startsWith("data:"));
      if (!eventLine || !dataLine) continue;
      const event = eventLine.slice("event:".length).trim();
      const rawData = dataLine.slice("data:".length).trim();
      try {
        onEvent({ event, data: JSON.parse(rawData) });
      } catch {
        onEvent({ event, data: rawData });
      }
    }
  }
}
