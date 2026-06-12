"""
missing_detector.py
Search the full FAISS knowledge-base index to find evidence that should
have been retrieved for MISSING aspects but wasn't in the top-k.
"""
import faiss
import numpy as np
from typing import List, Dict, Optional

from models import AspectCoverage, MissingEvidence
from ingestion import get_model

# Module-level KB state (set after /upload-kb)
_index: Optional[faiss.Index] = None
_kb_chunks: List[Dict] = []


def set_kb_index(index: faiss.Index, chunks: List[Dict]) -> None:
    """Store FAISS index and chunk metadata for later searches."""
    global _index, _kb_chunks
    _index = index
    _kb_chunks = chunks
    print(f"[missing_detector] KB index updated: {index.ntotal} vectors, {len(chunks)} chunks")


def find_missing_evidence(
    aspect_coverages: List[AspectCoverage],
    retrieved_chunk_ids: List[str],
    top_k: int = 3,
) -> List[MissingEvidence]:
    """
    For every MISSING aspect, search the full KB FAISS index to surface
    candidate chunks that should have been retrieved.

    Args:
        aspect_coverages: Output of get_aspect_coverage().
        retrieved_chunk_ids: IDs already in the top-k retrieval.
        top_k: Max candidates to fetch per aspect (before filtering).

    Returns:
        List of MissingEvidence instances (one best candidate per MISSING aspect).
    """
    if _index is None or _index.ntotal == 0:
        print("[missing_detector] No KB index available — skipping.")
        return []

    model = get_model()
    missing_evidence: List[MissingEvidence] = []
    retrieved_set = set(retrieved_chunk_ids)

    for ac in aspect_coverages:
        if ac.status != "MISSING":
            continue

        # Embed the aspect phrase
        query_vec = model.encode([ac.aspect], show_progress_bar=False)
        query_vec = np.array(query_vec, dtype=np.float32)

        # Search more candidates than top_k so we can skip already-retrieved ones
        search_k = min(top_k + len(retrieved_chunk_ids) + 5, _index.ntotal)
        distances, indices = _index.search(query_vec, search_k)

        found = False
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(_kb_chunks):
                continue
            chunk = _kb_chunks[idx]
            if chunk["chunk_id"] in retrieved_set:
                continue  # already retrieved — skip

            # Convert L2 distance to a similarity proxy in [0, 1]
            similarity = float(1.0 / (1.0 + dist))

            missing_evidence.append(
                MissingEvidence(
                    aspect=ac.aspect,
                    candidate_chunk_id=chunk["chunk_id"],
                    candidate_text=chunk["text"][:400],
                    candidate_doc_id=chunk["doc_id"],
                    similarity_score=round(similarity, 4),
                    reason_missed=(
                        f"Chunk ranked below the top-k retrieval cutoff "
                        f"for aspect: '{ac.aspect}'"
                    ),
                )
            )
            found = True
            break  # one best missed candidate per MISSING aspect

        if not found:
            print(f"[missing_detector] No un-retrieved candidate found for: {ac.aspect}")

    return missing_evidence
