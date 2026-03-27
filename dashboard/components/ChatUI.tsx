"use client";
import { useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTED = [
  "지금 BTC 사도 돼?",
  "이번주 수익 어때?",
  "제일 많이 번 코인이 뭐야?",
  "내 포트폴리오 보여줘",
];

export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "안녕하세요! 포트폴리오나 매매에 대해 질문해보세요 🤖" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer ?? "오류가 발생했습니다." }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "서버 연결 오류입니다." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto space-y-3 py-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-800 text-gray-100 rounded-bl-sm"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-2 text-sm text-gray-400">
              분석 중...
            </div>
          </div>
        )}
      </div>

      {/* 추천 질문 */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 pb-3">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-xs bg-gray-800 text-gray-300 rounded-full px-3 py-1.5 hover:bg-gray-700 transition"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* 입력창 */}
      <div className="flex gap-2 pb-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="질문을 입력하세요..."
          className="flex-1 bg-gray-800 rounded-full px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => send(input)}
          disabled={loading}
          className="bg-blue-600 rounded-full w-10 h-10 flex items-center justify-center disabled:opacity-50"
        >
          ↑
        </button>
      </div>
    </div>
  );
}
