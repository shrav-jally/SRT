"""
RAG Agent Module — Isolated RAG pipeline for EWS.

Provides:
    1. PDF upload → page-wise chunking → vector store (ChromaDB)
    2. Q/A chatbot over uploaded PDFs
    3. "Extra CA" agent that validates/fills extraction results using RAG

This module is isolated from the core ews_agent extraction pipeline.
They connect through API endpoints only.
"""

__version__ = "0.1.0"
