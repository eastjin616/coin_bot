import TradeTable from "@/components/TradeTable";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.API_KEY ?? "";

async function getAllTrades() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/trades`, {
      headers: { "X-API-Key": API_KEY },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function HistoryPage() {
  const trades = await getAllTrades();
  return (
    <div className="pt-8">
      <div className="flex items-end justify-between mb-5">
        <div>
          <p className="text-xs font-mono tracking-[0.2em] mb-0.5" style={{ color: "rgba(0,229,255,0.5)" }}>TRADE LOG</p>
          <h1 className="text-xl font-bold tracking-tight text-white">History</h1>
        </div>
        <span className="text-xs font-mono px-2.5 py-1 rounded-lg" style={{ background: "rgba(0,229,255,0.08)", color: "rgba(0,229,255,0.6)", border: "1px solid rgba(0,229,255,0.15)" }}>
          {trades.length} TRADES
        </span>
      </div>
      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(255,255,255,0.05)", background: "#0a0a0a" }}>
        <TradeTable trades={trades} />
      </div>
    </div>
  );
}
