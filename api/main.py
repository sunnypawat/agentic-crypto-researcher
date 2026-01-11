import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.agent import run_agent, run_research, stream_research_sse

app = FastAPI()

allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
allow_origins = [o.strip() for o in allow_origins_env.split(",")] if allow_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_internal_auth(x_internal_auth: Optional[str] = Header(default=None)) -> None:
    """
    Optional shared-secret protection for the backend.
    If BACKEND_SHARED_SECRET is set, requests must include matching X-Internal-Auth.
    This prevents public callers from consuming your API keys directly on the backend.
    """
    secret = (os.getenv("BACKEND_SHARED_SECRET") or "").strip()
    if not secret:
        return
    if (x_internal_auth or "").strip() != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ResearchRequest(BaseModel):
    query: str = Field(..., description="User question, e.g. 'Should I buy ETH?'")
    session_id: Optional[str] = Field(
        None,
        description="Opaque client session id used to keep conversation memory stateful across turns.",
    )
    selection: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional UI selection for disambiguation, e.g. {'kind':'geckoterminal_pool','id':'solana_...'}",
    )


class ResearchResponse(BaseModel):
    query: str
    language: Optional[str] = Field(
        None, description="Detected language for this query (e.g. 'en' or 'it')."
    )
    is_crypto: bool = Field(True, description="True if a specific crypto asset was resolved and tools were used.")
    crypto_intent: Optional[bool] = None
    unresolved_asset: Optional[bool] = None
    asset_query: Optional[str] = None
    symbol: str
    answer: str
    session_id: Optional[str] = None
    memory: Optional[Dict[str, Any]] = None
    geckoterminal_candidates: Optional[List[Dict[str, Any]]] = None
    token_profile: Optional[Dict[str, Any]] = None
    technicals: Dict[str, Any]
    news: Dict[str, Any]
    sources: List[Dict[str, Any]]
    steps: List[Dict[str, Any]]
    generated_at: str
    agent: Dict[str, Any]


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "agentic-crypto-researcher",
        "status": "ok",
        "routes": {
            "docs": "/docs",
            "health": "/health",
            "research": {"method": "POST", "path": "/research"},
        },
        "example": {"method": "POST", "path": "/research", "json": {"query": "Should I buy ETH?"}},
    }


@app.get("/health")
def health(x_internal_auth: Optional[str] = Header(default=None)) -> Dict[str, str]:
    _require_internal_auth(x_internal_auth)
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse)
def research(req: ResearchRequest, x_internal_auth: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    _require_internal_auth(x_internal_auth)
    return run_research(req.query, session_id=req.session_id, selection=req.selection)


@app.post("/research/stream")
def research_stream(req: ResearchRequest, x_internal_auth: Optional[str] = Header(default=None)) -> StreamingResponse:
    """
    Server-Sent Events stream.
    Events:
      - step: {"step": "...", "ok": true/false, "ms"?: number, ...}
      - answer_delta: {"delta": "..."}
      - final: full ResearchResponse JSON
    """
    _require_internal_auth(x_internal_auth)
    return StreamingResponse(
        stream_research_sse(req.query, session_id=req.session_id, selection=req.selection),
        media_type="text/event-stream",
    )


# Backwards-compatible endpoint from the initial skeleton
@app.post("/analyze")
def analyze(symbol: str) -> Dict[str, str]:
    return {"report": run_agent(symbol)}