import logging
from typing import List
import numpy as np

logger = logging.getLogger(__name__)

# Try to import optional RAG dependencies
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logger.warning("RAG dependencies not found. Falling back to simple truncation.")

_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None and RAG_AVAILABLE:
        try:
            logger.info("Loading sentence-transformers embedding model (all-MiniLM-L6-v2)...")
            _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
    return _embedding_model

def get_relevant_chunks(text: str, query: str, top_k: int = 5, chunk_size: int = 4000, chunk_overlap: int = 500) -> str:
    """
    Splits the text into chunks and returns the top_k most semantically relevant chunks for the query.
    If RAG is not available, falls back to returning the truncated text.
    """
    if not RAG_AVAILABLE or len(text) < chunk_size * 2:
        return text[:50000]

    model = get_embedding_model()
    if model is None:
        return text[:50000]

    try:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        chunks = splitter.split_text(text)
        
        if not chunks:
            return text[:50000]

        # Embed query and chunks
        query_embedding = model.encode([query])
        chunk_embeddings = model.encode(chunks)

        # Compute cosine similarities
        similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]

        # Get top k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # Sort indices sequentially so the text flows naturally
        top_indices = sorted(top_indices)

        relevant_text = "\n\n...[SNIP]...\n\n".join([chunks[i] for i in top_indices])
        return relevant_text

    except Exception as e:
        logger.error(f"Semantic chunking failed: {e}. Falling back to truncation.")
        return text[:50000]
