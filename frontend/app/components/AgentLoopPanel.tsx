import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";

type Trace = { phase: string; message: string };
type ToolLog = { tool: string; ok: boolean; ms: number; note?: string };
type Observation = { kind: string; summary: string };

export function AgentLoopPanel({
  open,
  onToggle,
  busy,
  stage,
  trace,
  tools,
  observations,
  context,
}: {
  open: boolean;
  onToggle: () => void;
  busy: boolean;
  stage: "idle" | "parsing" | "tools" | "synthesis";
  trace: Trace[];
  tools: ToolLog[];
  observations: Observation[];
  context: Record<string, unknown> | null;
}) {
  const [tab, setTab] = useState<"plan" | "tools" | "obs" | "context">("plan");
  const [showRaw, setShowRaw] = useState(false);

  const stages = useMemo(
    () =>
      [
        { id: "plan", label: "Plan" },
        { id: "tools", label: "Tools" },
        { id: "obs", label: "Observations" },
        { id: "context", label: "Context" },
      ] as const,
    []
  );

  const stageLabel =
    stage === "parsing"
      ? "Plan"
      : stage === "tools"
      ? "Tools"
      : stage === "synthesis"
      ? "Synthesis"
      : "Idle";

  const content = (() => {
    if (tab === "plan") {
      if (!trace.length) return <div className="mutedText">No plan yet.</div>;
      return (
        <div className="panelList">
          {trace.slice(-12).map((t, i) => (
            <div className="panelRow" key={i}>
              <div className="panelTag">{t.phase || "trace"}</div>
              <div className="panelText">{t.message}</div>
            </div>
          ))}
        </div>
      );
    }
    if (tab === "tools") {
      if (!tools.length)
        return <div className="mutedText">No tool calls yet.</div>;
      return (
        <div className="panelList">
          {tools.slice(-12).map((t, i) => (
            <div className="panelRow" key={i}>
              <div className="panelTag" data-ok={t.ok ? "true" : "false"}>
                {t.ok ? "ok" : "err"}
              </div>
              <div className="panelText">
                <div className="panelTitleLine">
                  <span className="mono">{t.tool}</span>
                  <span className="mutedText">{t.ms}ms</span>
                </div>
                {t.note ? <div className="panelNote">{t.note}</div> : null}
              </div>
            </div>
          ))}
        </div>
      );
    }
    if (tab === "obs") {
      if (!observations.length)
        return <div className="mutedText">No observations yet.</div>;
      return (
        <div className="panelList">
          {observations.slice(-12).map((o, i) => (
            <div className="panelRow" key={i}>
              <div className="panelTag">{o.kind}</div>
              <div className="panelText">{o.summary}</div>
            </div>
          ))}
        </div>
      );
    }
    // context
    if (!context) return <div className="mutedText">No context yet.</div>;
    const mem = (context as any)?.memory;
    const summary =
      mem && typeof mem.summary === "string" ? (mem.summary as string) : "";
    const recent = Array.isArray(mem?.recent_turns) ? mem.recent_turns : [];

    return (
      <div className="contextWrap">
        <div className="contextHeader">
          <div className="contextTitle">Context snapshot</div>
          <button
            type="button"
            className="miniBtn"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? "Hide raw" : "Show raw"}
          </button>
        </div>

        <div className="contextSection">
          <div className="contextSectionTitle">Memory summary</div>
          {summary ? (
            <pre className="contextSummary">{summary}</pre>
          ) : (
            <div className="mutedText">
              No summary yet (it appears after enough turns or when context
              grows).
            </div>
          )}
        </div>

        <div className="contextSection">
          <div className="contextSectionTitle">Recent turns</div>
          {recent.length ? (
            <div className="contextTurns">
              {recent.slice(-8).map((t: any, i: number) => (
                <div className="turnRow" key={i}>
                  <div className="turnRole">{String(t?.role ?? "")}</div>
                  <div className="turnText">{String(t?.content ?? "")}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mutedText">No recent turns yet.</div>
          )}
        </div>

        {showRaw ? (
          <div className="contextSection">
            <div className="contextSectionTitle">Raw JSON</div>
            <pre className="contextBox">{JSON.stringify(context, null, 2)}</pre>
          </div>
        ) : null}
      </div>
    );
  })();

  return (
    <div className="agentPanel">
      <div className="agentTop">
        <div>
          <div className="agentTitle">Agent loop</div>
          <div className="agentSub">
            Plan → tools → observations (no private chain-of-thought)
          </div>
        </div>
        <button className="miniBtn" type="button" onClick={onToggle}>
          {open ? "Collapse" : "Expand"}
        </button>
      </div>

      <div className="agentStatus">
        <span className="statusDot" data-busy={busy ? "true" : "false"} />
        {busy ? `Running: ${stageLabel}` : "Idle"}
      </div>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            className="agentBodyWrap"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            <div className="agentTabs">
              {stages.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="tabBtn"
                  data-active={tab === s.id ? "true" : "false"}
                  onClick={() => setTab(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>

            <div className="agentBody">{content}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
