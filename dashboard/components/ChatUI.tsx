"use client";
import { useState, useRef, useEffect } from "react";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
}

const SUGGESTED = ["BTC 지금 사도 돼?", "수익 어때?", "포트폴리오 보여줘", "최근 매매 알려줘"];

let nextId = 1;

export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([
    { id: nextId++, role: "assistant", content: "포트폴리오나 매매에 대해 물어보세요." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    setMessages((prev) => [...prev, { id: nextId++, role: "user", content: text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      const content = res.ok ? (data.answer ?? "응답을 받지 못했습니다.") : "오류가 발생했습니다.";
      setMessages((prev) => [...prev, { id: nextId++, role: "assistant", content }]);
    } catch {
      setMessages((prev) => [...prev, { id: nextId++, role: "assistant", content: "서버 연결 오류입니다." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-9rem)]">
      <div className="flex-1 overflow-y-auto space-y-3 py-2">
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            {m.role === "assistant" && (
              <div className="w-6 h-6 rounded-md mr-2 mt-0.5 flex-shrink-0 flex items-center justify-center text-[10px] font-bold"
                style={{ background: "rgba(0,229,255,0.1)", color: "#00e5ff", border: "1px solid rgba(0,229,255,0.2)" }}>
                AI
              </div>
            )}
            <div className="max-w-[80%] text-sm whitespace-pre-wrap leading-relaxed"
              style={m.role === "user"
                ? { background: "rgba(0,229,255,0.1)", color: "#e0e0e0", border: "1px solid rgba(0,229,255,0.2)", borderRadius: "16px 16px 4px 16px", padding: "10px 14px" }
                : { background: "#111", color: "#ccc", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "4px 16px 16px 16px", padding: "10px 14px" }}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="w-6 h-6 rounded-md mr-2 flex-shrink-0 flex items-center justify-center text-[10px] font-bold"
              style={{ background: "rgba(0,229,255,0.1)", color: "#00e5ff", border: "1px solid rgba(0,229,255,0.2)" }}>
              AI
            </div>
            <div className="flex items-center gap-1 px-4 py-3 rounded-2xl" style={{ background: "#111", border: "1px solid rgba(255,255,255,0.06)" }}>
              {[0,1,2].map(i => (
                <span key={i} className="w-1 h-1 rounded-full animate-bounce" style={{ background: "#00e5ff", animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 py-3">
          {SUGGESTED.map((q) => (
            <button key={q} onClick={() => send(q)} disabled={loading}
              className="text-xs px-3 py-1.5 rounded-full transition-all disabled:opacity-40"
              style={{ background: "rgba(0,229,255,0.05)", color: "rgba(0,229,255,0.7)", border: "1px solid rgba(0,229,255,0.15)" }}>
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="flex gap-2 pt-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) send(input); }}
          placeholder="질문 입력..."
          className="flex-1 text-sm outline-none px-4 py-3 rounded-xl"
          style={{ background: "#111", border: "1px solid rgba(255,255,255,0.08)", color: "#e0e0e0" }}
        />
        <button onClick={() => send(input)} disabled={loading}
          className="w-11 h-11 rounded-xl flex items-center justify-center transition-all disabled:opacity-40"
          style={{ background: "rgba(0,229,255,0.1)", border: "1px solid rgba(0,229,255,0.2)", color: "#00e5ff" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
          </svg>
        </button>
      </div>
    </div>
  );
}
