"""
Grafo de agentes do PRISMA — v0 (esqueleto).

Cada nó abaixo representa uma fase do pipeline PRISMA 2020 como se fosse um
agente próprio. Por enquanto os nós são SIMULADOS (não chamam nenhuma API
real nem LLM) — o objetivo desta primeira versão é validar que o grafo
aparece e roda corretamente no LangGraph Studio, com o estado passando de
nó em nó.

Próximo incremento: trocar o corpo de cada nó pra chamar de verdade o
prisma_review (busca em OpenAlex/arXiv/Semantic Scholar) e um LLM (Claude)
para a triagem — sem precisar mudar a estrutura do grafo.
"""

from __future__ import annotations

import time
from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class PrismaState(TypedDict):
    """Estado compartilhado entre os agentes, evolui conforme o grafo roda."""

    project_name: str
    log: list[str]
    papers_found: int
    papers_deduped: int
    papers_screened: int
    papers_eligible: int


def search_node(state: PrismaState) -> dict:
    """Agente de busca — hoje simulado. Depois: prisma_review.search()."""
    time.sleep(1.2)
    found = 120
    return {
        "log": state["log"] + [f"🔍 search: {found} papers encontrados (simulado)"],
        "papers_found": found,
    }


def dedup_node(state: PrismaState) -> dict:
    """Agente de deduplicação — hoje simulado. Depois: prisma_review.dedup()."""
    time.sleep(1.2)
    removed = 12
    remaining = state["papers_found"] - removed
    return {
        "log": state["log"] + [f"🧹 dedup: {removed} duplicatas removidas, {remaining} restantes (simulado)"],
        "papers_deduped": remaining,
    }


def screen_node(state: PrismaState) -> dict:
    """Agente de triagem (regras) — hoje simulado. Depois: prisma_review.screen_rules()."""
    time.sleep(1.2)
    excluded = 40
    remaining = state["papers_deduped"] - excluded
    return {
        "log": state["log"] + [f"✅ screen: {excluded} excluídos por regra, {remaining} restantes (simulado)"],
        "papers_screened": remaining,
    }


def eligibility_node(state: PrismaState) -> dict:
    """Agente de elegibilidade (IA) — hoje simulado. Depois: LLM lê abstracts de verdade."""
    time.sleep(1.2)
    excluded = 15
    remaining = state["papers_screened"] - excluded
    return {
        "log": state["log"] + [f"🤖 eligibility: {excluded} excluídos pela IA, {remaining} elegíveis (simulado)"],
        "papers_eligible": remaining,
    }


builder = StateGraph(PrismaState)
builder.add_node("search", search_node)
builder.add_node("dedup", dedup_node)
builder.add_node("screen", screen_node)
builder.add_node("eligibility", eligibility_node)

builder.add_edge(START, "search")
builder.add_edge("search", "dedup")
builder.add_edge("dedup", "screen")
builder.add_edge("screen", "eligibility")
builder.add_edge("eligibility", END)

graph = builder.compile()
