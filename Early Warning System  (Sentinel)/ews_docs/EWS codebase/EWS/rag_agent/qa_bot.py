"""
Q/A Chatbot Module for RAG Pipeline

Provides a conversational Q/A interface over uploaded PDFs using:
1. Semantic search (ChromaDB) to find relevant chunks
2. LLM to generate answers grounded in retrieved context

The chatbot maintains conversation history for follow-up questions.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from . import config
from . import vector_store

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "user" or "assistant"
    content: str


@dataclass
class ChatSession:
    """A chat session with conversation history."""
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    filter_filename: Optional[str] = None  # Restrict to one PDF if set

    def add_message(self, role: str, content: str):
        self.messages.append(ChatMessage(role=role, content=content))

    def get_history_text(self, max_messages: int = 10) -> str:
        """Get recent conversation history as formatted text."""
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        lines = []
        for msg in recent:
            prefix = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)


# ============================================================================
# SESSION STORE (in-memory, per process)
# ============================================================================

_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str, filter_filename: str = None) -> ChatSession:
    """Get an existing session or create a new one."""
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession(
            session_id=session_id,
            filter_filename=filter_filename,
        )
    return _sessions[session_id]


def clear_session(session_id: str):
    """Delete a chat session."""
    _sessions.pop(session_id, None)


# ============================================================================
# LLM HELPER (uses shared ews_agent.llm_config)
# ============================================================================

_llm_instance = None


def _get_llm():
    """Get or create the LLM instance for RAG Q/A (uses shared llm_config)."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    try:
        from ews_agent.llm_config import get_llm

        # Q/A bot needs conversational answers but 2000 tokens is plenty
        # (model has 20K context window; 2000 output + ~5K input = well within limit)
        _llm_instance = get_llm(temperature=0.3, max_tokens=2000)
        logger.info("RAG Q/A LLM initialized via ews_agent.llm_config.get_llm()")
        return _llm_instance
    except Exception as e:
        logger.error(f"Failed to initialize RAG LLM: {e}")
        raise


# ============================================================================
# Q/A FUNCTION
# ============================================================================


def ask_question(
    question: str,
    session_id: str = "default",
    filter_filename: str = None,
    top_k: int = None,
) -> dict:
    """
    Answer a question using RAG (retrieve + generate).

    Steps:
    1. Retrieve top-k relevant chunks from vector store
    2. Build prompt with retrieved context + conversation history
    3. Call LLM to generate answer
    4. Store Q/A in session history

    Args:
        question: The user's question.
        session_id: Chat session ID for conversation continuity.
        filter_filename: If set, only search within this PDF.
        top_k: Number of chunks to retrieve (default: config.RAG_TOP_K).

    Returns:
        Dict with 'answer', 'sources', 'session_id'.
    """
    if top_k is None:
        top_k = config.RAG_TOP_K

    # Get or create session
    session = get_or_create_session(session_id, filter_filename)

    # Step 1: Retrieve relevant chunks
    search_results = vector_store.search(
        query=question,
        top_k=top_k,
        filter_filename=filter_filename or session.filter_filename,
    )

    if not search_results:
        answer = (
            "I couldn't find any relevant information in the uploaded PDFs. "
            "Please make sure PDFs are uploaded to the RAG knowledge base first."
        )
        session.add_message("user", question)
        session.add_message("assistant", answer)
        return {
            "answer": answer,
            "sources": [],
            "session_id": session_id,
        }

    # Step 2: Build context from retrieved chunks
    context_parts = []
    sources = []
    for i, result in enumerate(search_results):
        meta = result["metadata"]
        page = meta.get("page_number", "?")
        fname = meta.get("pdf_filename", "unknown")
        context_parts.append(
            f"[Page {page} of {fname}]:\n{result['text']}"
        )
        sources.append({
            "filename": fname,
            "page": page,
            "distance": round(result["distance"], 4),
            "chunk_id": result.get("chunk_id", ""),
        })

    context_text = "\n\n---\n\n".join(context_parts)

    # Step 3: Build prompt with context + history
    history_text = session.get_history_text(max_messages=6)

    prompt = f"""You are a financial analyst assistant. Answer the user's question based ONLY on the provided context from Indian company annual reports.

If the answer is not found in the context, say "I could not find this information in the uploaded documents." Do NOT make up information.

Context from annual reports:
{context_text}

Conversation history:
{history_text}

User's question: {question}

Provide a clear, concise answer. If you reference specific numbers, mention which page they come from. If the context contains tables, extract the relevant values accurately."""

    # Step 4: Call LLM
    try:
        llm = _get_llm()
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error(f"LLM call failed for Q/A: {e}")
        answer = f"Error generating answer: {str(e)}"

    # Step 5: Store in session history
    session.add_message("user", question)
    session.add_message("assistant", answer)

    return {
        "answer": answer,
        "sources": sources,
        "session_id": session_id,
    }
