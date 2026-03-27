interface Trade {
  id: number;
  symbol: string;
  action: string;
  price: number;
  quantity: number;
  confidence: number;
  executed_at: string;
}

export default function TradeTable({ trades, limit }: { trades: Trade[]; limit?: number }) {
  const rows = limit ? trades.slice(0, limit) : trades;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.2)" }}>
            <th className="text-left py-2.5 px-3 font-normal tracking-widest uppercase">Coin</th>
            <th className="text-left py-2.5 font-normal tracking-widest uppercase">Side</th>
            <th className="text-right py-2.5 font-normal tracking-widest uppercase">Price</th>
            <th className="text-right py-2.5 px-3 font-normal tracking-widest uppercase">AI</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
              <td className="py-2.5 px-3 text-white/70">{t.symbol.replace("KRW-", "")}</td>
              <td className="py-2.5">
                <span className="text-xs px-2 py-0.5 rounded font-bold tracking-wider"
                  style={t.action === "BUY"
                    ? { background: "rgba(0,255,135,0.1)", color: "#00ff87", border: "1px solid rgba(0,255,135,0.2)" }
                    : { background: "rgba(255,59,92,0.1)", color: "#ff3b5c", border: "1px solid rgba(255,59,92,0.2)" }}>
                  {t.action}
                </span>
              </td>
              <td className="py-2.5 text-right text-white/60">{Number(t.price).toLocaleString()}</td>
              <td className="py-2.5 px-3 text-right" style={{ color: "rgba(0,229,255,0.6)" }}>{t.confidence.toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="text-center py-8 text-xs font-mono tracking-widest" style={{ color: "rgba(255,255,255,0.15)" }}>
          — NO TRADES —
        </p>
      )}
    </div>
  );
}
