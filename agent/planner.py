from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from agent.llm import OpenAIChatLLM
from agent.memory import SessionMemory


@dataclass(frozen=True)
class Plan:
    intent: str  # "crypto" | "general"
    asset_query: Optional[str] = None  # user-provided coin name/ticker or token keyword
    language: Optional[str] = None  # "it" | "en" | None (auto)


def plan_query(llm: Optional[OpenAIChatLLM], *, query: str, memory: Optional[SessionMemory]) -> Plan:
    """
    LLM-first planning:
    - Determine if the user is asking about a specific crypto asset
    - Extract a short asset query suitable for CoinGecko/GeckoTerminal search

    If LLM not available, degrade gracefully (treat as general).
    """
    if not llm:
        return Plan(intent="general", asset_query=None)

    mem_summary = (memory.summary if memory else "") or ""
    recent = memory.turns[-6:] if memory else []
    recent_text = "\n".join(f"{t.role}: {t.content}" for t in recent)

    schema = (
        "Return JSON only with keys:\n"
        "- intent: 'crypto' or 'general'\n"
        "- asset_query: string or null (short; coin name/ticker/token keyword)\n"
        "- language: 'it' or 'en' (match the user's language)\n"
    )

    prompt = (
        "You are a planner for an agentic crypto researcher.\n"
        "Decide whether the user asks about a specific crypto asset (token/coin). If yes, extract the asset query.\n"
        "If they ask a general question (including crypto education), choose 'general'.\n"
        "Use conversation context for coreference (e.g. 'buy it' refers to the last asset).\n\n"
        "When you output asset_query:\n"
        "- Keep it VERY short (1–3 words max)\n"
        "- Prefer ticker or the distinctive token name\n"
        "- Do NOT include generic words like 'coin', 'token', 'crypto'\n"
        "- Do NOT include the full question\n\n"
        f"Memory summary:\n{mem_summary}\n\n"
        f"Recent turns:\n{recent_text}\n\n"
        f"User question:\n{query}\n\n"
        + schema
    )

    out = llm.chat(
        [
            {"role": "system", "content": "You output strict JSON. No prose."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        timeout=30.0,
    )
    try:
        obj = json.loads(out)
        intent = str(obj.get("intent") or "general").lower()
        if intent not in ("crypto", "general"):
            intent = "general"
        aq = obj.get("asset_query")
        asset_query = str(aq).strip() if isinstance(aq, str) and aq.strip() else None
        if asset_query and len(asset_query) > 60:
            asset_query = asset_query[:60]
        if asset_query:
            # deterministic cleanup: remove generic words the planner might include
            lowered = asset_query.lower()
            for w in (" coin", " token", " crypto", " cryptocurrency"):
                lowered = lowered.replace(w, "")
            asset_query = " ".join(lowered.split()).strip()
            if not asset_query:
                asset_query = None
        lang = obj.get("language")
        language = str(lang).strip().lower() if isinstance(lang, str) else None
        if language not in ("it", "en"):
            language = None
        return Plan(intent=intent, asset_query=asset_query, language=language)
    except Exception:
        return Plan(intent="general", asset_query=None, language=None)

