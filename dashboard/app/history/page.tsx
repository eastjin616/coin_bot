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
    <div className="pt-6">
      <h1 className="text-lg font-bold mb-4">매매 히스토리</h1>
      <p className="text-gray-500 text-sm mb-4">총 {trades.length}건</p>
      <div className="bg-gray-900 rounded-xl p-4">
        <TradeTable trades={trades} />
      </div>
    </div>
  );
}
