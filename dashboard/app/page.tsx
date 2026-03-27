import CoinCard from "@/components/CoinCard";
import TradeTable from "@/components/TradeTable";

interface Holding {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  eval_value: number;
  profit_rate: number;
}

interface Portfolio {
  krw_balance: number;
  holdings: Holding[];
  total_value: number;
}

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.API_KEY ?? "";

async function getPortfolio(): Promise<Portfolio | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/portfolio`, {
      headers: { "X-API-Key": API_KEY },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function getTrades() {
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

export default async function DashboardPage() {
  const [portfolio, trades] = await Promise.all([getPortfolio(), getTrades()]);

  return (
    <div className="pt-6 space-y-6">
      {/* 잔고 요약 */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-5">
        {portfolio ? (
          <>
            <p className="text-blue-200 text-sm">총 평가금액</p>
            <p className="text-3xl font-bold mt-1">
              {portfolio.total_value.toLocaleString()}원
            </p>
            <p className="text-blue-200 text-sm mt-2">
              KRW 잔고: {portfolio.krw_balance.toLocaleString()}원
            </p>
          </>
        ) : (
          <>
            <p className="text-blue-200 text-sm">총 평가금액</p>
            <p className="text-xl font-bold mt-1 text-blue-300">데이터를 불러올 수 없습니다</p>
          </>
        )}
      </div>

      {/* 보유 코인 */}
      <section>
        <h2 className="text-gray-400 text-sm font-medium mb-3">보유 코인</h2>
        {(portfolio?.holdings?.length ?? 0) > 0 ? (
          <div className="space-y-3">
            {portfolio!.holdings.map((h) => (
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
