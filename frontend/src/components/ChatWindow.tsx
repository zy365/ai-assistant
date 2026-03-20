import React, { useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble";
import SessionSidebar from "./SessionSidebar";
import { useSSE } from "../hooks/useSSE";

const token = localStorage.getItem("ai_token") ?? "";

export default function ChatWindow() {
  const [input, setInput]     = useState("");
  const [authToken, setAuthToken] = useState(token);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { messages, status, sessionId, sendMessage, stopStream, resumeWorkflow, startNewSession, customerCandidates, selectCustomer, loadSession } =
    useSSE({ apiBase: "", token: authToken });

  useEffect(() => { localStorage.setItem("ai_token", authToken); }, [authToken]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || status === "streaming") return;
    setInput("");
    sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleSelectSession = async (sid: string) => {
    await loadSession(sid);
  };

  const statusColor = status === "streaming" ? "var(--accent)" : status === "error" ? "var(--danger)" : status === "paused" ? "var(--warn)" : "var(--accent3)";
  const statusLabel = status === "streaming" ? "PROCESSING" : status === "error" ? "ERROR" : status === "paused" ? "PAUSED" : "READY";

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <SessionSidebar token={authToken} apiBase="" currentSessionId={sessionId}
        onSelectSession={handleSelectSession} onNewSession={startNewSession} />

      {/* main panel */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--bg)", position: "relative", minWidth: 0 }}>

        {/* scanline effect */}
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none", zIndex: 0,
          background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)",
        }} />

        {/* top bar */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 24px", height: 48, flexShrink: 0,
          borderBottom: "1px solid var(--border2)",
          background: "var(--bg2)", position: "relative", zIndex: 1,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Space Mono", letterSpacing: "0.15em" }}>
              TERMINAL / CHAT
            </span>
            {sessionId && (
              <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Space Mono" }}>
                SESSION:{sessionId.slice(0, 8)}
              </span>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* status indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor, boxShadow: `0 0 8px ${statusColor}`, animation: status === "streaming" ? "pulse 1s infinite" : "none" }} />
              <span style={{ fontSize: 10, color: statusColor, fontFamily: "Space Mono", letterSpacing: "0.1em" }}>{statusLabel}</span>
            </div>

            {/* token input */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "Space Mono" }}>TOKEN:</span>
              <input value={authToken} onChange={e => setAuthToken(e.target.value)}
                placeholder="(dev mode: leave empty)"
                style={{
                  background: "var(--bg3)", border: "1px solid var(--border2)",
                  color: "var(--text2)", padding: "4px 10px", borderRadius: 3,
                  fontSize: 11, width: 200, outline: "none", fontFamily: "Space Mono",
                }}
              />
            </div>
          </div>
        </div>

        {/* messages */}
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px", position: "relative", zIndex: 1 }}>
          {messages.length === 0 && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 20, opacity: 0.6 }}>
              {/* big hex */}
              <svg width="80" height="80" viewBox="0 0 80 80">
                <polygon points="40,5 71,22.5 71,57.5 40,75 9,57.5 9,22.5" fill="none" stroke="var(--accent)" strokeWidth="1" opacity="0.5"/>
                <polygon points="40,15 63,27.5 63,52.5 40,65 17,52.5 17,27.5" fill="rgba(0,212,255,0.05)" stroke="var(--accent)" strokeWidth="0.5" opacity="0.5"/>
                <text x="40" y="46" textAnchor="middle" fill="var(--accent)" fontSize="16" fontFamily="Space Mono" fontWeight="700" opacity="0.8">AI</text>
              </svg>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 13, color: "var(--text2)", fontFamily: "Space Mono", letterSpacing: "0.1em", marginBottom: 8 }}>ENTERPRISE ASSISTANT READY</div>
                <div style={{ fontSize: 11, color: "var(--text3)", fontFamily: "Space Mono" }}>// enter query to begin session</div>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={msg.id} message={msg}
              isStreaming={status === "streaming" && i === messages.length - 1 && msg.role === "assistant"} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* 多客户选择栏 */}
        {status === "select_customer" && customerCandidates && (
          <div style={{
            padding: "12px 28px", background: "rgba(0,212,255,0.04)",
            borderTop: "1px solid rgba(0,212,255,0.3)",
            flexShrink: 0, zIndex: 1,
          }}>
            <div style={{ fontSize: 11, color: "var(--accent)", fontFamily: "Space Mono", letterSpacing: "0.1em", marginBottom: 10 }}>
              ⚡ {customerCandidates.message}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {customerCandidates.customers.map((c: import("../hooks/useSSE").Customer) => (
                <button key={c.userId} onClick={() => selectCustomer(c)} style={{
                  padding: "7px 16px", background: "transparent",
                  border: "1px solid var(--accent)", color: "var(--accent)",
                  borderRadius: 4, cursor: "pointer", fontSize: 12,
                  fontFamily: "Space Mono", transition: "all 0.15s",
                }}
                  onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--glow)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                >
                  {c.userName}
                  {c.userId && <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.6 }}>#{c.userId}</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* pause bar */}
        {status === "paused" && (
          <div style={{
            padding: "12px 28px", background: "rgba(255,170,0,0.06)",
            borderTop: "1px solid rgba(255,170,0,0.3)",
            display: "flex", gap: 10, alignItems: "center", zIndex: 1, flexShrink: 0,
          }}>
            <span style={{ fontSize: 11, color: "var(--warn)", fontFamily: "Space Mono", letterSpacing: "0.1em" }}>⚠ WORKFLOW PAUSED — SELECT ACTION:</span>
            <button onClick={() => resumeWorkflow("continue")} style={resumeBtnStyle("#00d4ff")}>CONTINUE ▶</button>
            <button onClick={() => resumeWorkflow("cancel")}   style={resumeBtnStyle("#ff3b5c")}>CANCEL ✕</button>
          </div>
        )}

        {/* input area */}
        <div style={{
          padding: "16px 28px 20px", borderTop: "1px solid var(--border2)",
          background: "var(--bg2)", position: "relative", zIndex: 1, flexShrink: 0,
        }}>
          {/* top accent line */}
          <div style={{ position: "absolute", top: 0, left: 28, right: 28, height: 1, background: "linear-gradient(90deg, transparent, var(--accent), transparent)", opacity: 0.2 }} />

          <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <div style={{ flex: 1, position: "relative" }}>
              <div style={{ position: "absolute", left: 14, top: 14, fontSize: 11, color: "var(--accent)", fontFamily: "Space Mono", opacity: 0.6, pointerEvents: "none" }}>❯</div>
              <textarea
                ref={textareaRef}
                value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder="enter query..."
                rows={2}
                style={{
                  width: "100%", padding: "12px 14px 12px 30px",
                  background: "var(--bg3)", border: "1px solid var(--border)",
                  color: "var(--text)", borderRadius: 4, resize: "none",
                  fontSize: 13, outline: "none", fontFamily: "Space Mono",
                  lineHeight: 1.6, caretColor: "var(--accent)",
                  transition: "border-color 0.2s, box-shadow 0.2s",
                }}
                onFocus={e => { e.target.style.borderColor = "var(--accent)"; e.target.style.boxShadow = "0 0 0 1px rgba(0,212,255,0.2), inset 0 0 20px rgba(0,212,255,0.03)"; }}
                onBlur={e =>  { e.target.style.borderColor = "var(--border)";  e.target.style.boxShadow = "none"; }}
              />
            </div>

            {status === "streaming"
              ? <button onClick={stopStream} style={sendBtnStyle("var(--danger)")}>■ STOP</button>
              : <button onClick={handleSend} disabled={!input.trim()} style={sendBtnStyle(input.trim() ? "var(--accent)" : "var(--text3)")}>SEND ▶</button>
            }
          </div>

          <div style={{ marginTop: 8, fontSize: 10, color: "var(--text3)", fontFamily: "Space Mono", letterSpacing: "0.08em" }}>
            ENTER to send · SHIFT+ENTER for newline
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fadeUp  { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes pulse   { 0%,100%{opacity:0.5} 50%{opacity:1} }
        @keyframes blink   { 0%,100%{opacity:1} 50%{opacity:0} }
      `}</style>
    </div>
  );
}

const resumeBtnStyle = (color: string): React.CSSProperties => ({
  padding: "6px 16px", background: "transparent", border: `1px solid ${color}`,
  color, borderRadius: 3, cursor: "pointer", fontSize: 10,
  fontFamily: "Space Mono", letterSpacing: "0.1em", fontWeight: 700,
  transition: "all 0.15s",
});

const sendBtnStyle = (color: string): React.CSSProperties => ({
  padding: "12px 22px", background: "transparent",
  border: `1px solid ${color}`, color,
  borderRadius: 4, cursor: color === "var(--text3)" ? "not-allowed" : "pointer",
  fontSize: 11, fontFamily: "Space Mono", fontWeight: 700,
  letterSpacing: "0.12em", whiteSpace: "nowrap",
  transition: "all 0.2s", flexShrink: 0,
  boxShadow: color !== "var(--text3)" ? `0 0 12px rgba(0,212,255,0.1)` : "none",
});
