"""
evidence_classifier.py
Classify each retrieved chunk as SUPPORTING, PARTIAL, or NOISE.
"""
from typing import List, Dict
from models import ChunkClassification

SUPPORT_THRESHOLD = 0.40   # covers aspect well
NOISE_THRESHOLD = 0.25     # weakly relevant


def classify_chunks(
    retrieved_chunks: List[Dict],
    aspects: List[str],
    matrix: Dict[str, Dict[str, float]],
) -> List[ChunkClassification]:
    """
    For every retrieved chunk, determine its role:
    - SUPPORTING : max similarity across all aspects >= SUPPORT_THRESHOLD
    - PARTIAL    : max similarity in [NOISE_THRESHOLD, SUPPORT_THRESHOLD)
    - NOISE      : max similarity < NOISE_THRESHOLD

    Args:
        retrieved_chunks: List of chunk dicts.
        aspects: List of aspect strings.
        matrix: Pre-computed {aspect: {chunk_id: score}} dict.

    Returns:
        List of ChunkClassification instances.
    """
    results: List[ChunkClassification] = []

    for chunk in retrieved_chunks:
        chunk_id = chunk["chunk_id"]
        covered_aspects: List[str] = []
        max_score = 0.0

        for aspect in aspects:
            score = matrix.get(aspect, {}).get(chunk_id, 0.0)
            if score > max_score:
                max_score = score
            if score >= SUPPORT_THRESHOLD:
                covered_aspects.append(aspect)

        if max_score >= SUPPORT_THRESHOLD:
            classification = "SUPPORTING"
            noise_reason = ""
        elif max_score >= NOISE_THRESHOLD:
            classification = "PARTIAL"
            noise_reason = f"Weakly relevant — max aspect similarity: {max_score:.2f}"
        else:
            classification = "NOISE"
            noise_reason = (
                f"No aspect covered above noise threshold — max similarity: {max_score:.2f}"
            )

        results.append(
            ChunkClassification(
                chunk_id=chunk_id,
                text=chunk["text"],
                classification=classification,
                covers_aspects=covered_aspects,
                noise_reason=noise_reason,
            )
        )

    return results
