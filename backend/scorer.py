"""
scorer.py
Compute the Retrieval Integrity Score (0–100) with penalties for noise and
uncovered aspects.
"""
from typing import List
from models import AspectCoverage, ChunkClassification, AuditSummary


def compute_integrity_score(
    aspect_coverages: List[AspectCoverage],
    chunk_classifications: List[ChunkClassification],
) -> AuditSummary:
    """
    Compute the Retrieval Integrity Score.

    Formula:
        base            = (covered_aspects / total_aspects) * 100
        noise_penalty   = noise_ratio * 20          (max −20 pts)
        partial_penalty = partial_aspects * 5        (−5 pts each)
        final           = clamp(base − noise_penalty − partial_penalty, 0, 100)

    Args:
        aspect_coverages: Per-aspect coverage results.
        chunk_classifications: Per-chunk classification results.

    Returns:
        AuditSummary with all counts and the final score.
    """
    total_aspects = len(aspect_coverages)
    covered = sum(1 for a in aspect_coverages if a.status == "COVERED")
    missing = sum(1 for a in aspect_coverages if a.status == "MISSING")
    partial_aspects = sum(1 for a in aspect_coverages if a.status == "PARTIAL")

    total_chunks = len(chunk_classifications)
    noise_count = sum(1 for c in chunk_classifications if c.classification == "NOISE")
    supporting_count = sum(1 for c in chunk_classifications if c.classification == "SUPPORTING")
    noise_ratio = noise_count / total_chunks if total_chunks > 0 else 0.0

    base_score = (covered / total_aspects * 100) if total_aspects > 0 else 0.0
    noise_penalty = noise_ratio * 20
    partial_penalty = partial_aspects * 5
    final_score = max(0, min(100, int(round(base_score - noise_penalty - partial_penalty))))

    print(
        f"[scorer] base={base_score:.1f} | noise_pen={noise_penalty:.1f} | "
        f"partial_pen={partial_penalty:.1f} | final={final_score}"
    )

    return AuditSummary(
        integrity_score=final_score,
        total_aspects=total_aspects,
        covered_aspects=covered,
        missing_aspects=missing,
        supporting_chunks=supporting_count,
        noise_chunks=noise_count,
        noise_ratio=round(noise_ratio, 3),
    )
