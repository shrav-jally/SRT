"""
Vector Store Module for RAG Pipeline

Manages ChromaDB vector store operations:
- Store PDF page chunks with embeddings
- Delete PDF chunks by filename
- Semantic search (retrieve top-k chunks for a query)
- List stored PDFs

Uses ChromaDB's default embedding function (ONNX Runtime based)
which runs all-MiniLM-L6-v2 without needing PyTorch/sentence-transformers.
ChromaDB persists to disk so data survives restarts.
"""

import logging
import os
from typing import Optional

from . import config
from .pdf_parser import PageChunk

logger = logging.getLogger(__name__)

# ============================================================================
# EMBEDDING FUNCTION (lazy-loaded singleton)
# ============================================================================

_embedding_fn = None


def _get_embedding_function():
    """
    Get or create the embedding function.

    Uses ChromaDB's default embedding function which runs all-MiniLM-L6-v2
    via ONNX Runtime — no PyTorch or sentence-transformers needed (~20MB vs ~900MB).

    Lazy-loaded to avoid importing heavy ML libraries at module level.
    Cached as module-level singleton for reuse.
    """
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn

    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        _embedding_fn = DefaultEmbeddingFunction()
        logger.info("Loaded ChromaDB default embedding function (all-MiniLM-L6-v2 via ONNX)")
        return _embedding_fn
    except ImportError:
        logger.error(
            "chromadb not installed. "
            "Run: pip install chromadb"
        )
        raise
    except Exception as e:
        logger.error(f"Failed to load embedding function: {e}")
        raise


# ============================================================================
# CHROMA DB CLIENT (lazy-loaded singleton)
# ============================================================================

_chroma_client = None
_collection = None


def _get_client():
    """Get or create the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    try:
        import chromadb
        os.makedirs(config.CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=config.CHROMA_PERSIST_DIR,
        )
        logger.info(f"ChromaDB client initialized at: {config.CHROMA_PERSIST_DIR}")
        return _chroma_client
    except ImportError:
        logger.error(
            "chromadb not installed. Run: pip install chromadb"
        )
        raise
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        raise


def _get_collection():
    """Get or create the ChromaDB collection."""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()
    embedding_fn = _get_embedding_function()

    _collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(
        f"Collection '{config.CHROMA_COLLECTION_NAME}' ready "
        f"({_collection.count()} existing chunks)"
    )
    return _collection


# ============================================================================
# PUBLIC API
# ============================================================================


def store_chunks(chunks: list[PageChunk]) -> int:
    """
    Store a list of PageChunk objects in the vector store.

    Each chunk gets a unique ID based on filename, page, and sub-chunk index.
    If chunks with the same IDs already exist, they are updated (upsert).

    Args:
        chunks: List of PageChunk objects from pdf_parser.

    Returns:
        Number of chunks stored.
    """
    if not chunks:
        return 0

    collection = _get_collection()

    ids = [c.chunk_id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [c.metadata for c in chunks]

    # Upsert in batches of 100 (ChromaDB recommendation)
    batch_size = 100
    stored = 0

    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]

        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_meta,
        )
        stored += len(batch_ids)

    logger.info(f"Stored {stored} chunks from '{chunks[0].pdf_filename}'")
    return stored


def delete_pdf(filename: str) -> int:
    """
    Delete all chunks belonging to a specific PDF file.

    Args:
        filename: The PDF filename to delete.

    Returns:
        Number of chunks deleted.
    """
    collection = _get_collection()

    # Find all chunk IDs for this filename
    results = collection.get(
        where={"pdf_filename": filename},
    )

    if not results or not results["ids"]:
        logger.info(f"No chunks found for '{filename}' to delete")
        return 0

    chunk_ids = results["ids"]
    collection.delete(ids=chunk_ids)

    logger.info(f"Deleted {len(chunk_ids)} chunks for '{filename}'")
    return len(chunk_ids)


def search(query: str, top_k: int = None, filter_filename: str = None) -> list[dict]:
    """
    Semantic search: find the top-k most relevant chunks for a query.

    Args:
        query: The search query string.
        top_k: Number of results to return (default: config.RAG_TOP_K).
        filter_filename: If set, only search within this PDF file.

    Returns:
        List of dicts with keys: 'text', 'metadata', 'distance', 'chunk_id'.
    """
    if top_k is None:
        top_k = config.RAG_TOP_K

    collection = _get_collection()

    where_filter = None
    if filter_filename:
        where_filter = {"pdf_filename": filter_filename}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    if not results or not results["documents"] or not results["documents"][0]:
        return []

    search_results = []
    for i in range(len(results["documents"][0])):
        search_results.append({
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
            "chunk_id": results["ids"][0][i] if results["ids"] else "",
        })

    return search_results


def list_pdfs() -> list[dict]:
    """
    List all PDFs stored in the vector store with their chunk counts.

    Returns:
        List of dicts with keys: 'filename', 'num_chunks', 'pages'.
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    # Get all unique filenames
    results = collection.get(
        include=["metadatas"],
    )

    if not results or not results["metadatas"]:
        return []

    # Aggregate by filename
    pdf_info = {}
    for meta in results["metadatas"]:
        fname = meta.get("pdf_filename", "unknown")
        if fname not in pdf_info:
            pdf_info[fname] = {
                "filename": fname,
                "num_chunks": 0,
                "pages": set(),
            }
        pdf_info[fname]["num_chunks"] += 1
        page_num = meta.get("page_number")
        if page_num:
            pdf_info[fname]["pages"].add(page_num)

    # Convert sets to sorted lists
    result = []
    for fname, info in pdf_info.items():
        result.append({
            "filename": fname,
            "num_chunks": info["num_chunks"],
            "pages": sorted(info["pages"]),
        })

    return sorted(result, key=lambda x: x["filename"])


def get_stats() -> dict:
    """
    Get vector store statistics.

    Returns:
        Dict with 'total_chunks', 'total_pdfs', 'collection_name'.
    """
    collection = _get_collection()
    pdfs = list_pdfs()

    return {
        "total_chunks": collection.count(),
        "total_pdfs": len(pdfs),
        "collection_name": config.CHROMA_COLLECTION_NAME,
        "pdfs": pdfs,
    }


def reset_store() -> bool:
    """
    Delete the entire collection and recreate it.

    WARNING: This deletes ALL stored data!

    Returns:
        True if successful.
    """
    global _collection

    try:
        client = _get_client()
        client.delete_collection(config.CHROMA_COLLECTION_NAME)
        _collection = None  # Force re-creation on next access
        logger.info(f"Collection '{config.CHROMA_COLLECTION_NAME}' deleted")
        # Recreate
        _get_collection()
        return True
    except Exception as e:
        logger.error(f"Failed to reset store: {e}")
        return False
