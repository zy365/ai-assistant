import { useCallback, useRef, useState } from "react";

export interface ChartSpec {
  type: "line" | "bar" | "pie" | "table";
  title: string;
  x_field?: string;
  y_field?: string;
  name_field?: string;
  value_field?: string;
  columns?: Array<{ field: string; label: string }>;
  data: Record<string, unknown>[];
}

export interface MessagePart {
  type: "text" | "chart";
  content?: string;
  data?: ChartSpec;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  parts: MessagePart[];
  createdAt: Date;
}

export type StreamStatus = "idle" | "streaming" | "paused" | "error" | "select_customer";

export interface Customer {
  userId: string;
  userName: string;
  [key: string]: unknown;
}

export interface SelectCustomerEvent {
  customers: Customer[];
  message: string;
}

export function parseMessageParts(raw: string): MessagePart[] {
  const parts: MessagePart[] = [];
  const regex = /```chart\n([\s\S]*?)\n```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(raw)) !== null) {
    if (match.index > lastIndex)
      parts.push({ type: "text", content: raw.slice(lastIndex, match.index) });
    try {
      parts.push({ type: "chart", data: JSON.parse(match[1]) as ChartSpec });
    } catch {
      parts.push({ type: "text", content: match[0] });
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < raw.length)
    parts.push({ type: "text", content: raw.slice(lastIndex) });

  return parts.length ? parts : [{ type: "text", content: raw }];
}

interface UseSSEOptions {
  apiBase?: string;
  token: string;
}

export function useSSE({ apiBase = "", token }: UseSSEOptions) {
  const [messages, setMessages]           = useState<Message[]>([]);
  const [status, setStatus]               = useState<StreamStatus>("idle");
  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [customerCandidates, setCustomerCandidates] = useState<SelectCustomerEvent | null>(null);
  const abortRef  = useRef<AbortController | null>(null);
  const bufferRef = useRef<string>("");

  const sendMessage = useCallback(async (text: string) => {
    setStatus("streaming");
    bufferRef.current = "";

    const userMsg: Message = {
      id: crypto.randomUUID(), role: "user",
      parts: [{ type: "text", content: text }],
      createdAt: new Date(),
    };
    // 不提前插入空 AI 气泡，收到第一个 token 时再创建
    let assistantId: string | null = null;
    setMessages(prev => [...prev, userMsg]);

    abortRef.current = new AbortController();

    try {
      const resp = await fetch(`${apiBase}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        signal: abortRef.current.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader  = resp.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        for (const line of decoder.decode(value, { stream: true }).split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));

            if (evt.type === "text") {
              if (!assistantId) {
                assistantId = crypto.randomUUID();
                setMessages(prev => [...prev, {
                  id: assistantId!, role: "assistant", parts: [], createdAt: new Date(),
                }]);
              }
              bufferRef.current += evt.content ?? "";
              const parts = parseMessageParts(bufferRef.current);
              setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, parts } : m));
            }
            if (evt.type === "done") {
              if (evt.session_id) setSessionId(evt.session_id);
              setStatus("idle");
            }
            if (evt.type === "select_customer") {
              if (evt.session_id) setSessionId(evt.session_id);
              setCustomerCandidates({ customers: evt.customers, message: evt.message });
              setStatus("select_customer");
            }
            if (evt.type === "interrupt") setStatus("paused");
            if (evt.type === "error")     setStatus("error");
          } catch { /* 忽略非 JSON 行 */ }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        setStatus("paused");
      } else {
        setStatus("error");
      }
    }
  }, [apiBase, token, sessionId]);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setStatus("paused");
  }, []);

  const resumeWorkflow = useCallback(async (
    action: "continue" | "modify" | "cancel",
    newParams?: Record<string, unknown>,
  ) => {
    if (!sessionId) return;
    try {
      const resp = await fetch(`${apiBase}/api/chat/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ session_id: sessionId, action, new_params: newParams }),
      });
      const data = await resp.json();
      if (data.messages?.length) {
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(), role: "assistant",
          parts: parseMessageParts(data.messages.join("\n")),
          createdAt: new Date(),
        }]);
      }
    } catch { /* ignore */ }
    setStatus("idle");
  }, [apiBase, token, sessionId]);

  const startNewSession = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setStatus("idle");
    bufferRef.current = "";
  }, []);

  const selectCustomer = useCallback(async (customer: Customer) => {
    if (!sessionId) return;
    setCustomerCandidates(null);
    setStatus("streaming");
    bufferRef.current = "";

    // 不提前插入空气泡，收到第一个 token 时再创建
    let assistantId: string | null = null;

    try {
      const resp = await fetch(`${apiBase}/api/chat/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          session_id:         sessionId,
          action:             "select_customer",
          selected_user_id:   customer.userId,
          selected_user_name: customer.userName,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader  = resp.body!.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value, { stream: true }).split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "text") {
              if (!assistantId) {
                assistantId = crypto.randomUUID();
                setMessages(prev => [...prev, {
                  id: assistantId!, role: "assistant", parts: [], createdAt: new Date(),
                }]);
              }
              bufferRef.current += evt.content ?? "";
              const parts = parseMessageParts(bufferRef.current);
              setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, parts } : m));
            }
            if (evt.type === "done") setStatus("idle");
            if (evt.type === "error") setStatus("error");
          } catch {}
        }
      }
    } catch {
      setStatus("error");
    }
  }, [apiBase, token, sessionId]);

  const loadSession = useCallback(async (sid: string) => {
    setMessages([]);
    setStatus("idle");
    setCustomerCandidates(null);
    bufferRef.current = "";
    setSessionId(sid);
    try {
      const resp = await fetch(`${apiBase}/api/sessions/${sid}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        console.error("[loadSession] HTTP", resp.status, await resp.text());
        return;
      }
      const d = await resp.json();
      console.log("[loadSession] data:", d);
      const loaded: Message[] = (d.data ?? []).map((m: {
        id: string; role: string; content: string; created_at: string;
      }) => ({
        id:        m.id,
        role:      m.role as "user" | "assistant",
        parts:     parseMessageParts(m.content),
        createdAt: new Date(m.created_at),
      }));
      setMessages(loaded);
    } catch (e) {
      console.error("[loadSession] error:", e);
    }
  }, [apiBase, token]);

  return {
    messages, status, sessionId, customerCandidates,
    sendMessage, stopStream, resumeWorkflow, startNewSession, selectCustomer, loadSession,
  };
}
