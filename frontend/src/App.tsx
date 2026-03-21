import { useState, useEffect } from 'react'
import CoinTab from './components/CoinTab'
import { getTrades } from './api/client'

interface Trade { id: number; market: string; symbol: string; action: string; confidence: number; price: number; quantity: number; executed_at: string }

type Tab = 'coin' | 'trades'

export default function App() {
  const [tab, setTab] = useState<Tab>('coin')
  const [trades, setTrades] = useState<Trade[]>([])

  useEffect(() => {
    const load = async () => {
      try {
        const t = await getTrades()
        setTrades(t)
      } catch {}
    }
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">🤖 AI Trader</h1>
            <p className="text-gray-400 text-xs">코인 자동매매 시스템</p>
          </div>
        </div>
      </header>

      <div className="flex border-b border-gray-700 bg-gray-800 px-6">
        <div className="max-w-4xl mx-auto flex w-full">
          {([['coin', '🪙 코인'], ['trades', '📋 매매내역']] as [Tab, string][]).map(([t, label]) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${tab === t ? 'border-yellow-400 text-yellow-400' : 'border-transparent text-gray-400 hover:text-white'}`}>
              {label}
            </button>
          ))}
          <button disabled
            className="px-5 py-3 text-sm font-medium border-b-2 border-transparent text-gray-600 cursor-not-allowed ml-2">
            📈 주식 (준비중)
          </button>
        </div>
      </div>

      <main className="max-w-4xl mx-auto p-6">
        {tab === 'coin' && <CoinTab />}
        {tab === 'trades' && (
          <div className="bg-gray-800 rounded-xl p-5">
            <h2 className="text-lg font-bold mb-4">📋 전체 매매 내역</h2>
            {trades.length === 0 ? (
              <p className="text-gray-500 text-center py-8">아직 매매 내역이 없습니다</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="text-left py-2 pr-4">종목</th>
                      <th className="text-left py-2 pr-4">액션</th>
                      <th className="text-left py-2 pr-4">신뢰도</th>
                      <th className="text-left py-2 pr-4">가격</th>
                      <th className="text-left py-2 pr-4">수량</th>
                      <th className="text-left py-2">시각</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map(t => (
                      <tr key={t.id} className="border-b border-gray-700 hover:bg-gray-750">
                        <td className="py-2 pr-4 font-medium">{t.symbol}</td>
                        <td className={`py-2 pr-4 font-bold ${t.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{t.action === 'BUY' ? '매수' : '매도'}</td>
                        <td className="py-2 pr-4 text-yellow-400">{t.confidence.toFixed(1)}%</td>
                        <td className="py-2 pr-4">{t.price.toLocaleString()}원</td>
                        <td className="py-2 pr-4 text-gray-300">{t.quantity.toFixed(8)}</td>
                        <td className="py-2 text-gray-400 text-xs">{new Date(t.executed_at).toLocaleString('ko-KR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
