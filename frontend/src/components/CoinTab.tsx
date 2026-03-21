import { useEffect, useState } from 'react'
import { getWatchlist, addWatchlist, removeWatchlist, getSignals } from '../api/client'

interface WatchItem { id: number; market: string; symbol: string; name: string; active: boolean }
interface Signal { id: number; market: string; symbol: string; action: string; confidence: number; executed_at: string }

export default function CoinTab() {
  const [watchlist, setWatchlist] = useState<WatchItem[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [newSymbol, setNewSymbol] = useState('')
  const [newName, setNewName] = useState('')

  const load = async () => {
    const [wl, sg] = await Promise.all([getWatchlist(), getSignals('coin')])
    setWatchlist(wl.filter((w: WatchItem) => w.market === 'coin' && w.active))
    setSignals(sg)
  }

  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t) }, [])

  const add = async () => {
    if (!newSymbol) return
    await addWatchlist({ market: 'coin', symbol: newSymbol.trim(), name: newName.trim() })
    setNewSymbol(''); setNewName('')
    load()
  }

  const remove = async (symbol: string) => {
    await removeWatchlist('coin', symbol); load()
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-lg font-bold mb-3 text-yellow-400">🪙 감시 종목 (코인)</h2>
        <div className="flex gap-2 mb-3">
          <input className="bg-gray-700 text-white rounded px-3 py-1 flex-1" placeholder="종목코드 (예: KRW-BTC)" value={newSymbol} onChange={e => setNewSymbol(e.target.value)} />
          <input className="bg-gray-700 text-white rounded px-3 py-1 w-32" placeholder="종목명" value={newName} onChange={e => setNewName(e.target.value)} />
          <button className="bg-yellow-600 hover:bg-yellow-500 text-white rounded px-3 py-1" onClick={add}>추가</button>
        </div>
        <ul className="space-y-1">
          {watchlist.map(w => (
            <li key={w.id} className="flex justify-between items-center bg-gray-700 rounded px-3 py-2">
              <span className="text-white">{w.name || w.symbol} <span className="text-gray-400 text-sm ml-2">{w.symbol}</span></span>
              <button className="text-red-400 hover:text-red-300 text-sm" onClick={() => remove(w.symbol)}>삭제</button>
            </li>
          ))}
        </ul>
      </div>
      <div className="bg-gray-800 rounded-xl p-5">
        <h2 className="text-lg font-bold mb-3 text-yellow-400">최근 신호</h2>
        <ul className="space-y-2">
          {signals.slice(0, 10).map(s => (
            <li key={s.id} className="flex justify-between items-center bg-gray-700 rounded px-3 py-2 text-sm">
              <span className="text-white">{s.symbol}</span>
              <span className={`font-bold ${s.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{s.action}</span>
              <span className="text-yellow-400">{s.confidence.toFixed(1)}%</span>
              <span className="text-gray-400">{new Date(s.executed_at).toLocaleString('ko-KR')}</span>
            </li>
          ))}
          {signals.length === 0 && <li className="text-gray-500 text-sm">아직 신호 없음</li>}
        </ul>
      </div>
    </div>
  )
}
