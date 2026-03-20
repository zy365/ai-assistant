import React from "react";
import ChartMessage from "./ChartMessage";
import { Message } from "../hooks/useSSE";

interface Props { message: Message; isStreaming?: boolean; }

export default function MessageBubble({ message, isStreaming }: Props) {
  const isUser = message.role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 20, animation: "fadeUp 0.25s ease" }}>
      {!isUser && (
        <div style={{ flexShrink: 0, marginRight: 12, marginTop: 2 }}>
          <svg width="30" height="30" viewBox="0 0 30 30">
            <polygon points="15,2 27,9 27,21 15,28 3,21 3,9" fill="none" stroke="var(--accent)" strokeWidth="1"/>
            <polygon points="15,6 23,11 23,19 15,24 7,19 7,11" fill="rgba(0,212,255,0.1)"/>
            <text x="15" y="19" textAnchor="middle" fill="var(--accent)" fontSize="9" fontFamily="Space Mono" fontWeight="700">AI</text>
          </svg>
        </div>
      )}

      <div style={{
        maxWidth: "70%",
        padding: isUser ? "10px 16px" : "14px 16px",
        fontSize: 14, lineHeight: 1.7,
        fontFamily: isUser ? "'Syne', sans-serif" : "'Syne', sans-serif",
        background: isUser
          ? "linear-gradient(135deg, #0d2a4a 0%, #0a1f3a 100%)"
          : "var(--panel)",
        color: isUser ? "#c8dff0" : "var(--text)",
        borderRadius: isUser ? "12px 2px 12px 12px" : "2px 12px 12px 12px",
        border: isUser ? "1px solid var(--border)" : "1px solid var(--border2)",
        boxShadow: isUser
          ? "inset 0 1px 0 rgba(0,212,255,0.1)"
          : "0 2px 16px rgba(0,0,0,0.4)",
        whiteSpace: "pre-wrap", wordBreak: "break-word",
        position: "relative",
      }}>
        {/* user accent line */}
        {isUser && <div style={{ position:"absolute", top:0, right:0, width:"30%", height:1, background:"linear-gradient(90deg, transparent, var(--accent))", opacity:0.4 }} />}

        {message.parts.map((p, i) =>
          p.type === "chart" && p.data
            ? <ChartMessage key={i} data={p.data} />
            : <span key={i}>{p.content}</span>
        )}

        {isStreaming && (
          <span style={{
            display: "inline-block", width: 2, height: 16,
            background: "var(--accent)", marginLeft: 4,
            borderRadius: 1, verticalAlign: "text-bottom",
            animation: "blink 0.8s step-end infinite",
            boxShadow: "0 0 8px var(--accent)",
          }} />
        )}
      </div>

      {isUser && (
        <div style={{ flexShrink: 0, marginLeft: 12, marginTop: 2 }}>
          <div style={{
            width: 30, height: 30, borderRadius: "50%",
            background: "var(--panel)", border: "1px solid var(--border)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, color: "var(--text2)", fontFamily: "Space Mono",
          }}>
            USR
          </div>
        </div>
      )}
    </div>
  );
}
