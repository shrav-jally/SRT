"""
RAG Agent Configuration

All settings for the RAG pipeline: vector store, embeddings, LLM, chunking.
"""

import os

# ============================================================================
# VECTOR STORE (ChromaDB)
# ============================================================================
CHROMA_PERSIST_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")
)
CHROMA_COLLECTION_NAME = "ews_pdf_pages"

# ============================================================================
# EMBEDDING MODEL
# ============================================================================
# Using ChromaDB's default embedding function (all-MiniLM-L6-v2 via ONNX Runtime)
# No PyTorch or sentence-transformers needed — ~20MB vs ~900MB
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # Same model, ONNX-based inference

# ============================================================================
# CHUNKING SETTINGS
# ============================================================================
# Page-wise chunking: each PDF page becomes one chunk.
# For pages with very long text, split further.
CHUNK_MAX_CHARS = 3000       # Max characters per chunk
CHUNK_OVERLAP_CHARS = 200    # Overlap between sub-chunks within a page

# ============================================================================
# RETRIEVAL SETTINGS
# ============================================================================
RAG_TOP_K = 5                # Number of top chunks to retrieve for Q/A
RAG_TOP_K_CA = 5             # Number of top chunks for CA agent validation

# ============================================================================
# LLM CONFIGURATION
# ============================================================================
# RAG modules (qa_bot.py, ca_rag_agent.py) use ews_agent.llm_config.get_llm()
# which reads LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, LLM_MAX_TOKENS,
# LLM_TEMPERATURE, LLM_VERIFY_SSL from environment variables.
# No duplicate LLM config here — single source of truth in ews_agent/llm_config.py.

# ============================================================================
# RAG APP SERVER
# ============================================================================
RAG_APP_HOST = "0.0.0.0"
RAG_APP_PORT = 8081  # Separate port from main EWS app (8080)

# ============================================================================
# FILE PATHS
# ============================================================================
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag_uploads")
RAG_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag_output")
