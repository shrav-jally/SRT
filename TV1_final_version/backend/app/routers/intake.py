"""
Conversational intake endpoints driving the LangGraph agent.

  POST /api/intake/start   {code} | {custom:{...}}  -> {thread_id, question}
  POST /api/intake/answer  {thread_id, answer}       -> {question} | {done, result}

State persists in the graph's MemorySaver keyed by thread_id (single-worker dev).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langgraph.types import Command

from ..agents.intake import GRAPH

router = APIRouter(prefix="/api/intake", tags=["intake"])


class StartRequest(BaseModel):
    code: Optional[int] = None
    custom: Optional[dict] = None


class AnswerRequest(BaseModel):
    thread_id: str
    answer: Any = None


def _emit(state: dict, thread_id: str) -> dict:
    """Turn a graph invoke result into an API response (question or result)."""
    interrupts = state.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        return {"thread_id": thread_id, "done": False, "question": payload}
    return {"thread_id": thread_id, "done": True,
            "result": state.get("result")}


@router.post("/start")
def start(req: StartRequest):
    if req.code is None and not req.custom:
        raise HTTPException(422, "provide either code or custom")
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    ref = {"code": req.code} if req.code is not None else {"custom": req.custom}
    state = GRAPH.invoke({"ref": ref}, config)
    return _emit(state, thread_id)


@router.post("/answer")
def answer(req: AnswerRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    snapshot = GRAPH.get_state(config)
    if not snapshot.created_at:
        raise HTTPException(404, "unknown or expired intake session")
    state = GRAPH.invoke(Command(resume=req.answer), config)
    return _emit(state, req.thread_id)
