"""
main.py — FastAPI application for the Retrieval Integrity Auditor.

Routes:
    GET  /health          → liveness check
    POST /upload-kb       → ingest documents into FAISS
    POST /audit           → run full retrieval integrity audit
    GET  /                → serve frontend index.html
    GET  /demo/*          → serve demo files
"""

import os
import sys
import io
import json
import faiss
import numpy as np
from typing import List

# Force UTF-8 output on Windows (avoids UnicodeEncodeError with box-drawing chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from dotenv import load_dotenv

from models import AuditRequest, AuditResult, UploadResponse, AuditSummary
from ingestion import ingest_documents
from aspect_decomposer import decompose_query
from coverage_matrix import compute_coverage_matrix, get_aspect_coverage
from evidence_classifier import classify_chunks
from missing_detector import find_missing_evidence, set_kb_index
from scorer import compute_integrity_score
from explainer import generate_explanation_and_recommendations
from ground_truth import evaluate_ground_truth

load_dotenv()

# ─── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Retrieval Integrity Auditor",
    description="Audit the retrieval step of RAG systems to detect coverage gaps and noise.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory KB state ────────────────────────────────────────────────────────
_kb_index = None
_kb_chunks: List[dict] = []

# ─── Path helpers ──────────────────────────────────────────────────────────────
_this_dir      = os.path.dirname(os.path.abspath(__file__))
_frontend_dir  = os.path.normpath(os.path.join(_this_dir, "..", "frontend"))
_demo_dir      = os.path.normpath(os.path.join(_this_dir, "..", "demo"))


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "kb_loaded": _kb_index is not None,
        "kb_chunks": len(_kb_chunks),
    }


# ─── Upload Knowledge Base ─────────────────────────────────────────────────────
@app.post("/upload-kb", response_model=UploadResponse)
async def upload_kb(files: List[UploadFile] = File(...)):
    """
    Ingest one or more PDF/TXT files, chunk them, embed with all-MiniLM-L6-v2,
    and store in a FAISS IndexFlatL2.
    """
    global _kb_index, _kb_chunks

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    file_infos = []
    for f in files:
        content = await f.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"File '{f.filename}' is empty.")
        file_infos.append({"filename": f.filename, "bytes": content})

    result = ingest_documents(file_infos)
    embeddings: np.ndarray = result["embeddings"]
    _kb_chunks = result["chunks"]

    if len(_kb_chunks) == 0:
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from the uploaded files."
        )

    # Build FAISS index
    dim = embeddings.shape[1]
    _kb_index = faiss.IndexFlatL2(dim)
    _kb_index.add(embeddings)

    set_kb_index(_kb_index, _kb_chunks)
    print(f"[main] FAISS index built: {_kb_index.ntotal} vectors | dim={dim}")

    return UploadResponse(
        status="success",
        num_chunks=len(_kb_chunks),
        doc_ids=list({c["doc_id"] for c in _kb_chunks}),
    )


# ─── Audit ─────────────────────────────────────────────────────────────────────
@app.post("/audit", response_model=AuditResult)
async def audit(request: AuditRequest):
    """
    Full 8-step retrieval integrity audit pipeline.
    """
    if _kb_index is None:
        raise HTTPException(
            status_code=400,
            detail="Knowledge base not loaded. Please upload documents first via POST /upload-kb.",
        )
    if not request.retrieved_chunks:
        raise HTTPException(
            status_code=400,
            detail="No retrieved chunks provided in request body."
        )

    query = request.query
    chunks_raw = [c.dict() for c in request.retrieved_chunks]
    retrieved_ids = [c["chunk_id"] for c in chunks_raw]

    print(f"\n[audit] -- New Audit ------------------------------------------")
    print(f"[audit] Query: {query[:120]}")
    print(f"[audit] Retrieved chunks: {len(chunks_raw)}")

    # Step 1 — Decompose query into aspects
    aspects = decompose_query(query)

    # Step 2 — Coverage matrix
    matrix = compute_coverage_matrix(aspects, chunks_raw)

    # Step 3 — Per-aspect coverage status
    aspect_coverages = get_aspect_coverage(aspects, matrix)

    # Step 4 — Classify each chunk
    chunk_classifications = classify_chunks(chunks_raw, aspects, matrix)

    # Step 5 — Find missing evidence from full KB
    missing_evidence = find_missing_evidence(aspect_coverages, retrieved_ids)

    # Step 6 — Compute integrity score
    summary = compute_integrity_score(aspect_coverages, chunk_classifications)

    # Step 7 — Generate explanation + recommendations
    explain_data = generate_explanation_and_recommendations(
        query, aspect_coverages, chunk_classifications, missing_evidence, summary.integrity_score
    )

    # Step 7b — Optional ground-truth evaluation (precision / recall / F1)
    gt_eval = evaluate_ground_truth(chunks_raw, request.ground_truth)

    # Step 8 — Build embedded HTML report
    report_html = _build_report_html(
        query, summary, aspect_coverages, chunk_classifications, missing_evidence, explain_data, gt_eval
    )

    print(f"[audit] -- Complete. Score: {summary.integrity_score}/100 --")

    return AuditResult(
        query=query,
        summary=summary,
        aspects=aspect_coverages,
        chunk_classifications=chunk_classifications,
        missing_evidence=missing_evidence,
        recommendations=explain_data["recommendations"],
        coverage_matrix=matrix,
        explanation=explain_data["explanation"],
        report_html=report_html,
        ground_truth_eval=gt_eval,
    )


# ─── HTML report builder ───────────────────────────────────────────────────────
def _build_report_html(query, summary, aspects, chunks, missing, explain_data, gt_eval=None) -> str:
    status_colors = {
        "COVERED": "#d4edda",
        "PARTIAL": "#fff3cd",
        "MISSING": "#f8d7da",
    }
    chunk_colors = {
        "SUPPORTING": "#d4edda",
        "PARTIAL": "#fff3cd",
        "NOISE": "#f8d7da",
    }

    aspect_rows = ""
    for a in aspects:
        bg = status_colors.get(a.status, "#fff")
        aspect_rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{a.aspect}</td><td><strong>{a.status}</strong></td>"
            f"<td>{a.best_score:.2f}</td><td>{a.best_chunk_id or '—'}</td></tr>"
        )

    chunk_rows = ""
    for c in chunks:
        bg = chunk_colors.get(c.classification, "#fff")
        aspects_covered = ", ".join(c.covers_aspects) or "—"
        chunk_rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{c.chunk_id}</td><td><strong>{c.classification}</strong></td>"
            f"<td>{c.text[:120]}…</td><td>{aspects_covered}</td>"
            f"<td>{c.noise_reason or '—'}</td></tr>"
        )

    rec_items = ""
    for r in explain_data.get("recommendations", []):
        rec_items += (
            f"<li><strong>[{r.type}]</strong> {r.description}"
            f"<br><em>Example:</em> {r.example}</li>"
        )

    missing_section = ""
    for m in missing:
        missing_section += (
            f"<div style='background:#fff3cd;border:1px solid #ffc107;padding:10px;"
            f"margin:8px 0;border-radius:6px'>"
            f"<strong>Aspect:</strong> {m.aspect}<br>"
            f"<strong>Candidate chunk:</strong> {m.candidate_chunk_id} ({m.candidate_doc_id})<br>"
            f"<strong>Similarity:</strong> {m.similarity_score:.4f}<br>"
            f"<strong>Reason missed:</strong> {m.reason_missed}<br>"
            f"<strong>Text preview:</strong> {m.candidate_text[:300]}…"
            f"</div>"
        )

    gt_section = ""
    if gt_eval is not None:
        gt_section = (
            "<h2>Ground-Truth Evaluation</h2>"
            "<table>"
            "<tr><th>Precision</th><th>Recall</th><th>F1</th>"
            "<th>True Pos</th><th>False Pos</th><th>False Neg</th></tr>"
            f"<tr><td>{gt_eval.precision:.2f}</td><td>{gt_eval.recall:.2f}</td>"
            f"<td><strong>{gt_eval.f1:.2f}</strong></td><td>{gt_eval.true_positives}</td>"
            f"<td>{gt_eval.false_positives}</td><td>{gt_eval.false_negatives}</td></tr>"
            "</table>"
            f"<p><strong>Missed relevant chunks:</strong> "
            f"{', '.join(gt_eval.missed_relevant_ids) or 'none'}</p>"
        )

    score = summary.integrity_score
    score_color = "#dc3545" if score < 40 else "#ffc107" if score < 70 else "#28a745"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Retrieval Integrity Report</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 960px; margin: auto; padding: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  .score {{ font-size: 3rem; font-weight: bold; color: {score_color}; }}
</style>
</head>
<body>
<h1>📋 Retrieval Integrity Report</h1>
<p><strong>Query:</strong> {query}</p>
<p class="score">{score}/100</p>
<p>{explain_data.get('explanation', '')}</p>

{gt_section}

<h2>Aspect Coverage</h2>
<table>
  <tr><th>Aspect</th><th>Status</th><th>Best Score</th><th>Best Chunk</th></tr>
  {aspect_rows}
</table>

<h2>Chunk Classifications</h2>
<table>
  <tr><th>Chunk ID</th><th>Class</th><th>Text Preview</th><th>Aspects Covered</th><th>Noise Reason</th></tr>
  {chunk_rows}
</table>

<h2>Missing Evidence</h2>
{missing_section if missing_section else "<p>No missing evidence detected.</p>"}

<h2>Recommendations</h2>
<ul>{rec_items}</ul>
</body>
</html>"""


# ─── Static file serving ───────────────────────────────────────────────────────

# Serve frontend at /static/
if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")
    print(f"[main] Frontend mounted from: {_frontend_dir}")

# Serve demo files at /demo/
if os.path.isdir(_demo_dir):
    app.mount("/demo", StaticFiles(directory=_demo_dir), name="demo")
    print(f"[main] Demo dir mounted from: {_demo_dir}")

# Root → serve frontend index.html
@app.get("/", response_class=FileResponse)
def serve_frontend():
    index_path = os.path.join(_frontend_dir, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Frontend not found. Run the app from the project root.</h1>", status_code=404)
    return FileResponse(index_path)


# ─── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
