"use client";

import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEffect, useMemo, useRef, useState } from "react";
import { Robot } from "./components/Robot";
import { Sparkline } from "./components/Sparkline";
import { AgentLoopPanel } from "./components/AgentLoopPanel";

type ResearchStep = Record<string, unknown> & {
  step?: string;
  ok?: boolean;
  ms?: number;
};

type ResearchResponse = {
  query: string;
  language?: string;
  is_crypto?: boolean;
  crypto_intent?: boolean;
  unresolved_asset?: boolean;
  asset_query?: string | null;
  symbol: string;
  answer: string;
  session_id?: string;
  memory?: Record<string, unknown> | null;
  geckoterminal_candidates?: Array<Record<string, unknown>>;
  token_profile?: Record<string, unknown>;
  technicals: Record<string, unknown>;
  news: { items?: Array<Record<string, unknown>> } & Record<string, unknown>;
  sources: Array<Record<string, unknown>>;
  steps?: ResearchStep[];
  generated_at: string;
  agent: Record<string, unknown>;
};

type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  report?: ResearchResponse;
  error?: { message: string; retryQuery: string };
};

type LiveToken = {
  symbol?: string;
  name?: string;
  image_url?: string;
  last_price_usd?: number;
  rsi_14?: number;
  macd_label?: string;
  price_series?: Array<{ t: number; p: number }>;
};

export default function Page() {
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "connected" | "disconnected"
  >("checking");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [activeSteps, setActiveSteps] = useState<ResearchStep[]>([]);
  const [stage, setStage] = useState<
    "idle" | "parsing" | "tools" | "synthesis"
  >("idle");
  const [trace, setTrace] = useState<Array<{ phase: string; message: string }>>(
    []
  );
  const [toolLog, setToolLog] = useState<
    Array<{ tool: string; ok: boolean; ms: number; note?: string }>
  >([]);
  const [observations, setObservations] = useState<
    Array<{ kind: string; summary: string }>
  >([]);
  const [context, setContext] = useState<Record<string, unknown> | null>(null);
  const [memoryStats, setMemoryStats] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [liveToken, setLiveToken] = useState<LiveToken | null>(null);
  const [poolChoice, setPoolChoice] = useState<Record<string, string>>({});
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const lastReport = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.report) return m.report;
    }
    return undefined;
  }, [messages]);

  const suggestions = useMemo(
    () => [
      "Should I buy ETH?",
      "Give me a quick report on BTC",
      "Summarize today's crypto market sentiment",
      "Explain RSI vs MACD in simple terms",
      "JUP coin performance? (DEX token example)",
    ],
    []
  );

  const formatUsd = (v: number) => {
    const abs = Math.abs(v);
    if (abs >= 1000) return `$${v.toFixed(0)}`;
    if (abs >= 10) return `$${v.toFixed(2)}`;
    if (abs >= 1) return `$${v.toFixed(3)}`;
    if (abs >= 0.01) return `$${v.toFixed(4)}`;
    if (abs === 0) return "$0";
    // tiny microcaps: show compact scientific-ish without being ugly
    return `$${v.toExponential(2)}`;
  };

  const formatWhen = (iso?: string, lang?: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    const isYesterday =
      d.getFullYear() === yesterday.getFullYear() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getDate() === yesterday.getDate();

    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const l = (lang || "").toLowerCase();
    const isIt = l === "it";
    const isEn = l === "en";
    const locale = isIt ? "it-IT" : isEn ? "en-US" : undefined;

    if (sameDay) return `${isIt ? "oggi" : "today"} ${hh}:${mm}`;
    if (isYesterday) return `${isIt ? "ieri" : "yesterday"} ${hh}:${mm}`;
    return `${d.toLocaleDateString(locale)} ${hh}:${mm}`;
  };

  useEffect(() => {
    const key = "acr_session_id";
    const existing = window.localStorage.getItem(key);
    const sid = existing || crypto.randomUUID();
    if (!existing) window.localStorage.setItem(key, sid);
    setSessionId(sid);

    const check = async () => {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        setBackendStatus(res.ok ? "connected" : "disconnected");
      } catch {
        setBackendStatus("disconnected");
      }
    };
    check();
    const id = setInterval(check, 7000);
    return () => clearInterval(id);
  }, []);

  const autoGrow = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "0px";
    const next = Math.min(el.scrollHeight, 140);
    el.style.height = `${next}px`;
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy]);

  const submit = async (queryOverride?: string, selection?: any) => {
    const q = (queryOverride ?? input).trim();
    if (!q || busy) return;

    const userMsg: ChatMsg = {
      id: crypto.randomUUID(),
      role: "user",
      content: q,
    };
    const assistantId = crypto.randomUUID();
    const placeholder: ChatMsg = {
      id: assistantId,
      role: "assistant",
      content: "",
    };

    setMessages((m) => [...m, userMsg, placeholder]);
    setInput("");
    setBusy(true);
    setStage("parsing");
    setActiveSteps([]);
    setActivityOpen(true);
    setTrace([]);
    setToolLog([]);
    setObservations([]);
    setContext(null);
    setMemoryStats(null);
    // Don't hard-reset liveToken here; we update it deterministically from SSE.
    // This avoids the header going blank while tools are still starting.
    // reset composer height
    requestAnimationFrame(() => autoGrow());

    try {
      // GPT/Gemini-like: stream steps + answer deltas via SSE
      const resp = await fetch("/api/research_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, session_id: sessionId, selection }),
      });
      if (!resp.ok || !resp.body) {
        const txt = await resp.text();
        throw new Error(`Backend error (${resp.status}): ${txt}`);
      }

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let answerSoFar = "";

      const applyDelta = (delta: string) => {
        answerSoFar += delta;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: answerSoFar } : m
          )
        );
      };

      const pushStep = (step: ResearchStep) => {
        setActiveSteps((s) => [...s, step]);
        const name = String(step.step ?? "");
        if ((step as any).symbol) {
          const sym = String((step as any).symbol ?? "").toUpperCase();
          if (sym) {
            setLiveToken((t) => {
              const prev = String(t?.symbol ?? "").toUpperCase();
              // If the symbol changes, wipe name/image/series to avoid showing the wrong token briefly.
              if (prev && prev !== sym) return { symbol: sym };
              return { ...(t ?? {}), symbol: sym };
            });
            // If we already attached a report shell, keep it in sync.
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                if (!m.report) return m;
                return { ...m, report: { ...(m.report as any), symbol: sym } };
              })
            );
          }
        }

        // As soon as we know it's a crypto query, attach a minimal report shell so the
        // report header/news section appears while the answer is streaming.
        if (
          name === "plan_done" &&
          String((step as any).intent ?? "") === "crypto"
        ) {
          const aq = String((step as any).asset_query ?? "").trim();
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;
              if (m.report) return m;
              const shell: ResearchResponse = {
                query: q,
                session_id: sessionId,
                language: String((step as any).language ?? "") || undefined,
                is_crypto: true,
                crypto_intent: true,
                unresolved_asset: false,
                asset_query: aq || undefined,
                symbol: aq ? aq.toUpperCase() : "",
                answer: "",
                token_profile: undefined,
                technicals: {},
                news: { items: [] },
                sources: [],
                steps: [],
                generated_at: new Date().toISOString(),
                agent: { framework: "stream_shell", is_crypto: true },
              };
              return { ...m, report: shell };
            })
          );
        }
        if (
          name.includes("received") ||
          name.includes("extract") ||
          name.includes("detect")
        ) {
          setStage("parsing");
        } else if (name.includes("fetch")) {
          setStage("tools");
        } else if (name.includes("llm_")) {
          setStage("synthesis");
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });

        let idx: number;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);

          let event = "message";
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          const dataStr = dataLines.join("\n");
          if (!dataStr) continue;

          let payload: any;
          try {
            payload = JSON.parse(dataStr);
          } catch {
            payload = { raw: dataStr };
          }

          if (event === "step") {
            pushStep(payload);
          } else if (event === "answer_delta") {
            const delta = String(payload.delta ?? "");
            if (delta) applyDelta(delta);
          } else if (event === "trace") {
            setTrace((t) => [
              ...t,
              {
                phase: String(payload.phase ?? ""),
                message: String(payload.message ?? ""),
              },
            ]);
          } else if (event === "tool") {
            setToolLog((l) => [
              ...l,
              {
                tool: String(payload.tool ?? ""),
                ok: payload.ok !== false,
                ms: Number(payload.ms ?? 0),
                note: payload.note ? String(payload.note) : undefined,
              },
            ]);
          } else if (event === "observation") {
            const kind = String(payload.kind ?? "");
            setObservations((o) => [
              ...o,
              { kind, summary: String(payload.summary ?? "") },
            ]);

            // Smooth header updates while streaming: use observation payload.data.
            const data = payload?.data;
            if (kind === "token_profile" && data && typeof data === "object") {
              setLiveToken((t) => ({
                ...(t ?? {}),
                symbol:
                  typeof (data as any).symbol === "string"
                    ? String((data as any).symbol).toUpperCase()
                    : t?.symbol,
                name:
                  typeof (data as any).name === "string"
                    ? (data as any).name
                    : t?.name,
                image_url:
                  typeof (data as any).image_url === "string"
                    ? (data as any).image_url
                    : t?.image_url,
              }));
            }
            if (kind === "technicals" && data && typeof data === "object") {
              setLiveToken((t) => ({
                ...(t ?? {}),
                symbol:
                  typeof (data as any).symbol === "string"
                    ? String((data as any).symbol).toUpperCase()
                    : t?.symbol,
                last_price_usd:
                  typeof (data as any).last_price_usd === "number"
                    ? (data as any).last_price_usd
                    : t?.last_price_usd,
                rsi_14:
                  typeof (data as any).rsi_14 === "number"
                    ? (data as any).rsi_14
                    : t?.rsi_14,
                macd_label:
                  typeof (data as any).macd_label === "string"
                    ? (data as any).macd_label
                    : t?.macd_label,
                price_series: Array.isArray((data as any).price_series)
                  ? ((data as any).price_series as any)
                  : t?.price_series,
              }));
            }
          } else if (event === "context") {
            setContext(payload);
          } else if (event === "memory") {
            setMemoryStats(payload);
          } else if (event === "final") {
            const report = payload as ResearchResponse;
            const steps = Array.isArray(report.steps) ? report.steps : [];
            setActiveSteps(steps);
            const isCrypto =
              report.is_crypto === true ||
              (report.agent as any)?.is_crypto === true;
            const hasDexCandidates =
              report.unresolved_asset === true &&
              Array.isArray(report.geckoterminal_candidates) &&
              report.geckoterminal_candidates.length > 0;
            const attachReport = isCrypto || hasDexCandidates;

            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                // General-mode: don't attach a crypto report object, so UI stays in "normal chat" format.
                if (!attachReport)
                  return { ...m, content: report.answer ?? answerSoFar };
                // Crypto-mode: attach report so we render token header + mini report cards.
                return { ...m, content: report.answer ?? answerSoFar, report };
              })
            );
            if (report.memory) setMemoryStats(report.memory);

            // Hydrate header from final report too (in case tool events arrived late).
            if (isCrypto) {
              const profile = (report.token_profile ?? {}) as any;
              const tech = (report.technicals ?? {}) as any;
              setLiveToken((t) => ({
                ...(t ?? {}),
                symbol: report.symbol,
                name:
                  typeof profile?.name === "string" ? profile.name : t?.name,
                image_url:
                  typeof profile?.image_url === "string"
                    ? profile.image_url
                    : t?.image_url,
                last_price_usd:
                  typeof tech?.last_price_usd === "number"
                    ? tech.last_price_usd
                    : t?.last_price_usd,
                rsi_14:
                  typeof tech?.indicators?.rsi_14 === "number"
                    ? tech.indicators.rsi_14
                    : t?.rsi_14,
                macd_label:
                  typeof tech?.indicators?.macd?.label === "string"
                    ? tech.indicators.macd.label
                    : t?.macd_label,
                price_series: Array.isArray(tech?.price_series)
                  ? tech.price_series
                  : t?.price_series,
              }));
            }
          }
        }
      }
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "",
                error: { message: `Error: ${String(e)}`, retryQuery: q },
              }
            : m
        )
      );
    } finally {
      setBusy(false);
      setStage("idle");
    }
  };

  return (
    <div className="bg">
      <div className="bgBlob blobA" />
      <div className="bgBlob blobB" />
      <div className="bgGrid" />

      <div className="container">
        <div className="topBar">
          <div className="brand">
            <div className="brandMark" aria-hidden />
            <div>
              <h1 className="title">Agentic Crypto Researcher</h1>
              <p className="subtitle">
                CoinGecko + CryptoPanic · RSI/MACD computed locally · FastAPI
              </p>
            </div>
          </div>

          <div className="statusPill" data-status={backendStatus}>
            <span className="dot" aria-hidden />
            {backendStatus === "checking"
              ? "Checking backend…"
              : backendStatus === "connected"
              ? "Backend connected"
              : "Backend disconnected"}
          </div>
          <div className="topActions">
            {/* Explore drawer removed: quick-start chips are shown in the empty chat state */}
            {/* <button
              type="button"
              className="miniBtn"
              onClick={() => setActivityOpen((v) => !v)}
            >
              {activityOpen ? "Hide agent" : "Show agent"}
            </button> */}
          </div>
        </div>

        <div className="layout">
          <aside className="leftPane">
            <div className="heroRow">
              <Robot
                mood={
                  busy
                    ? stage === "tools"
                      ? "tools"
                      : stage === "synthesis"
                      ? "speaking"
                      : "thinking"
                    : "idle"
                }
                message={
                  trace.length
                    ? trace[trace.length - 1].message
                    : busy
                    ? "Working on your request…"
                    : "Ask about a token (BTC/ETH/SOL) to see the full agent loop."
                }
              />

              <div
                className="memoryPill"
                title="Session memory (summary + recent turns)"
              >
                <span className="memoryDot" aria-hidden />
                <span
                  className="memoryRing"
                  style={
                    {
                      ["--p" as any]: (() => {
                        const used = Number(
                          (memoryStats as any)?.approx_chars ?? 0
                        );
                        const max = Number(
                          (memoryStats as any)?.max_chars ?? 9000
                        );
                        if (!used || !max) return 0;
                        return Math.max(0, Math.min(100, (used / max) * 100));
                      })(),
                    } as any
                  }
                  aria-hidden
                />
                {memoryStats ? (
                  <>
                    Context{" "}
                    <span className="mono">
                      {String((memoryStats as any).approx_chars ?? "—")}
                    </span>
                    {" chars · "}
                    <span className="mono">
                      {String((memoryStats as any).turns ?? "—")}
                    </span>{" "}
                    turns
                    {(memoryStats as any).was_summarized ? " · summarized" : ""}
                  </>
                ) : (
                  <>Context —</>
                )}
              </div>

              <AgentLoopPanel
                open={activityOpen}
                onToggle={() => setActivityOpen((v) => !v)}
                busy={busy}
                stage={stage}
                trace={trace}
                tools={toolLog}
                observations={observations}
                context={context}
              />
            </div>
          </aside>

          <main className="rightPane">
            <div className="tokenCard tokenCardHeader">
              {(() => {
                const rp = lastReport as any;
                const profile = (rp?.token_profile ?? {}) as any;
                const tech = (rp?.technicals ?? {}) as any;
                const websiteUrl =
                  typeof profile?.homepage === "string" &&
                  /^https?:\/\//i.test(profile.homepage)
                    ? (profile.homepage as string)
                    : null;
                const coingeckoUrl =
                  typeof profile?.coingecko_url === "string" &&
                  /^https?:\/\//i.test(profile.coingecko_url)
                    ? (profile.coingecko_url as string)
                    : typeof profile?.coin_id === "string"
                    ? (`https://www.coingecko.com/en/coins/${String(
                        profile.coin_id
                      )}` as string)
                    : null;
                const geckoTerminalUrl =
                  typeof profile?.geckoterminal_url === "string" &&
                  /^https?:\/\//i.test(profile.geckoterminal_url)
                    ? (profile.geckoterminal_url as string)
                    : typeof tech?.dex_pool?.pool_url === "string" &&
                      /^https?:\/\//i.test(tech.dex_pool.pool_url)
                    ? (tech.dex_pool.pool_url as string)
                    : null;

                const symbol =
                  (liveToken?.symbol ||
                    (typeof rp?.symbol === "string" ? rp.symbol : "")) ??
                  "";
                const name =
                  liveToken?.name ||
                  (typeof profile?.name === "string" ? profile.name : symbol) ||
                  symbol;
                const img =
                  liveToken?.image_url ||
                  (typeof profile?.image_url === "string"
                    ? profile.image_url
                    : null);

                const price =
                  typeof liveToken?.last_price_usd === "number"
                    ? liveToken.last_price_usd
                    : typeof tech?.last_price_usd === "number"
                    ? tech.last_price_usd
                    : undefined;

                const rsi =
                  typeof liveToken?.rsi_14 === "number"
                    ? liveToken.rsi_14
                    : typeof tech?.indicators?.rsi_14 === "number"
                    ? tech.indicators.rsi_14
                    : undefined;

                const macdLabel =
                  typeof liveToken?.macd_label === "string"
                    ? liveToken.macd_label
                    : typeof tech?.indicators?.macd?.label === "string"
                    ? tech.indicators.macd.label
                    : undefined;

                const series = (
                  Array.isArray(liveToken?.price_series)
                    ? liveToken?.price_series
                    : Array.isArray(tech?.price_series)
                    ? tech.price_series
                    : []
                ) as Array<{ t: number; p: number }>;

                if (!symbol || symbol === "GENERAL") return null;

                const headerKey = `${symbol}-${img ?? "noimg"}-${
                  typeof price === "number" ? price.toFixed(2) : "na"
                }-${typeof rsi === "number" ? rsi.toFixed(1) : "na"}-${
                  macdLabel ?? "na"
                }`;

                return (
                  <motion.div
                    key={headerKey}
                    className="tokenCardInner"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                  >
                    <div className="tokenTop">
                      <div className="tokenLeft">
                        <div className="coinWrap">
                          <motion.div
                            className="coinShadow"
                            animate={{
                              scaleX: [1, 0.9, 1],
                              opacity: [0.75, 0.55, 0.75],
                            }}
                            transition={{
                              duration: 3.6,
                              repeat: Infinity,
                              ease: "easeInOut",
                            }}
                          />
                          <motion.div
                            className="coinFloat"
                            animate={{ y: [0, -3, 0] }}
                            transition={{
                              duration: 3.6,
                              repeat: Infinity,
                              ease: "easeInOut",
                            }}
                          >
                            <motion.div
                              className="coin"
                              style={{ transformStyle: "preserve-3d" }}
                              animate={{
                                rotateY: 360,
                                rotateX: 12,
                              }}
                              transition={{
                                duration: 12,
                                repeat: Infinity,
                                ease: "linear",
                              }}
                            >
                              <div className="coinFace">
                                {img ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    className="coinImg"
                                    src={img}
                                    alt={`${name} logo`}
                                  />
                                ) : (
                                  <div className="coinFallback" />
                                )}
                              </div>
                            </motion.div>
                          </motion.div>
                        </div>
                        <div>
                          <div className="tokenName">{String(name)}</div>
                          <div className="tokenSym">
                            {symbol}
                            {websiteUrl ? (
                              <a
                                className="tokenExt"
                                href={websiteUrl}
                                target="_blank"
                                rel="noreferrer"
                                title="Website"
                              >
                                Website
                              </a>
                            ) : null}
                            {coingeckoUrl ? (
                              <a
                                className="tokenExt"
                                href={coingeckoUrl}
                                target="_blank"
                                rel="noreferrer"
                                title="CoinGecko"
                              >
                                CoinGecko
                              </a>
                            ) : null}
                            {geckoTerminalUrl ? (
                              <a
                                className="tokenExt"
                                href={geckoTerminalUrl}
                                target="_blank"
                                rel="noreferrer"
                                title="GeckoTerminal"
                              >
                                GeckoTerminal
                              </a>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      <div className="tokenRight">
                        <div className="tokenPrice">
                          {typeof price === "number" ? formatUsd(price) : "—"}
                        </div>
                        <div className="badges">
                          <span className="badge2">
                            RSI {typeof rsi === "number" ? rsi.toFixed(1) : "—"}
                          </span>
                          <span className="badge2">
                            MACD {String(macdLabel ?? "—")}
                          </span>
                        </div>
                        <div className="sparklineWrap">
                          {Array.isArray(series) && series.length > 2 ? (
                            <Sparkline
                              points={series}
                              width={260}
                              height={44}
                            />
                          ) : (
                            <div className="mutedText">
                              No price series yet.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })()}

              {!liveToken?.symbol &&
              messages.filter((m) => m.role === "assistant" && m.report)
                .length === 0 ? (
                <div className="tokenCardEmpty">
                  Ask about a token to populate the header.
                </div>
              ) : null}
            </div>

            <div className="chatShell">
              <div className="chatScroll">
                {messages.length === 0 ? (
                  <div className="welcome">
                    <div className="welcomeTop">
                      <div className="welcomeTitle">Start here</div>
                      <div className="welcomeSub">
                        Pick a prompt to generate a tool-backed report
                        (CoinGecko + CryptoPanic), or ask anything.
                      </div>
                    </div>
                    <div className="welcomeChips">
                      {suggestions.map((s) => (
                        <button
                          key={s}
                          className="chip"
                          type="button"
                          onClick={() => submit(s)}
                          disabled={busy}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                    <div className="welcomeFoot">
                      Tip: Try a DEX-only token name to see the GeckoTerminal
                      picker.
                    </div>
                  </div>
                ) : null}

                {messages.map((m) => (
                  <div key={m.id} className={`msg ${m.role}`}>
                    <div className="bubble">
                      {m.role === "assistant" && m.error ? (
                        <div className="report">
                          <div className="mutedText">{m.error.message}</div>
                          <div className="retryRow">
                            <button
                              type="button"
                              className="retryBtn"
                              onClick={() => submit(m.error!.retryQuery)}
                              disabled={busy}
                            >
                              Retry
                            </button>
                          </div>
                        </div>
                      ) : m.role === "assistant" && m.report ? (
                        <div className="report">
                          <div className="reportTop">
                            <div className="reportTitle">
                              Report · {m.report.symbol}
                            </div>
                            <div className="reportActions" />
                          </div>

                          <div className="md">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: (props) => (
                                  <a
                                    {...props}
                                    target="_blank"
                                    rel="noreferrer"
                                  />
                                ),
                                img: () => null,
                              }}
                            >
                              {m.content}
                            </ReactMarkdown>
                          </div>

                          {m.report.unresolved_asset &&
                          Array.isArray(m.report.geckoterminal_candidates) &&
                          m.report.geckoterminal_candidates.length > 0 ? (
                            <div className="dexPicker">
                              <div className="dexPickerTitle">
                                DEX pools found (tap one to analyze)
                              </div>
                              <div className="dexPills">
                                {m.report.geckoterminal_candidates
                                  .slice(0, 8)
                                  .map((c: any) => {
                                    const id = String(c?.id ?? "");
                                    const name = String(c?.name ?? id);
                                    const network = String(c?.network ?? "");
                                    const dex = String(c?.dex?.id ?? "");
                                    const liq =
                                      typeof c?.liquidity_usd === "number"
                                        ? `$${c.liquidity_usd.toFixed(0)}`
                                        : "—";
                                    const active = poolChoice[m.id] === id;
                                    const baseName = String(
                                      c?.base_token?.name ?? ""
                                    ).trim();
                                    const baseSym = String(
                                      c?.base_token?.symbol ?? ""
                                    ).trim();
                                    const pretty =
                                      baseName && baseSym
                                        ? `${baseName} (${baseSym})`
                                        : baseName || baseSym || name;
                                    return (
                                      <div key={id} className="dexPill">
                                        <button
                                          type="button"
                                          className="dexBtn"
                                          data-active={
                                            active ? "true" : "false"
                                          }
                                          onClick={() => {
                                            setPoolChoice((p) => ({
                                              ...p,
                                              [m.id]: id,
                                            }));
                                            submit(
                                              `Analyze DEX pool ${pretty}`,
                                              {
                                                kind: "geckoterminal_pool",
                                                id,
                                              }
                                            );
                                          }}
                                        >
                                          <span className="mono">{pretty}</span>
                                          <span className="mutedText">
                                            {network} · {dex} · liq {liq}
                                          </span>
                                        </button>
                                        {c?.pool_url ? (
                                          <a
                                            className="dexMiniLink"
                                            href={String(c.pool_url)}
                                            target="_blank"
                                            rel="noreferrer"
                                            title="Open in GeckoTerminal"
                                          >
                                            Open
                                          </a>
                                        ) : null}
                                      </div>
                                    );
                                  })}
                              </div>
                            </div>
                          ) : null}

                          <div className="newsLinks">
                            <div className="newsLinksTitle">News links</div>
                            <div className="newsLinksList">
                              {(() => {
                                const tech = (m.report?.technicals ??
                                  {}) as any;
                                if (tech?.error_kind !== "rate_limited")
                                  return null;
                                const ra =
                                  typeof tech?.retry_after_s === "number"
                                    ? Math.max(
                                        1,
                                        Math.floor(tech.retry_after_s)
                                      )
                                    : 30;
                                return (
                                  <div className="rateLimitBanner">
                                    <div>
                                      Rate limited by CoinGecko. Try again in ~
                                      {ra}s.
                                    </div>
                                    <button
                                      type="button"
                                      className="retryBtn"
                                      onClick={() => submit(m.report!.query)}
                                      disabled={busy}
                                      title="Resend the same prompt"
                                    >
                                      Retry
                                    </button>
                                  </div>
                                );
                              })()}
                              {Array.isArray(m.report.news?.items) &&
                              m.report.news.items.length > 0 ? (
                                m.report.news.items
                                  .slice(0, 5)
                                  .map((it, idx) => {
                                    const urlRaw = (it as any).url;
                                    const url =
                                      typeof urlRaw === "string" &&
                                      /^https?:\/\//i.test(urlRaw)
                                        ? urlRaw
                                        : null;
                                    const title = String(
                                      (it as any).title ?? ""
                                    );
                                    const domain = (it as any).domain
                                      ? String((it as any).domain)
                                      : null;
                                    const when = formatWhen(
                                      typeof (it as any).published_at ===
                                        "string"
                                        ? String((it as any).published_at)
                                        : "",
                                      (m.report as any)?.language
                                    );
                                    const sentiment = String(
                                      (it as any).sentiment ?? "unknown"
                                    );
                                    const sentimentSource = String(
                                      (it as any).sentiment_source ?? ""
                                    );
                                    return (
                                      <div className="newsLinkRow" key={idx}>
                                        <span
                                          className="badge"
                                          data-tone={sentiment}
                                          title={
                                            sentimentSource
                                              ? `${sentiment} (${sentimentSource})`
                                              : sentiment
                                          }
                                        >
                                          {sentiment}
                                        </span>
                                        {url ? (
                                          <a
                                            className="newsLinkBtn"
                                            href={url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                          >
                                            {title}
                                          </a>
                                        ) : (
                                          <span className="newsText">
                                            {title}
                                          </span>
                                        )}
                                        <span className="newsDomain">
                                          {domain ? domain : ""}
                                          {domain && when ? " · " : ""}
                                          {when ? when : ""}
                                        </span>
                                      </div>
                                    );
                                  })
                              ) : (
                                <div className="mutedText">
                                  {(() => {
                                    const err = String(
                                      (m.report as any)?.news?.error ?? ""
                                    );
                                    if (
                                      err.toLowerCase().includes("missing") &&
                                      err.toLowerCase().includes("cryptopanic")
                                    ) {
                                      return "News disabled (missing API key).";
                                    }
                                    if (err)
                                      return "News unavailable right now.";
                                    return "No recent news found.";
                                  })()}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="md">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: (props) => (
                                <a
                                  {...props}
                                  target="_blank"
                                  rel="noreferrer"
                                />
                              ),
                            }}
                          >
                            {m.content}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {busy ? (
                  <div className="msg assistant">
                    <div className="bubble typing">
                      <span className="typingDot" />
                      <span className="typingDot" />
                      <span className="typingDot" />
                      <span className="typingLabel">
                        {stage === "parsing"
                          ? "Parsing"
                          : stage === "tools"
                          ? "Running tools"
                          : stage === "synthesis"
                          ? "Synthesizing"
                          : "Working"}
                      </span>
                    </div>
                  </div>
                ) : null}

                <div ref={bottomRef} />
              </div>

              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <motion.textarea
                  className="input"
                  ref={inputRef}
                  value={input}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => (
                    setInput(e.target.value),
                    requestAnimationFrame(() => autoGrow())
                  )}
                  placeholder="Ask about BTC, ETH, SOL… or anything else"
                  rows={1}
                  whileFocus={{ scale: 1.01 }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submit();
                    }
                  }}
                />
                <motion.button
                  className="sendBtn"
                  type="submit"
                  disabled={busy}
                  whileHover={{ y: -1 }}
                  whileTap={{ scale: 0.98 }}
                >
                  {busy ? (
                    "Thinking…"
                  ) : (
                    <span className="sendInner">
                      Send
                      <span className="sendIcon" aria-hidden>
                        ↑
                      </span>
                    </span>
                  )}
                </motion.button>
              </form>
              <div className="hint">
                Press <span className="kbd">Enter</span> to send ·{" "}
                <span className="kbd">Shift</span>+
                <span className="kbd">Enter</span> for newline
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* Explore drawer removed */}
    </div>
  );
}
