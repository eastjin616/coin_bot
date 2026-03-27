// dashboard/app/page.tsx
import CoinCard from "@/components/CoinCard";
import TradeTable from "@/components/TradeTable";

async function getPortfolio() {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const res = await fetch(`${baseUrl}/api/portfolio`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

async function getTrades() {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const res = await fetch(`${baseUrl}/api/trades`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export default async function DashboardPage() {
  const [portfolio, trades] = await Promise.all([getPortfolio(), getTrades()]);

  return (
    <div className="pt-6 space-y-6">
      {/* 잔고 요약 */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-5">
        <p className="text-blue-200 text-sm">총 평가금액</p>
        <p className="text-3xl font-bold mt-1">
          {portfolio?.total_value?.toLocaleString() ?? "-"}원
        </p>
        <p className="text-blue-200 text-sm mt-2">
          KRW 잔고: {portfolio?.krw_balance?.toLocaleString() ?? "-"}원
        </p>
      </div>

      {/* 보유 코인 */}
      <section>
        <h2 className="text-gray-400 text-sm font-medium mb-3">보유 코인</h2>
        {portfolio?.holdings?.length > 0 ? (
          <div className="space-y-3">
            {portfolio.holdings.map((h: any) => (
              <CoinCard key={h.symbol} holding={h} />
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm text-center py-6">보유 코인 없음</p>
        )}
      </section>

      {/* 최근 매매 */}
      <section>
        <h2 className="text-gray-400 text-sm font-medium mb-3">최근 매매</h2>
        <div className="bg-gray-900 rounded-xl p-4">
          <TradeTable trades={trades} limit={3} />
        </div>
      </section>
    </div>
  );
}
