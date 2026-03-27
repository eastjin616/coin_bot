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

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-bold text-lg">{ticker}</p>
          <p className="text-gray-400 text-sm">{holding.quantity.toFixed(6)}개</p>
        </div>
        <div className="text-right">
          <p className={`font-bold text-lg ${isProfit ? "text-green-400" : "text-red-400"}`}>
            {isProfit ? "+" : ""}{holding.profit_rate.toFixed(2)}%
          </p>
          <p className="text-gray-400 text-sm">{holding.eval_value.toLocaleString()}원</p>
        </div>
      </div>
      <div className="mt-2 flex justify-between text-sm text-gray-500">
        <span>평균 {holding.avg_price.toLocaleString()}원</span>
        <span>현재 {holding.current_price.toLocaleString()}원</span>
      </div>
    </div>
  );
}
