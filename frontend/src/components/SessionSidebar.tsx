import React, { useCallback, useEffect, useState } from "react";

interface Session { id: string; title: string; updated_at: string; }
interface Props {
  token: string; apiBase?: string;
  currentSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
}

const SessionSidebar: React.FC<Props> = ({ token, apiBase = "", currentSessionId, onSelectSession, onNewSession }) => {
  const [sessions, setSessions] = useState<Session[]>([]);

  const fetchSessions = useCallback(async () => {
    try {
      const r = await fetch(`${apiBase}/api/sessions`, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) return;
      const d = await r.json();
      // 后端返回 {data: [...]}，每条记录字段：id, title, operator_id, updated_at
      setSessions(d.data ?? []);
    } catch {}
  }, [apiBase, token]);

  // token 变化或会话切换时重新拉取列表
  useEffect(() => { fetchSessions(); }, [fetchSessions, currentSessionId]);

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });

  return (
    <aside style={{
      width: 240, background: "var(--bg2)",
      borderRight: "1px solid var(--border2)",
      display: "flex", flexDirection: "column", height: "100vh",
      flexShrink: 0, position: "relative", overflow: "hidden",
    }}>
      {/* grid overlay */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        backgroundImage: "linear-gradient(var(--border2) 1px, transparent 1px), linear-gradient(90deg, var(--border2) 1px, transparent 1px)",
        backgroundSize: "40px 40px", opacity: 0.3,
      }} />

      {/* logo */}
      <div style={{ padding: "24px 20px 16px", position: "relative" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          {/* hex icon */}
          <svg width="28" height="28" viewBox="0 0 28 28">
            <polygon points="14,2 25,8 25,20 14,26 3,20 3,8" fill="none" stroke="var(--accent)" strokeWidth="1.5"/>
            <polygon points="14,6 21,10 21,18 14,22 7,18 7,10" fill="var(--accent)" opacity="0.15"/>
            <text x="14" y="18" textAnchor="middle" fill="var(--accent)" fontSize="10" fontFamily="Space Mono" fontWeight="700">AI</text>
          </svg>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, letterSpacing: "0.12em", color: "#fff", textTransform: "uppercase" }}>Enterprise</div>
            <div style={{ fontSize: 9, color: "var(--accent)", letterSpacing: "0.2em", fontFamily: "Space Mono" }}>ASSISTANT v1.0</div>
          </div>
        </div>
        <div style={{ height: 1, background: "linear-gradient(90deg, var(--accent) 0%, transparent 100%)", opacity: 0.4, marginTop: 12 }} />
      </div>

      {/* new chat btn */}
      <div style={{ padding: "0 16px 16px", position: "relative" }}>
        <button onClick={onNewSession} style={{
          width: "100%", padding: "10px 0",
          background: "transparent",
          border: "1px solid var(--accent)",
          color: "var(--accent)",
          borderRadius: 4, cursor: "pointer",
          fontSize: 11, fontWeight: 700, letterSpacing: "0.15em",
          fontFamily: "Space Mono", textTransform: "uppercase",
          transition: "all 0.2s",
          position: "relative", overflow: "hidden",
        }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--glow)";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 0 16px var(--glow)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = "transparent";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
          }}
        >
          ＋ NEW SESSION
        </button>
      </div>

      {/* label */}
      <div style={{ padding: "0 20px 8px", fontSize: 9, color: "var(--text3)", letterSpacing: "0.2em", fontFamily: "Space Mono" }}>
        RECENT SESSIONS
      </div>

      {/* session list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 8px" }}>
        {sessions.length === 0 && (
          <div style={{ padding: "16px 12px", fontSize: 11, color: "var(--text3)", fontFamily: "Space Mono" }}>
            // no sessions yet
          </div>
        )}
        {sessions.map(s => (
          <div key={s.id} onClick={() => onSelectSession(s.id)} style={{
            padding: "10px 12px", cursor: "pointer", borderRadius: 4,
            marginBottom: 2, border: "1px solid transparent",
            background: s.id === currentSessionId ? "var(--panel)" : "transparent",
            borderColor: s.id === currentSessionId ? "var(--border)" : "transparent",
            transition: "all 0.15s",
          }}
            onMouseEnter={e => { if (s.id !== currentSessionId) (e.currentTarget as HTMLDivElement).style.background = "rgba(0,212,255,0.04)"; }}
            onMouseLeave={e => { if (s.id !== currentSessionId) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
          >
            {s.id === currentSessionId && (
              <div style={{ width: 2, height: "100%", background: "var(--accent)", position: "absolute", left: 8, top: 0, borderRadius: 1 }} />
            )}
            <div style={{ fontSize: 12, color: s.id === currentSessionId ? "#fff" : "var(--text2)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {s.title || "New Session"}
            </div>
            <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 3, fontFamily: "Space Mono" }}>
              {formatDate(s.updated_at)}
            </div>
          </div>
        ))}
      </div>

      {/* status bar */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border2)", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent3)", boxShadow: "0 0 8px var(--accent3)", animation: "pulse 2s infinite" }} />
        <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Space Mono", letterSpacing: "0.1em" }}>SYSTEM ONLINE</span>
      </div>
    </aside>
  );
};

export default SessionSidebar;
