from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.llm import OpenAIChatLLM


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class SessionMemory:
    session_id: str
    summary: str = ""
    turns: List[Turn] = None  # recent turns (verbatim)
    pending: List[Turn] = None  # older turns pending summarization
    last_crypto_symbol: Optional[str] = None
    last_seen_s: float = 0.0

    def __post_init__(self) -> None:
        if self.turns is None:
            self.turns = []
        if self.pending is None:
            self.pending = []


class MemoryStore:
    """
    A small, production-friendly memory:
    - Keep last N turns verbatim
    - Batch older turns into 'pending'
    - Summarize pending into 'summary' periodically (or when size grows)
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 7200,
        keep_last_turns: int = 6,
        pending_trigger: int = 6,
        max_chars: int = 9000,
        summary_target_chars: int = 900,
    ):
        self.ttl_seconds = ttl_seconds
        self.keep_last_turns = keep_last_turns
        self.pending_trigger = pending_trigger
        self.max_chars = max_chars
        self.summary_target_chars = summary_target_chars
        self._sessions: Dict[str, SessionMemory] = {}

    @staticmethod
    def from_env() -> "MemoryStore":
        return MemoryStore(
            ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "7200")),
            keep_last_turns=int(os.getenv("MEMORY_KEEP_LAST_TURNS", "6")),
            pending_trigger=int(os.getenv("MEMORY_PENDING_TRIGGER", os.getenv("MEMORY_KEEP_LAST_TURNS", "6"))),
            max_chars=int(os.getenv("MEMORY_MAX_CHARS", "9000")),
            summary_target_chars=int(os.getenv("MEMORY_SUMMARY_TARGET_CHARS", "900")),
        )

    def _cleanup(self) -> None:
        now = time.time()
        dead = [sid for sid, s in self._sessions.items() if (now - s.last_seen_s) > self.ttl_seconds]
        for sid in dead:
            self._sessions.pop(sid, None)

    def get(self, session_id: Optional[str]) -> Optional[SessionMemory]:
        if not session_id:
            return None
        self._cleanup()
        s = self._sessions.get(session_id)
        if not s:
            s = SessionMemory(session_id=session_id, last_seen_s=time.time())
            self._sessions[session_id] = s
        s.last_seen_s = time.time()
        return s

    def append(self, s: SessionMemory, role: str, content: str) -> None:
        s.turns.append(Turn(role=role, content=content))
        # enforce keep_last by moving to pending
        while len(s.turns) > self.keep_last_turns:
            s.pending.append(s.turns.pop(0))

    def _chars(self, s: SessionMemory) -> int:
        n = len(s.summary)
        for t in s.pending:
            n += len(t.content)
        for t in s.turns:
            n += len(t.content)
        return n

    def maybe_summarize(self, s: SessionMemory, llm: Optional[OpenAIChatLLM]) -> Dict[str, Any]:
        before = self._chars(s)
        should = bool(s.pending) and (len(s.pending) >= self.pending_trigger or before > self.max_chars)
        dropped = 0
        was_summarized = False

        if should:
            pending_text = "\n".join(f"{t.role}: {t.content}".strip() for t in s.pending)
            if llm and pending_text.strip():
                prompt = (
                    "Write a compact MEMORY SUMMARY for future turns.\n"
                    f"Hard limits:\n- Max {self.summary_target_chars} characters\n- Max 6 bullet points\n\n"
                    "Only keep DURABLE state:\n"
                    "- user goal / task\n"
                    "- explicit user preferences (language, formatting)\n"
                    "- decisions made / selected asset or selected DEX pool id\n"
                    "- unresolved questions / next step\n\n"
                    "DO NOT include:\n"
                    "- any numeric market data (prices, RSI, liquidity, volume)\n"
                    "- lists of news headlines\n"
                    "- long explanations or action plans\n"
                    "- unrelated topics (never introduce new coins/topics)\n\n"
                    "Output: bullet points in plain text (no markdown headings).\n\n"
                    f"Existing summary:\n{s.summary}\n\n"
                    f"Dialogue to compress:\n{pending_text}\n"
                )
                try:
                    s.summary = llm.chat(
                        [
                            {"role": "system", "content": "You summarize chat history into short memory."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        timeout=30.0,
                    ).strip()
                    was_summarized = True
                except Exception:
                    # fall back to truncation
                    was_summarized = False
            if not was_summarized:
                if s.summary:
                    s.summary = (s.summary[: self.summary_target_chars] + " …").strip()
                else:
                    s.summary = "• (Older context summarized/trimmed.)"
            # deterministic cleanup: keep only a few short bullets and avoid numeric dumps
            lines = [ln.strip() for ln in s.summary.splitlines() if ln.strip()]
            cleaned: List[str] = []
            for ln in lines:
                # drop lines with obvious numeric market stats / links
                if "$" in ln or "http" in ln or "www." in ln:
                    continue
                digit_count = sum(1 for ch in ln if ch.isdigit())
                if digit_count >= 6:
                    continue
                cleaned.append(ln)
                if len(cleaned) >= 6:
                    break
            s.summary = "\n".join(cleaned)[: self.summary_target_chars].strip() or "• (Summary trimmed.)"
            dropped = len(s.pending)
            s.pending = []

        after = self._chars(s)
        return {
            "approx_chars": after,
            "summary_chars": len(s.summary),
            "turns": len(s.turns),
            "pending_turns": len(s.pending),
            "max_chars": self.max_chars,
            "was_summarized": bool(should),
            "dropped_turns": dropped,
        }

