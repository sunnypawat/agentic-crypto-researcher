"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

export default function LoginPage() {
  const sp = useSearchParams();
  const next = useMemo(() => sp.get("next") || "/", [sp]);
  const [token, setToken] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, next }),
      });
      if (!res.ok) throw new Error(await res.text());
      const out = await res.json();
      window.location.href = out.next || "/";
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div style={{ width: "min(520px, 92vw)" }}>
        <div style={{ fontSize: 12, opacity: 0.7, letterSpacing: 0.6 }}>
          Login
        </div>
        <h1 style={{ margin: "8px 0 10px", fontSize: 28 }}>
          Agentic Crypto Researcher
        </h1>
        <p style={{ margin: "0 0 14px", opacity: 0.8 }}>
          Enter the shared access token to continue.
        </p>

        <div style={{ display: "flex", gap: 10 }}>
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Access token"
            type="password"
            autoComplete="current-password"
            style={{
              flex: 1,
              padding: "12px 12px",
              borderRadius: 14,
              border: "1px solid rgba(255,255,255,0.14)",
              background: "rgba(10,14,26,0.55)",
              color: "inherit",
              outline: "none",
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy || !token.trim()}
            style={{
              padding: "12px 14px",
              borderRadius: 14,
              border: "1px solid rgba(255,255,255,0.18)",
              background:
                "linear-gradient(135deg, rgba(124,58,237,0.35), rgba(34,197,94,0.22))",
              color: "inherit",
              cursor: "pointer",
              minWidth: 96,
              opacity: busy ? 0.7 : 1,
            }}
          >
            {busy ? "…" : "Enter"}
          </button>
        </div>

        {err ? (
          <div style={{ marginTop: 10, fontSize: 13, opacity: 0.8 }}>{err}</div>
        ) : null}

        <div style={{ marginTop: 12, fontSize: 12, opacity: 0.65 }}>
          Next: <code>{next}</code>
        </div>
      </div>
    </main>
  );
}
