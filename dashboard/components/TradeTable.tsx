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
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="text-left py-2">코인</th>
            <th className="text-left py-2">구분</th>
            <th className="text-right py-2">가격</th>
            <th className="text-right py-2">AI%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id} className="border-b border-gray-800/50">
              <td className="py-2">{t.symbol.replace("KRW-", "")}</td>
              <td className={`py-2 font-medium ${t.action === "BUY" ? "text-green-400" : "text-red-400"}`}>
                {t.action}
              </td>
              <td className="py-2 text-right">{Number(t.price).toLocaleString()}</td>
              <td className="py-2 text-right text-gray-400">{t.confidence.toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="text-center text-gray-500 py-8">매매 내역 없음</p>}
    </div>
  );
}
