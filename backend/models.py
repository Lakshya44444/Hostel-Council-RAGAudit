from pydantic import BaseModel
from typing import List, Optional, Dict


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    rank: int
    similarity_score: float
    doc_id: str


class GroundTruth(BaseModel):
    """Optional labeled relevance for evaluation."""
    relevant_chunk_ids: List[str] = []
    relevant_doc_ids: List[str] = []


class AuditRequest(BaseModel):
    query: str
    retrieved_chunks: List[RetrievedChunk]
    ground_truth: Optional[GroundTruth] = None


class AspectCoverage(BaseModel):
    aspect: str
    status: str            # COVERED | PARTIAL | MISSING
    best_chunk_id: str     # chunk_id with highest coverage, or empty string
    best_score: float


class ChunkClassification(BaseModel):
    chunk_id: str
    text: str
    classification: str    # SUPPORTING | PARTIAL | NOISE
    covers_aspects: List[str]
    noise_reason: str      # empty if not noise


class MissingEvidence(BaseModel):
    aspect: str
    candidate_chunk_id: str
    candidate_text: str
    candidate_doc_id: str
    similarity_score: float
    reason_missed: str


class Recommendation(BaseModel):
    type: str              # QUERY_REWRITE | CHUNKING | HYBRID_SEARCH | THRESHOLD
    description: str
    example: str


class GroundTruthEval(BaseModel):
    """Retrieval quality vs. labeled ground truth."""
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    retrieved_count: int
    relevant_count: int
    hit_ids: List[str]            # retrieved AND relevant
    noise_ids: List[str]          # retrieved but NOT relevant
    missed_relevant_ids: List[str]  # relevant but NOT retrieved


class AuditSummary(BaseModel):
    integrity_score: int
    total_aspects: int
    covered_aspects: int
    missing_aspects: int
    supporting_chunks: int
    noise_chunks: int
    noise_ratio: float


class AuditResult(BaseModel):
    query: str
    summary: AuditSummary
    aspects: List[AspectCoverage]
    chunk_classifications: List[ChunkClassification]
    missing_evidence: List[MissingEvidence]
    recommendations: List[Recommendation]
    coverage_matrix: Dict[str, Dict[str, float]]  # aspect -> chunk_id -> score
    explanation: str
    report_html: str
    ground_truth_eval: Optional[GroundTruthEval] = None


class UploadResponse(BaseModel):
    status: str
    num_chunks: int
    doc_ids: List[str]
