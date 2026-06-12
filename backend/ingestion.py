import io
import numpy as np
from typing import List, Dict
from sentence_transformers import SentenceTransformer

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("[ingestion] Loading model: all-MiniLM-L6-v2 ...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[ingestion] Model loaded.")
    return _model


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from a PDF or TXT file."""
    if filename.lower().endswith(".pdf") and PyPDF2:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            return "".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"[ingestion] PDF read error for {filename}: {e}")
            return ""
    return file_bytes.decode("utf-8", errors="ignore")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks of chunk_size characters."""
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start: start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def ingest_documents(files: List[Dict]) -> Dict:
    """
    Ingest a list of files, chunk each document, embed all chunks,
    and return chunks + embeddings ready for FAISS indexing.

    Args:
        files: List of {"filename": str, "bytes": bytes}

    Returns:
        {"chunks": List[Dict], "embeddings": np.ndarray}
    """
    model = get_model()
    all_chunks: List[Dict] = []
    all_texts: List[str] = []

    for f in files:
        doc_id = f["filename"].replace(" ", "_")
        text = extract_text(f["bytes"], f["filename"])
        raw_chunks = chunk_text(text)
        print(f"[ingestion] {f['filename']}: {len(raw_chunks)} chunks")

        for i, chunk in enumerate(raw_chunks):
            all_chunks.append({
                "doc_id": doc_id,
                "chunk_id": f"{doc_id}_c{i}",
                "text": chunk,
                "page": 0,          # page tracking can be enhanced for PDFs
            })
            all_texts.append(chunk)

    if not all_texts:
        return {"chunks": [], "embeddings": np.empty((0, 384), dtype=np.float32)}

    print(f"[ingestion] Embedding {len(all_texts)} chunks …")
    embeddings = model.encode(all_texts, show_progress_bar=False, batch_size=64)
    print(f"[ingestion] Done. Embedding shape: {embeddings.shape}")

    return {"chunks": all_chunks, "embeddings": np.array(embeddings, dtype=np.float32)}
