import { useState, useEffect } from 'react'
import StockTab from './components/StockTab'
import CoinTab from './components/CoinTab'
import { getBalance, getTrades } from './api/client'

type Tab = 'stock' | 'coin' | 'trades'

interface Balance { stock_krw: number; coin_krw: number }
interface Trade { id: number; market: string; symbol: string; action: string; confidence: number; price: number; quantity: number; executed_at: string }

export default function App() {
  const [tab, setTab] = useState<Tab>('stock')
  const [balance, setBalance] = useState<Balance | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    const load = async () => {
      try {
        const [b, t] = await Promise.all([getBalance(), getTrades()])
        setBalance(b); setTrades(t)
      } catch {}
    }
    load(); const t = setInterval(load, 60000); return () => clearInterval(t)
  }, [])

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">🤖 coin_bot</h1>
          <p className="text-gray-400 text-sm">AI 자동매매 시스템</p>
        </div>
        {balance && (
          <div className="flex gap-6 text-sm">
            <div><span className="text-gray-400">주식 잔고 </span><span className="text-green-400 font-bold">{balance.stock_krw.toLocaleString()}원</span></div>
            <div><span className="text-gray-400">코인 잔고 </span><span className="text-yellow-400 font-bold">{balance.coin_krw.toLocaleString()}원</span></div>
          </div>
        )}
      </header>

      <div className="flex border-b border-gray-700 bg-gray-800 px-6">
        {([['stock', '📈 주식'], ['coin', '🪙 코인'], ['trades', '📋 매매내역']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${tab === t ? 'border-blue-500 text-white' : 'border-transparent text-gray-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      <main className="max-w-4xl mx-auto p-6">
        {tab === 'stock' && <StockTab />}
        {tab === 'coin' && <CoinTab />}
        {tab === 'trades' && (
          <div className="bg-gray-800 rounded-xl p-5">
            <h2 className="text-lg font-bold mb-4">📋 전체 매매 내역</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-gray-400 border-b border-gray-700">
                  <th className="text-left py-2">시장</th>
                  <th className="text-left py-2">종목</th>
                  <th className="text-left py-2">액션</th>
                  <th className="text-left py-2">신뢰도</th>
                  <th className="text-left py-2">가격</th>
                  <th className="text-left py-2">수량</th>
                  <th className="text-left py-2">시각</th>
                </tr></thead>
                <tbody>
                  {trades.map(t => (
                    <tr key={t.id} className="border-b border-gray-700 hover:bg-gray-700">
                      <td className="py-2">{t.market}</td>
                      <td className="py-2">{t.symbol}</td>
                      <td className={`py-2 font-bold ${t.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{t.action}</td>
                      <td className="py-2 text-yellow-400">{t.confidence.toFixed(1)}%</td>
                      <td className="py-2">{t.price.toLocaleString()}원</td>
                      <td className="py-2">{t.quantity.toFixed(6)}</td>
                      <td className="py-2 text-gray-400">{new Date(t.executed_at).toLocaleString('ko-KR')}</td>
                    </tr>
                  ))}
                  {trades.length === 0 && <tr><td colSpan={7} className="py-4 text-center text-gray-500">아직 매매 내역 없음</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
