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
    <div className="pt-8 space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-mono tracking-[0.2em] text-[#00e5ff]/60 uppercase">AI Trading</p>
          <h1 className="text-xl font-bold tracking-tight text-white">COIN_BOT</h1>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00ff87] animate-pulse" />
          <span className="text-xs text-[#00ff87] font-mono">LIVE</span>
        </div>
      </div>

      {/* 총 자산 카드 */}
      <div className="relative rounded-2xl p-5 overflow-hidden"
        style={{ background: "linear-gradient(135deg, #0d1f2d 0%, #050f18 100%)", border: "1px solid rgba(0,229,255,0.15)" }}>
        <div className="absolute inset-0 opacity-20"
          style={{ background: "radial-gradient(circle at 80% 20%, rgba(0,229,255,0.3) 0%, transparent 60%)" }} />
        <div className="relative">
          <p className="text-xs font-mono tracking-widest text-[#00e5ff]/60 uppercase mb-2">Total Value</p>
          {portfolio ? (
            <>
              <p className="text-4xl font-bold tracking-tight text-white glow-cyan">
                {portfolio.total_value.toLocaleString()}
                <span className="text-lg text-[#00e5ff]/70 ml-1">₩</span>
              </p>
              <div className="mt-3 pt-3 border-t border-white/5 flex justify-between">
                <div>
                  <p className="text-xs text-white/30 mb-0.5">KRW 잔고</p>
                  <p className="text-sm font-mono text-white/70">{portfolio.krw_balance.toLocaleString()}원</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-white/30 mb-0.5">보유 코인</p>
                  <p className="text-sm font-mono text-white/70">{portfolio.holdings.length}종</p>
                </div>
              </div>
            </>
          ) : (
            <p className="text-lg text-white/30 mt-1">데이터 없음</p>
          )}
        </div>
      </div>

      {/* 보유 코인 */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-mono tracking-widest text-white/30 uppercase">Holdings</span>
          <div className="flex-1 h-px bg-white/5" />
        </div>
        {(portfolio?.holdings?.length ?? 0) > 0 ? (
          <div className="space-y-2">
            {portfolio!.holdings.map((h) => (
              <CoinCard key={h.symbol} holding={h} />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-white/5 py-8 text-center">
            <p className="text-sm text-white/20 font-mono">— NO POSITIONS —</p>
          </div>
        )}
      </section>

      {/* 최근 매매 */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-mono tracking-widest text-white/30 uppercase">Recent Trades</span>
          <div className="flex-1 h-px bg-white/5" />
        </div>
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(255,255,255,0.05)", background: "#0a0a0a" }}>
          <TradeTable trades={trades} limit={5} />
        </div>
      </section>
    </div>
  );
}
