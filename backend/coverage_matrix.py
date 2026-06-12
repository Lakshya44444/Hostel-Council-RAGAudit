"""
coverage_matrix.py
Compute a (aspect × chunk) similarity matrix and derive per-aspect coverage status.
"""
import numpy as np
from typing import List, Dict

from ingestion import get_model

# Thresholds
COVERAGE_THRESHOLD = 0.40   # score >= this → COVERED
PARTIAL_THRESHOLD = 0.24    # score >= this → PARTIAL; below → MISSING


def compute_coverage_matrix(
    aspects: List[str],
    retrieved_chunks: List[Dict]
) -> Dict[str, Dict[str, float]]:
    """
    Compute cosine-similarity for every (aspect, chunk) pair.

    Args:
        aspects: List of aspect strings.
        retrieved_chunks: List of chunk dicts with 'chunk_id' and 'text'.

    Returns:
        Nested dict: {aspect: {chunk_id: score}}
    """
    if not aspects or not retrieved_chunks:
        return {a: {} for a in aspects}

    model = get_model()

    # Embed aspects and chunks
    aspect_embeddings = model.encode(aspects, show_progress_bar=False, batch_size=64)
    chunk_texts = [c["text"] for c in retrieved_chunks]
    chunk_ids = [c["chunk_id"] for c in retrieved_chunks]
    chunk_embeddings = model.encode(chunk_texts, show_progress_bar=False, batch_size=64)

    # Normalize for cosine similarity via dot product
    def normalize(mat: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat / norms

    a_norm = normalize(np.array(aspect_embeddings, dtype=np.float32))
    c_norm = normalize(np.array(chunk_embeddings, dtype=np.float32))

    # Shape: (num_aspects, num_chunks)
    scores = np.clip(a_norm @ c_norm.T, 0.0, 1.0)

    matrix: Dict[str, Dict[str, float]] = {}
    for i, aspect in enumerate(aspects):
        matrix[aspect] = {
            chunk_id: round(float(scores[i, j]), 4)
            for j, chunk_id in enumerate(chunk_ids)
        }

    return matrix


def get_aspect_coverage(
    aspects: List[str],
    matrix: Dict[str, Dict[str, float]],
    threshold: float = COVERAGE_THRESHOLD,
) -> List:
    """
    Derive coverage status for each aspect from the pre-computed matrix.

    Returns a list of AspectCoverage model instances.
    """
    from models import AspectCoverage

    results = []
    for aspect in aspects:
        scores = matrix.get(aspect, {})
        if not scores:
            results.append(
                AspectCoverage(aspect=aspect, status="MISSING", best_chunk_id="", best_score=0.0)
            )
            continue

        best_chunk_id = max(scores, key=scores.get)
        best_score = scores[best_chunk_id]

        if best_score >= threshold:
            status = "COVERED"
        elif best_score >= PARTIAL_THRESHOLD:
            status = "PARTIAL"
        else:
            status = "MISSING"

        results.append(
            AspectCoverage(
                aspect=aspect,
                status=status,
                best_chunk_id=best_chunk_id,
                best_score=best_score,
            )
        )

    return results
