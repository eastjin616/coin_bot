import { useEffect, useState } from 'react'
import { getWatchlist, addWatchlist, removeWatchlist, getSignals, getBalance, testBuy, testSell } from '../api/client'

interface WatchItem { id: number; market: string; symbol: string; name: string; active: boolean }
interface Signal { id: number; symbol: string; action: string; confidence: number; executed_at: string }
interface Balance { stock_krw: number; coin_krw: number }

export default function CoinTab() {
  const [watchlist, setWatchlist] = useState<WatchItem[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [balance, setBalance] = useState<Balance | null>(null)
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')
  const [buyAmount, setBuyAmount] = useState('10000')
  const [selectedSymbol, setSelectedSymbol] = useState('KRW-BTC')
  const [loading, setLoading] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  const load = async () => {
    try {
      const [wl, sg, bal] = await Promise.all([getWatchlist(), getSignals('coin'), getBalance()])
      setWatchlist(wl.filter((w: WatchItem) => w.market === 'coin' && w.active))
      setSignals(sg)
      setBalance(bal)
    } catch {}
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  const showMessage = (text: string, type: 'success' | 'error') => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 4000)
  }

  const handleBuy = async () => {
    const amount = parseFloat(buyAmount)
    if (!amount || amount < 5000) {
      showMessage('최소 주문 금액은 5,000원입니다', 'error')
      return
    }
    setLoading('buy')
    try {
      const result = await testBuy(selectedSymbol, amount)
      if (result.status === '매수 완료') {
        showMessage(`✅ ${selectedSymbol} 매수 완료!`, 'success')
        load()
      } else {
        showMessage('매수 실패. 잔고를 확인해주세요', 'error')
      }
    } catch {
      showMessage('오류가 발생했습니다', 'error')
    } finally {
      setLoading(null)
    }
  }

  const handleSell = async (symbol: string) => {
    setLoading('sell-' + symbol)
    try {
      const result = await testSell(symbol)
      if (result.status === '매도 완료') {
        showMessage(`✅ ${symbol} 매도 완료!`, 'success')
        load()
      } else {
        showMessage('보유 수량이 없습니다', 'error')
      }
    } catch {
      showMessage('오류가 발생했습니다', 'error')
    } finally {
      setLoading(null)
    }
  }

  const addToWatchlist = async () => {
    if (!newSymbol) return
    await addWatchlist({ market: 'coin', symbol: newSymbol.trim().toUpperCase(), name: newName.trim() })
    setNewSymbol(''); setNewName('')
    load()
  }

  const removeFromWatchlist = async (symbol: string) => {
    await removeWatchlist('coin', symbol)
    load()
  }

  return (
    <div className="space-y-5">
      {/* 메시지 알림 */}
      {message && (
        <div className={`rounded-lg p-3 text-sm font-medium ${message.type === 'success' ? 'bg-green-900 text-green-300 border border-green-700' : 'bg-red-900 text-red-300 border border-red-700'}`}>
          {message.text}
        </div>
      )}

      {/* 잔고 카드 */}
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-sm text-gray-400 mb-1">💰 현재 잔고</h2>
        <p className="text-3xl font-bold text-yellow-400">
          {balance ? balance.coin_krw.toLocaleString() : '—'}
          <span className="text-base font-normal text-gray-400 ml-1">KRW</span>
        </p>
      </div>

      {/* 매수 패널 */}
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-lg font-bold mb-4 text-yellow-400">🪙 수동 매수</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">종목</label>
            <select
              value={selectedSymbol}
              onChange={e => setSelectedSymbol(e.target.value)}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-yellow-400 outline-none"
            >
              {watchlist.map(w => (
                <option key={w.id} value={w.symbol}>{w.name || w.symbol} ({w.symbol})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">매수 금액 (원)</label>
            <input
              type="number"
              value={buyAmount}
              onChange={e => setBuyAmount(e.target.value)}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-yellow-400 outline-none"
              placeholder="10000"
            />
            <div className="flex gap-2 mt-2">
              {[5000, 10000, 30000, 50000].map(a => (
                <button key={a} onClick={() => setBuyAmount(String(a))}
                  className="text-xs bg-gray-600 hover:bg-gray-500 rounded px-2 py-1 text-gray-300">
                  {(a/1000).toFixed(0)}천원
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={handleBuy}
            disabled={loading === 'buy'}
            className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-600 text-white font-bold rounded-lg py-3 transition-colors"
          >
            {loading === 'buy' ? '처리 중...' : `${parseInt(buyAmount || '0').toLocaleString()}원 매수`}
          </button>
        </div>
      </div>

      {/* 감시 종목 & 매도 */}
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-lg font-bold mb-4 text-yellow-400">📋 감시 종목</h2>
        <ul className="space-y-2 mb-4">
          {watchlist.map(w => (
            <li key={w.id} className="flex justify-between items-center bg-gray-700 rounded-lg px-4 py-3">
              <div>
                <span className="font-medium">{w.name || w.symbol}</span>
                <span className="text-gray-400 text-xs ml-2">{w.symbol}</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleSell(w.symbol)}
                  disabled={loading === 'sell-' + w.symbol}
                  className="text-xs bg-red-700 hover:bg-red-600 disabled:bg-gray-600 text-white rounded px-3 py-1"
                >
                  {loading === 'sell-' + w.symbol ? '...' : '매도'}
                </button>
                <button onClick={() => removeFromWatchlist(w.symbol)}
                  className="text-xs text-gray-500 hover:text-red-400">삭제</button>
              </div>
            </li>
          ))}
        </ul>

        {/* 종목 추가 */}
        <div className="border-t border-gray-700 pt-4">
          <p className="text-xs text-gray-400 mb-2">종목 추가</p>
          <div className="flex gap-2">
            <input className="bg-gray-700 text-white rounded-lg px-3 py-2 flex-1 text-sm border border-gray-600 focus:border-yellow-400 outline-none"
              placeholder="KRW-ETH" value={newSymbol} onChange={e => setNewSymbol(e.target.value)} />
            <input className="bg-gray-700 text-white rounded-lg px-3 py-2 w-24 text-sm border border-gray-600 focus:border-yellow-400 outline-none"
              placeholder="이름" value={newName} onChange={e => setNewName(e.target.value)} />
            <button onClick={addToWatchlist}
              className="bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg px-3 py-2 text-sm">추가</button>
          </div>
        </div>
      </div>

      {/* 최근 AI 신호 */}
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-lg font-bold mb-3 text-yellow-400">🤖 최근 AI 신호</h2>
        {signals.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-4">아직 신호 없음 (1분마다 분석 중)</p>
        ) : (
          <ul className="space-y-2">
            {signals.slice(0, 8).map(s => (
              <li key={s.id} className="flex justify-between items-center bg-gray-700 rounded-lg px-4 py-2 text-sm">
                <span className="font-medium">{s.symbol}</span>
                <span className={`font-bold ${s.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                  {s.action === 'BUY' ? '📈 매수' : '📉 매도'}
                </span>
                <span className="text-yellow-400">{s.confidence.toFixed(1)}%</span>
                <span className="text-gray-400 text-xs">{new Date(s.executed_at).toLocaleString('ko-KR')}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
