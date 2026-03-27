import ChatUI from "@/components/ChatUI";

export default function ChatPage() {
  return (
    <div className="pt-8">
      <div className="mb-4">
        <p className="text-xs font-mono tracking-[0.2em] mb-0.5" style={{ color: "rgba(0,229,255,0.5)" }}>GROQ LLM</p>
        <h1 className="text-xl font-bold tracking-tight text-white">AI Assistant</h1>
      </div>
      <ChatUI />
    </div>
  );
}
