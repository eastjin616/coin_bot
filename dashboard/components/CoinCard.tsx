interface Holding {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  eval_value: number;
  profit_rate: number;
}

export default function CoinCard({ holding }: { holding: Holding }) {
  const isProfit = holding.profit_rate >= 0;
  const ticker = holding.symbol.replace("KRW-", "");
  const accentColor = isProfit ? "#00ff87" : "#ff3b5c";

  return (
    <div className="rounded-xl px-4 py-3.5"
      style={{ background: "#0d0d0d", border: "1px solid rgba(255,255,255,0.06)" }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold tracking-wider"
            style={{ background: `${accentColor}12`, color: accentColor, border: `1px solid ${accentColor}25` }}>
            {ticker.slice(0, 2)}
          </div>
          <div>
            <p className="font-semibold text-sm text-white tracking-wide">{ticker}</p>
            <p className="text-xs font-mono mt-0.5" style={{ color: "rgba(255,255,255,0.25)" }}>
              {holding.quantity.toFixed(6)}
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold font-mono" style={{ color: accentColor }}>
            {isProfit ? "+" : ""}{holding.profit_rate.toFixed(2)}%
          </p>
          <p className="text-xs font-mono mt-0.5" style={{ color: "rgba(255,255,255,0.25)" }}>
            {holding.eval_value.toLocaleString()}원
          </p>
        </div>
      </div>
      <div className="mt-2.5 pt-2.5 flex justify-between text-xs font-mono"
        style={{ borderTop: "1px solid rgba(255,255,255,0.04)", color: "rgba(255,255,255,0.2)" }}>
        <span>AVG {holding.avg_price.toLocaleString()}</span>
        <span>NOW {holding.current_price.toLocaleString()}</span>
      </div>
    </div>
  );
}
