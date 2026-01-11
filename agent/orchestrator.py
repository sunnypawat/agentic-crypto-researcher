from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from agent.llm import OpenAIChatLLM
from agent.memory import MemoryStore, SessionMemory
from agent.planner import plan_query
from agent.prompts import CRYPTO_SYSTEM, GENERAL_SYSTEM, UNRESOLVED_CRYPTO_SYSTEM
from agent.tools import (
    HttpGetError,
    get_geckoterminal_pool,
    get_latest_news,
    get_market_data,
    get_token_profile,
    resolve_coingecko_id_from_query,
    search_geckoterminal_pools,
)


def _sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _compact_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n")
    # collapse extreme spacing
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def _safe_ms(dt_s: float) -> int:
    return int(max(0.0, dt_s) * 1000)


class ResearchOrchestrator:
    def __init__(self, *, memory: MemoryStore, llm: Optional[OpenAIChatLLM]):
        self.memory = memory
        self.llm = llm

    def stream(
        self, *, query: str, session_id: Optional[str], selection: Optional[Dict[str, Any]]
    ) -> Iterable[str]:
        t0 = time.perf_counter()
        steps: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []

        market: Dict[str, Any] = {}
        news: Dict[str, Any] = {}
        token_profile: Dict[str, Any] = {}
        symbol: Optional[str] = None

        crypto_intent = False
        unresolved_asset = False
        asset_query: Optional[str] = None
        gecko_candidates: List[Dict[str, Any]] = []
        lang: Optional[str] = None

        def step(payload: Dict[str, Any]) -> str:
            payload.setdefault("ms", 0)
            steps.append(payload)
            return _sse("step", payload)

        def trace(phase: str, message: str) -> str:
            return _sse("trace", {"phase": phase, "message": message, "t": int(time.time() * 1000)})

        def tool(name: str, *, inputs: Dict[str, Any], ok: bool, ms: int, note: Optional[str] = None) -> str:
            p = {"tool": name, "inputs": inputs, "ok": ok, "ms": ms}
            if note:
                p["note"] = note
            return _sse("tool", p)

        def obs(kind: str, summary: str, data: Optional[Dict[str, Any]] = None) -> str:
            p: Dict[str, Any] = {"kind": kind, "summary": summary}
            if data is not None:
                p["data"] = data
            return _sse("observation", p)

        def ctx(payload: Dict[str, Any]) -> str:
            return _sse("context", payload)

        yield step({"step": "received_query", "ok": True})
        yield trace("plan", "Planning the next actions (tools vs normal answer).")

        sess = self.memory.get(session_id)
        if sess is not None:
            self.memory.append(sess, "user", query)
            mem_stats = self.memory.maybe_summarize(sess, self.llm)
            yield _sse("memory", {"session_id": session_id, **mem_stats})
        else:
            mem_stats = None

        # ---- Selection flow (DEX pool) ----
        if selection and isinstance(selection, dict) and selection.get("kind") == "geckoterminal_pool":
            pool_id = str(selection.get("id") or "").strip()
            if pool_id:
                yield step({"step": "apply_selection", "ok": True, "kind": "geckoterminal_pool", "id": pool_id})
                yield trace("tools", "Fetching selected pool from GeckoTerminal.")
                t_pool = time.perf_counter()
                try:
                    pool = get_geckoterminal_pool(pool_id)
                    yield tool(
                        "get_geckoterminal_pool",
                        inputs={"id": pool_id},
                        ok=True,
                        ms=_safe_ms(time.perf_counter() - t_pool),
                    )
                    sources.extend(pool.get("sources", []) if isinstance(pool, dict) else [])
                    base = pool.get("base_token", {}) if isinstance(pool, dict) else {}
                    symbol = str(base.get("symbol") or "DEX").upper()
                    token_profile = {
                        "name": base.get("name"),
                        "symbol": symbol,
                        "coin_id": None,
                        "image_url": base.get("image_url"),
                        "homepage": None,
                        "geckoterminal_url": pool.get("pool_url"),
                        "coingecko_url": None,
                        "sources": pool.get("sources", []),
                    }
                    market = {
                        "symbol": symbol,
                        "coin_id": None,
                        "days": 0,
                        "last_price_usd": pool.get("price_usd"),
                        "price_series": [],
                        "indicators": {},
                        "dex_pool": pool,
                        "sources": pool.get("sources", []),
                    }
                    crypto_intent = True
                    yield obs(
                        "token_profile",
                        f"Loaded DEX token profile for {symbol}.",
                        {"symbol": symbol, "name": token_profile.get("name"), "image_url": token_profile.get("image_url")},
                    )
                    yield obs(
                        "technicals",
                        "Loaded DEX pool stats (price/liquidity/volume). RSI/MACD not available for DEX-only analysis.",
                        {"symbol": symbol, "last_price_usd": market.get("last_price_usd"), "rsi_14": None, "macd_label": None, "price_series": []},
                    )
                except Exception as e:
                    yield tool(
                        "get_geckoterminal_pool",
                        inputs={"id": pool_id},
                        ok=False,
                        ms=_safe_ms(time.perf_counter() - t_pool),
                        note=str(e),
                    )
                    # fall back to normal planning

        # ---- Plan (LLM-first) ----
        # We use the planner primarily for intent + clean asset query + language.
        plan = plan_query(self.llm, query=query, memory=sess)
        if plan.language:
            lang = plan.language
        if not crypto_intent:
            crypto_intent = plan.intent == "crypto"
        if not asset_query:
            asset_query = plan.asset_query
        yield step(
            {
                "step": "plan_done",
                "ok": True,
                "intent": plan.intent,
                "asset_query": asset_query,
                "language": plan.language,
            }
        )

        # ---- Crypto tool path (CoinGecko) ----
        if crypto_intent and symbol is None:
            if not asset_query:
                unresolved_asset = True
            else:
                t_res = time.perf_counter()
                try:
                    resolved = resolve_coingecko_id_from_query(asset_query)
                    symbol = str((resolved.get("symbol") or "N/A")).upper()
                    yield step({"step": "resolve_asset", "ok": True, "symbol": symbol, "coin_id": resolved.get("id"), "ms": _safe_ms(time.perf_counter() - t_res)})
                except Exception as e:
                    unresolved_asset = True
                    yield step({"step": "resolve_asset", "ok": False, "error": str(e), "ms": _safe_ms(time.perf_counter() - t_res)})

        is_crypto = bool(crypto_intent and symbol and not unresolved_asset) or bool(market.get("dex_pool"))

        if is_crypto and symbol and not market.get("dex_pool"):
            # token profile
            yield trace("tools", "Fetching token profile from CoinGecko.")
            t_prof = time.perf_counter()
            try:
                token_profile = get_token_profile(symbol)
                yield tool("get_token_profile", inputs={"symbol": symbol}, ok=True, ms=_safe_ms(time.perf_counter() - t_prof))
                sources.extend(token_profile.get("sources", []) if isinstance(token_profile, dict) else [])
                yield obs(
                    "token_profile",
                    f"Loaded token profile for {symbol}.",
                    {"symbol": symbol, "name": token_profile.get("name"), "image_url": token_profile.get("image_url")},
                )
            except Exception as e:
                token_profile = {"symbol": symbol, "error": str(e), "sources": []}
                yield tool("get_token_profile", inputs={"symbol": symbol}, ok=False, ms=_safe_ms(time.perf_counter() - t_prof), note=str(e))

            # market
            yield trace("tools", "Fetching 30-day market data and computing RSI/MACD.")
            t_m = time.perf_counter()
            try:
                market = get_market_data(symbol)
                yield tool(
                    "get_market_data",
                    inputs={"symbol": symbol, "days": 30, "vs_currency": "usd"},
                    ok=True,
                    ms=_safe_ms(time.perf_counter() - t_m),
                )
                sources.extend(market.get("sources", []) if isinstance(market, dict) else [])
                rsi = (market.get("indicators") or {}).get("rsi_14")
                macd_label = ((market.get("indicators") or {}).get("macd") or {}).get("label")
                yield obs(
                    "technicals",
                    f"Computed RSI/MACD for {symbol}.",
                    {
                        "symbol": symbol,
                        "last_price_usd": market.get("last_price_usd"),
                        "rsi_14": rsi,
                        "macd_label": macd_label,
                        "range_30d": market.get("range_30d"),
                        "volatility_30d": market.get("volatility_30d"),
                        "price_series": market.get("price_series"),
                    },
                )
            except Exception as e:
                error_kind = "upstream_error"
                retry_after_s = None
                status_code = None
                if isinstance(e, HttpGetError):
                    status_code = e.status_code
                    retry_after_s = e.retry_after_s
                    if int(e.status_code) == 429:
                        error_kind = "rate_limited"
                        if retry_after_s is None:
                            retry_after_s = 30
                market = {
                    "symbol": symbol,
                    "error": str(e),
                    "error_kind": error_kind,
                    "retry_after_s": retry_after_s,
                    "status_code": status_code,
                    "sources": [],
                }
                yield tool(
                    "get_market_data",
                    inputs={"symbol": symbol, "days": 30, "vs_currency": "usd"},
                    ok=False,
                    ms=_safe_ms(time.perf_counter() - t_m),
                    note=str(e),
                )
                # Keep the stream alive and let the UI fill what it can.
                yield obs(
                    "technicals",
                    f"Market data unavailable for {symbol} (CoinGecko error).",
                    {
                        "symbol": symbol,
                        "error_kind": error_kind,
                        "retry_after_s": retry_after_s,
                        "status_code": status_code,
                        "last_price_usd": None,
                        "rsi_14": None,
                        "macd_label": None,
                        "range_30d": None,
                        "volatility_30d": None,
                        "price_series": [],
                    },
                )

            # news
            yield trace("tools", "Fetching latest news from CryptoPanic.")
            t_n = time.perf_counter()
            try:
                news = get_latest_news(symbol)
                yield tool("get_latest_news", inputs={"symbol": symbol, "limit": 5}, ok=True, ms=_safe_ms(time.perf_counter() - t_n))
                sources.extend(news.get("sources", []) if isinstance(news, dict) else [])
                titles = [i.get("title") for i in (news.get("items") or []) if isinstance(i, dict)]
                yield obs("news", f"Retrieved {len(titles)} headlines.", {"headlines": titles[:5]})
            except Exception as e:
                news = {"symbol": symbol, "items": [], "error": str(e), "sources": []}
                yield tool("get_latest_news", inputs={"symbol": symbol, "limit": 5}, ok=False, ms=_safe_ms(time.perf_counter() - t_n), note=str(e))

        # ---- Unresolved asset: GeckoTerminal candidates ----
        if crypto_intent and unresolved_asset and asset_query:
            yield trace("tools", "Searching GeckoTerminal pools for possible matches.")
            t_gt = time.perf_counter()
            try:
                res = search_geckoterminal_pools(asset_query, limit=8)
                yield tool(
                    "search_geckoterminal_pools",
                    inputs={"query": asset_query, "limit": 8},
                    ok=True,
                    ms=_safe_ms(time.perf_counter() - t_gt),
                )
                gecko_candidates = res.get("items", []) if isinstance(res, dict) else []
                sources.extend(res.get("sources", []) if isinstance(res, dict) else [])
                if gecko_candidates:
                    yield obs(
                        "geckoterminal_candidates",
                        f"Found {len(gecko_candidates)} candidate pools on GeckoTerminal.",
                        {"items": gecko_candidates[:8]},
                    )
            except Exception as e:
                yield tool(
                    "search_geckoterminal_pools",
                    inputs={"query": asset_query, "limit": 8},
                    ok=False,
                    ms=_safe_ms(time.perf_counter() - t_gt),
                    note=str(e),
                )

        # ---- Synthesis (stream) ----
        answer_parts: List[str] = []
        framework = "openai_stream" if self.llm else "no_llm"

        if self.llm:
            yield step({"step": "llm_synthesis_start", "ok": True, "model": self.llm.cfg.model, "ms": 0})
            yield trace("synthesis", "Writing the final answer using tool observations.")

            if crypto_intent and unresolved_asset:
                ctx_payload = {
                    "asset_query": asset_query,
                    "candidates": gecko_candidates[:8],
                    "language": lang,
                    "memory": {
                        "summary": (sess.summary if sess else ""),
                        "recent_turns": [{"role": t.role, "content": t.content} for t in (sess.turns[-6:] if sess else [])],
                    },
                }
                yield ctx(ctx_payload)
                msgs = [
                    {"role": "system", "content": UNRESOLVED_CRYPTO_SYSTEM},
                    {
                        "role": "system",
                        "content": f"Answer in {'Italian' if (lang or '').lower() == 'it' else 'English'}.",
                    },
                    {"role": "user", "content": query},
                ]
            elif is_crypto:
                ctx_payload = {
                    "symbol": symbol,
                    "token_profile": token_profile,
                    "technicals": market,
                    "news": news,
                    "dex_pool": market.get("dex_pool"),
                    "language": lang,
                    "memory": {
                        "summary": (sess.summary if sess else ""),
                        "recent_turns": [{"role": t.role, "content": t.content} for t in (sess.turns[-6:] if sess else [])],
                    },
                }
                yield ctx(ctx_payload)
                user_rules = (
                    "Write a compact answer in markdown.\n"
                    "- Keep it short but actionable (~12–18 lines)\n"
                    "- Use headings 'Summary' and 'Action plan' (in the user's language)\n"
                    "- Do NOT include any images (no markdown image syntax like ![...](...)); the UI header already shows the token.\n"
                    "- If RSI/MACD are not available (DEX-only), say so briefly\n"
                    "- Action plan must be concrete:\n"
                    "  - 1 bullish scenario trigger + what to do\n"
                    "  - 1 bearish scenario trigger + what to do\n"
                    "  - 1 invalidation / risk control rule (e.g., stop / max loss / position sizing)\n"
                    "  - 2 things to watch (news/catalysts/levels)\n"
                    "- End with a short sources list\n"
                    "- Include one short 'Not financial advice' sentence\n"
                )
                msgs = [
                    {"role": "system", "content": CRYPTO_SYSTEM},
                    {
                        "role": "system",
                        "content": f"Answer in {'Italian' if (lang or '').lower() == 'it' else 'English'}.",
                    },
                    {"role": "user", "content": f"{query}\n\nContext (JSON): {json.dumps(ctx_payload, ensure_ascii=False)}\n\n{user_rules}"},
                ]
            else:
                ctx_payload = {
                    "language": lang,
                    "memory": {
                        "summary": (sess.summary if sess else ""),
                        "recent_turns": [{"role": t.role, "content": t.content} for t in (sess.turns[-6:] if sess else [])],
                    }
                }
                yield ctx({"query": query, **ctx_payload})
                msgs = [{"role": "system", "content": GENERAL_SYSTEM}]
                if lang in ("it", "en"):
                    msgs.append(
                        {
                            "role": "system",
                            "content": f"Answer in {'Italian' if lang == 'it' else 'English'}.",
                        }
                    )
                if sess:
                    for t in sess.turns[-6:]:
                        msgs.append({"role": t.role, "content": t.content})
                msgs.append({"role": "user", "content": query})

            try:
                for delta in self.llm.chat_stream(msgs, temperature=0.2, timeout=60.0):
                    answer_parts.append(delta)
                    yield _sse("answer_delta", {"delta": delta})
                yield step({"step": "llm_synthesis_done", "ok": True, "ms": _safe_ms(time.perf_counter() - t0)})
            except Exception as e:
                framework = "llm_error"
                answer_parts = ["Sorry—there was an LLM error. Please retry."]

        answer = _compact_markdown("".join(answer_parts)) if answer_parts else "LLM not configured."

        # Update memory with assistant response
        mem_stats_final = None
        if sess is not None:
            self.memory.append(sess, "assistant", answer)
            if is_crypto and symbol:
                sess.last_crypto_symbol = symbol
            mem_stats_final = self.memory.maybe_summarize(sess, self.llm)
            yield _sse("memory", {"session_id": session_id, **mem_stats_final})

        final = {
            "query": query,
            "session_id": session_id,
            "language": lang,
            "is_crypto": bool(is_crypto),
            "crypto_intent": bool(crypto_intent),
            "unresolved_asset": bool(unresolved_asset),
            "asset_query": asset_query,
            "symbol": symbol or ("GENERAL" if not is_crypto else "N/A"),
            "answer": answer,
            "token_profile": token_profile if is_crypto else None,
            "technicals": market if is_crypto else {},
            "news": news if is_crypto else {},
            "sources": sources if is_crypto else [],
            "geckoterminal_candidates": gecko_candidates,
            "memory": mem_stats_final if mem_stats_final is not None else mem_stats,
            "steps": steps + [{"step": "done", "ok": True, "ms_total": _safe_ms(time.perf_counter() - t0)}],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": {"framework": framework, "is_crypto": bool(is_crypto)},
        }
        yield _sse("final", final)


_MEMORY = MemoryStore.from_env()
_LLM = OpenAIChatLLM.from_env()
_ORCH = ResearchOrchestrator(memory=_MEMORY, llm=_LLM)


def stream_research_sse(query: str, *, session_id: Optional[str] = None, selection: Optional[Dict[str, Any]] = None) -> Iterable[str]:
    return _ORCH.stream(query=query, session_id=session_id, selection=selection)

