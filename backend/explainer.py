"""
explainer.py
Generate a human-readable explanation of retrieval failures plus
actionable recommendations.

Uses the free LLM client (Ollama / Groq / Gemini).
Falls back to a rich, fully rule-based generator that needs ZERO API key.
"""

import os
from typing import List

from llm_client import llm_json_chat
from models import (
    AspectCoverage,
    MissingEvidence,
    ChunkClassification,
    Recommendation,
)

# ── LLM system prompt ─────────────────────────────────────────────────────────
_SYSTEM = (
    "You are a RAG system expert auditor. "
    "Given a retrieval audit report, produce a JSON response with exactly two keys:\n"
    "  \"explanation\": A 3–4 sentence plain-English explanation of WHY retrieval "
    "failed, written for a non-technical reviewer. Be specific about which aspects "
    "were missed and how noisy chunks hurt quality.\n"
    "  \"recommendations\": A JSON array of 3–5 objects each with keys:\n"
    "    \"type\": one of QUERY_REWRITE | CHUNKING | HYBRID_SEARCH | THRESHOLD | RERANKING\n"
    "    \"description\": what to do (one sentence)\n"
    "    \"example\": a concrete actionable example (one sentence)\n\n"
    "Return ONLY valid JSON — no markdown fences, no preamble."
)


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _rule_based_explain(
    query: str,
    aspect_coverages: List[AspectCoverage],
    chunk_classifications: List[ChunkClassification],
    missing_evidence: List[MissingEvidence],
    integrity_score: int,
) -> dict:
    """
    Generate explanation and recommendations using pure logic — no LLM needed.
    """
    missing  = [a for a in aspect_coverages if a.status == "MISSING"]
    partial  = [a for a in aspect_coverages if a.status == "PARTIAL"]
    covered  = [a for a in aspect_coverages if a.status == "COVERED"]
    noise    = [c for c in chunk_classifications if c.classification == "NOISE"]
    total    = len(aspect_coverages)
    n_chunks = len(chunk_classifications)

    # ── Explanation ───────────────────────────────────────────────────────
    sentences = []

    if integrity_score >= 71:
        sentences.append(
            f"The retrieval system performed well, covering {len(covered)} of {total} "
            f"query aspects with relevant chunks."
        )
    elif integrity_score >= 41:
        sentences.append(
            f"The retrieval system achieved partial coverage, addressing {len(covered)} of "
            f"{total} query aspects but leaving {len(missing)} aspect(s) unaddressed."
        )
    else:
        sentences.append(
            f"The retrieval system failed significantly, covering only {len(covered)} of "
            f"{total} query aspects and missing {len(missing)} critical sub-topic(s)."
        )

    if missing:
        aspect_list = ", ".join(f'"{a.aspect}"' for a in missing[:3])
        suffix = f" and {len(missing)-3} more" if len(missing) > 3 else ""
        sentences.append(
            f"The following aspect(s) had no relevant chunks retrieved: "
            f"{aspect_list}{suffix}."
        )

    if noise:
        sentences.append(
            f"{len(noise)} of {n_chunks} retrieved chunk(s) were classified as NOISE — "
            f"they consumed retrieval slots without providing useful information, "
            f"which reduced the overall integrity score."
        )

    if partial:
        sentences.append(
            f"{len(partial)} aspect(s) had only weak partial coverage (below the 0.40 "
            f"similarity threshold), meaning the retrieved chunks touched on these topics "
            f"but did not answer them sufficiently."
        )

    if missing_evidence:
        docs = list({m.candidate_doc_id for m in missing_evidence})
        sentences.append(
            f"Better-matching chunks were found in the knowledge base "
            f"(from: {', '.join(docs)}) but were not included in the top-k retrieval."
        )

    explanation = " ".join(sentences)

    # ── Recommendations ───────────────────────────────────────────────────
    recs = []

    if missing:
        missing_terms = " AND ".join(a.aspect for a in missing[:2])
        recs.append(Recommendation(
            type="QUERY_REWRITE",
            description=(
                "Rewrite the query to explicitly include keywords from the missing aspects, "
                "so the retriever can surface relevant chunks."
            ),
            example=(
                f'Expand your query to include phrases like "{missing_terms}" '
                f"to improve recall for those sub-topics."
            ),
        ))

    if noise:
        recs.append(Recommendation(
            type="THRESHOLD",
            description=(
                "Raise the similarity score cutoff to filter out low-relevance chunks "
                "before they enter the retrieved set."
            ),
            example=(
                "Set a minimum similarity threshold of 0.45 (instead of 0.38) "
                "in your vector retriever to eliminate noise chunks."
            ),
        ))

    recs.append(Recommendation(
        type="CHUNKING",
        description=(
            "Reduce chunk size so each chunk focuses on a single topic, "
            "improving both precision and aspect-level coverage."
        ),
        example=(
            "Try 250-char chunks with 50-char overlap instead of 500-char chunks — "
            "smaller chunks map more cleanly to individual query aspects."
        ),
    ))

    recs.append(Recommendation(
        type="HYBRID_SEARCH",
        description=(
            "Combine dense vector search with sparse keyword (BM25) search "
            "to improve recall for exact-match terms like policy names or numbers."
        ),
        example=(
            "Use a hybrid retriever (e.g., Weaviate, Qdrant, or Elasticsearch) "
            "with alpha=0.5 to blend vector and BM25 scores."
        ),
    ))

    if len(aspect_coverages) > 2:
        recs.append(Recommendation(
            type="RERANKING",
            description=(
                "Apply a cross-encoder reranker after initial retrieval to re-score "
                "chunks against the full query, surfacing deeper matches."
            ),
            example=(
                "Use 'cross-encoder/ms-marco-MiniLM-L-6-v2' from Hugging Face "
                "(free) to rerank the top-20 candidates and select the best 5."
            ),
        ))

    return {"explanation": explanation, "recommendations": recs[:5]}


# ── Public API ────────────────────────────────────────────────────────────────

def generate_explanation_and_recommendations(
    query: str,
    aspect_coverages: List[AspectCoverage],
    chunk_classifications: List[ChunkClassification],
    missing_evidence: List[MissingEvidence],
    integrity_score: int,
) -> dict:
    """
    Produce a plain-English explanation + typed recommendations.

    Tries the configured free LLM first; falls back to rule-based generator
    if no LLM is available. Always returns a valid dict.

    Returns:
        {"explanation": str, "recommendations": List[Recommendation]}
    """
    missing_aspects = [a.aspect for a in aspect_coverages if a.status == "MISSING"]
    partial_aspects = [a.aspect for a in aspect_coverages if a.status == "PARTIAL"]
    noise_ids       = [c.chunk_id for c in chunk_classifications if c.classification == "NOISE"]
    missed_docs     = list({m.candidate_doc_id for m in missing_evidence})

    context = (
        f"Query: {query}\n"
        f"Integrity Score: {integrity_score}/100\n"
        f"Missing aspects: {missing_aspects}\n"
        f"Partial aspects: {partial_aspects}\n"
        f"Noise chunk IDs: {noise_ids}\n"
        f"Documents with missed evidence: {missed_docs}\n"
        f"Coverage breakdown:\n"
        + "\n".join(
            f"  • {a.aspect} → {a.status} (best score: {a.best_score:.2f})"
            for a in aspect_coverages
        )
    )

    # ── Try LLM ───────────────────────────────────────────────────────────
    data = llm_json_chat(system=_SYSTEM, user=f"Audit context:\n{context}\n\nGenerate output:")

    if isinstance(data, dict) and "explanation" in data and "recommendations" in data:
        try:
            recs = [Recommendation(**r) for r in data["recommendations"]]
            print(f"[explainer] LLM returned {len(recs)} recommendations.")
            return {"explanation": data["explanation"], "recommendations": recs}
        except Exception as e:
            print(f"[explainer] LLM response parse error: {e}")

    # ── Fallback: rule-based ───────────────────────────────────────────────
    print("[explainer] Using rule-based fallback.")
    return _rule_based_explain(
        query, aspect_coverages, chunk_classifications, missing_evidence, integrity_score
    )
