from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from agent.orchestrator import stream_research_sse as _stream
from agent.prompts import CRYPTO_SYSTEM


def stream_research_sse(query: str, session_id: Optional[str] = None, selection: Optional[Dict[str, Any]] = None) -> Iterable[str]:
    """
    Public streaming API used by FastAPI SSE endpoint.
    """
    return _stream(query, session_id=session_id, selection=selection)


def run_research(query: str, session_id: Optional[str] = None, selection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Non-streaming wrapper for /research.
    We reuse the streaming loop and return the `final` JSON payload for consistency.
    This avoids brittle regex parsing and keeps behavior aligned with the UI stream.
    """
    final_payload: Optional[Dict[str, Any]] = None

    for chunk in stream_research_sse(query, session_id=session_id, selection=selection):
        if "event: final" not in chunk:
            continue
        for line in chunk.splitlines():
            if line.startswith("data:"):
                data_str = line[len("data:") :].strip()
                try:
                    final_payload = json.loads(data_str)
                except Exception:
                    final_payload = None

    if not final_payload:
        return {
            "query": query,
            "symbol": "N/A",
            "answer": "Unable to produce a report.",
            "token_profile": {},
            "technicals": {},
            "news": {},
            "sources": [],
            "steps": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": {"framework": "error", "system_prompt": CRYPTO_SYSTEM},
        }
    return final_payload


def run_agent(symbol_or_query: str) -> str:
    """
    Backwards-compatible entrypoint: returns the answer text.
    """
    report = run_research(symbol_or_query)
    return report["answer"]