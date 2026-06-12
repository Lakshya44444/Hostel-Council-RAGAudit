"""
ground_truth.py
Optional evaluation of retrieval quality against labeled ground truth.

Given the chunks (and/or documents) that a human marked as truly relevant,
compute precision / recall / F1 for the retrieved set — the standard IR
metrics that quantify Coverage Detection Accuracy and Missing Evidence.
"""
from typing import List, Dict, Optional

from models import GroundTruth, GroundTruthEval


def evaluate_ground_truth(
    retrieved_chunks: List[Dict],
    ground_truth: Optional[GroundTruth],
) -> Optional[GroundTruthEval]:
    """
    Compare the retrieved chunk set against labeled relevant chunks/docs.

    A retrieved chunk counts as a hit if its chunk_id is in relevant_chunk_ids
    OR its doc_id is in relevant_doc_ids.

    Args:
        retrieved_chunks: List of chunk dicts (chunk_id, doc_id, ...).
        ground_truth: Optional labeled relevance. If None or empty, returns None.

    Returns:
        GroundTruthEval, or None when no ground truth was supplied.
    """
    if ground_truth is None:
        return None

    relevant_chunk_ids = set(ground_truth.relevant_chunk_ids or [])
    relevant_doc_ids = set(ground_truth.relevant_doc_ids or [])
    if not relevant_chunk_ids and not relevant_doc_ids:
        return None

    def is_relevant(c: Dict) -> bool:
        return c["chunk_id"] in relevant_chunk_ids or c.get("doc_id") in relevant_doc_ids

    retrieved_ids = [c["chunk_id"] for c in retrieved_chunks]
    hit_ids   = [c["chunk_id"] for c in retrieved_chunks if is_relevant(c)]
    noise_ids = [c["chunk_id"] for c in retrieved_chunks if not is_relevant(c)]

    # Relevant chunk_ids that never appeared in the retrieved set (false negatives).
    retrieved_set = set(retrieved_ids)
    missed_relevant_ids = sorted(relevant_chunk_ids - retrieved_set)

    tp = len(hit_ids)
    fp = len(noise_ids)
    # Recall is only well-defined against explicitly labeled chunk ids; doc-level
    # labels can't tell us how many relevant chunks exist, so they don't add FNs.
    fn = len(missed_relevant_ids)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    print(f"[ground_truth] P={precision:.3f} R={recall:.3f} F1={f1:.3f} (TP={tp} FP={fp} FN={fn})")

    return GroundTruthEval(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        retrieved_count=len(retrieved_ids),
        relevant_count=len(relevant_chunk_ids) if relevant_chunk_ids else tp,
        hit_ids=hit_ids,
        noise_ids=noise_ids,
        missed_relevant_ids=missed_relevant_ids,
    )
