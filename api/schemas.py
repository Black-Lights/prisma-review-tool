"""Pydantic models for API request/response validation."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


class ScreenDecision(BaseModel):
    decision: Literal["include", "exclude"]
    reason: str


class BatchScreenItem(BaseModel):
    paper_id: str
    decision: Literal["include", "exclude"]
    reason: str


class PaperSummary(BaseModel):
    id: str
    title: str
    authors: str
    year: int
    abstract: str
    venue: str
    source: str
    doi: str
    current_decision: Optional[str] = None
    current_reason: Optional[str] = None


class PaperDetail(BaseModel):
    id: str
    title: str
    authors: list[str]
    year: int
    abstract: str
    venue: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: str
    keywords: list[str] = []
    screen_decision: Optional[str] = None
    screen_reason: Optional[str] = None
    screen_method: Optional[str] = None
    eligibility_decision: Optional[str] = None
    eligibility_reason: Optional[str] = None
    eligibility_method: Optional[str] = None
