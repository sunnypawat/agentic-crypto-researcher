from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import re
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
# CryptoPanic Developer API v2 base (per https://cryptopanic.com/developers/api/)
# Docs (as provided by user): base endpoint https://cryptopanic.com/api/developer/v2
CRYPTOPANIC_API_BASE = "https://cryptopanic.com/api/developer/v2"
GECKOTERMINAL_API_BASE = "https://api.geckoterminal.com/api/v2"


@dataclass(frozen=True)
class Source:
    name: str
    endpoint: str
    docs: str


COINGECKO_MARKET_CHART_SOURCE = Source(
    name="CoinGecko",
    endpoint="GET /coins/{id}/market_chart?vs_currency=usd&days=30",
    docs="https://docs.coingecko.com/reference/coins-id-market-chart",
)

COINGECKO_SEARCH_SOURCE = Source(
    name="CoinGecko",
    endpoint="GET /search?query={symbol}",
    docs="https://docs.coingecko.com/reference/search",
)

COINGECKO_COIN_SOURCE = Source(
    name="CoinGecko",
    endpoint="GET /coins/{id}",
    docs="https://docs.coingecko.com/reference/coins-id",
)

GECKOTERMINAL_SEARCH_POOLS_SOURCE = Source(
    name="GeckoTerminal",
    endpoint="GET /search/pools?query={query}&include=base_token,quote_token,dex",
    docs="https://api.geckoterminal.com/api-docs",
)

GECKOTERMINAL_POOL_SOURCE = Source(
    name="GeckoTerminal",
    endpoint="GET /networks/{network}/pools/{address}?include=base_token,quote_token,dex",
    docs="https://api.geckoterminal.com/api-docs",
)


_CACHE: Dict[Tuple[str, str], Tuple[float, Any]] = {}


class HttpGetError(RuntimeError):
    def __init__(
        self,
        *,
        url: str,
        status_code: int,
        body_snippet: str = "",
        retry_after_s: Optional[int] = None,
    ) -> None:
        self.url = url
        self.status_code = int(status_code)
        self.body_snippet = body_snippet
        self.retry_after_s = retry_after_s
        bits = [f"HTTP {self.status_code}", url]
        if retry_after_s is not None:
            bits.append(f"retry_after_s={retry_after_s}")
        if body_snippet:
            bits.append(f"body={body_snippet}")
        super().__init__(" · ".join(bits))


def _cache_get(key: Tuple[str, str]) -> Optional[Any]:
    ttl_seconds = int(os.getenv("TOOLS_CACHE_TTL_SECONDS", "60"))
    now = time.time()
    if key in _CACHE:
        expires_at, value = _CACHE[key]
        if now < expires_at:
            return value
        del _CACHE[key]
    return None


def _cache_set(key: Tuple[str, str], value: Any) -> None:
    ttl_seconds = int(os.getenv("TOOLS_CACHE_TTL_SECONDS", "60"))
    _CACHE[key] = (time.time() + ttl_seconds, value)


def _http_get_json(url: str, *, params: Dict[str, Any], timeout: float = 15.0) -> Any:
    # Light retry to tolerate transient 429/5xx in free tiers.
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            status = int(resp.status_code)
            if status >= 400:
                ra = resp.headers.get("retry-after")
                retry_after_s: Optional[int] = None
                try:
                    if ra is not None:
                        retry_after_s = int(float(str(ra).strip()))
                except Exception:
                    retry_after_s = None
                body = (resp.text or "").strip().replace("\n", " ")
                if len(body) > 220:
                    body = body[:220] + "…"
                err = HttpGetError(
                    url=url,
                    status_code=status,
                    body_snippet=body,
                    retry_after_s=retry_after_s,
                )

                # Retry only on rate limit / transient upstream errors.
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    last_err = err
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise err

            try:
                return resp.json()
            except Exception as e:  # pragma: no cover
                # Invalid JSON / decode error from upstream.
                body = (resp.text or "").strip().replace("\n", " ")
                if len(body) > 220:
                    body = body[:220] + "…"
                raise HttpGetError(url=url, status_code=status, body_snippet=body) from e
        except Exception as e:  # pragma: no cover
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"HTTP GET failed after retries: {url}") from last_err


def _symbol_to_coingecko_id(symbol: str) -> str:
    symbol = symbol.strip().lower()
    overrides = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "ada": "cardano",
        "xrp": "ripple",
        "doge": "dogecoin",
    }
    if symbol in overrides:
        return overrides[symbol]

    cache_key = ("coingecko_id", symbol)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _http_get_json(
        f"{COINGECKO_API_BASE}/search",
        params={"query": symbol},
    )
    coins = data.get("coins", []) if isinstance(data, dict) else []
    if not coins:
        raise ValueError(f"CoinGecko: could not resolve symbol '{symbol}' to a coin id.")

    # Prefer exact symbol match, then first result.
    exact = [c for c in coins if str(c.get("symbol", "")).lower() == symbol]
    picked = exact[0] if exact else coins[0]
    coin_id = picked.get("id")
    if not coin_id:
        raise ValueError(f"CoinGecko: search result missing id for symbol '{symbol}'.")

    _cache_set(cache_key, coin_id)
    return coin_id


def coingecko_search(query: str) -> List[Dict[str, Any]]:
    """
    Thin wrapper around CoinGecko /search, returning the `coins` array.
    Useful for semantic resolution from natural-language queries.
    """
    q = query.strip()
    if not q:
        return []
    data = _http_get_json(f"{COINGECKO_API_BASE}/search", params={"query": q})
    coins = data.get("coins", []) if isinstance(data, dict) else []
    out: List[Dict[str, Any]] = []
    for c in coins:
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "symbol": str(c.get("symbol", "")).upper() if c.get("symbol") else None,
                "market_cap_rank": c.get("market_cap_rank"),
            }
        )
    return out


def resolve_coingecko_id_from_query(query: str) -> Dict[str, Any]:
    """
    Resolve a CoinGecko coin id from a natural-language query (e.g. 'should i buy cardano?').
    Picks the best match by market cap rank (lower is better).
    """
    coins = coingecko_search(query)
    coins = [c for c in coins if c.get("id")]
    if not coins:
        raise ValueError(f"CoinGecko: no search results for query '{query}'.")

    def rank_key(c: Dict[str, Any]) -> tuple:
        r = c.get("market_cap_rank")
        # rank missing -> push down
        r_val = r if isinstance(r, int) else 10**9
        return (r_val,)

    best = sorted(coins, key=rank_key)[0]
    return best


def _compute_rsi_macd(close_prices: pd.Series) -> Dict[str, Any]:
    # RSI(14)
    delta = close_prices.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD(12,26,9)
    ema12 = close_prices.ewm(span=12, adjust=False).mean()
    ema26 = close_prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal

    macd_label = "bullish" if float(hist.iloc[-1]) >= 0 else "bearish"

    return {
        "rsi_14": float(rsi.iloc[-1]),
        "macd": {
            "line": float(macd_line.iloc[-1]),
            "signal": float(signal.iloc[-1]),
            "histogram": float(hist.iloc[-1]),
            "label": macd_label,
        },
    }


def get_market_data(coin_symbol: str) -> Dict[str, Any]:
    """
    Fetch the last 30 days of USD prices from CoinGecko and compute RSI/MACD locally.
    Returns a dict suitable for both deterministic and LLM-based synthesis.
    """
    symbol = coin_symbol.strip().lower()
    cache_key = ("market", symbol)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    coin_id = _symbol_to_coingecko_id(symbol)
    data = _http_get_json(
        f"{COINGECKO_API_BASE}/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": 30},
    )
    prices = data.get("prices", []) if isinstance(data, dict) else []
    if not prices or not isinstance(prices, list):
        raise RuntimeError(f"CoinGecko: unexpected market_chart response for '{coin_id}'.")

    df = pd.DataFrame(prices, columns=["timestamp_ms", "price_usd"])
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df = df.dropna().sort_values("timestamp")
    close = df["price_usd"].astype(float)

    indicators = _compute_rsi_macd(close)
    # Extra, actionable stats for synthesis/UI
    low_30d = float(close.min())
    high_30d = float(close.max())
    last = float(close.iloc[-1])
    pct_from_low = (last / low_30d - 1.0) if low_30d > 0 else None
    pct_from_high = (last / high_30d - 1.0) if high_30d > 0 else None

    # Daily volatility estimate from simple returns
    rets = close.pct_change().dropna()
    daily_std = float(rets.std()) if len(rets) else None
    ann_std = float(daily_std * np.sqrt(365)) if isinstance(daily_std, float) else None
    # Sparkline-friendly series (downsample to ~60 points max)
    series_df = df[["timestamp_ms", "price_usd"]].copy()
    if len(series_df) > 60:
        stride = max(1, len(series_df) // 60)
        series_df = series_df.iloc[::stride]
    price_series = [
        {"t": int(r["timestamp_ms"]), "p": float(r["price_usd"])}
        for _, r in series_df.iterrows()
    ]

    out: Dict[str, Any] = {
        "symbol": symbol.upper(),
        "coin_id": coin_id,
        "days": 30,
        "last_price_usd": last,
        "range_30d": {
            "low_usd": low_30d,
            "high_usd": high_30d,
            "pct_from_low": float(pct_from_low) if pct_from_low is not None else None,
            "pct_from_high": float(pct_from_high) if pct_from_high is not None else None,
        },
        "volatility_30d": {
            "daily_return_std": daily_std,
            "annualized_std": ann_std,
        },
        "price_series": price_series,
        "indicators": indicators,
        "sources": [
            {
                "name": COINGECKO_MARKET_CHART_SOURCE.name,
                "endpoint": COINGECKO_MARKET_CHART_SOURCE.endpoint,
                "docs": COINGECKO_MARKET_CHART_SOURCE.docs,
            },
            {
                "name": COINGECKO_SEARCH_SOURCE.name,
                "endpoint": COINGECKO_SEARCH_SOURCE.endpoint,
                "docs": COINGECKO_SEARCH_SOURCE.docs,
            },
        ],
    }
    _cache_set(cache_key, out)
    return out


def get_token_profile(coin_symbol: str) -> Dict[str, Any]:
    """
    Fetch minimal token profile info from CoinGecko, including an image URL.
    Uses the same symbol->CoinGecko ID resolution as market data.
    """
    symbol = coin_symbol.strip().lower()
    cache_key = ("token_profile", symbol)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    coin_id = _symbol_to_coingecko_id(symbol)
    data = _http_get_json(
        f"{COINGECKO_API_BASE}/coins/{coin_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
    )

    image = data.get("image", {}) if isinstance(data, dict) else {}
    out = {
        "symbol": symbol.upper(),
        "coin_id": coin_id,
        "name": data.get("name") if isinstance(data, dict) else None,
        "image_url": image.get("large") or image.get("small") or image.get("thumb"),
        "homepage": (data.get("links", {}).get("homepage", [None])[0] if isinstance(data, dict) else None),
        "coingecko_url": f"https://www.coingecko.com/en/coins/{coin_id}",
        "sources": [
            {
                "name": COINGECKO_COIN_SOURCE.name,
                "endpoint": COINGECKO_COIN_SOURCE.endpoint,
                "docs": COINGECKO_COIN_SOURCE.docs,
            },
            {
                "name": COINGECKO_SEARCH_SOURCE.name,
                "endpoint": COINGECKO_SEARCH_SOURCE.endpoint,
                "docs": COINGECKO_SEARCH_SOURCE.docs,
            },
        ],
    }
    _cache_set(cache_key, out)
    return out


CRYPTOPANIC_SOURCE = Source(
    name="CryptoPanic",
    endpoint="GET /api/developer/v2/posts/?auth_token={key}&currencies={SYMBOL}&public=true",
    docs="https://cryptopanic.com/developers/api/",
)


def get_latest_news(coin_symbol: str) -> Dict[str, Any]:
    """
    Fetch the latest CryptoPanic headlines for a coin symbol.
    Requires CRYPTOPANIC_API_KEY in environment.
    """
    symbol = coin_symbol.strip().upper()
    cache_key = ("news", symbol)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # Accept common env var names (people often call it auth_token)
    api_key = (os.getenv("CRYPTOPANIC_API_KEY", "") or os.getenv("CRYPTOPANIC_AUTH_TOKEN", "")).strip()
    if not api_key:
        raise RuntimeError("Missing CRYPTOPANIC_API_KEY (or CRYPTOPANIC_AUTH_TOKEN) in environment.")

    data = _http_get_json(
        f"{CRYPTOPANIC_API_BASE}/posts/",
        params={
            "auth_token": api_key,
            "currencies": symbol,
            # Per CryptoPanic docs: &public=true enables public usage mode (recommended for web apps).
            "public": os.getenv("CRYPTOPANIC_PUBLIC", "true"),
            # Reduce "media" noise; keep it configurable via env.
            "kind": os.getenv("CRYPTOPANIC_KIND", "news"),
        },
    )
    results = data.get("results", []) if isinstance(data, dict) else []
    items_all: List[Dict[str, Any]] = []

    def _domain_from_url(u: Optional[str]) -> Optional[str]:
        if not isinstance(u, str) or not u:
            return None
        try:
            host = urlparse(u).netloc
            if host.startswith("www."):
                host = host[4:]
            return host or None
        except Exception:
            return None

    def _estimate_sentiment(title: str, desc: str = "") -> str:
        """
        Heuristic sentiment for UI when CryptoPanic votes are unavailable.
        We keep it simple and transparent; caller should label as estimated.
        """
        t = f"{title} {desc}".lower()
        bullish_kw = (
            "surge",
            "rally",
            "breakout",
            "approval",
            "inflows",
            "record",
            "launch",
            "partnership",
            "adoption",
            "wins",
            "settlement",
        )
        bearish_kw = (
            "hack",
            "exploit",
            "ban",
            "lawsuit",
            "charges",
            "sell-off",
            "plunge",
            "crash",
            "liquidation",
            "downgrade",
            "outflows",
        )
        if any(k in t for k in bearish_kw):
            return "bearish"
        if any(k in t for k in bullish_kw):
            return "bullish"
        return "neutral"

    want_estimate = os.getenv("CRYPTOPANIC_ESTIMATE_SENTIMENT", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )

    for r in results[:20]:
        title = r.get("title")
        # Per CryptoPanic Developer API v2 schema:
        # - original_url: link to the original article
        # - url: link to the CryptoPanic-hosted post
        # - source: { domain, title, ... }
        original_url = r.get("original_url")
        cp_url = r.get("url")
        # Prefer original article, fall back to CryptoPanic post url.
        url = original_url or cp_url
        # Some plans/public mode may omit url fields in the list endpoint.
        # We can still construct a stable CryptoPanic post page URL from id + slug.
        if not url:
            pid = r.get("id")
            slug = r.get("slug")
            if pid and slug:
                try:
                    url = f"https://cryptopanic.com/news/{int(pid)}/{str(slug)}"
                except Exception:
                    url = None
        src = r.get("source", {}) if isinstance(r.get("source"), dict) else {}
        domain = src.get("domain") or _domain_from_url(url)
        published_at = r.get("published_at") or r.get("created_at")
        # CryptoPanic v2 fields vary by plan; votes may or may not include bullish/bearish.
        votes = r.get("votes", {}) if isinstance(r.get("votes"), dict) else {}
        bullish = votes.get("bullish")
        bearish = votes.get("bearish")
        sentiment: Optional[str] = None
        try:
            if bullish is not None or bearish is not None:
                b = int(bullish or 0)
                br = int(bearish or 0)
                sentiment = "bullish" if b >= br else "bearish"
        except Exception:
            sentiment = None

        # If we don't have votes, don't pretend it's neutral.
        if sentiment is None:
            sentiment = "unknown"

        if title:
            title_s = str(title)
            desc_s = str(r.get("description") or "")
            sentiment_source = "votes" if sentiment in ("bullish", "bearish") else "unknown"
            if sentiment == "unknown" and want_estimate:
                sentiment = _estimate_sentiment(title_s, desc_s)
                sentiment_source = "estimated"

            items_all.append(
                {
                    "title": title_s,
                    "url": url,
                    "domain": domain,
                    "published_at": published_at,
                    "sentiment": sentiment,
                    "sentiment_source": sentiment_source,
                }
            )

    # Return the newest 5, plus up to 2 extra "high-signal" items (bullish/bearish) if available.
    items: List[Dict[str, Any]] = []
    for it in items_all[:5]:
        items.append(it)
    for it in items_all[5:]:
        if len(items) >= 7:
            break
        if it.get("sentiment") in ("bullish", "bearish"):
            items.append(it)

    out = {
        "symbol": symbol,
        "items": items,
        "sources": [
            {
                "name": CRYPTOPANIC_SOURCE.name,
                "endpoint": CRYPTOPANIC_SOURCE.endpoint,
                "docs": CRYPTOPANIC_SOURCE.docs,
            }
        ],
    }
    _cache_set(cache_key, out)
    return out


def search_geckoterminal_pools(query: str, *, limit: int = 6) -> Dict[str, Any]:
    """
    Search GeckoTerminal pools for a query (useful for DEX-only tokens not on CoinGecko).
    Returns a compact list of candidate pools including base/quote tokens and liquidity.
    """
    q = query.strip()
    if not q:
        return {"query": query, "items": [], "sources": []}

    cache_key = ("geckoterminal_search", q.lower())
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _http_get_json(
        f"{GECKOTERMINAL_API_BASE}/search/pools",
        params={"query": q, "include": "base_token,quote_token,dex"},
    )
    included = data.get("included", []) if isinstance(data, dict) else []
    inc_map: Dict[str, Dict[str, Any]] = {}
    for inc in included:
        if not isinstance(inc, dict):
            continue
        t = inc.get("type")
        i = inc.get("id")
        if t and i:
            inc_map[f"{t}:{i}"] = inc

    import difflib

    ql = q.lower().strip()
    q_tokens = [t for t in re.split(r"[^a-z0-9]+", ql) if t]
    q_tokens = [t for t in q_tokens if t not in {"coin", "token", "crypto", "sol", "eth", "btc", "usdc", "usdt"}]

    def sim(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    items_scored: List[Tuple[float, Dict[str, Any]]] = []
    rows = data.get("data", []) if isinstance(data, dict) else []
    for r in rows[: max(1, min(int(limit), 20))]:
        if not isinstance(r, dict):
            continue
        pool_id = r.get("id")
        attrs = r.get("attributes", {}) if isinstance(r.get("attributes"), dict) else {}
        rel = r.get("relationships", {}) if isinstance(r.get("relationships"), dict) else {}

        dex_id = rel.get("dex", {}).get("data", {}).get("id") if isinstance(rel.get("dex"), dict) else None
        base_ref = rel.get("base_token", {}).get("data", {}) if isinstance(rel.get("base_token"), dict) else {}
        quote_ref = rel.get("quote_token", {}).get("data", {}) if isinstance(rel.get("quote_token"), dict) else {}

        base_inc = inc_map.get(f"token:{base_ref.get('id')}") if isinstance(base_ref, dict) else None
        quote_inc = inc_map.get(f"token:{quote_ref.get('id')}") if isinstance(quote_ref, dict) else None
        dex_inc = inc_map.get(f"dex:{dex_id}") if dex_id else None

        base_a = base_inc.get("attributes", {}) if isinstance(base_inc, dict) else {}
        quote_a = quote_inc.get("attributes", {}) if isinstance(quote_inc, dict) else {}
        dex_a = dex_inc.get("attributes", {}) if isinstance(dex_inc, dict) else {}

        # pool_id looks like "{network}_{address}" but network ids can contain underscores
        # e.g. "polygon_pos_0x..." -> network="polygon_pos", address="0x..."
        network = None
        address = None
        if isinstance(pool_id, str) and "_" in pool_id:
            parts = pool_id.split("_")
            if len(parts) >= 2:
                network = "_".join(parts[:-1])
                address = parts[-1]

        base_name = str(base_a.get("name") or "")
        base_sym = str(base_a.get("symbol") or "")
        pool_name = str(attrs.get("name") or "")
        joined = f"{pool_name} {base_name} {base_sym}".lower()

        liq_val = None
        try:
            if attrs.get("reserve_in_usd") is not None:
                liq_val = float(attrs.get("reserve_in_usd"))
        except Exception:
            liq_val = None

        # Score relevance: prefer query token matches in base token or pool name, then liquidity.
        token_hit = 0.0
        if q_tokens:
            token_hit = sum(1.0 for t in q_tokens if t in joined) / float(len(q_tokens))
        name_sim = sim(ql, joined[:80]) if ql else 0.0
        liq_score = 0.0
        if isinstance(liq_val, float) and liq_val > 0:
            # gentle preference, saturating around $50k
            liq_score = min(1.0, liq_val / 50000.0)

        score = token_hit * 0.65 + name_sim * 0.25 + liq_score * 0.10
        # Penalize obvious junk when query tokens exist but none hit
        if q_tokens and token_hit == 0.0:
            score -= 0.35

        item = (
            {
                "id": pool_id,
                "network": network,
                "address": address or attrs.get("address"),
                "name": attrs.get("name"),
                "dex": {"id": dex_id, "name": dex_a.get("name")},
                "liquidity_usd": liq_val,
                "base_token": {
                    "name": base_a.get("name"),
                    "symbol": base_a.get("symbol"),
                    "address": base_a.get("address"),
                    "image_url": base_a.get("image_url"),
                },
                "quote_token": {
                    "name": quote_a.get("name"),
                    "symbol": quote_a.get("symbol"),
                    "address": quote_a.get("address"),
                    "image_url": quote_a.get("image_url"),
                },
                "price_usd": float(attrs.get("base_token_price_usd")) if attrs.get("base_token_price_usd") is not None else None,
                "price_change_pct_h24": (attrs.get("price_change_percentage", {}) or {}).get("h24")
                if isinstance(attrs.get("price_change_percentage"), dict)
                else None,
                "pool_url": f"https://www.geckoterminal.com/{network}/pools/{address}" if network and address else None,
            }
        )
        items_scored.append((score, item))

    # Sort by score desc, then liquidity desc
    items_scored.sort(key=lambda x: (x[0], float(x[1].get("liquidity_usd") or 0.0)), reverse=True)
    items = [it for _, it in items_scored[: max(1, min(int(limit), 20))]]

    out = {
        "query": q,
        "items": items,
        "sources": [
            {
                "name": GECKOTERMINAL_SEARCH_POOLS_SOURCE.name,
                "endpoint": GECKOTERMINAL_SEARCH_POOLS_SOURCE.endpoint,
                "docs": GECKOTERMINAL_SEARCH_POOLS_SOURCE.docs,
            }
        ],
    }
    _cache_set(cache_key, out)
    return out


def get_geckoterminal_pool(pool_id: str) -> Dict[str, Any]:
    """
    Fetch a single GeckoTerminal pool by id '{network}_{address}'.
    """
    pid = pool_id.strip()
    if not pid or "_" not in pid:
        raise ValueError("Invalid GeckoTerminal pool id. Expected format '{network}_{address}'.")
    parts = pid.split("_")
    if len(parts) < 2:
        raise ValueError("Invalid GeckoTerminal pool id. Expected format '{network}_{address}'.")
    network = "_".join(parts[:-1])
    address = parts[-1]

    cache_key = ("geckoterminal_pool", pid)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _http_get_json(
        f"{GECKOTERMINAL_API_BASE}/networks/{network}/pools/{address}",
        params={"include": "base_token,quote_token,dex"},
    )
    included = data.get("included", []) if isinstance(data, dict) else []
    inc_map: Dict[str, Dict[str, Any]] = {}
    for inc in included:
        if not isinstance(inc, dict):
            continue
        t = inc.get("type")
        i = inc.get("id")
        if t and i:
            inc_map[f"{t}:{i}"] = inc

    row = data.get("data", {}) if isinstance(data, dict) else {}
    attrs = row.get("attributes", {}) if isinstance(row, dict) else {}
    rel = row.get("relationships", {}) if isinstance(row, dict) else {}
    dex_id = rel.get("dex", {}).get("data", {}).get("id") if isinstance(rel.get("dex"), dict) else None
    base_ref = rel.get("base_token", {}).get("data", {}) if isinstance(rel.get("base_token"), dict) else {}
    quote_ref = rel.get("quote_token", {}).get("data", {}) if isinstance(rel.get("quote_token"), dict) else {}

    base_inc = inc_map.get(f"token:{base_ref.get('id')}") if isinstance(base_ref, dict) else None
    quote_inc = inc_map.get(f"token:{quote_ref.get('id')}") if isinstance(quote_ref, dict) else None
    dex_inc = inc_map.get(f"dex:{dex_id}") if dex_id else None
    base_a = base_inc.get("attributes", {}) if isinstance(base_inc, dict) else {}
    quote_a = quote_inc.get("attributes", {}) if isinstance(quote_inc, dict) else {}
    dex_a = dex_inc.get("attributes", {}) if isinstance(dex_inc, dict) else {}

    out = {
        "id": pid,
        "network": network,
        "address": address,
        "name": attrs.get("name"),
        "dex": {"id": dex_id, "name": dex_a.get("name")},
        "liquidity_usd": float(attrs.get("reserve_in_usd")) if attrs.get("reserve_in_usd") is not None else None,
        "price_usd": float(attrs.get("base_token_price_usd")) if attrs.get("base_token_price_usd") is not None else None,
        "price_change_percentage": attrs.get("price_change_percentage"),
        "volume_usd": attrs.get("volume_usd"),
        "transactions": attrs.get("transactions"),
        "base_token": {
            "name": base_a.get("name"),
            "symbol": base_a.get("symbol"),
            "address": base_a.get("address"),
            "image_url": base_a.get("image_url"),
        },
        "quote_token": {
            "name": quote_a.get("name"),
            "symbol": quote_a.get("symbol"),
            "address": quote_a.get("address"),
            "image_url": quote_a.get("image_url"),
        },
        "pool_url": f"https://www.geckoterminal.com/{network}/pools/{address}",
        "sources": [
            {
                "name": GECKOTERMINAL_POOL_SOURCE.name,
                "endpoint": GECKOTERMINAL_POOL_SOURCE.endpoint,
                "docs": GECKOTERMINAL_POOL_SOURCE.docs,
            }
        ],
    }
    _cache_set(cache_key, out)
    return out


# Backwards-compat shim (old code used get_news)
def get_news(symbol: str) -> List[str]:
    news = get_latest_news(symbol)
    return [i["title"] for i in news.get("items", [])]
