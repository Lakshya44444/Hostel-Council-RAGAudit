"""
llm_client.py — Unified FREE LLM client.

Priority order (all free, pick one via LLM_PROVIDER env var):
  1. ollama   – 100% local, completely free, no API key needed
                Install: https://ollama.com  →  ollama pull llama3.2
  2. groq     – Free-tier API, very fast (llama3-8b-8192)
                Get key: https://console.groq.com  (free, no credit card)
  3. gemini   – Google Gemini free tier (gemini-1.5-flash)
                Get key: https://aistudio.google.com/app/apikey
  4. fallback – Built-in rule-based logic, zero dependencies, zero cost

Set LLM_PROVIDER=ollama|groq|gemini in your .env  (default: fallback)
"""

import os
import json
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "fallback").lower().strip()
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_HOST   = os.getenv("OLLAMA_HOST", "http://localhost:11434")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama3-8b-8192")
GEMINI_MODEL  = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def _chat(system: str, user: str) -> str:
    """Route to the configured free LLM provider and return raw response text."""
    provider = LLM_PROVIDER
    print(f"[llm_client] Provider={provider}")

    if provider == "ollama":
        return _ollama_chat(system, user)
    elif provider == "groq":
        return _groq_chat(system, user)
    elif provider == "gemini":
        return _gemini_chat(system, user)
    else:
        return ""   # caller handles empty → rule-based fallback


# ── Ollama (100% free, local) ─────────────────────────────────────────────────

def _ollama_chat(system: str, user: str) -> str:
    try:
        import requests
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        print(f"[llm_client] Ollama error: {e}")
        return ""


# ── Groq (free tier) ──────────────────────────────────────────────────────────

def _groq_chat(system: str, user: str) -> str:
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[llm_client] Groq error: {e}")
        return ""


# ── Google Gemini (free tier) ─────────────────────────────────────────────────

def _gemini_chat(system: str, user: str) -> str:
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system,
        )
        resp = model.generate_content(user)
        return resp.text.strip()
    except Exception as e:
        print(f"[llm_client] Gemini error: {e}")
        return ""


# ── Public helpers ─────────────────────────────────────────────────────────────

def llm_json_chat(system: str, user: str) -> Optional[dict]:
    """
    Ask the LLM for a JSON response.
    Returns parsed dict/list or None if provider is unavailable/fails.
    """
    raw = _chat(system, user)
    if not raw:
        return None
    cleaned = re.sub(r"```json|```", "", raw).strip()
    # Find first JSON structure
    for pattern in (r'\{.*\}', r'\[.*\]'):
        m = re.search(pattern, cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    try:
        return json.loads(cleaned)
    except Exception:
        return None
