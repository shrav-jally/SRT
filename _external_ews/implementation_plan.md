# EWS Architecture Review & SOTA Integration Plan

This document outlines an architectural review of the current Annual Report Extraction pipeline (EWS), identifies critical flaws, proposes State-of-the-Art (SOTA) inspirations, and provides a roadmap for the next phases of development.

## 1. Current Architectural Flaws

While the 9-layer pipeline is robust, it currently suffers from several structural limitations inherent to traditional NLP pipelines:

*   **Context Window Truncation (`text[:20000]`)**: 
    *   *Flaw*: In `content_extractor.py`, narrative text is arbitrarily truncated to avoid token limits. Annual reports have massive, sprawling sections (e.g., Notes to Accounts, MD&A). Blind truncation silently drops critical data, such as subsidiary lists or late-section ESG metrics.
*   **Deterministic Regex Brittleness**: 
    *   *Flaw*: Relying heavily on Regex as a pre-extractor (e.g., for Board Members, CINs, Subsidiaries) is highly fragile. OCR anomalies, slight tabular misalignments, or unconventional formatting common in Indian Annual Reports will cause the regex to fail silently.
*   **Lack of Multi-Modal Spatial Awareness for Narrative**: 
    *   *Flaw*: While VLMs are used for table extraction, narrative extraction relies on flattened `pdf_text`. This destroys spatial relationships in complex infographics, multi-column layouts, and nested text-tables often found in the MD&A and CSR sections.
*   **Absence of Agentic Self-Correction**: 
    *   *Flaw*: If an LLM hallucinates a metric or fails Pydantic schema validation, the system logs a warning and either returns raw text or drops the field. There is no feedback loop where the LLM is given its error and asked to self-correct.
*   **Siloed Section Routing**: 
    *   *Flaw*: The router assumes that "ESG Metrics" only live in the "ESG & Sustainability" section. In reality, a Chairman's Speech might contain the most critical ESG targets. Hardcoded routing misses cross-document insights.

## 2. SOTA Inspirations (State-of-the-Art)

To elevate this pipeline to a truly enterprise, AI-native system, we should integrate the following SOTA methodologies:

*   **Agentic Workflows (Reflexion / Multi-Agent Debate)**:
    *   Implement an "Extractor Agent" and a "Critic Agent". The Critic compares the Extractor's JSON output directly against the raw text to verify grounding. If hallucination is detected, the Critic forces the Extractor to retry, significantly boosting accuracy.
*   **GraphRAG (Knowledge Graphs + Retrieval)**:
    *   Instead of flattening data into isolated Excel rows, construct a Knowledge Graph (Entities: Director, Subsidiary, Risk, Segment; Relationships: `MANAGES`, `OWNS`, `THREATENS`). GraphRAG allows complex traversal (e.g., "How does this subsidiary impact this specific operational risk?").
*   **Semantic Chunking & Vector Retrieval (RAG)**:
    *   Replace arbitrary text truncation with a dynamic RAG approach. Embed the entire document into a vector store (e.g., Qdrant, Chroma). When querying for "Future Outlook", the system retrieves the top-k most semantically relevant chunks from the *entire* document, not just the MD&A section.
*   **Vision-Language Native Extraction**:
    *   Process complex narrative pages (like the Company Profile or Business Overview) directly as high-resolution images using models like Gemini 1.5 Pro or GPT-4o. This bypasses the text-flattening step entirely and allows the model to "see" charts and infographics.

## 3. Proposed Roadmap: What's Next

We should execute these improvements in a phased, iterative approach:

### Phase 1: Agentic Self-Correction & Verification
*   **Action**: Wrap `llm_call_with_retry` in a Reflexion loop. 
*   **Detail**: If `validate_entity_list` fails, feed the Pydantic error back to the LLM. Add a post-extraction verification prompt to double-check numerical extractions against the source snippet.

### Phase 2: RAG-based Unbounded Context
*   **Action**: Remove `text[:20000]` truncations.
*   **Detail**: Integrate a lightweight Vector DB or a robust chunking algorithm (like RecursiveCharacterTextSplitter) to dynamically feed only the relevant sub-sections to the LLM, regardless of section length.

### Phase 3: Cross-Sectional Entity Resolution
*   **Action**: Consolidate entities across sections.
*   **Detail**: A Director might be mentioned in Corporate Governance, Remuneration, and the Chairman's letter. Implement a deduplication/merging layer to create a single, unified "Director" profile that aggregates data from all 9 layers.

### Phase 4: Full Multi-Modal Narrative
*   **Action**: Transition Priority 2 & Priority 3 narrative extraction to image-based VLM processing.
*   **Detail**: Send page screenshots to the VLM instead of parsed text strings to capture visually rich data (charts, graphs, infographics).

---

> [!IMPORTANT]
> **User Review Required**
> Which of these SOTA phases do you want to prioritize first? 
> 1. Implementing the **Agentic Self-Correction loop** (highest impact on accuracy).
> 2. Moving to **RAG/Semantic Chunking** to solve the text truncation issue.
> 3. Refactoring narrative extraction to use **Multi-Modal / VLM Vision**. 

Please provide your feedback and we will begin execution on the selected phase!
