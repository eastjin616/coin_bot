import TradeTable from "@/components/TradeTable";

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL ??
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");

async function getAllTrades() {
  const res = await fetch(`${BASE_URL}/api/trades`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
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
